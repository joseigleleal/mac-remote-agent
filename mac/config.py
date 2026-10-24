"""Configuración: rutas y variables de entorno. Todo lo propio de cada persona (bot, chat, perfiles) va en .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHROME_DIR = Path.home() / "Library/Application Support/Google/Chrome"

load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def lista(name: str) -> list[str]:
    """Variable separada por comas → lista sin vacíos."""
    return [x.strip() for x in (env(name) or "").split(",") if x.strip()]


def alias_perfiles() -> dict[str, str]:
    """CHROME_PERFILES=personal:Default,estudio:Profile 2 → {"personal": "Default", "estudio": "Profile 2"}.
    Así se le puede decir "mi perfil personal" en vez del nombre de la carpeta."""
    salida = {}
    for par in lista("CHROME_PERFILES"):
        alias, _, carpeta = par.partition(":")
        if alias.strip() and carpeta.strip():
            salida[alias.strip().lower()] = carpeta.strip()
    return salida
