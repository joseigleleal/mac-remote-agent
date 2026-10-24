"""Apps de la Mac: cuáles están abiertas, qué consume más y cerrar una (como ⌘Q: si hay algo sin guardar, la app
pregunta).

- Abiertas: System Events (procesos que no son de fondo), con su bundle id para cerrarlas sin ambigüedad.
- Consumo: `ps` de todos los procesos, sumando cada uno a la app (`/Algo.app/`) a la que pertenece; así los
  ayudantes de Chrome cuentan como Chrome.
"""
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass

from mac.chrome import osascript
from mac.config import lista
from mac.interprete import normalizar

PROTEGIDAS = {"Finder", "loginwindow", "Dock", "SystemUIServer", "WindowServer"}  # nunca se cierran desde el bot

LISTAR = '''tell application "System Events"
  set salida to ""
  repeat with p in (every application process whose background only is false)
    set salida to salida & (name of p) & tab & (bundle identifier of p) & linefeed
  end repeat
  return salida
end tell'''


@dataclass
class App:
    nombre: str
    bundle: str


def abiertas() -> list[App]:
    salida = []
    for linea in osascript(LISTAR).splitlines():
        nombre, _, bundle = linea.partition("\t")
        if nombre:
            salida.append(App(nombre, bundle))
    return salida


def protegida(nombre: str) -> bool:
    return nombre in PROTEGIDAS or nombre in lista("APPS_PROTEGIDAS")


def buscar(texto: str) -> list[App]:
    """Apps abiertas cuyo nombre coincide con el texto (sin mayúsculas ni tildes); exacta primero."""
    t = normalizar(texto)
    todas = abiertas()
    exactas = [a for a in todas if normalizar(a.nombre) == t]
    return exactas or [a for a in todas if t and (t in normalizar(a.nombre) or normalizar(a.nombre) in t)]


def memoria() -> dict[int, float]:
    """GB por proceso según `top` (la «Memoria» del Monitor de Actividad). Incluye la memoria de la GPU, que en los
    chips de Apple es la misma RAM: el RSS de `ps` no la cuenta y un entrenamiento con MLX parecía usar 0,2 GB."""
    r = subprocess.run(["top", "-l", "1", "-stats", "pid,mem"], capture_output=True, text=True, timeout=20)
    unidades = {"B": 1 / 1024 ** 3, "K": 1 / 1024 ** 2, "M": 1 / 1024, "G": 1}
    salida = {}
    for linea in r.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s+([\d.]+)([BKMG])", linea)
        if m:
            salida[int(m.group(1))] = float(m.group(2)) * unidades[m.group(3)]
    return salida


def consumo(n: int = 6) -> list[tuple[str, float, float]]:
    """Las `n` apps (o procesos sueltos) que más consumen: (nombre, % CPU, GB de RAM), por RAM y luego CPU."""
    gb = memoria()
    r = subprocess.run(["ps", "-Ao", "pid=,pcpu=,comm="], capture_output=True, text=True)
    cpu, ram = defaultdict(float), defaultdict(float)
    for linea in r.stdout.splitlines():
        partes = linea.split(None, 2)
        if len(partes) < 3:
            continue
        m = re.search(r"/([^/]+)\.app/", partes[2])
        nombre = m.group(1) if m else os.path.basename(partes[2])
        cpu[nombre] += float(partes[1])
        ram[nombre] += gb.get(int(partes[0]), 0)
    orden = sorted(ram, key=lambda k: (ram[k], cpu[k]), reverse=True)
    return [(k, cpu[k], ram[k]) for k in orden[:n]]


def resumen_mac() -> str:
    """Carga, RAM libre y lo que más consume."""
    presion = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
    libre = re.search(r"(\d+)%", presion)
    total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout or 0)
    lineas = [f"🖥️ Mac: carga {os.getloadavg()[0]:.1f} con {os.cpu_count()} núcleos · RAM libre "
              f"{libre.group(1) if libre else '?'} % de {total / 1024 ** 3:.0f} GB", "Lo que más consume:"]
    lineas += [f"· {nombre}: {gb:.1f} GB · CPU {c:.0f} %" for nombre, c, gb in consumo()]
    return "\n".join(lineas)


def cerrar(app: App) -> None:
    """Le pide a la app que se cierre (como ⌘Q). Por bundle id: dos apps no se confunden por nombre."""
    osascript('on run argv\ntell application id (item 1 of argv) to quit\nend run', app.bundle)


def sigue_abierta(app: App) -> bool:
    return any(a.bundle == app.bundle for a in abiertas())
