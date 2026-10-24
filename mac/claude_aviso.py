"""Aviso por Telegram desde un hook de Claude Code: cuando termina un turno (Stop) o necesita algo (Notification).

Claude Code le pasa por la entrada estándar un JSON con el evento. Uso en .claude/settings.local.json del proyecto:
    "Stop" / "Notification" → command: cd <este repo> && .venv/bin/python -m mac.claude_aviso

- Stop: manda el comienzo de la última respuesta de Claude (del transcript de la sesión).
- Notification: manda el aviso (pide permiso, espera una respuesta…).
Para responder desde el celular se usa el control remoto de Claude Code (/remote-control); esto solo avisa.
Se silencia creando data/claude_avisos_off (o con «avisos claude off» en el bot).
"""
import json
import sys
from pathlib import Path

from mac import telegram
from mac.config import DATA_DIR, lista

APAGADO = DATA_DIR / "claude_avisos_off"
LARGO = 900  # caracteres de la respuesta que se mandan


def ultima_respuesta(transcript: str) -> str:
    """Texto de la última respuesta de Claude en el transcript (un JSON por línea)."""
    try:
        lineas = Path(transcript).read_text(errors="replace").split("\n")
    except OSError:
        return ""
    for linea in reversed(lineas):
        try:
            evento = json.loads(linea)
        except ValueError:
            continue
        mensaje = evento.get("message") or {}
        if evento.get("type") != "assistant" or not isinstance(mensaje.get("content"), list):
            continue
        texto = "\n".join(b.get("text", "") for b in mensaje["content"] if b.get("type") == "text").strip()
        if texto:
            return texto
    return ""


def texto_aviso(evento: dict) -> str:
    proyecto = Path(evento.get("cwd") or "").name or "Claude"
    if evento.get("hook_event_name") == "Notification":
        return f"🔔 Claude ({proyecto}): {evento.get('message') or 'necesita tu atención'}"
    respuesta = ultima_respuesta(evento.get("transcript_path") or "")
    if not respuesta:
        return f"✅ Claude ({proyecto}) terminó."
    corto = respuesta[:LARGO] + ("…" if len(respuesta) > LARGO else "")
    return f"✅ Claude ({proyecto}) terminó:\n\n{corto}"


def main() -> None:
    if APAGADO.exists():
        return
    try:
        evento = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    for chat in lista("TELEGRAM_CHAT_ID")[:1]:
        telegram.enviar(chat, texto_aviso(evento))


if __name__ == "__main__":
    main()
