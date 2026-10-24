"""Puente entre Telegram y una sesión de Claude Code, con hooks. Solo actúa en «modo fuera» (avisos encendidos).

Hooks (en .claude/settings.local.json del proyecto donde corre la sesión):
    Stop          (async + asyncRewake)  python -m mac.claude_puente stop
    Notification  (async)                python -m mac.claude_puente aviso
    PreToolUse    matcher AskUserQuestion python -m mac.claude_puente pregunta

- stop: avisa que Claude terminó (con el comienzo de su respuesta) y espera hasta ESPERA_STOP un mensaje tuyo por
  Telegram (respondiendo a ese aviso o con «claude: …»). Si llega, sale con código 2 y el texto en stderr: Claude
  Code despierta a Claude con ese mensaje y sigue trabajando.
- pregunta: cuando Claude te pregunta con opciones, las manda con botones y espera hasta ESPERA_PREGUNTA. Lo que
  elijas vuelve como respuesta (updatedInput.answers); si no contestas a tiempo, la pregunta sale en la consola.
- El bot es quien recibe los mensajes de Telegram (solo de tu chat) y los deja en data/claude/: buzon.jsonl y
  respuestas/<id>. Los hooks solo leen esos archivos: nunca hablan con getUpdates (chocarían con el bot).
"""
import json
import sys
import time
import uuid
from pathlib import Path

from mac import telegram
from mac.claude_aviso import APAGADO, texto_aviso, ultima_respuesta
from mac.config import DATA_DIR, lista

CARPETA = DATA_DIR / "claude"
BUZON = CARPETA / "buzon.jsonl"          # mensajes tuyos para Claude (los escribe el bot)
RESPUESTAS = CARPETA / "respuestas"      # respuestas a preguntas con opciones (las escribe el bot)
ALERTAS = CARPETA / "alertas.json"       # message_id de cada aviso → sesión (responder a un aviso = escribirle)
PREGUNTAS = CARPETA / "preguntas.json"  # message_id de cada pregunta → id (responder escribiendo a una pregunta)
TURNO = CARPETA / "turno"                # cambia en cada Stop: un hook viejo deja de esperar
ESPERA_STOP = 30 * 60
ESPERA_PREGUNTA = 5 * 60


def fuera() -> bool:
    return not APAGADO.exists()


def chat() -> str | None:
    chats = lista("TELEGRAM_CHAT_ID")
    return chats[0] if chats else None


def leer_json(ruta: Path, defecto):
    try:
        return json.loads(ruta.read_text())
    except (OSError, ValueError):
        return defecto


# --- Lo usa el bot ----------------------------------------------------------------------------------------------
def es_alerta(message_id: int | None) -> bool:
    return str(message_id) in leer_json(ALERTAS, {})


def pregunta_de(message_id: int | None) -> str | None:
    return leer_json(PREGUNTAS, {}).get(str(message_id))


def dejar_mensaje(texto: str) -> None:
    """El bot deja aquí lo que escribiste para Claude."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    with BUZON.open("a") as f:
        f.write(json.dumps({"t": time.time(), "texto": texto}, ensure_ascii=False) + "\n")


def dejar_respuesta(pregunta_id: str, respuesta: str) -> None:
    RESPUESTAS.mkdir(parents=True, exist_ok=True)
    (RESPUESTAS / pregunta_id).write_text(respuesta)


def ultima_sesion() -> Path | None:
    """El transcript de Claude Code modificado más recientemente (la sesión que está trabajando)."""
    archivos = list((Path.home() / ".claude/projects").glob("*/*.jsonl"))
    return max(archivos, key=lambda f: f.stat().st_mtime) if archivos else None


def que_haces() -> str:
    """Última respuesta de Claude y lo último que hizo, leídos del transcript (solo lectura)."""
    sesion = ultima_sesion()
    if not sesion:
        return "No encuentro ninguna sesión de Claude Code."
    hace = int(time.time() - sesion.stat().st_mtime)
    ultima_accion = ""
    for linea in reversed(sesion.read_text(errors="replace").split("\n")[-400:]):
        try:
            evento = json.loads(linea)
        except ValueError:
            continue
        for bloque in (evento.get("message") or {}).get("content") or []:
            if isinstance(bloque, dict) and bloque.get("type") == "tool_use":
                entrada = bloque.get("input") or {}
                ultima_accion = f"{bloque.get('name')}: {entrada.get('description') or entrada.get('file_path') or ''}"
                break
        if ultima_accion:
            break
    respuesta = ultima_respuesta(str(sesion))[:1200]
    estado = "trabajando" if hace < 60 else f"sin actividad hace {hace // 60} min"
    return (f"🤖 Claude ({estado})\nÚltima acción: {ultima_accion or '—'}\n\nÚltimo mensaje:\n{respuesta or '—'}")


# --- Hooks -------------------------------------------------------------------------------------------------------
def hook_aviso(evento: dict) -> None:
    if fuera() and chat():
        telegram.enviar(chat(), texto_aviso(evento))


def hook_stop(evento: dict) -> None:
    """Avisa y espera un mensaje tuyo. Con mensaje: exit 2 (Claude Code despierta a Claude con él)."""
    if not fuera() or not chat():
        return
    CARPETA.mkdir(parents=True, exist_ok=True)
    turno = uuid.uuid4().hex
    TURNO.write_text(turno)
    desde = time.time()
    mid = telegram.enviar(chat(), texto_aviso(evento) + "\n\n↩️ Responde a este mensaje para escribirle a Claude.")
    if mid:
        alertas = leer_json(ALERTAS, {})
        alertas[str(mid)] = evento.get("session_id", "")
        ALERTAS.write_text(json.dumps(dict(list(alertas.items())[-50:])))
    while time.time() - desde < ESPERA_STOP:
        time.sleep(3)
        if TURNO.read_text() != turno or not fuera():  # llegó otro turno o volviste a la Mac
            return
        nuevos = [m for m in (json.loads(l) for l in BUZON.read_text().split("\n") if l.strip())
                  if m["t"] > desde] if BUZON.exists() else []
        if nuevos:
            texto = "\n".join(m["texto"] for m in nuevos)
            print(f"Mensaje del usuario desde Telegram (está fuera de la Mac; contéstale breve, en español, y "
                  f"sigue con lo que pide): {texto}", file=sys.stderr)
            sys.exit(2)


def hook_pregunta(evento: dict) -> None:
    """Pregunta con opciones → botones en Telegram. Si contestas a tiempo, la respuesta vuelve sola."""
    if not fuera() or not chat():
        return
    entrada = evento.get("tool_input") or {}
    respuestas = {}
    for pregunta in entrada.get("questions") or []:
        pid = uuid.uuid4().hex[:12]
        opciones = [o.get("label", "") for o in pregunta.get("options") or []]
        filas = [[(o[:60], f"cq:{pid}:{i}")] for i, o in enumerate(opciones)]
        detalle = "\n".join(f"· {o.get('label')}: {o.get('description', '')}" for o in pregunta.get("options") or [])
        mid = telegram.enviar(chat(), f"❓ Claude pregunta: {pregunta.get('question')}\n\n{detalle}\n\nToca una "
                                      f"opción o responde a este mensaje con otra cosa.", telegram.teclado(filas))
        if mid:
            CARPETA.mkdir(parents=True, exist_ok=True)
            mapa = leer_json(PREGUNTAS, {})
            mapa[str(mid)] = pid
            PREGUNTAS.write_text(json.dumps(dict(list(mapa.items())[-50:])))
        archivo = RESPUESTAS / pid
        limite = time.time() + ESPERA_PREGUNTA
        while time.time() < limite and not archivo.exists():
            time.sleep(2)
        if not archivo.exists():
            return  # sin respuesta: la pregunta aparece normal en la consola
        valor = archivo.read_text()
        archivo.unlink(missing_ok=True)
        respuestas[pregunta.get("question")] = opciones[int(valor)] if valor.isdigit() and int(valor) < len(opciones) \
            else valor
    if respuestas:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow",
            "permissionDecisionReason": "Respondido por Telegram",
            "updatedInput": {**entrada, "answers": respuestas}}}, ensure_ascii=False))


def main() -> None:
    try:
        evento = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    {"stop": hook_stop, "aviso": hook_aviso, "pregunta": hook_pregunta}[sys.argv[1]](evento)


if __name__ == "__main__":
    main()
