"""Escribir un comando en una terminal visible, para verlo correr: la del IDE (PyCharm, IntelliJ) o iTerm.

- IDE de JetBrains: no tiene AppleScript propio, así que se simula el teclado (System Events). Exige darle a la app
  que corre el bot el permiso de **Accesibilidad**. Secuencia: traer el IDE al frente → Esc (foco al editor) →
  ⌥F12 (abre la terminal) → ⌘T (pestaña nueva: nunca se escribe en una terminal ocupada) → comando → Enter.
- iTerm: tiene AppleScript propio (pestaña nueva + `write text`); no necesita Accesibilidad.
Quién decide si el comando se puede ejecutar es `comandos.py` (lista permitida), no este módulo.
"""
import time

from mac.chrome import ChromeError, osascript

IDES = {"pycharm": "PyCharm", "intellij": "IntelliJ IDEA"}

TECLADO_IDE = '''on run argv
set app_ide to item 1 of argv
set comando to item 2 of argv
tell application app_ide to activate
delay 0.8
tell application "System Events"
  key code 53 -- Esc: foco al editor (si la terminal ya tenía el foco, ⌥F12 la cerraría)
  delay 0.3
  key code 111 using {option down} -- ⌥F12: abre la terminal
  delay 1.0
  keystroke "t" using {command down} -- ⌘T: pestaña nueva
  delay 1.5
  keystroke comando
  delay 0.2
  key code 36 -- Enter
end tell
end run'''

ITERM = '''on run argv
tell application "iTerm"
  activate
  if (count of windows) = 0 then
    create window with default profile
  else
    tell current window to create tab with default profile
  end if
  tell current session of current window to write text (item 1 of argv)
end tell
end run'''


def escribir(donde: str, comando: str) -> str:
    """Escribe y ejecuta `comando` en una pestaña nueva de la terminal de `donde` (pycharm, intellij o iterm)."""
    try:
        if donde in IDES:
            osascript(TECLADO_IDE, IDES[donde], comando)
            nombre = IDES[donde]
        elif donde == "iterm":
            osascript(ITERM, comando)
            nombre = "iTerm"
        else:
            return f"No sé escribir en «{donde}». Puedo en: {', '.join([*IDES, 'iterm'])}."
    except ChromeError as e:
        if "1002" in str(e) or "1719" in str(e) or "asistencia" in str(e) or "assistive" in str(e).lower():
            return ("macOS no deja que el bot use el teclado. Dale permiso en Ajustes → Privacidad y seguridad → "
                    "Accesibilidad a la app que corre el bot (Python) y vuelve a pedírmelo.")
        return f"⚠️ {e}"
    time.sleep(0.5)
    return f"⌨️ Escribí «{comando}» en una pestaña nueva de la terminal de {nombre} y le di Enter."
