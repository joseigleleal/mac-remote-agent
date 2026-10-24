"""Chrome en la Mac: qué perfiles hay abiertos, qué ventana es de cada uno, buscar pestañas y actuar en ellas.

- Perfiles y sus nombres: el archivo `Local State` de Chrome (`profile.info_cache`).
- Perfiles abiertos: las carpetas de perfil que el proceso de Chrome tiene abiertas (`lsof`).
- Ventanas y pestañas: AppleScript. AppleScript no dice de qué perfil es cada ventana, así que se cruzan sus URLs
  con el archivo de sesión de cada perfil (`<perfil>/Sessions/Session_*`): la ventana es del perfil que más las tiene.
- Ejecutar JavaScript en una pestaña exige activar en Chrome, en ese perfil: Ver → Opciones para desarrolladores →
  Permitir JavaScript desde Eventos de Apple.

    python -m mac.chrome    # muestra perfiles, cuáles están abiertos y sus ventanas
"""
import json
import re
import subprocess
from dataclasses import dataclass, field

from mac.config import CHROME_DIR, alias_perfiles, lista

APP = "Google Chrome"


class ChromeError(Exception):
    """Algo que conviene contarle a la persona tal cual (Chrome cerrado, permiso faltante…)."""


@dataclass
class Perfil:
    carpeta: str   # "Default", "Profile 6"…
    nombre: str    # el que se ve en Chrome
    alias: str = ""  # el apodo de CHROME_PERFILES, si tiene

    @property
    def etiqueta(self) -> str:
        return self.alias or f"{self.nombre} ({self.carpeta})"


@dataclass
class Ventana:
    id: int
    urls: list[str] = field(default_factory=list)
    perfil: str | None = None  # carpeta del perfil, si se pudo saber


def osascript(script: str, *args: str) -> str:
    """Corre AppleScript pasando los datos como argumentos (`on run argv`), nunca pegados al código."""
    r = subprocess.run(["osascript", "-", *args], input=script, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        error = r.stderr.strip()
        if "JavaScript" in error:
            raise ChromeError("Chrome no deja ejecutar JavaScript desde AppleScript en ese perfil. Actívalo en "
                              "Chrome: Ver → Opciones para desarrolladores → Permitir JavaScript desde Eventos de Apple.")
        if "-1743" in error or "not allowed" in error.lower():
            raise ChromeError("macOS no deja controlar Chrome. Permítelo en Ajustes → Privacidad y seguridad → "
                              "Automatización (para la app que corre el bot).")
        raise ChromeError(f"AppleScript falló: {error[-300:]}")
    return r.stdout.rstrip("\n")


def esta_corriendo() -> bool:
    return subprocess.run(["pgrep", "-x", APP], capture_output=True).returncode == 0


# --- Perfiles --------------------------------------------------------------------------------------------------
def perfiles() -> dict[str, Perfil]:
    """Todos los perfiles de Chrome de este usuario: {carpeta: Perfil}."""
    try:
        cache = json.loads((CHROME_DIR / "Local State").read_text())["profile"]["info_cache"]
    except (OSError, ValueError, KeyError):
        return {}
    apodos = {carpeta: alias for alias, carpeta in alias_perfiles().items()}
    return {c: Perfil(c, i.get("name") or c, apodos.get(c, "")) for c, i in cache.items()}


def carpetas_abiertas() -> list[str]:
    """Perfiles con ventana abierta ahora: carpetas de perfil que el proceso de Chrome tiene en uso."""
    pid = subprocess.run(["pgrep", "-x", APP], capture_output=True, text=True).stdout.split()
    if not pid:
        return []
    salida = subprocess.run(["lsof", "-p", pid[0]], capture_output=True, text=True).stdout
    vistas = set(re.findall(r"/Google/Chrome/(Default|Profile \d+)/", salida))
    return sorted(vistas, key=lambda c: (c != "Default", int(c.split()[-1]) if c[-1].isdigit() else 0))


def permitido(carpeta: str) -> bool:
    permitidos = lista("CHROME_PERFILES_PERMITIDOS")
    return not permitidos or carpeta in permitidos


def abiertos() -> list[Perfil]:
    """Perfiles abiertos que el bot puede usar."""
    todos = perfiles()
    return [todos.get(c, Perfil(c, c)) for c in carpetas_abiertas() if permitido(c)]


def resolver(texto: str) -> Perfil | None:
    """Encuentra un perfil por apodo, nombre o carpeta mencionado en el texto (sin importar mayúsculas)."""
    t = texto.lower()
    todos = perfiles()
    for alias, carpeta in alias_perfiles().items():
        if re.search(rf"\b{re.escape(alias)}\b", t) and carpeta in todos:
            return todos[carpeta]
    for p in todos.values():
        if re.search(rf"\b{re.escape(p.carpeta.lower())}\b", t):
            return p
    nombres = [p for p in todos.values() if re.search(rf"\b{re.escape(p.nombre.lower())}\b", t)]
    return nombres[0] if len(nombres) == 1 else None  # nombre repetido en dos perfiles: ambiguo


# --- Ventanas y pestañas ---------------------------------------------------------------------------------------
LISTAR = '''on run argv
tell application "Google Chrome"
  set salida to ""
  set sep to character id 9 -- tabulador (dentro de Chrome, "tab" es una pestaña)
  repeat with w in windows
    try -- una ventana o pestaña puede cerrarse o cambiar mientras se recorre (ej. una redirección de login)
      if mode of w is "normal" then
        set wid to id of w
        set urls to URL of every tab of w -- de una vez: no cambia a mitad de camino
        repeat with u in urls
          set salida to salida & wid & sep & (u as text) & linefeed
        end repeat
      end if
    end try
  end repeat
  return salida
end tell
end run'''


def ventanas() -> list[Ventana]:
    """Ventanas normales (no incógnito) con sus URLs y el perfil de cada una."""
    if not esta_corriendo():
        return []
    por_id: dict[int, Ventana] = {}
    for linea in osascript(LISTAR).splitlines():
        wid, _, url = linea.partition("\t")
        if wid.isdigit():
            por_id.setdefault(int(wid), Ventana(int(wid))).urls.append(url)
    lista_v = list(por_id.values())
    asignar_perfiles(lista_v, {c: sesion(c) for c in carpetas_abiertas()})
    return lista_v


def sesion(carpeta: str) -> bytes:
    """Contenido del archivo de sesión más reciente del perfil (ahí Chrome anota las pestañas abiertas)."""
    archivos = sorted((CHROME_DIR / carpeta / "Sessions").glob("Session_*"), key=lambda f: f.stat().st_mtime)
    try:
        return archivos[-1].read_bytes() if archivos else b""
    except OSError:
        return b""


def asignar_perfiles(lista_v: list[Ventana], sesiones: dict[str, bytes]) -> None:
    """A cada ventana, el perfil cuya sesión contiene más de sus URLs (si ninguna coincide, queda sin perfil)."""
    for v in lista_v:
        puntos = {c: sum(u.encode() in datos for u in v.urls if u) for c, datos in sesiones.items()}
        mejor = max(puntos, key=puntos.get, default=None)
        v.perfil = mejor if mejor and puntos[mejor] > 0 else None


def buscar_pestana_tolerante(carpeta: str, contiene: str) -> tuple[int, int] | None:
    """Como `buscar_pestana`, pero un error momentáneo (Chrome abriendo una ventana: «conexión no válida», -609)
    cuenta como «todavía no está»: sirve para esperar una pestaña recién abierta."""
    try:
        return buscar_pestana(carpeta, contiene)
    except ChromeError:
        return None


def buscar_pestana(carpeta: str, contiene: str) -> tuple[int, int] | None:
    """(id de ventana, número de pestaña desde 1) de la primera pestaña del perfil cuya URL contiene `contiene`."""
    for v in ventanas():
        if v.perfil == carpeta:
            for i, url in enumerate(v.urls, 1):
                if contiene in url:
                    return v.id, i
    return None


def mostrar(ventana: int, pestana: int) -> None:
    """Trae al frente la ventana y deja activa esa pestaña."""
    osascript('''on run argv
tell application "Google Chrome"
  set w to window id (item 1 of argv as integer)
  set active tab index of w to (item 2 of argv as integer)
  set index of w to 1
  activate
end tell
end run''', str(ventana), str(pestana))


def url(ventana: int, pestana: int) -> str:
    """Dirección actual de esa pestaña."""
    return osascript('''on run argv
tell application "Google Chrome" to return URL of tab (item 2 of argv as integer) of window id (item 1 of argv as integer)
end run''', str(ventana), str(pestana))


def ir(ventana: int, pestana: int, url: str) -> None:
    """Lleva esa pestaña a otra dirección."""
    osascript('''on run argv
tell application "Google Chrome" to set URL of tab (item 2 of argv as integer) of window id (item 1 of argv as integer) to (item 3 of argv)
end run''', str(ventana), str(pestana), url)


def ejecutar_js(ventana: int, pestana: int, js: str) -> str:
    """Ejecuta JavaScript en esa pestaña y devuelve el resultado como texto."""
    return osascript('''on run argv
tell application "Google Chrome"
  return execute (tab (item 2 of argv as integer) of window id (item 1 of argv as integer)) javascript (item 3 of argv)
end tell
end run''', str(ventana), str(pestana), js)


def ejecutar_js_privado(ventana: int, pestana: int, js: str) -> str:
    """Como `ejecutar_js`, pero el JavaScript (que puede llevar una contraseña) va dentro del script que osascript lee
    por la entrada estándar, no como argumento: los argumentos de un proceso se ven con `ps`."""
    texto = js.replace("\\", "\\\\").replace('"', '\\"')  # comillas y barras escapadas para AppleScript
    return osascript(f'tell application "Google Chrome" to return execute (tab {int(pestana)} of window id '
                     f'{int(ventana)}) javascript "{texto}"')


def abrir(carpeta: str, url: str) -> None:
    """Abre la URL en ese perfil (pestaña nueva en su ventana; si el perfil no estaba abierto, ventana nueva)."""
    subprocess.run(["open", "-na", APP, "--args", f"--profile-directory={carpeta}", url], check=True, timeout=30)


def main() -> None:
    todos, abiertas = perfiles(), carpetas_abiertas()
    print("Perfiles (carpeta → nombre):")
    for p in todos.values():
        marca = "abierto" if p.carpeta in abiertas else ""
        permiso = "" if permitido(p.carpeta) else "no permitido"
        print(f"  {p.carpeta:<11} {p.nombre:<20} {p.alias:<10} {marca} {permiso}")
    print("\nVentanas:")
    for v in ventanas():
        print(f"  {v.id}: perfil {v.perfil or '?'} · {len(v.urls)} pestañas")


if __name__ == "__main__":
    main()
