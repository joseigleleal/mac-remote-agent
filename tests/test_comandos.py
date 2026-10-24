"""Pruebas de comandos permitidos: solo la lista, en segundo plano y se pueden detener.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mac import comandos
from mac.interprete import interpretar


class Comandos(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for p in (mock.patch.object(comandos, "DATA_DIR", tmp), mock.patch.object(comandos, "REGISTRO", tmp / "c.json"),
                  mock.patch.object(comandos, "ESPERA", 1),
                  mock.patch.dict(os.environ, {"COMANDOS_PERMITIDOS": "echo hola ; sleep 30"})):
            p.start()
            self.addCleanup(p.stop)

    def test_fuera_de_la_lista_no_se_ejecuta(self):
        with mock.patch.object(comandos.subprocess, "Popen") as popen:
            for c in ("rm -rf /", "echo hola; rm x", "echo  hola  mundo"):
                self.assertIn("no está en la lista", comandos.ejecutar(c))
        popen.assert_not_called()

    def test_corto_devuelve_salida_y_largo_queda_corriendo_hasta_detenerlo(self):
        self.assertIn("hola", comandos.ejecutar("echo   hola"))  # los espacios de más no importan
        self.assertIn("segundo plano", comandos.ejecutar("sleep 30"))
        self.assertEqual([d["comando"] for d in comandos.corriendo().values()], ["sleep 30"])
        self.assertIn("Detenido", comandos.detener("sleep"))
        time.sleep(0.5)
        self.assertEqual(comandos.corriendo(), {})

    def test_en_terminal_visible_tambien_exige_la_lista(self):
        with mock.patch.object(comandos.terminal, "escribir", return_value="ok") as escribir:
            self.assertIn("no está en la lista", comandos.ejecutar("rm -rf /", "pycharm"))
            escribir.assert_not_called()
            self.assertEqual(comandos.ejecutar("echo hola", "pycharm"), "ok")
            escribir.assert_called_once_with("pycharm", "echo hola")

    def test_frases(self):
        pedido = interpretar("ejecuta caffeinate -d en la consola terminal que esta libre en pycharm")
        self.assertEqual((pedido.accion, pedido.datos), ("comando", {"comando": "caffeinate -d", "donde": "pycharm"}))
        self.assertEqual(interpretar("ejecuta caffeinate -d").datos["donde"], None)  # sin decir dónde: en segundo plano
        self.assertEqual(interpretar("ejecuta caffeinate -d en intellij").datos["donde"], "intellij")
        self.assertEqual(interpretar("ejecuta caffeinate -d en la terminal de iTerm").datos["donde"], "iterm")
        self.assertEqual(interpretar("detén caffeinate").datos, {"comando": "caffeinate"})
        self.assertEqual(interpretar("qué comandos hay").accion, "comandos")


if __name__ == "__main__":
    unittest.main()
