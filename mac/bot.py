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

from mac import chrome, telegram
from mac.config import lista
from mac.interprete import interpretar

AYUDA = """Hola 👋 Soy tu Mac. Puedo:
· ver qué perfiles de Chrome tienes abiertos: «hola mac, qué perfiles hay»
· buscar y reproducir en Spotify: «hola mac, en mi perfil personal pon bad bunny en spotify»
Si no me dices el perfil, te pregunto con botones."""


def log(texto: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}", flush=True)


def autorizado(chat_id) -> bool:
    return str(chat_id) in lista("TELEGRAM_CHAT_ID")


class Bot:
    def __init__(self):
        self.offset = None

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

    def mensaje(self, chat, texto: str) -> None:
        pedido = interpretar(texto)
        log(f"pedido: {pedido.accion} {pedido.datos}")
        if pedido.accion == "perfiles":
            telegram.enviar(chat, texto_perfiles())
        else:
            telegram.enviar(chat, AYUDA)

    def boton(self, chat, q: dict) -> None:
        telegram.responder_boton(q["id"])

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
