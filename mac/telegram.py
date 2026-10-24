"""Cliente mínimo de la API de bots de Telegram: recibir mensajes y botones, responder y editar."""
import requests

from mac.config import env

LIMITE = 4000  # Telegram corta en 4096 caracteres
ultimo_error = ""  # motivo del último fallo (sin el token, que va en la URL)


def llamar(metodo: str, datos: dict | None = None, timeout: int = 30) -> dict | list | None:
    """Llama a un método de la API. Devuelve el `result` de Telegram, o None si falla."""
    global ultimo_error
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        ultimo_error = "falta TELEGRAM_BOT_TOKEN en .env"
        return None
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{metodo}", json=datos or {}, timeout=timeout)
        cuerpo = r.json()
    except (requests.RequestException, ValueError) as e:
        ultimo_error = type(e).__name__  # el mensaje completo incluiría la URL con el token
        return None
    if not cuerpo.get("ok"):
        ultimo_error = f"HTTP {r.status_code}: {cuerpo.get('description', '')}"
        return None
    return cuerpo.get("result")


def teclado(filas: list[list[tuple[str, str]]]) -> dict:
    """[[("texto", "dato"), …], …] → botones bajo el mensaje. El dato vuelve al tocar el botón (máx. 64 bytes)."""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in fila] for fila in filas]}


def enviar(chat_id: str | int, texto: str, botones: dict | None = None) -> int | None:
    """Envía un mensaje (los botones van en el último trozo). Devuelve su id."""
    trozos = [texto[i:i + LIMITE] for i in range(0, len(texto), LIMITE)] or [""]
    mid = None
    for n, trozo in enumerate(trozos):
        datos = {"chat_id": chat_id, "text": trozo, "disable_web_page_preview": True}
        if botones and n == len(trozos) - 1:
            datos["reply_markup"] = botones
        r = llamar("sendMessage", datos)
        mid = r.get("message_id") if r else mid
    return mid


def editar(chat_id: str | int, message_id: int, texto: str, botones: dict | None = None) -> None:
    datos = {"chat_id": chat_id, "message_id": message_id, "text": texto[:LIMITE]}
    if botones:
        datos["reply_markup"] = botones
    llamar("editMessageText", datos)


def responder_boton(callback_id: str, texto: str = "") -> None:
    """Quita el relojito del botón tocado (y muestra un texto corto arriba, si se da)."""
    llamar("answerCallbackQuery", {"callback_query_id": callback_id, "text": texto[:180]})


def actualizaciones(offset: int | None, espera: int = 50) -> list:
    """Mensajes y botones nuevos. Espera hasta `espera` segundos si no hay nada (long polling)."""
    return llamar("getUpdates", {"offset": offset, "timeout": espera,
                                 "allowed_updates": ["message", "callback_query"]}, timeout=espera + 10) or []
