"""Chequeo de la Mac: el bot revisa solo, cada CHEQUEO_MIN minutos, que lo que necesita siga funcionando.

Nadie vigila la Mac como vigía vigila los servidores (personal-agents): un permiso que macOS quita al actualizarse
Python, Ollama caído, una sesión vencida o el disco lleno se descubren tarde, cuando un pedido falla. Esto los
encuentra antes y, si el arreglo es conocido y seguro, lo aplica solo:

- Cada revisión mira solo lo que está configurado (Ollama si hay AGENTE_MODELO, eco si hay ECO_DIR, sesiones si hay
  LOGIN_SITIOS, WhatsApp si ya exportaste chats) más Accesibilidad y disco.
- Un problema nuevo se avisa UNA vez; cuando desaparece, «resuelto» (estado en data/chequeo.json).
- Arreglo automático solo de una lista cerrada (hoy: prender Ollama) y una sola vez por problema: si no sirve, avisa
  y no reintenta en bucle. Lo que necesita tu decisión (iniciar sesión) llega con un botón; lo que solo tú puedes
  dar (permisos de macOS, espacio en disco) llega con los pasos.

    python -m mac.chequeo    # corre las revisiones y muestra el informe (sin avisar ni reparar)
"""
import ctypes
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests

from mac import agente, chrome, login, whatsapp
from mac.config import DATA_DIR, env

ESTADO = DATA_DIR / "chequeo.json"
ESPERA = 8  # segundos máximos por revisión que toca carpetas protegidas (macOS puede quedar esperando un permiso)


@dataclass
class Problema:
    clave: str                                  # identifica el problema entre vueltas (para avisar una sola vez)
    texto: str                                  # qué pasa y cómo se arregla
    reparar: Callable[[], bool] | None = None   # arreglo conocido y seguro: se intenta solo, una vez por problema
    boton: tuple[str, str] | None = None        # (texto, dato) cuando el arreglo necesita tu toque


def minutos() -> int:
    """Cada cuánto revisa solo (0 = nunca; «chequeo» sigue funcionando a pedido)."""
    try:
        return int(env("CHEQUEO_MIN", "30"))
    except ValueError:
        return 30


# --- Revisiones: cada una devuelve (línea de «todo bien» o None, problema o None) ------------------------------------
def revisar_ollama() -> tuple[str | None, Problema | None]:
    if not agente.modelo():
        return None, None
    try:
        requests.get(f"{env('OLLAMA_URL', 'http://localhost:11434')}/api/version", timeout=3).raise_for_status()
        return f"Ollama responde ({agente.modelo()})", None
    except requests.RequestException:
        return None, Problema("ollama", "Ollama no responde: el agente no puede resolver pedidos libres.",
                              reparar=prender_ollama)


def prender_ollama() -> bool:
    """La app de Ollama si está instalada; si no, el servicio de Homebrew. Espera hasta 15 s a que responda."""
    if Path("/Applications/Ollama.app").exists():
        orden = ["open", "-a", "Ollama"]
    else:
        brew = next((b for b in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if Path(b).exists()), None)
        if not brew:
            return False
        orden = [brew, "services", "start", "ollama"]
    try:
        subprocess.run(orden, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    for _ in range(15):
        time.sleep(1)
        if revisar_ollama()[1] is None:
            return True
    return False


def accesibilidad() -> bool:
    """¿macOS deja a este Python simular teclado? (lo usa «ejecuta … en la terminal de pycharm»)."""
    ax = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(ax.AXIsProcessTrusted())


def python_app() -> str:
    """La app de Python que macOS muestra en Privacidad (la de la versión que corre ahora)."""
    import sys
    raiz = Path(sys.executable).resolve().parent.parent  # …/Versions/3.x
    app = raiz / "Resources/Python.app"
    return str(app if app.exists() else Path(sys.executable).resolve())


def revisar_accesibilidad() -> tuple[str | None, Problema | None]:
    try:
        ok = accesibilidad()
    except OSError:
        return None, None  # no es macOS: no aplica
    if ok:
        return "Permiso de Accesibilidad", None
    return None, Problema("accesibilidad", "macOS no le da Accesibilidad al bot: no puedo escribir en terminales "
                          "visibles. Ajustes → Privacidad y seguridad → Accesibilidad → agrega y enciende "
                          f"{python_app()} (si Python se actualizó, es la versión nueva).")


def lee_con_tope(orden: list[str]) -> bool | None:
    """True si el proceso terminó bien, False si falló, None si se quedó esperando (permiso pendiente)."""
    try:
        return subprocess.run(orden, capture_output=True, timeout=ESPERA).returncode == 0
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return False


def revisar_whatsapp() -> tuple[str | None, Problema | None]:
    if not whatsapp.CARPETA.exists():
        return None, None  # nunca se exportó nada: no se usa
    ok = lee_con_tope(["ls", str(whatsapp.BASE.parent)])
    if ok:
        return "Lectura de WhatsApp", None
    motivo = "macOS espera que apruebes el acceso" if ok is None else "macOS no deja leer la carpeta de la app"
    return None, Problema("whatsapp", f"WhatsApp: {motivo}. Ajustes → Privacidad y seguridad → Acceso total al "
                          f"disco → agrega y enciende {python_app()}.")


def revisar_eco() -> tuple[str | None, Problema | None]:
    carpeta = env("ECO_DIR")
    if not carpeta:
        return None, None
    python = Path(carpeta).expanduser() / ".venv/bin/python"
    if not python.exists():
        return None, Problema("eco", f"eco: no encuentro {python} (¿se movió el repo o su entorno?).")
    ok = lee_con_tope([str(python), "-c", f"import os; os.listdir({json.dumps(str(Path(carpeta).expanduser()))})"])
    if ok:
        return "eco (personal-agents)", None
    return None, Problema("eco", "eco: su Python no puede leer la carpeta del repo"
                          + (" (macOS espera que apruebes el acceso)" if ok is None else "")
                          + f". Ajustes → Privacidad y seguridad → Acceso total al disco → agrega "
                          f"{Path(python).resolve()}.")


def revisar_disco() -> tuple[str | None, Problema | None]:
    libre = shutil.disk_usage(Path.home()).free / 1024 ** 3
    try:
        minimo = float(env("CHEQUEO_DISCO_MIN_GB", "10"))
    except ValueError:
        minimo = 10.0
    if libre >= minimo:
        return f"Disco: {libre:.0f} GB libres", None
    return None, Problema("disco", f"Disco casi lleno: {libre:.1f} GB libres (mínimo {minimo:g}). Con poco espacio "
                          "macOS se pone lento y Ollama no puede cargar modelos. Mira qué ocupa más en Ajustes → "
                          "General → Almacenamiento (no borro nada por mi cuenta).")


def revisar_sesiones() -> tuple[str | None, list[Problema]]:
    """Sitios de LOGIN_SITIOS con una pestaña en la página de login (sesión vencida). Solo si Chrome está abierto."""
    sitios = login.sitios()
    if not sitios or not chrome.esta_corriendo():
        return None, []
    problemas = []
    for nombre, sitio in sitios.items():
        if not chrome.permitido(login.carpeta(sitio["perfil"])):
            continue
        try:
            vencida = login.pestana_de_login(sitio) is not None
        except chrome.ChromeError:
            continue  # Chrome ocupado: se mira en la vuelta siguiente
        if vencida:
            problemas.append(Problema(f"sesion:{nombre}", f"La sesión de {nombre} venció (hay una pestaña en su "
                                      "página de inicio de sesión).", boton=(f"🔑 Iniciar sesión en {nombre}",
                                                                             f"login:{nombre}")))
    return (f"Sesiones abiertas: {', '.join(sitios)}" if not problemas else None), problemas


def revisar() -> tuple[list[str], list[Problema]]:
    """Todas las revisiones: (lo que está bien, problemas)."""
    bien, problemas = [], []
    for revision in (revisar_ollama, revisar_accesibilidad, revisar_whatsapp, revisar_eco, revisar_disco):
        try:
            ok, problema = revision()
        except Exception as e:  # noqa: BLE001 - una revisión que falla no frena las demás
            ok, problema = None, Problema(revision.__name__, f"No pude revisar {revision.__name__[8:]}: {e}")
        bien += [ok] if ok else []
        problemas += [problema] if problema else []
    ok, vencidas = revisar_sesiones()
    return bien + ([ok] if ok else []), problemas + vencidas


# --- Vueltas: avisar una vez, reparar una vez, decir cuándo se resolvió ---------------------------------------------
def leer_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text())
    except (OSError, ValueError):
        return {}


def guardar_estado(estado: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1))


def toca(ahora: float | None = None) -> bool:
    """¿Ya pasaron CHEQUEO_MIN minutos desde la última vuelta?"""
    if minutos() <= 0:
        return False
    return (ahora or time.time()) - leer_estado().get("ultima", 0) >= minutos() * 60


def vuelta(avisar: Callable[[str, dict | None], None], revisar_=revisar) -> None:
    """Una vuelta automática. `avisar(texto, botones)` manda a Telegram. Solo habla si algo cambió."""
    from mac import telegram  # aquí: chequeo se puede correr sin Telegram (python -m mac.chequeo)
    estado = leer_estado()
    abiertos: dict = estado.get("abiertos", {})
    _, problemas = revisar_()
    actuales = {p.clave: p for p in problemas}
    for clave in [c for c in abiertos if c not in actuales]:
        avisar(f"✅ Resuelto: {abiertos.pop(clave)['texto']}", None)
    for p in problemas:
        if p.clave in abiertos:
            continue  # ya avisado: no se repite en cada vuelta
        abiertos[p.clave] = {"desde": datetime.now().isoformat(timespec="minutes"), "texto": p.texto}
        if p.reparar:
            if p.reparar():
                abiertos.pop(p.clave)
                avisar(f"🔧 {p.texto}\nLo arreglé solo y ya funciona.", None)
                continue
            avisar(f"⚠️ {p.texto}\nIntenté arreglarlo solo y no funcionó; no vuelvo a intentarlo hasta que se "
                   "resuelva.", None)
        else:
            avisar(f"⚠️ {p.texto}", telegram.teclado([[p.boton]]) if p.boton else None)
    guardar_estado({**estado, "abiertos": abiertos, "ultima": time.time()})


def informe(revisar_=revisar) -> tuple[str, dict | None]:
    """«chequeo» a pedido: todo lo revisado, sin reparar, con los botones de lo que necesita tu toque."""
    from mac import telegram
    bien, problemas = revisar_()
    lineas = ["🩺 Chequeo de la Mac"] + [f"✅ {b}" for b in bien] + [f"⚠️ {p.texto}" for p in problemas]
    if not problemas:
        lineas.append("Todo en orden.")
    elif any(p.reparar for p in problemas):
        lineas.append("Lo que tiene arreglo conocido lo intento solo en la próxima revisión automática.")
    if minutos() > 0:
        lineas.append(f"Reviso solo cada {minutos()} min y te aviso una vez si algo se rompe.")
    filas = [[p.boton] for p in problemas if p.boton]
    return "\n".join(lineas), (telegram.teclado(filas) if filas else None)


if __name__ == "__main__":
    print(informe()[0])
