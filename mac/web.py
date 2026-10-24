"""Abrir páginas en un perfil de Chrome y buscar dentro de la que se abrió (la conversación sigue en esa pestaña).

- Sitios conocidos por nombre («youtube», «gmail»…), con su dirección de búsqueda cuando la tienen.
- Otra cosa con punto («elpais.com») se abre como dirección; sin punto, se busca en Google.
- «busca X» en un sitio sin dirección de búsqueda: rellena el buscador visible de la página y lo envía.
"""
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

from mac import chrome
from mac.interprete import normalizar

# nombre → (dirección, plantilla de búsqueda o None)
SITIOS = {
    "youtube": ("https://www.youtube.com/", "https://www.youtube.com/results?search_query={}"),
    "google": ("https://www.google.com/", "https://www.google.com/search?q={}"),
    "gmail": ("https://mail.google.com/", "https://mail.google.com/mail/u/0/#search/{}"),
    "drive": ("https://drive.google.com/", "https://drive.google.com/drive/search?q={}"),
    "maps": ("https://www.google.com/maps/", "https://www.google.com/maps/search/{}"),
    "github": ("https://github.com/", "https://github.com/search?q={}"),
    "linkedin": ("https://www.linkedin.com/", "https://www.linkedin.com/search/results/all/?keywords={}"),
    "wikipedia": ("https://es.wikipedia.org/", "https://es.wikipedia.org/w/index.php?search={}"),
    "amazon": ("https://www.amazon.es/", "https://www.amazon.es/s?k={}"),
    "netflix": ("https://www.netflix.com/", "https://www.netflix.com/search?q={}"),
    "whatsapp": ("https://web.whatsapp.com/", None),
    "spotify": ("https://open.spotify.com/", "https://open.spotify.com/search/{}"),
    "chatgpt": ("https://chatgpt.com/", None),
    "claude": ("https://claude.ai/", None),
}
ALIAS = {"yt": "youtube", "correo": "gmail", "mapas": "maps", "google maps": "maps", "wiki": "wikipedia"}

# Rellena el buscador visible de la página (input de búsqueda) y lo envía.
JS_BUSCADOR = """(function (q) {
  var visibles = Array.prototype.slice.call(document.querySelectorAll(
    'input[type="search"], input[name="q"], input[name="query"], input[name="search"], input[aria-label*="earch"], ' +
    'input[aria-label*="usca"], input[placeholder*="usca"], input[placeholder*="earch"]'))
    .filter(function (e) { return e.offsetParent !== null && !e.disabled; });
  var c = visibles[0];
  if (!c) return "sin-buscador";
  c.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(c, q);
  c.dispatchEvent(new Event("input", {bubbles: true}));
  if (c.form) { c.form.requestSubmit ? c.form.requestSubmit() : c.form.submit(); }
  else { ["keydown", "keypress", "keyup"].forEach(function (t) {
    c.dispatchEvent(new KeyboardEvent(t, {key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true})); }); }
  return "ok";
})(%s)"""

# YouTube: abre el primer video de los resultados.
JS_YOUTUBE_PRIMERO = """(function () {
  var v = Array.prototype.slice.call(document.querySelectorAll('ytd-video-renderer a#video-title, a#video-title'))
    .filter(function (a) { return a.offsetParent !== null && a.href; })[0];
  if (!v) return "";
  location.href = v.href;
  return v.title || v.textContent.trim();
})()"""


@dataclass
class Contexto:
    """La pestaña con la que se está conversando («busca…» va ahí)."""
    carpeta: str
    ventana: int
    pestana: int
    sitio: str      # nombre conocido o dominio
    desde: float

    def vigente(self) -> bool:
        return time.time() - self.desde < 30 * 60


def sitio_conocido(texto: str) -> str | None:
    t = normalizar(texto).strip()
    t = ALIAS.get(t, t)
    return t if t in SITIOS else None


def direccion(texto: str) -> tuple[str, str]:
    """(url, nombre del sitio) para lo que se pidió abrir."""
    conocido = sitio_conocido(texto)
    if conocido:
        return SITIOS[conocido][0], conocido
    t = texto.strip()
    if re.match(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", t, re.I) or t.startswith("http"):
        url = t if t.startswith("http") else "https://" + t
        return url, urlparse(url).netloc.removeprefix("www.")
    return SITIOS["google"][1].format(quote_plus(t)), "google"


def abrir(carpeta: str, texto: str) -> tuple[str, Contexto | None]:
    """Abre la página en ese perfil (reutiliza una pestaña del mismo sitio si ya existe) y la trae al frente."""
    url, sitio = direccion(texto)
    dominio = urlparse(url).netloc.removeprefix("www.")
    pestana = chrome.buscar_pestana(carpeta, dominio)
    if pestana:
        chrome.ir(*pestana, url)
        como = "en la pestaña que ya tenías"
    else:
        chrome.abrir(carpeta, url)
        from mac.spotify import esperar
        pestana = esperar(lambda: chrome.buscar_pestana_tolerante(carpeta, dominio), segundos=15)
        como = "en una pestaña nueva"
    if not pestana:
        return f"Abrí {sitio}, pero no encuentro la pestaña para seguir desde ahí.", None
    chrome.mostrar(*pestana)
    return f"🌐 Abrí {sitio} {como}. Ahora puedes decirme «busca …».", Contexto(carpeta, *pestana, sitio, time.time())


def buscar(ctx: Contexto, consulta: str) -> str:
    """Busca dentro del sitio del contexto: por su dirección de búsqueda o con el buscador de la página."""
    plantilla = SITIOS.get(ctx.sitio, (None, None))[1]
    if plantilla:
        chrome.ir(ctx.ventana, ctx.pestana, plantilla.format(quote_plus(consulta)))
    else:
        if chrome.ejecutar_js(ctx.ventana, ctx.pestana, JS_BUSCADOR % json.dumps(consulta)) != "ok":
            return f"No encontré un buscador en {ctx.sitio}. Dime «abre google» si quieres buscarlo allá."
    chrome.mostrar(ctx.ventana, ctx.pestana)
    ctx.desde = time.time()
    extra = " Dime «pon el primero» para reproducirlo." if ctx.sitio == "youtube" else ""
    return f"🔎 Busqué «{consulta}» en {ctx.sitio}.{extra}"


def primero(ctx: Contexto) -> str:
    if ctx.sitio != "youtube":
        return "«Pon el primero» por ahora funciona en YouTube."
    from mac.spotify import esperar
    titulo = esperar(lambda: chrome.ejecutar_js(ctx.ventana, ctx.pestana, JS_YOUTUBE_PRIMERO), segundos=8)
    ctx.desde = time.time()
    return f"▶️ {titulo}" if titulo else "No encontré videos en la página (¿buscaste algo antes?)."
