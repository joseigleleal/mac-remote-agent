"""El agente: cuando ninguna regla entiende el pedido, un modelo local (Ollama) decide qué herramientas usar.

- Las herramientas son las mismas acciones de la lista cerrada (`interprete.ACCIONES`): el modelo solo puede pedir
  una acción conocida con sus datos; el bot la ejecuta igual que si la hubiera entendido una regla, con los mismos
  controles (perfiles permitidos, comandos de la lista, botones para confirmar lo delicado).
- Ciclo: el modelo pide una herramienta → el bot la ejecuta → el resultado vuelve al modelo → decide la siguiente o
  responde. Máximo MAX_PASOS. Si una herramienta pregunta con botones (perfil, cerrar una app), el ciclo termina ahí:
  tu toque sigue el camino de siempre.
- Memoria corta: los últimos intercambios de los últimos 30 min, para entender «y ahora súbele».
- El modelo se descarga de la memoria a los AGENTE_KEEP_ALIVE (1 min) sin uso: en espera no ocupa RAM.
"""
import json
import time
from dataclasses import dataclass, field

import requests

from mac.config import env
from mac.interprete import Pedido, normalizar

MAX_PASOS = 5
MEMORIA_MIN = 30
MEMORIA_TURNOS = 6

SISTEMA = """Eres el agente que maneja la Mac de tu usuario por Telegram. Respondes en español latino neutro, breve.
Reglas:
- Solo actúas con las herramientas. Úsalas para lo que te pidan, una tras otra si hace falta, mirando el resultado.
- Nunca inventes datos: no digas qué hay en una página, un correo o una app; solo lo que diga el resultado de una
  herramienta. Nunca rellenes un parámetro opcional que el usuario no dijo (perfil, sitio…): déjalo vacío.
- Si pide cerrar una app, usa cerrar_app directamente: ella misma le pide confirmación con botones.
- Si pregunta cómo responder un mensaje que le mandaron, usa sugerir_respuesta: no lo redactes tú.
- Si algo no se puede con tus herramientas, dilo en una frase y sugiere lo más parecido que sí puedes hacer.
- Si una herramienta dice que preguntó con botones, termina: el usuario elige ahí.
- Los resultados de las herramientas ya le llegan al usuario: al terminar, responde solo «listo»."""


def _h(nombre: str, descripcion: str, **parametros) -> dict:
    """Esquema de una herramienta para Ollama. parametros: nombre → (tipo, descripción[, valores permitidos])."""
    props, requeridos = {}, []
    for p, (tipo, desc, *enum) in parametros.items():
        opcional = desc.startswith("(opcional)")
        props[p] = {"type": tipo, "description": desc, **({"enum": enum[0]} if enum else {})}
        if not opcional:
            requeridos.append(p)
    return {"type": "function", "function": {"name": nombre, "description": descripcion,
                                             "parameters": {"type": "object", "properties": props,
                                                            "required": requeridos}}}


PERFIL = ("string", "(opcional) perfil de Chrome: su apodo o nombre (ej. personal). Vacío si no lo dijo")
HERRAMIENTAS = [
    _h("abrir_pagina", "Abre una página en Chrome: un sitio conocido (youtube, gmail, maps…), una dirección o, si no, "
       "la busca en Google. Queda como la página de la conversación.", sitio=("string", "sitio o dirección"),
       perfil=PERFIL),
    _h("buscar_en_pagina", "Busca algo dentro de la página abierta en la conversación (ej. en YouTube).",
       consulta=("string", "qué buscar")),
    _h("poner_primero", "En YouTube, reproduce el primer video de los resultados."),
    _h("spotify_reproducir", "Busca en Spotify (web) y reproduce el primer resultado.",
       consulta=("string", "canción, artista o lista"), perfil=PERFIL),
    _h("controlar_musica", "Controla la música que suena en Spotify.",
       accion=("string", "qué hacer", ["pausar", "seguir", "siguiente", "anterior"])),
    _h("volumen", "Ve o cambia el volumen de la Mac.",
       modo=("string", "qué hacer", ["ver", "subir", "bajar", "fijar", "silenciar", "activar"]),
       valor=("integer", "(opcional) cuánto: puntos para subir/bajar, o el nivel 0-100 para fijar")),
    _h("ver_apps", "Lista las apps abiertas y cuánto consume la Mac."),
    _h("consumo", "Qué apps están consumiendo más memoria y CPU."),
    _h("cerrar_app", "Pide confirmación con botones para cerrar una app.", app=("string", "nombre de la app")),
    _h("perfiles_chrome", "Qué perfiles de Chrome hay abiertos."),
    _h("estado_bot", "Cuánto consume el bot y cómo está la Mac."),
    _h("comandos_permitidos", "Lista los comandos permitidos y los que están corriendo."),
    _h("ejecutar_comando", "Ejecuta un comando SOLO si está en la lista permitida (si no, se niega solo).",
       comando=("string", "el comando exacto de la lista"),
       donde=("string", "(opcional) terminal visible", ["pycharm", "intellij", "iterm"])),
    _h("detener_comando", "Detiene un comando que lanzó el bot.", comando=("string", "el comando")),
    _h("iniciar_sesion", "Vuelve a iniciar sesión en un sitio configurado (sesión vencida).",
       sitio=("string", "(opcional) nombre del sitio")),
    _h("que_hace_claude", "Qué está haciendo la sesión de Claude Code (última acción y mensaje)."),
    _h("sugerir_respuesta", "Sugiere cómo respondería el usuario un mensaje que le mandaron, con su estilo.",
       mensaje=("string", "el mensaje que le mandaron"), chat=("string", "(opcional) quién se lo mandó")),
    _h("chats_whatsapp", "Lista los chats de WhatsApp con más mensajes del usuario."),
    _h("chequeo_mac", "Revisa que la Mac y el bot estén bien: Ollama, permisos de macOS, eco, disco y sesiones."),
    _h("ver_rutinas", "Lista las rutinas programadas (pedidos que el bot hace solo a una hora)."),
]
# herramienta → acción de la lista cerrada (y cómo pasan los datos)
ACCION = {"abrir_pagina": "abrir", "buscar_en_pagina": "buscar", "poner_primero": "primero",
          "spotify_reproducir": "spotify", "controlar_musica": "musica", "volumen": "volumen", "ver_apps": "apps",
          "consumo": "consumo", "cerrar_app": "cerrar", "perfiles_chrome": "perfiles", "estado_bot": "estado",
          "comandos_permitidos": "comandos", "ejecutar_comando": "comando", "detener_comando": "detener",
          "iniciar_sesion": "login", "que_hace_claude": "claude", "sugerir_respuesta": "eco",
          "chats_whatsapp": "wa_chats", "chequeo_mac": "chequeo", "ver_rutinas": "rutinas"}


def pedido(nombre: str, argumentos: dict, texto: str = "") -> Pedido | None:
    """La herramienta pedida, como Pedido de la lista cerrada (None si no existe). Un perfil que no está en lo que
    escribiste se descarta: el modelo a veces lo rellena solo, y entonces el bot pregunta con botones."""
    accion = ACCION.get(nombre)
    if not accion:
        return None
    datos = {k: v for k, v in (argumentos or {}).items() if v not in (None, "")}
    if datos.get("perfil") and normalizar(str(datos["perfil"])) not in normalizar(texto):
        datos.pop("perfil")
    if accion == "eco":
        datos.setdefault("chat", "")
    if accion == "abrir":
        datos.setdefault("perfil", "")
    if accion == "volumen" and datos.get("modo") not in ("ver", "subir", "bajar", "fijar", "silenciar", "activar"):
        datos["modo"] = "ver"
    return Pedido(accion, datos)


@dataclass
class Memoria:
    turnos: list = field(default_factory=list)  # (cuándo, rol, texto)

    def mensajes(self) -> list[dict]:
        limite = time.time() - MEMORIA_MIN * 60
        self.turnos = [t for t in self.turnos if t[0] >= limite][-MEMORIA_TURNOS * 2:]
        return [{"role": rol, "content": texto} for _, rol, texto in self.turnos]

    def agregar(self, rol: str, texto: str) -> None:
        self.turnos.append((time.time(), rol, texto[:1500]))


def modelo() -> str:
    return env("AGENTE_MODELO", "qwen3:8b") or ""


def chat_ollama(mensajes: list[dict]) -> dict:
    r = requests.post(f"{env('OLLAMA_URL', 'http://localhost:11434')}/api/chat", timeout=180, json={
        "model": modelo(), "messages": mensajes, "tools": HERRAMIENTAS, "stream": False, "think": False,
        "keep_alive": env("AGENTE_KEEP_ALIVE", "1m"), "options": {"temperature": 0.2}})
    r.raise_for_status()
    return r.json()["message"]


def atender(texto: str, ejecutar, memoria: Memoria, llamar=chat_ollama) -> str | None:
    """Ciclo del agente. `ejecutar(pedido) -> (resultado, pregunto_con_botones)` hace la acción con los controles del
    bot. Devuelve el texto final para el usuario: solo si no usó herramientas (sus resultados ya te llegaron, y un
    resumen del modelo solo agregaría la chance de inventar). None si terminó con botones o ya está todo dicho."""
    mensajes = [{"role": "system", "content": SISTEMA}, *memoria.mensajes(), {"role": "user", "content": texto}]
    memoria.agregar("user", texto)
    usadas = 0
    for _ in range(MAX_PASOS):
        respuesta = llamar(mensajes)
        llamadas = respuesta.get("tool_calls") or []
        if not llamadas:
            final = (respuesta.get("content") or "").strip()
            memoria.agregar("assistant", final)
            return None if usadas else final
        mensajes.append({"role": "assistant", "content": respuesta.get("content") or "", "tool_calls": llamadas})
        for llamada in llamadas:
            f = llamada.get("function") or {}
            args = f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            p = pedido(f.get("name", ""), args, texto)
            usadas += 1
            if p is None:
                resultado, botones = f"No existe la herramienta «{f.get('name')}».", False
            else:
                resultado, botones = ejecutar(p)
            memoria.agregar("assistant", f"[{f.get('name')}] {resultado}")
            if botones:
                return None
            mensajes.append({"role": "tool", "content": resultado or "hecho", "tool_name": f.get("name", "")})
    return "Llegué al máximo de pasos; dime cómo sigo."


def cargado() -> str | None:
    """Modelos que Ollama tiene en memoria ahora, con su tamaño (para «cuánto consumes»)."""
    try:
        r = requests.get(f"{env('OLLAMA_URL', 'http://localhost:11434')}/api/ps", timeout=3)
        modelos = r.json().get("models") or []
    except (requests.RequestException, ValueError):
        return None
    return ", ".join(f"{m['name']} ({m.get('size', 0) / 1024 ** 3:.1f} GB)" for m in modelos) or "ninguno (0 MB)"
