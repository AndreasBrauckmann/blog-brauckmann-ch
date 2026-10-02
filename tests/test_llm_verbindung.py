"""Verbindungsfehler: Wiederholungen mit Wartezeit, keine Wiederholung bei 4xx, Zustand „nicht bearbeitet“, Gesundheitstest."""

import io as pyio
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import llm  # noqa: E402


class Antwort:
    def __init__(self, inhalt="ok"):
        self.inhalt = inhalt

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self.inhalt}, "finish_reason": "stop"}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_fehler(code, body=b""):
    return urllib.error.HTTPError("http://x", code, "x", {}, pyio.BytesIO(body))


class Wiederholung(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"BLOG_LLM_API_KEY": "test-schluessel-nie-ausgeben"})
        self.env.start()
        self.schlaf = mock.patch.object(llm, "_schlafen")
        self.pause = self.schlaf.start()

    def tearDown(self):
        self.schlaf.stop()
        self.env.stop()

    def chat(self, folge):
        with mock.patch.object(urllib.request, "urlopen", side_effect=folge) as u:
            try:
                return llm.chat("s", "n"), u
            finally:
                self.aufrufe = u.call_count

    def test_verbindungsabbruch_wird_wiederholt(self):
        text, _ = self.chat([ConnectionResetError(), urllib.error.URLError(ConnectionRefusedError()), TimeoutError(), Antwort("fertig")])
        self.assertEqual(text, "fertig")
        self.assertEqual([c.args[0] for c in self.pause.call_args_list], [5, 15, 30])

    def test_nach_fuenf_wiederholungen_ist_schluss(self):
        with self.assertRaises(llm.LLMVerbindung) as ctx:
            self.chat([ConnectionResetError()] * 6)
        self.assertEqual(self.aufrufe, 6)
        self.assertEqual([c.args[0] for c in self.pause.call_args_list], [5, 15, 30, 60, 120])
        self.assertIn("nicht erreichbar", str(ctx.exception))
        self.assertNotIn("test-schluessel", str(ctx.exception))

    def test_5xx_und_wrapper_fehlertext_werden_wiederholt(self):
        text, _ = self.chat([http_fehler(502), http_fehler(500, b'{"error":"API Error: 503 overloaded"}'), Antwort("API Error: 529 busy"), Antwort("gut")])
        self.assertEqual(text, "gut")
        self.assertEqual(self.pause.call_count, 3)

    def test_4xx_wird_nicht_wiederholt(self):
        for code in (400, 401, 404):
            self.pause.reset_mock()
            with self.assertRaises(llm.LLMFehler) as ctx:
                self.chat([http_fehler(code)] * 6)
            self.assertNotIsInstance(ctx.exception, llm.LLMVerbindung)
            self.assertEqual(self.aufrufe, 1, code)
            self.assertEqual(self.pause.call_count, 0)
            self.assertIn(str(code), str(ctx.exception))

    def test_500_ohne_wrapper_text_ist_konfigurationsfehler(self):
        with self.assertRaises(llm.LLMFehler) as ctx:
            self.chat([http_fehler(500, b"Internal Server Error")] * 6)
        self.assertNotIsInstance(ctx.exception, llm.LLMVerbindung)
        self.assertEqual(self.aufrufe, 1)

    def test_gesundheitstest(self):
        with mock.patch.object(urllib.request, "urlopen", return_value=Antwort()):
            self.assertTrue(llm.dienst_erreichbar())
        with mock.patch.object(urllib.request, "urlopen", side_effect=ConnectionResetError()):
            self.assertFalse(llm.dienst_erreichbar())
        with mock.patch.object(urllib.request, "urlopen", side_effect=http_fehler(503)):
            self.assertFalse(llm.dienst_erreichbar())
        with mock.patch.object(urllib.request, "urlopen", side_effect=http_fehler(401)):
            self.assertTrue(llm.dienst_erreichbar())  # Dienst antwortet (nur Schluessel/Pfad anders)


if __name__ == "__main__":
    unittest.main()
