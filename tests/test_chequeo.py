"""Pruebas del chequeo de la Mac y de las rutinas, sin Telegram, Ollama ni macOS de verdad.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from mac import bot, chequeo, rutinas
from mac.chequeo import Problema
from mac.interprete import interpretar


class Temporal(unittest.TestCase):
    """Estado del chequeo y rutinas en una carpeta temporal (nunca los de data/)."""
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for p in (mock.patch.object(chequeo, "ESTADO", tmp / "chequeo.json"),
                  mock.patch.object(rutinas, "ARCHIVO", tmp / "rutinas.json"),
                  mock.patch.object(chequeo, "DATA_DIR", tmp), mock.patch.object(rutinas, "DATA_DIR", tmp)):
            p.start()
            self.addCleanup(p.stop)


class Vueltas(Temporal):
    def vuelta(self, *problemas):
        avisos = []
        chequeo.vuelta(lambda texto, botones: avisos.append((texto, botones)), lambda: ([], list(problemas)))
        return avisos

    def test_avisa_una_vez_y_dice_cuando_se_resuelve(self):
        disco = Problema("disco", "Disco casi lleno")
        self.assertEqual(len(self.vuelta(disco)), 1)
        self.assertEqual(self.vuelta(disco), [])  # sigue igual: no repite
        self.assertEqual(self.vuelta(), [("✅ Resuelto: Disco casi lleno", None)])
        self.assertEqual(self.vuelta(), [])

    def test_repara_una_sola_vez(self):
        intentos = []
        ollama = Problema("ollama", "Ollama no responde", reparar=lambda: intentos.append(1) or False)
        self.assertIn("no funcionó", self.vuelta(ollama)[0][0])
        self.vuelta(ollama)
        self.assertEqual(len(intentos), 1)  # no reintenta en bucle mientras siga roto

    def test_reparado_no_queda_abierto(self):
        ollama = Problema("ollama", "Ollama no responde", reparar=lambda: True)
        self.assertIn("Lo arreglé solo", self.vuelta(ollama)[0][0])
        self.assertIn("Lo arreglé solo", self.vuelta(ollama)[0][0])  # si se vuelve a caer, se vuelve a intentar

    def test_lo_que_necesita_tu_toque_va_con_boton(self):
        sesion = Problema("sesion:correo", "La sesión de correo venció", boton=("🔑 Iniciar sesión", "login:correo"))
        _, botones = self.vuelta(sesion)[0]
        self.assertEqual(botones["inline_keyboard"][0][0]["callback_data"], "login:correo")

    def test_cada_cuanto(self):
        with mock.patch.dict(os.environ, {"CHEQUEO_MIN": "30"}):
            self.assertTrue(chequeo.toca())
            self.vuelta()
            self.assertFalse(chequeo.toca())
        with mock.patch.dict(os.environ, {"CHEQUEO_MIN": "0"}):
            self.assertFalse(chequeo.toca())  # apagado: solo a pedido

    def test_solo_revisa_lo_configurado(self):
        with mock.patch.dict(os.environ, {"AGENTE_MODELO": "", "ECO_DIR": "", "LOGIN_SITIOS": ""}), \
                mock.patch.object(chequeo.agente, "modelo", return_value=""):
            self.assertEqual(chequeo.revisar_ollama(), (None, None))
            self.assertEqual(chequeo.revisar_eco(), (None, None))
            self.assertEqual(chequeo.revisar_sesiones(), (None, []))

    def test_disco(self):
        with mock.patch.dict(os.environ, {"CHEQUEO_DISCO_MIN_GB": "10"}), \
                mock.patch.object(chequeo.shutil, "disk_usage", return_value=mock.Mock(free=4 * 1024 ** 3)):
            self.assertEqual(chequeo.revisar_disco()[1].clave, "disco")


class Rutinas(Temporal):
    def test_entender(self):
        casos = {
            "rutina 8:00 qué está consumiendo más": ("08:00", "todos", "qué está consumiendo más"),
            "rutina lunes a viernes 7:30 pon lofi en spotify": ("07:30", "habiles", "pon lofi en spotify"),
            "/rutina fines de semana a las 10 chequeo": ("10:00", "finde", "chequeo"),
            "rutina todos los días 21.15, baja el volumen 20": ("21:15", "todos", "baja el volumen 20"),
        }
        for frase, (hora, dias, texto) in casos.items():
            r = rutinas.entender(frase)
            self.assertEqual((r["hora"], r["dias"], r["texto"]), (hora, dias, texto), frase)
        self.assertIsNone(rutinas.entender("rutina 25:00 chequeo"))
        self.assertIsNone(rutinas.entender("rutina chequeo"))

    def test_no_programa_lo_prohibido_ni_lo_que_no_entiende(self):
        self.assertIn("no la programo", rutinas.agregar("rutina 8:00 apágate del todo", True))
        self.assertIn("no la programo", rutinas.agregar("rutina 8:00 rutina 9:00 chequeo", True))
        self.assertIn("No entiendo", rutinas.agregar("rutina 8:00 cómo estás", hay_modelo=False))
        self.assertEqual(rutinas.leer(), [])

    def test_agregar_listar_y_borrar(self):
        rutinas.agregar("rutina 8:00 chequeo", True)
        rutinas.agregar("rutina 7:00 pausa spotify", True)
        self.assertIn("1. todos los días a las 08:00", rutinas.resumen())
        self.assertEqual(rutinas.borrar(1), "🗑️ Rutina 1 borrada.")
        self.assertEqual([r["id"] for r in rutinas.leer()], [2])
        self.assertIn("No hay una rutina 9", rutinas.borrar(9))

    def test_corre_una_vez_dentro_de_la_ventana(self):
        rutinas.agregar("rutina lunes a viernes 8:00 chequeo", True)
        lunes = datetime(2026, 10, 26, 8, 0, 30)
        self.assertEqual(rutinas.pendientes(lunes.replace(hour=7, minute=59)), [])  # todavía no
        self.assertEqual(len(rutinas.pendientes(lunes)), 1)
        self.assertEqual(rutinas.pendientes(lunes.replace(minute=5)), [])            # ya corrió hoy
        self.assertEqual(rutinas.pendientes(datetime(2026, 10, 31, 8, 1)), [])        # sábado
        self.assertEqual(rutinas.pendientes(datetime(2026, 10, 27, 9, 30)), [])       # Mac dormida: muy tarde
        self.assertEqual(len(rutinas.pendientes(datetime(2026, 10, 28, 8, 40))), 1)   # al despertar, a tiempo

    def test_frases(self):
        self.assertEqual(interpretar("rutinas").accion, "rutinas")
        self.assertEqual(interpretar("borra la rutina 2").datos, {"numero": 2})
        self.assertEqual(interpretar("hola mac, rutina 8:00 chequeo").datos, {"texto": "rutina 8:00 chequeo"})
        for frase in ("chequeo", "/chequeo", "revisa la mac", "cómo está la mac"):
            self.assertEqual(interpretar(frase).accion, "chequeo", frase)


class PorIniciativa(Temporal):
    def setUp(self):
        super().setUp()
        for p in (mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111", "CHEQUEO_MIN": "30"}),
                  mock.patch.object(bot, "log"), mock.patch.object(bot.telegram, "enviar"),
                  mock.patch.object(bot.servicio, "PAUSA", Path(tempfile.mkdtemp()) / "pausado")):
            p.start()
            self.addCleanup(p.stop)

    def test_rutina_pasa_por_el_camino_de_siempre(self):
        rutinas.agregar(f"rutina {datetime.now():%H:%M} chequeo", True)
        b = bot.Bot()
        with mock.patch.object(chequeo, "vuelta") as vuelta, mock.patch.object(b, "mensaje") as mensaje:
            b.por_iniciativa()
        vuelta.assert_called_once()
        mensaje.assert_called_once_with("111", "chequeo")

    def test_en_pausa_no_hace_nada(self):
        rutinas.agregar(f"rutina {datetime.now():%H:%M} chequeo", True)
        bot.servicio.pausar()
        b = bot.Bot()
        with mock.patch.object(chequeo, "vuelta") as vuelta, mock.patch.object(b, "mensaje") as mensaje:
            b.por_iniciativa()
        vuelta.assert_not_called()
        mensaje.assert_not_called()


if __name__ == "__main__":
    unittest.main()
