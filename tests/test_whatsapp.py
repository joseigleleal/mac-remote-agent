"""Pruebas de WhatsApp con una base de mentira: solo chats uno a uno, excluidos y pares (contexto, respuesta).

    .venv/bin/python -m unittest discover tests -v
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mac import whatsapp as wa
from mac.interprete import interpretar


def base_de_prueba(ruta: Path) -> None:
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE ZWACHATSESSION (Z_PK INTEGER, ZPARTNERNAME TEXT, ZSESSIONTYPE INTEGER)")
    con.execute("CREATE TABLE ZWAMESSAGE (Z_PK INTEGER, ZCHATSESSION INTEGER, ZISFROMME INTEGER, ZMESSAGETYPE INTEGER,"
                " ZTEXT TEXT, ZMESSAGEDATE REAL)")
    con.executemany("INSERT INTO ZWACHATSESSION VALUES (?,?,?)",
                    [(1, "Ana", 0), (2, "Jefe Trabajo", 0), (3, "Familia", 1)])
    con.executemany("INSERT INTO ZWAMESSAGE VALUES (?,?,?,?,?,?)", [
        (1, 1, 0, 0, "¿vamos al cine?", 10), (2, 1, 1, 0, "dale, a las 8", 20), (3, 1, 1, 0, "mi cel 600 123 456", 30),
        (4, 2, 1, 0, "listo jefe", 40), (5, 3, 1, 0, "hola a todos", 50)])
    con.commit()
    con.close()


class WhatsApp(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        base_de_prueba(tmp / "ChatStorage.sqlite")
        for p in (mock.patch.object(wa, "BASE", tmp / "ChatStorage.sqlite"),
                  mock.patch.object(wa, "CARPETA", tmp / "salida"),
                  mock.patch.object(wa, "EXCLUIDOS", tmp / "salida" / "excluidos.json"),
                  mock.patch.dict(os.environ, {"WHATSAPP_EXCLUIR": "trabajo"})):
            p.start()
            self.addCleanup(p.stop)

    def test_solo_uno_a_uno_y_sin_excluidos(self):
        con = wa.conectar()
        try:
            self.assertEqual([c["nombre"] for c in wa.chats(con)], ["Ana"])  # sin grupo ni «trabajo»
        finally:
            wa.cerrar(con)

    def test_exporta_tus_mensajes_con_contexto_y_sin_telefonos(self):
        self.assertIn("Ana: 2 mensajes tuyos", wa.exportar("ana"))
        filas = [json.loads(l) for l in (wa.CARPETA / "chat-1.jsonl").read_text().splitlines()]
        self.assertEqual(filas[0]["contexto"], "¿vamos al cine?")
        self.assertEqual(filas[0]["respuesta"], "dale, a las 8")
        self.assertEqual(filas[1]["respuesta"], "mi cel <teléfono>")
        self.assertIn("No encontré", wa.exportar("jefe"))  # excluido

    def test_frases(self):
        self.assertEqual(interpretar("exporta el chat de Ana").datos, {"valor": "ana"})
        self.assertEqual(interpretar("exporta 5 chats al azar").datos, {"valor": "5"})
        self.assertEqual(interpretar("excluye trabajo").accion, "wa_excluye")
        self.assertEqual(interpretar("mis chats").accion, "wa_chats")


if __name__ == "__main__":
    unittest.main()
