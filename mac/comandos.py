"""Comandos de terminal de una lista permitida (COMANDOS_PERMITIDOS en .env), sin shell.

Solo se ejecuta un comando si es **exactamente** uno de la lista: el texto de Telegram nunca se ejecuta tal cual.
Corre en segundo plano (no depende de una terminal abierta) y queda anotado en `data/comandos.json` para poder
verlo y detenerlo después, aunque el bot se haya reiniciado.
"""
import json
import os
import shlex
import signal
import subprocess
import time
from datetime import datetime

from mac.config import DATA_DIR, env

REGISTRO = DATA_DIR / "comandos.json"
ESPERA = 3  # segundos: si termina antes, se devuelve su salida; si no, queda corriendo


def permitidos() -> list[str]:
    """COMANDOS_PERMITIDOS=caffeinate -d;caffeinate -i → ["caffeinate -d", "caffeinate -i"] (separados por «;»)."""
    return [" ".join(c.split()) for c in (env("COMANDOS_PERMITIDOS") or "").split(";") if c.strip()]


def leer() -> dict:
    try:
        return json.loads(REGISTRO.read_text())
    except (OSError, ValueError):
        return {}


def vivo(pid: int) -> bool:
    try:  # si es hijo del bot y ya terminó, se recoge (si no, queda «zombi» y parece vivo)
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False
    except ChildProcessError:  # no es hijo de este proceso (lo lanzó el bot antes de reiniciarse)
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def es_el_mismo(pid: int, datos: dict) -> bool:
    """El pid sigue siendo ese comando (macOS reutiliza pids: sin esto, «detén» podría matar otro programa)."""
    actual = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return " ".join(actual.split()).endswith(datos["comando"]) or datos["comando"].split()[0] in actual


def corriendo() -> dict[int, dict]:
    """Los comandos lanzados por el bot que siguen vivos: {pid: {"comando", "desde"}}."""
    activos = {int(pid): datos for pid, datos in leer().items() if vivo(int(pid)) and es_el_mismo(int(pid), datos)}
    DATA_DIR.mkdir(exist_ok=True)
    REGISTRO.write_text(json.dumps(activos, ensure_ascii=False, indent=1))
    return activos


def ejecutar(comando: str) -> str:
    comando = " ".join(comando.split())
    if comando not in permitidos():
        return (f"«{comando}» no está en la lista de comandos permitidos, así que no lo ejecuto. Si lo quieres, "
                "agrégalo en .env a COMANDOS_PERMITIDOS (separados por «;») y reinicia el bot.")
    DATA_DIR.mkdir(exist_ok=True)
    salida = DATA_DIR / "comando.log"
    with open(salida, "w") as f:
        proceso = subprocess.Popen(shlex.split(comando), stdout=f, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)  # sobrevive al bot
    try:
        codigo = proceso.wait(timeout=ESPERA)
    except subprocess.TimeoutExpired:
        activos = corriendo()
        activos[proceso.pid] = {"comando": comando, "desde": datetime.now().isoformat(timespec="minutes")}
        REGISTRO.write_text(json.dumps(activos, ensure_ascii=False, indent=1))
        return f"▶️ «{comando}» corriendo en segundo plano (pid {proceso.pid}). Para pararlo: «detén {comando}»."
    texto = salida.read_text(errors="replace").strip()[-1500:]
    return f"{'✅' if codigo == 0 else '⚠️'} «{comando}» terminó (código {codigo})" + (f":\n{texto}" if texto else ".")


def detener(texto: str) -> str:
    """Detiene los comandos corriendo cuyo texto contiene `texto` (ej. «caffeinate»)."""
    texto = " ".join(texto.split())
    elegidos = {pid: d for pid, d in corriendo().items() if texto and texto in d["comando"]}
    if not elegidos:
        return f"No hay ningún comando corriendo que coincida con «{texto}»."
    for pid in elegidos:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.5)
    corriendo()
    return "⏹️ Detenido: " + ", ".join(f"«{d['comando']}»" for d in elegidos.values())


def resumen() -> str:
    lista = permitidos()
    activos = corriendo()
    lineas = ["Comandos permitidos:"] + ([f"· {c}" for c in lista] or ["· ninguno (COMANDOS_PERMITIDOS en .env)"])
    lineas.append("Corriendo:")
    lineas += [f"· {d['comando']} (desde {d['desde'][11:]}, pid {pid})" for pid, d in activos.items()] or ["· nada"]
    return "\n".join(lineas)
