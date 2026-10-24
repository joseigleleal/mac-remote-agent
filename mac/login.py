"""Volver a iniciar sesión en una pestaña que quedó en la página de login (sesión vencida), con datos del .env.

Cada sitio se define en .env (ver .env.example):
    LOGIN_SITIOS=correo                       nombres de los sitios
    LOGIN_CORREO_PERFIL=personal              apodo o carpeta del perfil de Chrome
    LOGIN_CORREO_DOMINIOS=accounts.google.com dominio(s) de la página de login, separados por coma
    LOGIN_CORREO_USUARIO=                     vacío si la página ya trae el usuario puesto
    LOGIN_CORREO_CLAVE=
    LOGIN_CORREO_INICIO=                      opcional: dirección por la que se entra; si está, el bot carga un login
                                              nuevo antes de rellenar (hay páginas de login que vencen a los minutos)

El bot busca en ese perfil una pestaña que esté en uno de esos dominios, rellena los campos visibles (usuario si
está vacío, contraseña) y pulsa el botón de continuar; en logins de dos pasos (correo → contraseña) repite. Si queda
en un segundo factor o un captcha, lo dice y no intenta saltarlo. Un paso sin campos con botón de continuar (Google:
«confirma que eres tú») se pulsa.
Para guardar los datos sin editor (los editores de texto a veces «corrigen» lo que se escribe):
    python -m mac.login --guardar <sitio>     pregunta usuario y clave (la clave sin mostrarla) y los escribe en .env

La contraseña nunca va a Telegram ni al log, ni como argumento de un proceso (se ve en `ps`): viaja a Chrome dentro
del script que osascript lee por la entrada estándar.
"""
import argparse
import getpass
import json
import re

from mac import chrome
from mac.config import ROOT, alias_perfiles, env, lista

# Rellena y envía. Usa el setter nativo y dispara input/change: las páginas hechas con React u otros frameworks no
# ven un valor puesto con `campo.value = …`.
JS_LLENAR = """(function (u, c) {
  function visible(e) { return e && e.offsetParent !== null && !e.disabled && !e.readOnly; }
  function poner(e, v) {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(e, v);
    e.dispatchEvent(new Event("input", {bubbles: true}));
    e.dispatchEvent(new Event("change", {bubbles: true}));
  }
  var todos = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)).filter(visible); };
  var clave = todos('input[type="password"]')[0];
  var usuario = todos('input[type="email"], input[type="text"], input:not([type])')[0];
  var hecho = [];
  if (u && usuario && !usuario.value) { poner(usuario, u); hecho.push("usuario"); }
  if (clave) { poner(clave, c); hecho.push("clave"); }
  var boton = todos('button, input[type="submit"], [role="button"]').filter(function (b) {
    return /siguiente|next|iniciar|acceder|entrar|login|continuar|sign in|identif|aceptar/i.test(
      (b.innerText || b.value || "") + " " + (b.id || ""));
  })[0];
  if (!hecho.length) {  // paso sin campos (ej. Google «confirma que eres tú»): solo se pulsa continuar
    if (boton) { boton.click(); return "continuar"; }
    return "sin-campos";
  }
  if (boton) { boton.click(); }
  else { var f = (clave || usuario).form; if (f) { f.requestSubmit ? f.requestSubmit() : f.submit(); } }
  return hecho.join("+");
})(%s, %s)"""


def sitios() -> dict[str, dict]:
    """Sitios configurados: {nombre: {perfil, dominios, usuario, clave}} (solo los que tienen perfil y clave)."""
    salida = {}
    for nombre in lista("LOGIN_SITIOS"):
        p = f"LOGIN_{nombre.upper()}_"
        datos = {"perfil": env(p + "PERFIL"), "dominios": lista(p + "DOMINIOS"),
                 "usuario": env(p + "USUARIO") or "", "clave": env(p + "CLAVE"), "inicio": env(p + "INICIO")}
        if datos["perfil"] and datos["dominios"] and datos["clave"]:
            salida[nombre.lower()] = datos
    return salida


def carpeta(perfil: str) -> str:
    return alias_perfiles().get(perfil.lower(), perfil)


def pestana_de_login(sitio: dict) -> tuple[int, int] | None:
    for dominio in sitio["dominios"]:
        p = chrome.buscar_pestana(carpeta(sitio["perfil"]), dominio)
        if p:
            return p
    return None


def en_login(pestana: tuple[int, int], sitio: dict) -> bool:
    """¿Esa pestaña sigue en una página de login del sitio?"""
    try:
        url = chrome.url(*pestana)
    except chrome.ChromeError:
        return True  # cambiando de página: todavía no se sabe
    return any(d in url for d in sitio["dominios"])


def estado_pagina(pestana: tuple[int, int]) -> str:
    """Huella de la página: dirección + cuántos campos visibles de clave y de texto hay. Sirve para esperar a que un
    paso del login termine de cargar el siguiente."""
    try:
        return chrome.ejecutar_js(*pestana, """(function () {
          var v = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s))
            .filter(function (e) { return e.offsetParent !== null; }).length; };
          return location.pathname + "|" + v('input[type="password"]') + "|" + v('input[type="text"], input[type="email"]');
        })()""")
    except chrome.ChromeError:
        return ""  # la pestaña está cambiando de página


def reautenticar(nombre: str) -> str:
    """Rellena el login del sitio `nombre` si hay una pestaña esperándolo. Devuelve qué pasó (sin datos)."""
    sitio = sitios().get(nombre)
    if not sitio:
        return f"No tengo datos para «{nombre}». Configúralo en .env (LOGIN_SITIOS y LOGIN_{nombre.upper()}_…)."
    if not chrome.permitido(carpeta(sitio["perfil"])):
        return f"El perfil de «{nombre}» no está en CHROME_PERFILES_PERMITIDOS."
    pestana = pestana_de_login(sitio)
    if not pestana:
        return f"✅ {nombre}: no hay ninguna pestaña pidiendo iniciar sesión (la sesión sigue abierta)."
    from mac.spotify import esperar
    chrome.mostrar(*pestana)  # a la vista: Chrome frena las pestañas de fondo y algunos logins quedan «Cargando»
    if sitio["inicio"]:  # login nuevo: el que estaba abierto puede haber vencido
        chrome.ir(*pestana, sitio["inicio"])
        esperar(lambda: "|0|0" not in estado_pagina(pestana) and estado_pagina(pestana) != "", segundos=20, cada=1)
        pestana = pestana_de_login(sitio) or pestana
    for _ in range(5):  # logins por pasos: confirmar cuenta → «demuestra que eres tú» → correo → contraseña
        antes = estado_pagina(pestana)
        js = JS_LLENAR % (json.dumps(sitio["usuario"]), json.dumps(sitio["clave"]))
        hecho = chrome.ejecutar_js_privado(*pestana, js)
        if hecho == "sin-campos":
            break
        if "clave" in hecho:  # se envió la contraseña: o sale del login, o queda en otro paso (2FA, error)
            # se mira esta pestaña, no el perfil: otra pestaña de login del mismo sitio tarda en redirigirse sola
            if esperar(lambda: not en_login(pestana, sitio), segundos=15, cada=1):
                return f"🔓 {nombre}: sesión iniciada de nuevo."
            break
        # se pulsó continuar o se puso el usuario: esperar a que la página cambie de verdad
        esperar(lambda: estado_pagina(pestana) not in ("", antes), segundos=15, cada=1)
    if en_login(pestana, sitio):
        return (f"⚠️ {nombre}: rellené lo que pude, pero la pestaña sigue en el inicio de sesión. Puede pedir un "
                "segundo factor, un captcha o que la contraseña del .env esté desactualizada: míralo en la Mac.")
    return f"🔓 {nombre}: sesión iniciada de nuevo."


def valor_env(texto: str) -> str:
    """Entre comillas simples, python-dotenv lo toma literal (sin interpretar $, # ni barras). Si trae una comilla
    simple, va entre dobles con las comillas y barras escapadas."""
    if "'" not in texto:
        return f"'{texto}'"
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'


def guardar(nombre: str) -> None:
    """Pregunta usuario y clave en la terminal y los escribe en .env (crea las líneas si no existen)."""
    nombre = nombre.lower()
    archivo = ROOT / ".env"
    texto = archivo.read_text() if archivo.exists() else ""
    usuario = input(f"Usuario para «{nombre}» (Enter = vacío, si la página ya lo trae puesto): ").strip()
    clave = getpass.getpass(f"Clave para «{nombre}» (no se muestra): ")
    if clave != getpass.getpass("Repítela: "):
        raise SystemExit("No coinciden; no guardé nada.")
    for campo, valor in (("USUARIO", usuario), ("CLAVE", clave)):
        linea = f"LOGIN_{nombre.upper()}_{campo}={valor_env(valor) if valor else ''}"
        patron = re.compile(rf"^LOGIN_{nombre.upper()}_{campo}=.*$", re.M)
        texto = patron.sub(lambda _: linea, texto) if patron.search(texto) else texto.rstrip("\n") + "\n" + linea + "\n"
    archivo.write_text(texto)
    archivo.chmod(0o600)
    if nombre not in [s.lower() for s in lista("LOGIN_SITIOS")]:
        print(f"Ojo: «{nombre}» no está en LOGIN_SITIOS; agrégalo, junto con LOGIN_{nombre.upper()}_PERFIL y _DOMINIOS.")
    print(f"Guardado en .env (usuario {'con valor' if usuario else 'vacío'}, clave de {len(clave)} caracteres).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login con datos del .env")
    parser.add_argument("--guardar", metavar="SITIO", help="Pregunta usuario y clave y los guarda en .env")
    args = parser.parse_args()
    if args.guardar:
        guardar(args.guardar)
