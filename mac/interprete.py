"""Del texto que llega por Telegram a una acción de una lista cerrada. Nunca se ejecuta el texto: solo se busca qué
acción conocida pide y con qué datos. Son reglas simples en español; lo que no encaja, se responde con la ayuda."""
import re
import unicodedata
from dataclasses import dataclass, field

ACCIONES = ("perfiles", "volumen", "spotify", "ayuda")

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
    if re.search(r"\b(silencia\w*|mute\w*|mutea\w*|silencio)\b", t):
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


def interpretar(texto: str) -> Pedido:
    t = normalizar(quitar_saludo(texto))
    if t in ("/start", "/ayuda", "ayuda", "") or t.startswith("/help"):
        return Pedido("ayuda")
    if t.startswith("/perfiles") or re.search(r"\bperfiles\b", t):
        return Pedido("perfiles")
    if t.startswith("/volumen"):
        return pedido_volumen("volumen " + t[len("/volumen"):]) or Pedido("ayuda")
    volumen = pedido_volumen(t)
    if volumen:
        return volumen
    if t.startswith("/spotify"):
        return Pedido("spotify", {"consulta": t[len("/spotify"):].strip()})
    if "spotify" in t or re.search(VERBOS_MUSICA, t):
        return Pedido("spotify", {"consulta": consulta_musica(t)})
    return Pedido("ayuda")
