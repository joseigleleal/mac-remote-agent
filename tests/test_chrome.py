"""Pruebas de Chrome sin abrir Chrome: perfil de cada ventana, apodos y perfiles permitidos.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import unittest
from unittest import mock

from mac import chrome
from mac.chrome import Perfil, Ventana

PERFILES = {"Default": Perfil("Default", "Ana"), "Profile 2": Perfil("Profile 2", "Ana"),
            "Profile 4": Perfil("Profile 4", "estudios")}


class Chrome(unittest.TestCase):
    def test_cada_ventana_es_del_perfil_que_mas_urls_tiene_en_su_sesion(self):
        v1 = Ventana(1, ["https://open.spotify.com/", "https://mail.google.com/"])
        v2 = Ventana(2, ["https://campus.ejemplo.edu/"])
        v3 = Ventana(3, ["https://nueva.ejemplo.com/"])
        sesiones = {"Default": b"..https://open.spotify.com/..https://mail.google.com/..",
                    "Profile 4": b"..https://campus.ejemplo.edu/..https://mail.google.com/.."}
        chrome.asignar_perfiles([v1, v2, v3], sesiones)
        self.assertEqual((v1.perfil, v2.perfil, v3.perfil), ("Default", "Profile 4", None))

    def test_resolver_por_apodo_carpeta_o_nombre_unico(self):
        with mock.patch.object(chrome, "perfiles", return_value=PERFILES), \
                mock.patch.dict(os.environ, {"CHROME_PERFILES": "personal:Default, uni:Profile 4"}):
            self.assertEqual(chrome.resolver("en mi perfil personal").carpeta, "Default")
            self.assertEqual(chrome.resolver("en el de la UNI").carpeta, "Profile 4")
            self.assertEqual(chrome.resolver("perfil estudios").carpeta, "Profile 4")
            self.assertEqual(chrome.resolver("en profile 2").carpeta, "Profile 2")
            self.assertIsNone(chrome.resolver("el de ana"))      # dos perfiles se llaman Ana: ambiguo
            self.assertIsNone(chrome.resolver("pon música"))

    def test_perfiles_permitidos(self):
        with mock.patch.object(chrome, "perfiles", return_value=PERFILES), \
                mock.patch.object(chrome, "carpetas_abiertas", return_value=["Default", "Profile 2"]):
            with mock.patch.dict(os.environ, {"CHROME_PERFILES_PERMITIDOS": ""}):
                self.assertEqual([p.carpeta for p in chrome.abiertos()], ["Default", "Profile 2"])
            with mock.patch.dict(os.environ, {"CHROME_PERFILES_PERMITIDOS": "Default"}):
                self.assertEqual([p.carpeta for p in chrome.abiertos()], ["Default"])


if __name__ == "__main__":
    unittest.main()
