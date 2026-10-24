"""Chats de la app de WhatsApp de la Mac, para que un agente aprenda cómo escribes (tu «clon» o eco).

Lee la base local de la app (ChatStorage.sqlite, solo lectura y sobre una copia temporal: WhatsApp la sigue usando).
- Solo chats uno a uno (ZSESSIONTYPE 0): sin grupos, estados ni canales.
- Excluidos: los que nombres en data/whatsapp/excluidos.json («excluye <nombre>» en el bot) y en WHATSAPP_EXCLUIR.
- Exporta pares (contexto, respuesta): tu mensaje y, como contexto, solo el mensaje anterior de la otra persona.
  Teléfonos, correos y enlaces se reemplazan. Nada sale de la Mac: queda en data/whatsapp/ (fuera de git).

    python -m mac.whatsapp chats              # tus chats con más mensajes tuyos
    python -m mac.whatsapp exporta <nombre>   # o «exporta 5» para 5 al azar
"""
import argparse
import json
import random
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from mac.config import DATA_DIR, lista
from mac.interprete import normalizar

BASE = Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
CARPETA = DATA_DIR / "whatsapp"
EXCLUIDOS = CARPETA / "excluidos.json"
EPOCA_APPLE = datetime(2001, 1, 1)  # las fechas de la base son segundos desde 2001
LIMPIAR = [(re.compile(r"https?://\S+"), "<enlace>"), (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<correo>"),
           (re.compile(r"\+?\d[\d\s-]{7,}\d"), "<teléfono>")]


class WhatsAppError(Exception):
    pass


class Conexion(sqlite3.Connection):
    """Conexión que recuerda su carpeta temporal, para borrar la copia de la base al cerrar."""
    tmp: Path


def conectar() -> sqlite3.Connection:
    """Copia la base (con su -wal) a una carpeta temporal y la abre en solo lectura."""
    if not BASE.exists():
        raise WhatsAppError("No encuentro la base de la app de WhatsApp en esta Mac (¿está instalada y con sesión?).")
    tmp = Path(tempfile.mkdtemp(prefix="wa-"))
    try:
        for archivo in BASE.parent.glob(BASE.name + "*"):
            shutil.copy2(archivo, tmp / archivo.name)
    except PermissionError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise WhatsAppError("macOS no deja leer los datos de WhatsApp. Permítelo en Ajustes → Privacidad y seguridad "
                            "→ Acceso total al disco (o «Datos de otras apps») para la app que corre el bot.")
    con = sqlite3.connect(f"file:{tmp / BASE.name}?mode=ro", uri=True, factory=Conexion)
    con.row_factory = sqlite3.Row
    con.tmp = tmp  # para borrarla al cerrar
    return con


def cerrar(con: Conexion) -> None:
    con.close()
    shutil.rmtree(con.tmp, ignore_errors=True)


def excluidos() -> list[str]:
    try:
        propios = json.loads(EXCLUIDOS.read_text())
    except (OSError, ValueError):
        propios = []
    return [normalizar(n) for n in propios + lista("WHATSAPP_EXCLUIR")]


def excluir(nombre: str) -> list[str]:
    CARPETA.mkdir(parents=True, exist_ok=True)
    try:
        actuales = json.loads(EXCLUIDOS.read_text())
    except (OSError, ValueError):
        actuales = []
    if nombre not in actuales:
        actuales.append(nombre)
    EXCLUIDOS.write_text(json.dumps(actuales, ensure_ascii=False, indent=1))
    return actuales


def permitido(nombre: str) -> bool:
    n = normalizar(nombre or "")
    return bool(n) and not any(x and x in n for x in excluidos())


def chats(con: sqlite3.Connection) -> list[dict]:
    """Chats uno a uno permitidos, con cuántos mensajes de texto tuyos tienen (más primero)."""
    filas = con.execute("""
        SELECT c.Z_PK AS id, c.ZPARTNERNAME AS nombre,
               SUM(m.ZISFROMME = 1 AND m.ZMESSAGETYPE = 0 AND m.ZTEXT IS NOT NULL) AS mios,
               SUM(m.ZISFROMME = 1 AND m.ZMESSAGETYPE = 2) AS audios, COUNT(m.Z_PK) AS total
        FROM ZWACHATSESSION c JOIN ZWAMESSAGE m ON m.ZCHATSESSION = c.Z_PK
        WHERE c.ZSESSIONTYPE = 0 GROUP BY c.Z_PK ORDER BY mios DESC""").fetchall()
    return [dict(f) for f in filas if f["mios"] and permitido(f["nombre"])]


def limpiar(texto: str) -> str:
    for patron, cambio in LIMPIAR:
        texto = patron.sub(cambio, texto)
    return texto.strip()


def pares(con: sqlite3.Connection, chat_id: int) -> list[dict]:
    """Tus mensajes del chat, cada uno con el mensaje anterior de la otra persona como contexto (si hay)."""
    mensajes = con.execute("""
        SELECT ZISFROMME AS mio, ZTEXT AS texto, ZMESSAGEDATE AS fecha FROM ZWAMESSAGE
        WHERE ZCHATSESSION = ? AND ZMESSAGETYPE = 0 AND ZTEXT IS NOT NULL ORDER BY ZMESSAGEDATE""",
                           (chat_id,)).fetchall()
    salida, contexto = [], ""
    for m in mensajes:
        if m["mio"]:
            salida.append({"fecha": (EPOCA_APPLE + timedelta(seconds=m["fecha"] or 0)).isoformat(timespec="minutes"),
                           "contexto": limpiar(contexto), "respuesta": limpiar(m["texto"])})
            contexto = ""
        else:
            contexto = m["texto"]  # solo el último mensaje del otro antes del tuyo
    return [p for p in salida if p["respuesta"]]


def exportar(pedido: str) -> str:
    """«<nombre>» exporta ese chat; «<n>» exporta n chats al azar (de los que más mensajes tuyos tienen)."""
    con = conectar()
    try:
        disponibles = chats(con)
        if pedido.strip().isdigit():
            elegidos = random.sample(disponibles[:60], min(int(pedido), len(disponibles[:60])))
        else:
            n = normalizar(pedido)
            elegidos = [c for c in disponibles if n and n in normalizar(c["nombre"])]
            if not elegidos:
                return f"No encontré un chat uno a uno permitido que se llame «{pedido}». Dime «chats» para verlos."
            if len(elegidos) > 3:
                return "Coinciden varios: " + ", ".join(c["nombre"] for c in elegidos[:10]) + ". Sé más específico."
        CARPETA.mkdir(parents=True, exist_ok=True)
        lineas = []
        for c in elegidos:
            datos = pares(con, c["id"])
            archivo = CARPETA / f"chat-{c['id']}.jsonl"
            archivo.write_text("".join(json.dumps({"chat": c["nombre"], **p}, ensure_ascii=False) + "\n"
                                       for p in datos))
            lineas.append(f"· {c['nombre']}: {len(datos)} mensajes tuyos")
        total = sum(1 for _ in CARPETA.glob("chat-*.jsonl"))
        return "📥 Exportado (solo en la Mac):\n" + "\n".join(lineas) + f"\n\nTotal exportado: {total} chats."
    finally:
        cerrar(con)


def resumen(n: int = 15) -> str:
    con = conectar()
    try:
        lista_c = chats(con)
    finally:
        cerrar(con)
    filas = [f"· {c['nombre']}: {c['mios']} tuyos" + (f", {c['audios']} audios" if c["audios"] else "")
             for c in lista_c[:n]]
    return (f"💬 Tus chats uno a uno con más mensajes tuyos ({len(lista_c)} permitidos):\n" + "\n".join(filas) +
            "\n\n«exporta <nombre>», «exporta 5» (al azar) o «excluye <nombre>» (p. ej. los del trabajo).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chats de WhatsApp para aprender tu estilo")
    parser.add_argument("accion", choices=["chats", "exporta", "excluye"])
    parser.add_argument("valor", nargs="?", default="")
    args = parser.parse_args()
    if args.accion == "chats":
        print(resumen())
    elif args.accion == "exporta":
        print(exportar(args.valor or "5"))
    else:
        print("Excluidos:", excluir(args.valor))


if __name__ == "__main__":
    main()
