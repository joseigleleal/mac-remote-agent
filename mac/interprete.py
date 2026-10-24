"""Del texto que llega por Telegram a una acción de una lista cerrada. Nunca se ejecuta el texto: solo se busca qué
acción conocida pide y con qué datos. Son reglas simples en español; lo que no encaja, se responde con la ayuda."""
import re
import unicodedata
from dataclasses import dataclass, field

ACCIONES = ("perfiles", "ayuda")


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


def interpretar(texto: str) -> Pedido:
    t = normalizar(quitar_saludo(texto))
    if t in ("/start", "/ayuda", "ayuda", "") or t.startswith("/help"):
        return Pedido("ayuda")
    if t.startswith("/perfiles") or re.search(r"\bperfiles\b", t):
        return Pedido("perfiles")
    return Pedido("ayuda")
