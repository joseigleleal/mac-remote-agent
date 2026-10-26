"""Pruebas del puente Telegram ↔ Claude Code sin red: el hook de Stop despierta a Claude con tu mensaje y el de
preguntas devuelve la opción elegida.

    .venv/bin/python -m unittest discover tests -v
"""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from mac import bot, claude_puente as cp

DORMIR = time.sleep  # el original: la prueba lo acorta sin llamarse a sí misma


class Puente(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        parches = [mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "111"}), mock.patch.object(bot, "log"),
                   mock.patch.object(cp, "APAGADO", tmp / "off")]
        for nombre in ("CARPETA", "BUZON", "RESPUESTAS", "ALERTAS", "PREGUNTAS", "TURNO", "RESPONDER"):
            ruta = tmp / getattr(cp, nombre).relative_to(cp.DATA_DIR)
            parches.append(mock.patch.object(cp, nombre, ruta))
        parches += [mock.patch.object(cp, "ESPERA_STOP", 10), mock.patch.object(cp, "ESPERA_PREGUNTA", 10),
                    mock.patch.object(cp.time, "sleep", lambda s: DORMIR(0.05))]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)
        self.enviar = mock.patch.object(cp.telegram, "enviar", return_value=500).start()
        self.addCleanup(mock.patch.stopall)

    def despues(self, funcion):
        threading.Timer(0.3, funcion).start()

    def test_stop_despierta_a_claude_con_tu_mensaje(self):
        self.despues(lambda: cp.dejar_mensaje("sigue con la VM"))
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as fin:
            cp.hook_stop({"session_id": "s1", "transcript_path": "/no/existe"})
        self.assertEqual(fin.exception.code, 2)
        self.assertIn("sigue con la VM", err.getvalue())
        self.assertTrue(cp.es_alerta(500))  # responder a ese aviso cuenta como mensaje para Claude

    def test_a_pedido_no_avisa_solo_pero_responde_lo_que_preguntas(self):
        cp.APAGADO.write_text("off")  # modo a pedido: en el PC se ve todo, a Telegram no va nada solo
        transcript = Path(tempfile.mkdtemp()) / "t.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Cita sigue pausada."}]}}) + "\n")
        self.despues(lambda: cp.dejar_mensaje("¿cómo va cita?"))
        with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            cp.hook_stop({"transcript_path": str(transcript)})  # terminó un turno normal: no avisa, pero escucha
        self.enviar.assert_not_called()
        self.assertIn("¿cómo va cita?", err.getvalue())
        with mock.patch.object(cp, "ESPERA_STOP", 0):
            cp.hook_stop({"transcript_path": str(transcript)})  # el turno que respondía a Telegram: vuelve allá
        self.assertIn("Cita sigue pausada.", self.enviar.call_args[0][1])
        self.enviar.reset_mock()
        with mock.patch.object(cp, "ESPERA_STOP", 0):
            cp.hook_stop({"transcript_path": str(transcript)})  # el siguiente turno, de nuevo nada
        self.enviar.assert_not_called()

    def test_pregunta_con_botones_devuelve_la_opcion(self):
        entrada = {"questions": [{"question": "¿Arranco?", "options": [{"label": "Sí"}, {"label": "No"}]}]}
        self.despues(lambda: cp.dejar_respuesta(cp.pregunta_de(500), "1"))
        out = io.StringIO()
        with redirect_stdout(out):
            cp.hook_pregunta({"tool_input": entrada})
        salida = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(salida["permissionDecision"], "allow")
        self.assertEqual(salida["updatedInput"]["answers"], {"¿Arranco?": "No"})

    def test_el_bot_pasa_la_respuesta_a_un_aviso(self):
        cp.ALERTAS.parent.mkdir(parents=True, exist_ok=True)
        cp.ALERTAS.write_text(json.dumps({"77": "s1"}))
        with mock.patch.object(bot.telegram, "enviar"):
            bot.Bot().atender({"update_id": 1, "message": {"chat": {"id": 111}, "text": "dale con q5",
                                                           "reply_to_message": {"message_id": 77}}})
        self.assertIn("dale con q5", cp.BUZON.read_text())


if __name__ == "__main__":
    unittest.main()
