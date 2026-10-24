"""Pruebas del login con datos del .env (sin Chrome): qué sitios hay y que la clave nunca salga del equipo.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import unittest
from unittest import mock

from mac import bot, login
from mac.interprete import interpretar

ENV = {"TELEGRAM_CHAT_ID": "111", "CHROME_PERFILES": "uni:Profile 4", "CHROME_PERFILES_PERMITIDOS": "",
       "LOGIN_SITIOS": "uni, correo, incompleto",
       "LOGIN_UNI_PERFIL": "uni", "LOGIN_UNI_DOMINIOS": "sso.ejemplo.edu", "LOGIN_UNI_USUARIO": "ana",
       "LOGIN_UNI_CLAVE": "s3cr3t\"o", "LOGIN_CORREO_PERFIL": "Default", "LOGIN_CORREO_DOMINIOS": "accounts.google.com",
       "LOGIN_CORREO_CLAVE": "otra", "LOGIN_INCOMPLETO_PERFIL": "Default"}


class Login(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.dict(os.environ, ENV), mock.patch.object(bot, "log"),
                  mock.patch.object(login.chrome, "mostrar"),  # sin Chrome real
                  mock.patch.object(login.chrome, "ejecutar_js", return_value="/login|1|1"),
                  mock.patch.object(login.chrome, "url", return_value="https://app.ejemplo.edu/inicio")):
            p.start()
            self.addCleanup(p.stop)

    def test_sitios_del_env(self):
        sitios = login.sitios()
        self.assertEqual(sorted(sitios), ["correo", "uni"])  # el incompleto (sin dominio ni clave) no cuenta
        self.assertEqual(login.carpeta(sitios["uni"]["perfil"]), "Profile 4")
        self.assertEqual(sitios["correo"]["usuario"], "")

    def test_sin_pestana_de_login_no_hace_nada(self):
        with mock.patch.object(login.chrome, "buscar_pestana", return_value=None), \
                mock.patch.object(login.chrome, "ejecutar_js_privado") as js:
            self.assertIn("sigue abierta", login.reautenticar("uni"))
        js.assert_not_called()

    def test_la_clave_no_sale_por_telegram_ni_por_el_log(self):
        pestanas = iter([(1, 2), None])  # en login → después ya no
        with mock.patch.object(login.chrome, "buscar_pestana", side_effect=lambda c, d: next(pestanas, None)), \
                mock.patch.object(login.chrome, "ejecutar_js_privado", return_value="usuario+clave") as js, \
                mock.patch.object(bot.telegram, "enviar") as enviar:
            bot.Bot().atender({"update_id": 1, "message": {"chat": {"id": 111}, "text": "reautentica uni"}})
        self.assertIn('"s3cr3t\\"o"', js.call_args.args[2])  # la clave va a Chrome, escapada para JavaScript
        textos = " ".join(str(c) for c in enviar.call_args_list + bot.log.call_args_list)
        self.assertNotIn("s3cr3t", textos)
        self.assertIn("sesión iniciada", enviar.call_args.args[1])

    def test_varios_sitios_pregunta(self):
        with mock.patch.object(bot.telegram, "enviar") as enviar:
            bot.Bot().atender({"update_id": 1, "message": {"chat": {"id": 111}, "text": "vuelve a iniciar sesión"}})
        datos = [f[0]["callback_data"] for f in enviar.call_args.args[2]["inline_keyboard"]]
        self.assertEqual(sorted(datos), ["login:correo", "login:uni"])

    def test_frases(self):
        self.assertEqual(interpretar("reautentica uni").datos, {"sitio": "uni"})
        self.assertEqual(interpretar("/login correo").datos, {"sitio": "correo"})


if __name__ == "__main__":
    unittest.main()
