"""Pruebas del bot sin red: solo obedece a los chats autorizados.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import unittest
from unittest import mock

from mac import bot


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


if __name__ == "__main__":
    unittest.main()
