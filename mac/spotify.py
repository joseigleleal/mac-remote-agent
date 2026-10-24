"""Spotify web (open.spotify.com) en un perfil de Chrome: buscar y reproducir el primer resultado.

Si el perfil ya tiene una pestaña de Spotify, la usa: cambia a la búsqueda sin recargar la página (la página sigue
"tocada" por la persona y Chrome la deja reproducir). Si no, abre la búsqueda en ese perfil.
Los selectores (`data-testid`) son los de la web de Spotify y pueden cambiar con sus actualizaciones.
"""
import json
import re
import time
from urllib.parse import quote

from mac import chrome

DOMINIO = "open.spotify.com"

# Cambia de página como lo hace la propia web (sin recargar).
JS_BUSCAR = """(function (q) {
  history.pushState({}, "", "/search/" + encodeURIComponent(q));
  window.dispatchEvent(new PopStateEvent("popstate", {state: {}}));
  return location.pathname;
})(%s)"""

# Botón de play del primer resultado. Solo <button>: Spotify también marca con "play-button" el contenedor (un div)
# que lo envuelve, y un clic ahí no hace nada.
JS_PLAY = """(function () {
  var b = document.querySelector('main button[data-testid="play-button"]');
  if (!b) return "sin-boton";
  b.click();
  return "ok";
})()"""

# Título del primer resultado con botón de play: sirve para saber cuándo la búsqueda nueva ya reemplazó a la vieja.
JS_PRIMERO = """(function () {
  var f = document.querySelector('main button[data-testid="play-button"]');
  for (var i = 0; i < 8 && f && !f.querySelector('[data-testid="title"]'); i++) f = f.parentElement;
  var t = f && f.querySelector('[data-testid="title"]');
  return t ? t.innerText : "";
})()"""

# Qué suena: el botón de play/pausa de la barra inferior y la canción del widget.
JS_ESTADO = """(function () {
  var b = document.querySelector('[data-testid="control-button-playpause"]');
  var w = document.querySelector('[data-testid^="now-playing-widget"]');  // "-v2" desde 2026
  return JSON.stringify({boton: b ? b.getAttribute("aria-label") : "",
                         cancion: w ? w.getAttribute("aria-label") : ""});
})()"""

PAUSA = ("pausa", "pausar", "pause")  # si el botón ofrece pausar, está sonando


def url_busqueda(consulta: str) -> str:
    return f"https://{DOMINIO}/search/{quote(consulta)}"


def esperar(funcion, segundos: float = 12, cada: float = 1):
    """Repite `funcion` hasta que devuelva algo verdadero o se acabe el tiempo."""
    limite = time.monotonic() + segundos
    while True:
        resultado = funcion()
        if resultado or time.monotonic() > limite:
            return resultado
        time.sleep(cada)


def reproducir(carpeta: str, consulta: str) -> str:
    """Busca `consulta` en Spotify en ese perfil y reproduce el primer resultado. Devuelve qué pasó, para contarlo."""
    pestana = chrome.buscar_pestana(carpeta, DOMINIO)
    if pestana:
        previo = chrome.ejecutar_js(*pestana, JS_PRIMERO)
        chrome.ejecutar_js(*pestana, JS_BUSCAR % json.dumps(consulta))
        # La página cambia de ruta al instante pero los resultados tardan: hasta que no cambie el primero, el botón
        # de play sigue siendo el de la búsqueda anterior.
        esperar(lambda: (lambda t: t and t != previo)(chrome.ejecutar_js(*pestana, JS_PRIMERO)), segundos=10)
        abierta = "en la pestaña de Spotify que ya tenías"
    else:
        chrome.abrir(carpeta, url_busqueda(consulta))
        pestana = esperar(lambda: chrome.buscar_pestana(carpeta, DOMINIO), segundos=15)
        if not pestana:
            return "Abrí Spotify, pero no encuentro la pestaña para darle play. Tócalo tú, por favor."
        abierta = "en una pestaña nueva"
    antes = sonando(pestana)
    clic = esperar(lambda: chrome.ejecutar_js(*pestana, JS_PLAY) == "ok")
    if not clic:
        return f"Busqué «{consulta}» {abierta}, pero no encontré el botón de play (¿la página cambió o no cargó?)."
    # El widget tarda un momento en cambiar de canción: se espera a que suene algo distinto de lo de antes.
    estado = esperar(lambda: (lambda e: e if e and e != antes else "")(sonando(pestana)), segundos=8)
    if estado:
        return f"▶️ {estado} ({abierta})."
    estado = sonando(pestana)
    if estado == antes and antes:
        return f"Busqué «{consulta}» {abierta}, pero sigue sonando {estado}: no pude cambiar de canción."
    if estado:
        return f"▶️ {estado} ({abierta})."
    return (f"Le di play a «{consulta}» {abierta}, pero no veo que suene. Si la pestaña es nueva, Chrome puede "
            "pedir que la toques una vez antes de dejarla reproducir.")


def sonando(pestana: tuple[int, int]) -> str:
    """La canción que suena en esa pestaña, o "" si está en pausa."""
    try:
        estado = json.loads(chrome.ejecutar_js(*pestana, JS_ESTADO) or "{}")
    except ValueError:
        return ""
    if not any(p in (estado.get("boton") or "").lower() for p in PAUSA):
        return ""
    cancion = re.sub(r"^[^:]*:\s*", "", estado.get("cancion") or "")  # quita «Estás escuchando:»
    return cancion or "Sonando"
