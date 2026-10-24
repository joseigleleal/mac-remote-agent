"""El bot como servicio: cuánto consume, pausa (sigue escuchando pero no hace nada) y apagado total por launchd."""
import os
import re
import subprocess
from datetime import datetime

from mac.config import DATA_DIR

ETIQUETA = "com.mac-remote-agent.bot"  # la misma de scripts/instalar_launchd.sh
PAUSA = DATA_DIR / "pausado"  # si existe, el bot está en pausa (sobrevive a reinicios)


def pausado() -> bool:
    return PAUSA.exists()


def pausar() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PAUSA.write_text(datetime.now().isoformat(timespec="minutes"))


def reanudar() -> None:
    PAUSA.unlink(missing_ok=True)


def con_launchd() -> bool:
    """¿Lo lanzó launchd? (si se corre a mano en una terminal, apagarlo es solo salir)."""
    return os.environ.get("XPC_SERVICE_NAME") == ETIQUETA


def apagar() -> None:
    """Apagado total: launchd lo baja y no lo vuelve a arrancar (ni al iniciar sesión) hasta `scripts/bot.sh prender`."""
    if con_launchd():
        dominio = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "disable", f"{dominio}/{ETIQUETA}"], timeout=10)
        subprocess.run(["launchctl", "bootout", f"{dominio}/{ETIQUETA}"], timeout=10)  # termina este proceso
    raise SystemExit(0)


def recursos() -> str:
    """Lo que gasta el bot (CPU, RAM, tiempo encendido) y cómo está la Mac."""
    ps = subprocess.run(["ps", "-o", "pcpu=,rss=,etime=,time=", "-p", str(os.getpid())],
                        capture_output=True, text=True).stdout.split()
    cpu, rss, encendido, cpu_total = (ps + ["?"] * 4)[:4]
    ram_mac = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout or 0)
    presion = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
    libre = re.search(r"(\d+)%", presion)
    carga = os.getloadavg()[0]
    nucleos = os.cpu_count() or 1
    lineas = [
        "⏸️ En pausa (dime «prende» para volver)" if pausado() else "▶️ Activo",
        f"Bot: CPU {cpu} % ahora · RAM {int(rss) / 1024:.0f} MB" if rss.isdigit() else "Bot: sin datos",
        f"Encendido hace {encendido} · CPU usada en total: {cpu_total}",
        f"Mac: carga {carga:.1f} con {nucleos} núcleos · RAM libre {libre.group(1) if libre else '?'} % "
        f"de {ram_mac / 1024 ** 3:.0f} GB",
    ]
    return "\n".join(lineas)
