"""Pruebas del agente sin modelo: respuestas de Ollama simuladas (llamadas a herramientas) y el bot de verdad.

    .venv/bin/python -m unittest discover tests -v
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from mac import agente, bot
from mac.interprete import Pedido


def llamada(nombre: str, **args) -> dict:
    return {"content": "", "tool_calls": [{"function": {"name": nombre, "arguments": args}}]}


def guion(*respuestas):
    """Un «modelo» que responde en orden y anota lo que recibió."""
    vistas = []

    def llamar(mensajes):
        vistas.append(list(mensajes))
        return respuestas[len(vistas) - 1]
    llamar.vistas = vistas
    return llamar


class Agente(unittest.TestCase):
    def test_varios_pasos_con_resultados(self):
        hechos = []
        llamar = guion(llamada("spotify_reproducir", consulta="salsa", perfil="personal"),  # no lo dijo: se descarta
                       llamada("volumen", modo="fijar", valor=20), {"content": "Puse salsa y bajé el volumen a 20."})
        final = agente.atender("pon algo de salsa y baja el volumen a 20",
                               lambda p: (hechos.append(p) or f"ok {p.accion}", False), agente.Memoria(), llamar)
        self.assertEqual(hechos, [Pedido("spotify", {"consulta": "salsa"}), Pedido("volumen", {"modo": "fijar", "valor": 20})])
        self.assertIsNone(final)  # usó herramientas: sus resultados ya llegaron, no se agrega un resumen
        self.assertEqual(llamar.vistas[1][-1], {"role": "tool", "content": "ok spotify", "tool_name": "spotify_reproducir"})

    def test_botones_terminan_el_ciclo(self):
        llamar = guion(llamada("cerrar_app", app="pycharm"), {"content": "no debería llegar"})
        self.assertIsNone(agente.atender("cierra lo de jetbrains", lambda p: ("¿Cierro PyCharm?", True),
                                         agente.Memoria(), llamar))
        self.assertEqual(len(llamar.vistas), 1)

    def test_herramienta_inexistente_y_tope_de_pasos(self):
        hechos = []
        llamar = guion(*[llamada("borrar_disco")] * agente.MAX_PASOS)
        final = agente.atender("x", lambda p: (hechos.append(p), False), agente.Memoria(), llamar)
        self.assertEqual(hechos, [])  # nunca se ejecuta algo fuera de la lista
        self.assertIn("No existe la herramienta", llamar.vistas[1][-1]["content"])
        self.assertIn("máximo de pasos", final)

    def test_sin_herramientas_responde_el_modelo_y_perfil_dicho_se_respeta(self):
        self.assertEqual(agente.atender("hola", lambda p: ("", False), agente.Memoria(), guion({"content": "¡Hola!"})),
                         "¡Hola!")
        self.assertEqual(agente.pedido("abrir_pagina", {"sitio": "gmail", "perfil": "Personal"}, "abre gmail en personal"),
                         Pedido("abrir", {"sitio": "gmail", "perfil": "Personal"}))

    def test_memoria_corta(self):
        memoria = agente.Memoria()
        agente.atender("sube el volumen", lambda p: ("🔊 50 %", False), memoria,
                       guion(llamada("volumen", modo="subir"), {"content": "Listo."}))
        llamar = guion({"content": "ok"})
        agente.atender("y ahora más", lambda p: ("", False), memoria, llamar)
        self.assertIn({"role": "user", "content": "sube el volumen"}, llamar.vistas[0])
        memoria.turnos = [(0, "user", "viejo")]  # de hace más de 30 min: se olvida
        self.assertEqual(memoria.mensajes(), [])

    def test_todas_las_herramientas_son_acciones_conocidas(self):
        from mac.interprete import ACCIONES
        nombres = {h["function"]["name"] for h in agente.HERRAMIENTAS}
        self.assertEqual(nombres, set(agente.ACCION))
        self.assertTrue(set(agente.ACCION.values()) <= set(ACCIONES))
        self.assertNotIn("apagar", agente.ACCION.values())  # lo irreversible queda solo para las reglas


class BotConAgente(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(bot, "OFFSET", Path(tempfile.mkdtemp()) / "offset")
        p.start()
        self.addCleanup(p.stop)

    def enviar(self, texto, **atender):
        b = bot.Bot()
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111", "AGENTE_MODELO": "qwen3:8b"}), \
                mock.patch.object(bot.telegram, "enviar") as enviar, mock.patch.object(bot, "log"), \
                mock.patch.object(bot.servicio, "pausado", return_value=False), \
                mock.patch.object(bot.agente, "atender", **atender) as atender_:
            b.atender({"update_id": 1, "message": {"chat": {"id": 111}, "text": texto}})
        return b, enviar, atender_

    def test_lo_que_entiende_una_regla_no_usa_el_modelo(self):
        with mock.patch.object(bot.volumen, "ajustar", return_value="🔊 Volumen: 60 %"):
            _, enviar, atender_ = self.enviar("sube el volumen")
        atender_.assert_not_called()
        self.assertEqual(enviar.call_args[0][1], "🔊 Volumen: 60 %")

    def test_lo_que_no_entiende_va_al_agente_y_usa_las_acciones_del_bot(self):
        def atender(texto, usar, memoria):
            with mock.patch.object(bot.volumen, "ajustar", return_value="🔊 Volumen: 20 %"):
                resultado, botones = usar(Pedido("volumen", {"modo": "fijar", "valor": 20}))
            self.assertEqual((resultado, botones), ("🔊 Volumen: 20 %", False))
            return None
        _, enviar, _ = self.enviar("déjalo bajito, como a 20", side_effect=atender)
        self.assertEqual([c[0][1] for c in enviar.call_args_list][1:], ["🔊 Volumen: 20 %"])

    def test_sin_ollama_responde_la_ayuda(self):
        _, enviar, _ = self.enviar("algo raro", side_effect=requests.ConnectionError("apagado"))
        self.assertIn("modelo local no responde", enviar.call_args[0][1])

    def test_ayuda_pedida_no_usa_el_modelo(self):
        _, enviar, atender_ = self.enviar("ayuda")
        atender_.assert_not_called()
        self.assertEqual(enviar.call_args[0][1], bot.AYUDA)


if __name__ == "__main__":
    unittest.main()
