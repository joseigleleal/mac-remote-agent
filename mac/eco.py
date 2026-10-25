"""«eco: <mensaje que te mandaron>»: le pide al agente `eco` (repo personal-agents) cómo responderías tú.

eco vive en otro repo y corre con su propio entorno: aquí solo se llama a su línea de comandos. El texto va como
argumento, nunca por un shell. Se activa con ECO_DIR (carpeta del repo con el agente) en el .env.
"""
import subprocess
from pathlib import Path

from mac.config import env


def sugerir(mensaje: str, chat: str = "") -> str:
    carpeta = env("ECO_DIR")
    if not carpeta:
        return "eco no está configurado: falta ECO_DIR en el .env (carpeta del repo con el agente eco)."
    raiz = Path(carpeta).expanduser()
    orden = [str(raiz / ".venv/bin/python"), "-m", "agents.eco.run", "--sugerir", mensaje]
    if chat:
        orden += ["--chat", chat]
    try:
        r = subprocess.run(orden, cwd=raiz, capture_output=True, text=True, timeout=150)
    except (OSError, subprocess.TimeoutExpired) as e:
        return (f"⚠️ eco no respondió ({type(e).__name__}). Si es la primera vez, macOS puede estar esperando que "
                "apruebes en la Mac el acceso de Python a la carpeta del repo (Ajustes → Privacidad y seguridad → "
                "Archivos y carpetas, o Acceso total al disco).")
    if r.returncode != 0:
        return f"⚠️ eco falló: {(r.stderr or r.stdout).strip()[-300:]}"
    return "🗣️ Yo respondería:\n" + r.stdout.strip()
