"""Del texto que llega por Telegram a una acción de una lista cerrada. Nunca se ejecuta el texto: solo se busca qué
acción conocida pide y con qué datos. Son reglas simples en español; lo que no encaja, se responde con la ayuda."""
import re
import unicodedata
from dataclasses import dataclass, field

ACCIONES = ("claude", "avisos", "login", "musica", "estado", "pausar", "reanudar", "apagar", "comando", "detener", "comandos", "apps", "consumo", "cerrar",
            "perfiles", "volumen", "spotify", "ayuda")

VERBOS_MUSICA = r"\b(busca\w*|busque\w*|pon|ponme|ponle|pongas|reproduc\w*|toca|tocame|escuch\w*|play)\b"
# Lo que no es parte de la búsqueda: el perfil, el sitio y el «y dale play» del final.
RELLENO = [
    r"\b(entra\w*|abr\w*|ve|vete|usa\w*)?\s*(a|en)\s+(mi|el|la)?\s*perfil\b(\s+de)?\s+[\w.-]+(\s+de\s+chrome)?",
    r"\b(en|de)\s+(la\s+)?(pestana|pagina|web)\s+de\s+spotify\b",
    r"\b(en|por)\s+spotify\b", r"\bspotify\b",
    r"\s+y\s+(le\s+)?(da|de|des|dale|dele|pon|pong|reproduc|toca)\w*(\s+play)?\b.*$",
]
PREFIJOS = r"^(a|la|el|los|las|un|una|algo|musica|canciones?|temas?|de|del|por favor|porfa)\s+"


@dataclass
class Pedido:
    accion: str
    datos: dict = field(default_factory=dict)


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar ("qué" = "que")."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def quitar_saludo(texto: str) -> str:
    """«hola mac, …» / «mac: …» → «…»."""
    return re.sub(r"^\s*(hola\s+)?mac\b[\s,:;.!-]*", "", texto, flags=re.I).strip()


def consulta_musica(t: str) -> str:
    """Lo que hay que buscar: lo que sigue al primer verbo de música, sin el perfil, el sitio ni el «dale play»."""
    m = re.search(VERBOS_MUSICA, t)
    resto = t[m.end():] if m else t
    for patron in RELLENO:
        resto = re.sub(patron, " ", resto)
    resto = re.sub(r"[\s,.;:!?]+$", "", re.sub(r"\s+", " ", resto)).strip()
    while re.match(PREFIJOS, resto + " ") and resto:
        nuevo = re.sub(PREFIJOS, "", resto + " ").strip()
        if nuevo == resto:
            break
        resto = nuevo
    return resto


def pedido_volumen(t: str) -> Pedido | None:
    """«sube el volumen», «baja el volumen 20», «volumen al 30», «silencia», «quita el silencio»."""
    if re.search(r"\b(quita\w* (el )?silencio|desmute\w*|activa\w* el (sonido|audio))\b", t):
        return Pedido("volumen", {"modo": "activar"})
    if re.search(r"\b(silencia\w*|mute\w*|mutea\w*|silencio|apaga\w* (el )?(sonido|volumen|audio))\b", t):
        return Pedido("volumen", {"modo": "silenciar"})
    if not re.search(r"\b(volumen|sonido)\b", t):
        return None
    numero = re.search(r"\b(\d{1,3})\b", t)
    valor = int(numero.group(1)) if numero else None
    if re.search(r"\b(sube\w*|subir|mas alto|aumenta\w*)\b", t):
        return Pedido("volumen", {"modo": "subir", "valor": valor})
    if re.search(r"\b(baja\w*|bajar|mas bajo|disminu\w*)\b", t):
        return Pedido("volumen", {"modo": "bajar", "valor": valor})
    if valor is not None:
        return Pedido("volumen", {"modo": "fijar", "valor": valor})
    return Pedido("volumen", {"modo": "ver"})


def pedido_servicio(t: str) -> Pedido | None:
    """El bot mismo: recursos, pausa, volver y apagado total (este último solo pide confirmación)."""
    if t.startswith("/apagar") or re.search(r"\bdel todo\b", t) and re.search(r"\bapag\w*", t):
        return Pedido("apagar")
    if t.startswith("/estado") or re.search(r"\b(consumes|gastas|estado)\b", t) or re.search(r"\bbot\b", t) \
            and re.search(r"\b(recursos|consum\w*|gast\w*)\b", t):
        return Pedido("estado")
    if t.startswith("/pausar") or re.fullmatch(r"(pausa\w*|apaga\w*|apagate|duerme\w*|descansa)( el bot)?", t):
        return Pedido("pausar")
    if t.startswith(("/reanudar", "/prender")) or re.fullmatch(
            r"(prende\w*|enciende\w*|reanuda\w*|despierta\w*|activate|vuelve)( el bot)?", t):
        return Pedido("reanudar")
    return None


MUSICA = r"\b(spotify|musica|cancion|tema)\b"


def pedido_login(t: str) -> Pedido | None:
    """«reautentica usal», «inicia sesión en correo», «/login usal». El sitio es la palabra que sigue (o ninguna)."""
    if t.startswith("/login"):
        return Pedido("login", {"sitio": t[len("/login"):].strip()})
    m = re.search(r"\b(re-?autentica\w*|re-?logea\w*|re-?loguea\w*|logea\w*|loguea\w*|inicia\w* sesion|"
                  r"vuelve a (entrar|iniciar sesion))\b\s*(en|a|de)?\s*(mi|el|la)?\s*(perfil|cuenta)?\s*(de)?\s*(?P<sitio>.*)$", t)
    if m:
        return Pedido("login", {"sitio": m.group("sitio").strip()})
    return None


def pedido_musica(t: str) -> Pedido | None:
    """«pausa spotify», «para la música», «sigue la música», «siguiente canción», «canción anterior».
    Va antes que el resto: «pausa» sola pausa el bot, y «detén la música» no es un comando de terminal."""
    if t.startswith("/musica"):
        t = t[len("/musica"):] + " musica"
    if re.search(r"\bsiguiente\b", t) or re.search(r"\b(salta\w*|skip)\b", t) and re.search(MUSICA, t) \
            or re.search(r"\bpasa\w* (de |a )?(la |esta |el )?(cancion|tema)\b", t):
        return Pedido("musica", {"accion": "siguiente"})
    if re.search(r"\banterior\b", t) and re.search(MUSICA + r"|\banterior\b", t):
        return Pedido("musica", {"accion": "anterior"})
    if not re.search(MUSICA, t):
        return None
    if re.search(r"\b(pausa\w*|para\w*|det[eé]n\w*|deten\w*|stop|apaga\w*|quita\w*)\b", t):
        return Pedido("musica", {"accion": "pausar"})
    if re.search(r"\b(sigue|segui\w*|continua\w*|reanuda\w*|reproduce|play|resume)\b", t) and \
            not re.search(r"\b(pon|ponme|busca\w*)\b", t) and len(t.split()) <= 5:
        return Pedido("musica", {"accion": "seguir"})
    return None


def pedido_comando(original: str, t: str) -> Pedido | None:
    """«ejecuta caffeinate -d (en la terminal…)», «detén caffeinate», «qué comandos hay». El comando se toma del texto
    original (con mayúsculas y signos); si se ejecuta o no lo decide la lista permitida, no esto."""
    if t.startswith("/comandos") or re.search(r"\bcomandos\b", t):
        return Pedido("comandos")
    m = re.match(r"^\s*(/ejecutar|ejecuta\w*|corre|lanza|run)\s+(.+?)"
                 r"(\s+(en|desde)\s+(la\s+|el\s+|una\s+|un\s+)?(consola|terminal|pycharm|intellij|iterm)\b.*)?\s*$",
                 original, flags=re.I | re.S)
    if m:
        cola = normalizar(m.group(3) or "")
        donde = next((d for d in ("pycharm", "intellij", "iterm") if d in cola), None)
        return Pedido("comando", {"comando": m.group(2).strip().strip("«»\"'`"), "donde": donde})
    m = re.match(r"^\s*(/detener|det[eé]n\w*|mata|termina|para el comando)\s+(.+?)\s*$", original, flags=re.I)
    if m:
        return Pedido("detener", {"comando": m.group(2).strip().strip("«»\"'`")})
    return None


def pedido_apps(original: str, t: str) -> Pedido | None:
    """«qué apps tengo abiertas», «qué está consumiendo más», «cierra pycharm»."""
    m = re.match(r"^\s*(/cerrar|cierra\w*|cerrar|sal\w* de)\s+(la\s+app\s+|la\s+aplicacion\s+|el\s+|la\s+)?(.+?)\s*$",
                 normalizar(original))
    if m:
        return Pedido("cerrar", {"app": m.group(3)})
    if t.startswith("/apps") or re.search(r"\b(apps|aplicaciones|programas)\b", t):
        return Pedido("apps")
    if t.startswith(("/consumo", "/recursos")) or re.search(r"\b(consum\w*|recursos|gasta\w*)\b", t):
        return Pedido("consumo")
    return None


def interpretar(texto: str) -> Pedido:
    original = quitar_saludo(texto)
    t = normalizar(original)
    if t.startswith("/claude") or re.search(r"\bque (haces|estas haciendo|dijiste|hiciste)\b", t) or \
            re.search(r"\bcomo va claude\b", t):
        return Pedido("claude")
    m = re.match(r"^/?avisos?(?: de | |_)claude\s*(on|off|si|no|activa\w*|apaga\w*|silencia\w*)?$", t)
    if m:
        valor = m.group(1) or ""
        return Pedido("avisos", {"activar": None if not valor else valor in ("on", "si") or valor.startswith("activa")})
    login = pedido_login(t)
    if login:
        return login
    musica = pedido_musica(t)
    if musica:
        return musica
    comando = pedido_comando(original, t)
    if comando:
        return comando
    if t in ("/start", "/ayuda", "ayuda", "") or t.startswith("/help"):
        return Pedido("ayuda")
    if t.startswith("/perfiles") or re.search(r"\bperfiles\b", t):
        return Pedido("perfiles")
    if t.startswith("/volumen"):
        return pedido_volumen("volumen " + t[len("/volumen"):]) or Pedido("ayuda")
    volumen = pedido_volumen(t)
    if volumen:
        return volumen
    servicio = pedido_servicio(t)
    if servicio:
        return servicio
    app = pedido_apps(original, t)
    if app:
        return app
    if t.startswith("/spotify"):
        return Pedido("spotify", {"consulta": t[len("/spotify"):].strip()})
    if "spotify" in t or re.search(VERBOS_MUSICA, t):
        return Pedido("spotify", {"consulta": consulta_musica(t)})
    return Pedido("ayuda")
