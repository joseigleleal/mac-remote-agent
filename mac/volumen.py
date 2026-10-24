"""Volumen de salida de la Mac (0-100) y silencio, con AppleScript."""
from mac.chrome import osascript

PASO = 10  # cuánto sube o baja «sube el volumen» si no se dice un número


def estado() -> tuple[int, bool]:
    """(volumen 0-100, silenciado)."""
    nivel, mudo = osascript('''set v to get volume settings
return ((output volume of v) as text) & "," & ((output muted of v) as text)''').split(",")
    return int(nivel), mudo.strip() == "true"


def ajustar(modo: str, valor: int | None = None) -> str:
    """modo: fijar (valor) · subir / bajar (valor o PASO) · silenciar · activar. Devuelve cómo quedó."""
    nivel, _ = estado()
    if modo == "silenciar":
        osascript("set volume with output muted")
    elif modo == "activar":
        osascript("set volume without output muted")
    else:
        if modo == "fijar":
            nuevo = valor or 0
        elif modo == "subir":
            nuevo = nivel + (valor or PASO)
        else:
            nuevo = nivel - (valor or PASO)
        nuevo = max(0, min(100, nuevo))
        osascript("on run argv\nset volume output volume (item 1 of argv as integer) without output muted\nend run",
                  str(nuevo))
    nivel, mudo = estado()
    return "🔇 Silenciado" if mudo else f"🔊 Volumen: {nivel} %"
