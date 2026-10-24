"""Pruebas del bot sin red: solo obedece a los chats autorizados.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import unittest
from unittest import mock

from mac import bot
from mac.chrome import Perfil
from mac.interprete import interpretar

PERSONAL, ESTUDIO = Perfil("Default", "Ana", "personal"), Perfil("Profile 4", "estudio")


def mensaje(chat: int, texto: str, update_id: int = 1) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": texto}}


class Autorizacion(unittest.TestCase):
    def test_solo_chats_de_la_lista(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111, 222"}):
            self.assertTrue(bot.autorizado(111))
            self.assertTrue(bot.autorizado("222"))
            self.assertFalse(bot.autorizado(333))
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": ""}):
            self.assertFalse(bot.autorizado(111))  # vacío = no obedece a nadie

    def test_chat_ajeno_no_recibe_respuesta(self):
        b = bot.Bot()
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111"}), \
                mock.patch.object(bot.telegram, "enviar") as enviar, mock.patch.object(bot, "log"):
            b.atender(mensaje(999, "hola mac, pon música", update_id=7))
        enviar.assert_not_called()
        self.assertEqual(b.offset, 8)  # igual se marca como leído


class Interprete(unittest.TestCase):
    def test_frases_de_musica(self):
        casos = {
            "hola mac quiero que entres a mi perfil personal de chrome que tengo abierto y en la pestaña de spotify "
            "busques musica de bad bunny y le des play": "bad bunny",
            "hola mac, en mi perfil personal pon bad bunny en spotify": "bad bunny",
            "hola mac dale play a karol g": "karol g",
            "/spotify feid": "feid",
            "pon bad bunny en spotify": "bad bunny",  # sin «hola mac»
        }
        for frase, consulta in casos.items():
            pedido = interpretar(frase)
            self.assertEqual((pedido.accion, pedido.datos["consulta"]), ("spotify", consulta), frase)

    def test_volumen(self):
        casos = {
            "hola mac sube el volumen": {"modo": "subir", "valor": None},
            "baja el volumen 20": {"modo": "bajar", "valor": 20},
            "pon el volumen al 30": {"modo": "fijar", "valor": 30},
            "silencia la mac": {"modo": "silenciar"},
            "quita el silencio": {"modo": "activar"},
            "cómo está el volumen": {"modo": "ver"},
            "/volumen 50": {"modo": "fijar", "valor": 50},
        }
        for frase, datos in casos.items():
            pedido = interpretar(frase)
            self.assertEqual((pedido.accion, pedido.datos), ("volumen", datos), frase)

    def test_otros_pedidos(self):
        self.assertEqual(interpretar("hola mac, qué perfiles hay").accion, "perfiles")
        self.assertEqual(interpretar("hola mac, ¿cómo estás?").accion, "ayuda")


class Servicio(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp())
        for p in (mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111"}), mock.patch.object(bot, "log"),
                  mock.patch.object(bot.servicio, "PAUSA", self.tmp / "pausado")):
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(bot.telegram, "enviar")
        self.enviar = p.start()
        self.addCleanup(p.stop)

    def test_frases(self):
        for frase, accion in {"cuánto consumes": "estado", "/estado": "estado", "hola mac, pausa": "pausar",
                              "apágate": "pausar", "préndete": "reanudar", "/reanudar": "reanudar",
                              "apágate del todo": "apagar", "/apagar": "apagar",
                              "apaga el sonido": "volumen"}.items():
            self.assertEqual(interpretar(frase).accion, accion, frase)

    def test_en_pausa_no_hace_nada_hasta_prender(self):
        b = bot.Bot()
        with mock.patch.object(bot.spotify, "reproducir") as reproducir, \
                mock.patch.object(bot.chrome, "resolver", return_value=PERSONAL):
            b.atender(mensaje(111, "pausa"))
            b.atender(mensaje(111, "pon bad bunny"))
            reproducir.assert_not_called()
            self.assertIn("pausa", self.enviar.call_args.args[1])
            b.atender(mensaje(111, "prende"))
            b.atender(mensaje(111, "pon bad bunny"))
            reproducir.assert_called_once()

    def test_apagar_pide_confirmacion(self):
        with mock.patch.object(bot.servicio, "apagar") as apagar:
            bot.Bot().atender(mensaje(111, "/apagar"))
            apagar.assert_not_called()  # primero pregunta
        datos = [b["callback_data"] for fila in self.enviar.call_args.args[2]["inline_keyboard"] for b in fila]
        self.assertEqual(datos, ["apagar:si", "apagar:no"])


class Spotify(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111", "CHROME_PERFILES_PERMITIDOS": ""}),
                  mock.patch.object(bot, "log")):
            p.start()
            self.addCleanup(p.stop)
        self.enviar = self.parche(bot.telegram, "enviar")
        self.reproducir = self.parche(bot.spotify, "reproducir", return_value="▶️ sonando")

    def parche(self, objeto, nombre, **kw):
        p = mock.patch.object(objeto, nombre, **kw)
        self.addCleanup(p.stop)
        return p.start()

    def test_con_varios_perfiles_pregunta_y_el_boton_reproduce(self):
        self.parche(bot.chrome, "abiertos", return_value=[PERSONAL, ESTUDIO])
        self.parche(bot.chrome, "perfiles", return_value={"Default": PERSONAL, "Profile 4": ESTUDIO})
        self.parche(bot.chrome, "resolver", return_value=None)
        self.parche(bot.telegram, "editar")
        self.parche(bot.telegram, "responder_boton")
        b = bot.Bot()
        b.atender(mensaje(111, "hola mac pon bad bunny en spotify"))
        self.reproducir.assert_not_called()
        botones = self.enviar.call_args.args[2]["inline_keyboard"]
        self.assertEqual([f[0]["callback_data"] for f in botones], ["perfil:Default", "perfil:Profile 4"])
        b.atender({"update_id": 2, "callback_query": {"id": "q", "data": "perfil:Profile 4",
                                                      "message": {"chat": {"id": 111}, "message_id": 5}}})
        self.reproducir.assert_called_once_with("Profile 4", "bad bunny")
        self.assertEqual(b.pendiente, {})

    def test_perfil_no_permitido_no_se_toca(self):
        self.parche(bot.chrome, "resolver", return_value=ESTUDIO)
        with mock.patch.dict(os.environ, {"CHROME_PERFILES_PERMITIDOS": "Default"}):
            bot.Bot().atender(mensaje(111, "en el perfil estudio pon feid"))
        self.reproducir.assert_not_called()
        self.assertIn("CHROME_PERFILES_PERMITIDOS", self.enviar.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
