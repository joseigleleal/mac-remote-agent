"""Bot «hola mac»: recibe pedidos por Telegram y los hace en la Mac.

Corre todo el tiempo (launchd lo mantiene vivo) y espera mensajes con long polling: no gasta CPU mientras espera.
Solo obedece a los chats de TELEGRAM_CHAT_ID; a cualquier otro no le responde.

Uso:
    python -m mac.bot           # atiende pedidos (lo que lanza launchd)
    python -m mac.bot --quien   # muestra el chat_id de quien le escribió al bot (para TELEGRAM_CHAT_ID)
"""
import argparse
import time
from datetime import datetime

from mac import chrome, comandos, servicio, spotify, telegram, volumen
from mac.config import lista
from mac.interprete import Pedido, interpretar

AYUDA = """Hola 👋 Soy tu Mac. Puedo:
· ver qué perfiles de Chrome tienes abiertos: «hola mac, qué perfiles hay»
· buscar y reproducir en Spotify: «pon bad bunny en spotify» o «en mi perfil personal pon karol g»
· el volumen: «sube el volumen», «baja el volumen 20», «volumen al 30», «silencia», «quita el silencio»
· comandos de tu lista permitida: «ejecuta caffeinate -d», «detén caffeinate», «qué comandos hay»
· el bot: «cuánto consumes» (/estado), «pausa» y «prende» (/pausar, /reanudar), «apágate del todo» (/apagar)
El «hola mac» es opcional. Si no me dices el perfil, te pregunto con botones."""

EN_PAUSA = ("estado", "reanudar", "apagar", "ayuda")  # lo único que atiende en pausa


def log(texto: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}", flush=True)


def autorizado(chat_id) -> bool:
    return str(chat_id) in lista("TELEGRAM_CHAT_ID")


class Bot:
    def __init__(self):
        self.offset = None
        self.pendiente: dict[str, Pedido] = {}  # chat → pedido que espera que se elija el perfil

    def atender(self, update: dict) -> None:
        self.offset = update["update_id"] + 1
        if "callback_query" in update:
            q = update["callback_query"]
            chat = (q.get("message") or {}).get("chat", {}).get("id")
            if autorizado(chat):
                self.boton(chat, q)
            return
        msg = update.get("message") or {}
        chat, texto = msg.get("chat", {}).get("id"), (msg.get("text") or "").strip()
        if not autorizado(chat):
            log(f"ignorado: mensaje de un chat no autorizado ({chat})")
            return
        if texto:
            self.mensaje(chat, texto)

    def decir(self, chat, texto: str, botones: dict | None = None) -> None:
        log(f"respuesta: {texto[:200]}")
        telegram.enviar(chat, texto, botones)

    def mensaje(self, chat, texto: str) -> None:
        pedido = interpretar(texto)
        log(f"pedido: «{texto[:200]}» → {pedido.accion} {pedido.datos}")
        if servicio.pausado() and pedido.accion not in EN_PAUSA:
            self.decir(chat, "⏸️ Estoy en pausa. Dime «prende» para volver.")
        elif pedido.accion == "estado":
            self.decir(chat, servicio.recursos())
        elif pedido.accion == "pausar":
            servicio.pausar()
            self.decir(chat, "⏸️ En pausa: sigo escuchando pero no hago nada hasta que me digas «prende».")
        elif pedido.accion == "reanudar":
            servicio.reanudar()
            self.decir(chat, "▶️ De vuelta. ¿Qué hago?")
        elif pedido.accion == "apagar":
            botones = telegram.teclado([[("⏻ Sí, apagar del todo", "apagar:si"), ("Cancelar", "apagar:no")]])
            self.decir(chat, "¿Me apago del todo? Ojo: después no podré escucharte; para prenderme hay que hacerlo "
                             "desde la Mac (scripts/bot.sh prender). Si solo quieres que no haga nada, di «pausa».",
                       botones)
        elif pedido.accion == "comando":
            self.decir(chat, comandos.ejecutar(pedido.datos["comando"]))
        elif pedido.accion == "detener":
            self.decir(chat, comandos.detener(pedido.datos["comando"]))
        elif pedido.accion == "comandos":
            self.decir(chat, comandos.resumen())
        elif pedido.accion == "perfiles":
            self.decir(chat, texto_perfiles())
        elif pedido.accion == "volumen":
            try:
                if pedido.datos["modo"] == "ver":
                    nivel, mudo = volumen.estado()
                    self.decir(chat, "🔇 Silenciado" if mudo else f"🔊 Volumen: {nivel} %")
                else:
                    self.decir(chat, volumen.ajustar(pedido.datos["modo"], pedido.datos.get("valor")))
            except chrome.ChromeError as e:
                self.decir(chat, f"⚠️ {e}")
        elif pedido.accion == "spotify":
            self.spotify(chat, pedido, chrome.resolver(quitar_consulta(texto, pedido)))
        else:
            self.decir(chat, AYUDA)

    def spotify(self, chat, pedido: Pedido, perfil: chrome.Perfil | None) -> None:
        """Con perfil, reproduce. Sin perfil: si hay uno solo abierto lo usa; si hay varios, pregunta con botones."""
        consulta = pedido.datos.get("consulta")
        if not consulta:
            self.decir(chat, "¿Qué busco? Ej.: «hola mac, pon bad bunny en spotify».")
            return
        if perfil is None:
            abiertos = chrome.abiertos()
            if len(abiertos) != 1:
                self.preguntar_perfil(chat, pedido, abiertos)
                return
            perfil = abiertos[0]
        if not chrome.permitido(perfil.carpeta):
            self.decir(chat, f"No uso el perfil {perfil.etiqueta}: no está en CHROME_PERFILES_PERMITIDOS.")
            return
        self.decir(chat, f"🎵 Busco «{consulta}» en Spotify, perfil {perfil.etiqueta}…")
        try:
            self.decir(chat, spotify.reproducir(perfil.carpeta, consulta))
        except chrome.ChromeError as e:
            self.decir(chat, f"⚠️ {e}")

    def preguntar_perfil(self, chat, pedido: Pedido, abiertos: list[chrome.Perfil]) -> None:
        if not abiertos:
            self.decir(chat, "No hay perfiles de Chrome abiertos que pueda usar. Dime cuál: «en mi perfil …».")
            return
        self.pendiente[str(chat)] = pedido
        botones = telegram.teclado([[(p.etiqueta, f"perfil:{p.carpeta}")] for p in abiertos])
        self.decir(chat, "¿En qué perfil de Chrome?", botones)

    def boton(self, chat, q: dict) -> None:
        log(f"botón: {q.get('data')}")
        telegram.responder_boton(q["id"])
        dato, mid = q.get("data", ""), (q.get("message") or {}).get("message_id")
        if dato == "apagar:no":
            telegram.editar(chat, mid, "Sigo encendido.")
            return
        if dato == "apagar:si":
            telegram.editar(chat, mid, "⏻ Me apago. Para prenderme: en la Mac, scripts/bot.sh prender.")
            log("apagado total pedido por Telegram")
            servicio.apagar()
        if not dato.startswith("perfil:"):
            return
        pedido = self.pendiente.pop(str(chat), None)
        if not pedido:
            telegram.editar(chat, mid, "Ese pedido ya no está pendiente. Pídemelo de nuevo.")
            return
        perfil = chrome.perfiles().get(dato[len("perfil:"):])
        if not perfil:
            telegram.editar(chat, mid, "Ese perfil ya no existe.")
            return
        telegram.editar(chat, mid, f"Perfil: {perfil.etiqueta}")
        if pedido.accion == "spotify":
            self.spotify(chat, pedido, perfil)

    def correr(self) -> None:
        if not lista("TELEGRAM_CHAT_ID"):
            log("TELEGRAM_CHAT_ID está vacío: no obedezco a nadie (ver .env.example)")
        log("escuchando")
        while True:
            updates = telegram.actualizaciones(self.offset)
            if not updates and telegram.ultimo_error:
                log(f"Telegram: {telegram.ultimo_error}")
                telegram.ultimo_error = ""
                time.sleep(10)  # sin red o token malo: no martillar la API
            for u in updates:
                try:
                    self.atender(u)
                except Exception as e:  # un pedido que falla no tumba al bot
                    log(f"error atendiendo: {type(e).__name__}: {e}")


def quitar_consulta(texto: str, pedido: Pedido) -> str:
    """El texto sin lo que se va a buscar, para que «pon la canción de estudio» no elija el perfil «estudio» por error."""
    consulta = pedido.datos.get("consulta") or ""
    return texto.lower().replace(consulta, " ") if consulta else texto


def texto_perfiles() -> str:
    if not chrome.esta_corriendo():
        return "Chrome está cerrado."
    abiertos = chrome.abiertos()
    if not abiertos:
        return "No hay perfiles abiertos que pueda usar."
    return "Perfiles abiertos en Chrome:\n" + "\n".join(f"· {p.etiqueta}" for p in abiertos)


def quien() -> None:
    """Lista los chats que le escribieron al bot hace poco, para poner el propio en TELEGRAM_CHAT_ID."""
    vistos = {}
    for u in telegram.actualizaciones(None, espera=0):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat:
            vistos[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
    if not vistos:
        print("Nadie le escribió al bot todavía. Mándale un mensaje y vuelve a correr esto."
              + (f" ({telegram.ultimo_error})" if telegram.ultimo_error else ""))
    for chat_id, nombre in vistos.items():
        print(f"{chat_id}  {nombre}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot «hola mac»")
    parser.add_argument("--quien", action="store_true", help="Muestra el chat_id de quien le escribió al bot")
    args = parser.parse_args()
    if args.quien:
        quien()
    else:
        Bot().correr()


if __name__ == "__main__":
    main()
