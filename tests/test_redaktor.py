"""Tests: Quick-Redaktor (Messregeln, feste Korrekturen, Schutzprüfung, Ratenbegrenzung, Zugangscode, CSRF,
kein Speichern von Texten, „Nur prüfen“ ohne LLM-Aufruf). LLM nur als Stub, kein Netz."""

import json
import logging
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import llm  # noqa: E402
import redaktor as rd  # noqa: E402

MARKE = "Zebrafink-Quittung-7Q3"  # eindeutiges Wort, nach dem in Dateien und Logs gesucht wird
SCHWACH = ("Kurz vorweg – ich bin wirklich begeistert! Heute möchte ich euch erzählen, was wir im Projekt mit 12 Leuten gelernt haben. "
           "Mehr dazu hier https://example.org/artikel lesen. #Cloud #KI #Digitalisierung #Innovation #Leadership")


def stub(antwort: str, modelle: list | None = None):
    def f(*a, **k):
        if modelle is not None:
            modelle.append(k.get("modell"))
        r = llm.Antwort(antwort)
        r.modell = k.get("modell") or ""
        return r
    return f


def pruefung(m: dict, pid: str) -> dict:
    return next(p for p in m["pruefungen"] if p["id"] == pid)


class Messregeln(unittest.TestCase):
    def test_zeichenlimit(self):
        self.assertEqual(pruefung(rd.messen("Satz. " * 400), "limit")["stufe"], "ok")
        m = rd.messen("Wort " * 700)
        self.assertEqual(pruefung(m, "limit")["stufe"], "fehler")
        self.assertLessEqual(m["punkte"], 49)

    def test_hashtags_anzahl_und_ende(self):
        m = rd.messen("Ein Satz mit Inhalt.\n\n#a1 #b2 #c3")
        self.assertEqual(pruefung(m, "hashtags")["stufe"], "ok")
        self.assertEqual(pruefung(m, "hashtags_ende")["stufe"], "ok")
        m = rd.messen("Ein #Satz mit Inhalt.\n\n#a1 #b2 #c3 #d4 #e5 #f6 #g7 #h8")
        self.assertEqual(pruefung(m, "hashtags")["stufe"], "fehler")
        self.assertEqual(pruefung(m, "hashtags_ende")["messwert"], "1 im Text verstreut")
        # Kette am Ende der letzten Textzeile zählt als „am Ende“
        self.assertEqual(pruefung(rd.messen("Ein Satz. #a1 #b2"), "hashtags_ende")["stufe"], "ok")

    def test_adresse_im_textabsatz_hashtags_zuletzt(self):
        """Hausregel 1.10.2026: Adresse direkt hinter dem Text, Leerzeile, Hashtags gesammelt in der letzten Zeile."""
        ok = rd.messen("Security sieht den Angriff, der Betrieb den Fehler. https://example.org/x\n\n#Monitoring #Cloudflare")
        self.assertEqual(pruefung(ok, "link")["stufe"], "ok")
        self.assertEqual(pruefung(rd.messen("Text hier. https://example.org/x"), "link")["stufe"], "ok")
        self.assertEqual(pruefung(rd.messen("Text hier.\n\nhttps://example.org/x\n\n#a"), "link")["stufe"], "warn")  # alte Form
        self.assertEqual(pruefung(rd.messen("Lies https://example.org/x jetzt. Mehr.\n\n#a"), "link")["stufe"], "fehler")
        self.assertEqual(pruefung(rd.messen("Text. https://example.org/x #a #b"), "link")["stufe"], "fehler")  # ohne Leerzeile
        self.assertEqual(pruefung(rd.messen("Ohne Link."), "link")["messwert"], "keine Adresse")
        self.assertEqual(pruefung(ok, "karte")["etikett"], "praxis")

    def test_karte_nur_bei_kurzem_text(self):
        kurz = rd.messen("Kurzer Text. https://example.org/x")
        self.assertTrue(kurz["kachel"]["karte_sichtbar"])
        lang = rd.messen("Wort " * 80 + "https://example.org/x")
        self.assertTrue(lang["kachel"]["karte_verdeckt"])
        self.assertEqual(pruefung(lang, "karte")["etikett"], "praxis")

    def test_markdown_unicode_fett_leerzeilen(self):
        m = rd.messen("Das ist **wichtig**.\n\n\n\nUnd 𝐟𝐞𝐭𝐭 hier.")
        self.assertEqual(pruefung(m, "markdown")["stufe"], "fehler")
        self.assertNotEqual(pruefung(m, "unicode_fett")["stufe"], "ok")
        self.assertNotEqual(pruefung(m, "leerzeilen")["stufe"], "ok")

    def test_haken_erste_140_zeichen(self):
        gut = rd.messen("Wir haben 40 Prozent Rechenzeit gespart. So ging es.")
        self.assertEqual(pruefung(gut, "haken")["stufe"], "ok")
        schlecht = rd.messen("Liebe Leute, " + "heute wieder ein ganz langer Anlauf mit vielen Wörtern und Nebensätzen, " * 3 + "bis endlich etwas kommt.")
        self.assertNotEqual(pruefung(schlecht, "haken")["stufe"], "ok")

    def test_absaetze_und_ki_muster(self):
        wand = " ".join(["Das ist ein Satz mit acht Wörtern hier."] * 15)
        self.assertEqual(pruefung(rd.messen(wand), "absaetze")["stufe"], "fehler")
        m = rd.messen(SCHWACH)
        self.assertNotEqual(pruefung(m, "ki_muster")["stufe"], "ok")

    def test_emojis_nur_hinweis(self):
        m1, m2 = rd.messen("Ein klarer Satz mit Inhalt."), rd.messen("Ein klarer Satz mit Inhalt. 🚀")
        self.assertEqual(m1["punkte"], m2["punkte"])
        self.assertTrue(pruefung(m2, "emojis")["info"])

    def test_beitragsart(self):
        self.assertIn("Text-Beitrag", pruefung(rd.messen("Nur Text."), "art")["messwert"])
        self.assertIn("Link-Beitrag", pruefung(rd.messen("Text. https://example.org"), "art")["messwert"])


class FesteKorrekturen(unittest.TestCase):
    def test_ohne_erlaubnis_bleiben_links_und_hashtags(self):
        t, aend = rd.feste_korrekturen("Das ist **fett**.\n\n\n\nLies https://example.org/x hier. #A #B #C #D", False)
        self.assertNotIn("**", t)
        self.assertNotIn("\n\n\n", t)
        self.assertIn("https://example.org/x hier", t)
        self.assertEqual(rd.HASHTAG.findall(t), ["A", "B", "C", "D"])
        self.assertEqual(len(aend), 2)

    def test_unicode_fett_wird_normal(self):
        t, aend = rd.feste_korrekturen("Ich bin 𝐂𝐥𝐨𝐮𝐝 𝐀𝐫𝐜𝐡𝐢𝐭𝐞𝐤𝐭 geworden.", False)
        self.assertEqual(t, "Ich bin Cloud Architekt geworden.")
        self.assertTrue(aend)

    def test_mit_erlaubnis_adresse_hinter_den_text_hashtags_auf_drei(self):
        t, aend = rd.feste_korrekturen("Lies https://example.org/x hier. Wir nutzen #Cloud im Alltag. #A #B #C #D", True)
        text, tags = t.split("\n\n")
        self.assertTrue(text.endswith("im Alltag. https://example.org/x"))
        self.assertIn("(Link am Ende)", text)
        self.assertIn("Wir nutzen Cloud im Alltag.", text)
        self.assertEqual(tags, "#Cloud #A #B")
        self.assertTrue(any("gestrichen" in a["was"] for a in aend))
        m = rd.messen(t)
        self.assertEqual(pruefung(m, "link")["stufe"], "ok")
        self.assertEqual(pruefung(m, "hashtags")["stufe"], "ok")

    def test_alte_form_wird_umgestellt(self):
        t, _ = rd.feste_korrekturen("Ein Satz.\n\nhttps://example.org/x\n\n#A", True)
        self.assertEqual(t, "Ein Satz. https://example.org/x\n\n#A")
        t, aend = rd.feste_korrekturen("Ein Satz. https://example.org/x\n\n#A", True)
        self.assertEqual(t, "Ein Satz. https://example.org/x\n\n#A")
        self.assertEqual(aend, [])


class Schutzpruefung(unittest.TestCase):
    def test_zahlen_links_erwaehnungen_hashtags_zitate_namen(self):
        self.assertTrue(rd.schutzpruefung("mit 12 Leuten", "mit 15 Leuten"))
        self.assertTrue(rd.schutzpruefung("siehe https://a.example/x", "siehe https://a.example/y"))
        self.assertTrue(rd.schutzpruefung("Danke @Anna_B für alles", "Danke für alles"))
        self.assertTrue(rd.schutzpruefung("Wir lieben #Cloud", "Wir lieben die Cloud"))
        self.assertTrue(rd.schutzpruefung("Sie sagte „das hält nie“ dazu", "Sie sagte „das hält kaum“ dazu"))
        self.assertTrue(rd.schutzpruefung("Wir setzen Kubernetes und OpenShift ein", "Wir setzen Kubernetes und Docker ein"))
        self.assertEqual(rd.schutzpruefung("Kurz vorweg – das ist wirklich gut.", "Das ist gut."), [])

    def test_straffen_darf_weglassen_aber_nichts_erfinden(self):
        self.assertEqual(rd.schutzpruefung("Wir waren 12 Leute in 3 Teams.", "Wir waren 12 Leute.", weglassen_erlaubt=True), [])
        self.assertTrue(rd.schutzpruefung("Wir waren 12 Leute.", "Wir waren 14 Leute.", weglassen_erlaubt=True))
        self.assertTrue(rd.schutzpruefung("Wir waren 12 Leute.", "Wir waren 12 Leute bei SAP.", weglassen_erlaubt=True))

    def test_aenderungen_einzeln_verworfen(self):
        rumpf = "Kurz vorweg – das ist wirklich gut. Wir waren 12 Leute."
        neu, an, weg = rd.wende_aenderungen_an(rumpf, [
            {"alt": "Kurz vorweg – das ist wirklich gut.", "neu": "Das ist gut.", "grund": "Floskel"},
            {"alt": "Wir waren 12 Leute.", "neu": "Wir waren 20 Leute.", "grund": "falsch"},
            {"alt": "steht nicht im Text", "neu": "x", "grund": "?"},
        ])
        self.assertEqual(neu, "Das ist gut. Wir waren 12 Leute.")
        self.assertEqual(len(an), 1)
        self.assertEqual(len(weg), 2)
        self.assertIn("Zahlen", weg[0]["warum"])
        self.assertIn("nicht", weg[1]["warum"])


class Durchlauf(unittest.TestCase):
    def test_nur_pruefen_ruft_kein_llm(self):
        with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x"}), \
                mock.patch.object(llm, "chat", side_effect=AssertionError("kein LLM-Aufruf erlaubt")) as c:
            e = rd.verarbeite(SCHWACH, "pruefen")
        c.assert_not_called()
        self.assertIsNone(e["vorschlag"])
        self.assertEqual(e["aufrufe"], 0)
        self.assertTrue(e["offen"])

    def test_ohne_ausdrueckliche_einstellung_kein_llm(self):
        env = {k: v for k, v in os.environ.items() if k != "REDAKTOR_LLM_MODUS"}
        env["BLOG_LLM_API_KEY"] = "x"
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(llm, "chat", side_effect=AssertionError) as c:
            self.assertEqual(rd.einstellungen()["llm_modus"], "aus")
            e = rd.verarbeite(SCHWACH, "behutsam")
        c.assert_not_called()
        self.assertEqual(e["modus"], "pruefen")
        self.assertIn("ausgeschaltet", e["meldung"])

    def test_behutsam_mit_stub(self):
        antwort = json.dumps({"aenderungen": [
            {"alt": "Kurz vorweg – ich bin wirklich begeistert!", "neu": "Ich bin begeistert.", "grund": "Floskel", "art": "ki_muster"},
            {"alt": "mit 12 Leuten", "neu": "mit 15 Leuten", "grund": "x", "art": "fehler"}], "offen": []})
        with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x"}), \
                mock.patch.object(llm, "chat", side_effect=stub(antwort)):
            e = rd.verarbeite(SCHWACH, "behutsam", aufbau_erlaubt=True)
        self.assertIn("Ich bin begeistert.", e["vorschlag"])
        self.assertIn("12 Leuten", e["vorschlag"])
        self.assertEqual(len(e["verworfen"]), 1)
        self.assertGreater(e["nachher"]["punkte"], e["vorher"]["punkte"])
        self.assertTrue(any(a == "neu" for a, _ in e["diff"]))

    def test_eskalation_bei_ungueltigem_json(self):
        modelle: list = []
        with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x", "BLOG_LLM_MODEL_STARK": "stark-m",
                                          "BLOG_LLM_MODEL_MAX": "max-m"}), \
                mock.patch.object(llm, "chat", side_effect=stub("kein json " + MARKE, modelle)):
            e = rd.verarbeite(SCHWACH, "behutsam")
        self.assertEqual(modelle, ["stark-m", "stark-m", "max-m", "max-m"])  # je Stufe: Aufruf + eine Nachfrage
        self.assertIn("nicht verwertbar", e["meldung"])

    def test_json_mit_deutschen_anfuehrungszeichen(self):
        roh = '```json\n{"aenderungen": [{"alt": "a", "neu": "b", "grund": "Floskeln „Kurz vorweg", „Der Punkt ist" entfernt"}], "offen": []}\n```'
        self.assertEqual(rd.json_ohne_ablage(roh)["aenderungen"][0]["neu"], "b")

    def test_verbindungsfehler_meldet_klar(self):
        with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x"}), \
                mock.patch.object(llm, "chat", side_effect=llm.LLMVerbindung("weg")):
            e = rd.verarbeite(SCHWACH, "straffen", ziel=300)
        self.assertIn("nicht erreichbar", e["meldung"])
        self.assertIsNotNone(e["vorschlag"])

    def test_straffen_verwirft_erfundene_zahl(self):
        antwort = json.dumps({"text": "Wir waren 99 Leute.", "aenderungen": [], "offen": []})
        with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x"}), \
                mock.patch.object(llm, "chat", side_effect=stub(antwort)) as c:
            e = rd.verarbeite(SCHWACH, "straffen", ziel=300)
        self.assertEqual(c.call_count, 2)
        self.assertNotIn("99", e["vorschlag"])
        self.assertIn("verworfen", e["meldung"])

    def test_llm_aufruf_nutzt_kurze_wartezeiten_und_starke_stufe(self):
        aufrufe = []
        def f(*a, **k):
            aufrufe.append(k)
            return llm.Antwort(json.dumps({"aenderungen": [], "offen": []}))
        with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x"}), mock.patch.object(llm, "chat", side_effect=f):
            rd.verarbeite(SCHWACH, "behutsam")
        self.assertEqual(aufrufe[0]["wartezeiten"], rd.WARTEZEITEN)
        self.assertEqual(aufrufe[0]["modell"], llm.modell_fuer("text_umschreiben"))


class Ratenbegrenzung(unittest.TestCase):
    def test_je_ip_und_fenster(self):
        r = rd.Ratenbegrenzer(fenster_s=3600)
        t0 = 1000.0
        self.assertTrue(all(r.zulassen("1.2.3.4", 3, t0 + i) for i in range(3)))
        self.assertFalse(r.zulassen("1.2.3.4", 3, t0 + 10))
        self.assertTrue(r.zulassen("5.6.7.8", 3, t0 + 10))
        self.assertTrue(r.zulassen("1.2.3.4", 3, t0 + 3601))

    def test_tageszaehler(self):
        with tempfile.TemporaryDirectory() as d:
            z = rd.Zaehler(Path(d) / "z.json")
            for _ in range(3):
                z.buchen({"laenge": 10, "modus": "pruefen", "dauer_s": 0.1, "text": "darf nicht rein", "ip": "1.2.3.4"})
            self.assertEqual(z.heute(), 3)
            inhalt = (Path(d) / "z.json").read_text()
            self.assertNotIn("darf nicht rein", inhalt)
            self.assertNotIn("1.2.3.4", inhalt)


class Seite(unittest.TestCase):
    """Flask-Testclient. Zähler in einem Wegwerf-Verzeichnis."""

    @classmethod
    def setUpClass(cls):
        import app as appmod
        import redaktor_views as rv
        cls.rv = rv
        cls.c_app = appmod.app

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"REDAKTOR_CODE": "geheim-123", "REDAKTOR_LIMIT_STUNDE_IP": "3", "REDAKTOR_LIMIT_TAG": "5",
                                                "REDAKTOR_FEHLVERSUCHE_STUNDE": "3", "REDAKTOR_LLM_MODUS": "aus"})
        self.env.start()
        self.z = mock.patch.object(self.rv, "zaehler", rd.Zaehler(Path(self.tmp.name) / "zaehler.json"))
        self.z.start()
        self.rv.begrenzer.leeren()
        self.rv.fehlversuche.leeren()
        self.c = self.c_app.test_client()

    def tearDown(self):
        self.z.stop()
        self.env.stop()
        self.tmp.cleanup()

    def anmelden(self, basis="/redaktor", ip="10.0.0.1") -> str:
        r = self.c.post(basis + "/anmelden", data={"code": "geheim-123"}, headers={"X-Forwarded-For": ip})
        self.assertEqual(r.status_code, 302)
        r = self.c.get(basis + "/")
        return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)

    def test_ohne_code_kein_zugang(self):
        r = self.c.get("/redaktor/")
        self.assertIn("Zugangscode", r.text)
        self.assertNotIn('name="text"', r.text)
        r = self.c.post("/redaktor/pruefen", data={"text": "x", "modus": "pruefen"})
        self.assertEqual(r.status_code, 302)

    def test_code_nicht_gesetzt(self):
        with mock.patch.dict(os.environ, {"REDAKTOR_CODE": ""}):
            r = self.c.post("/redaktor/anmelden", data={"code": ""})
            self.assertEqual(r.status_code, 503)

    def test_falscher_code_und_sperre(self):
        for _ in range(3):
            self.assertEqual(self.c.post("/redaktor/anmelden", data={"code": "falsch"}, headers={"X-Forwarded-For": "10.9.9.9"}).status_code, 403)
        r = self.c.post("/redaktor/anmelden", data={"code": "geheim-123"}, headers={"X-Forwarded-For": "10.9.9.9"})
        self.assertEqual(r.status_code, 429)

    def test_codewechsel_beendet_sitzungen(self):
        self.anmelden()
        with mock.patch.dict(os.environ, {"REDAKTOR_CODE": "neuer-code"}):
            self.assertNotIn('name="text"', self.c.get("/redaktor/").text)

    def test_csrf_pflicht(self):
        self.anmelden()
        r = self.c.post("/redaktor/pruefen", data={"text": "Hallo Welt.", "modus": "pruefen", "csrf": "falsch"})
        self.assertEqual(r.status_code, 403)

    def test_pruefen_und_ratenbegrenzung(self):
        csrf = self.anmelden()
        for _ in range(3):
            r = self.c.post("/redaktor/pruefen", data={"text": SCHWACH, "modus": "pruefen", "csrf": csrf}, headers={"X-Forwarded-For": "10.0.0.1"})
            self.assertEqual(r.status_code, 200)
            self.assertIn("Prüfliste", r.text)
        r = self.c.post("/redaktor/pruefen", data={"text": SCHWACH, "modus": "pruefen", "csrf": csrf}, headers={"X-Forwarded-For": "10.0.0.1"})
        self.assertEqual(r.status_code, 429)
        # Tageslimit (5) gilt gesamt, über alle IPs
        for ip in ("10.0.0.2", "10.0.0.3"):
            self.assertEqual(self.c.post("/redaktor/pruefen", data={"text": SCHWACH, "modus": "pruefen", "csrf": csrf},
                                         headers={"X-Forwarded-For": ip}).status_code, 200)
        r = self.c.post("/redaktor/pruefen", data={"text": SCHWACH, "modus": "pruefen", "csrf": csrf}, headers={"X-Forwarded-For": "10.0.0.4"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Tageskontingent", r.text)

    def test_textlaenge_begrenzt(self):
        csrf = self.anmelden()
        r = self.c.post("/redaktor/pruefen", data={"text": "x" * 3501, "modus": "pruefen", "csrf": csrf})
        self.assertEqual(r.status_code, 413)

    def test_betreiberhinweis_nur_intern_und_keine_verwaltungslinks(self):
        csrf = self.anmelden()
        r = self.c.post("/redaktor/pruefen", data={"text": SCHWACH, "modus": "pruefen", "csrf": csrf})
        self.assertNotIn("Nur für den Betreiber", r.text)
        self.assertNotIn("/verwaltung", r.text)
        self.assertNotIn("X-Blog", r.text)
        h = {"X-Blog-Verwaltung-Intern": "1"}
        self.c.post("/verwaltung/redaktor/anmelden", data={"code": "geheim-123"}, headers=h)
        r = self.c.get("/verwaltung/redaktor/", headers=h)
        self.assertIn("Nur für den Betreiber", r.text)
        self.assertIn("nicht geprüft", r.text)

    def test_kein_speichern_von_texten(self):
        """Der Eingabetext (mit Marke) darf nach einem Lauf in keiner Datei unter data/ oder im Wegwerf-Verzeichnis
        und in keiner Logausgabe auftauchen - auch nicht bei ungültiger KI-Antwort (llm_fehler-Ablage)."""
        start = time.time() - 1
        csrf = self.anmelden()
        logpuffer = []

        class Fang(logging.Handler):
            def emit(self, record):
                logpuffer.append(record.getMessage())

        h = Fang()
        logging.getLogger().addHandler(h)
        logging.getLogger("werkzeug").addHandler(h)
        try:
            text = SCHWACH + " " + MARKE
            with mock.patch.dict(os.environ, {"REDAKTOR_LLM_MODUS": "abo", "BLOG_LLM_API_KEY": "x"}), \
                    mock.patch.object(llm, "chat", side_effect=stub("kaputt { " + MARKE)):
                r = self.c.post("/redaktor/pruefen", data={"text": text, "modus": "behutsam", "csrf": csrf})
                self.assertEqual(r.status_code, 200)
            self.c.post("/redaktor/pruefen", data={"text": text, "modus": "pruefen", "csrf": csrf})
        finally:
            logging.getLogger().removeHandler(h)
            logging.getLogger("werkzeug").removeHandler(h)
        self.assertFalse([m for m in logpuffer if MARKE in m])
        gefunden = []
        for basis in (ROOT / "data", Path(self.tmp.name), ROOT / "logs"):
            if not basis.exists():
                continue
            for p in basis.rglob("*"):
                try:
                    if p.is_file() and p.stat().st_mtime >= start and p.stat().st_size < 5_000_000 and MARKE in p.read_text(errors="ignore"):
                        gefunden.append(str(p))
                except OSError:
                    pass
        self.assertEqual(gefunden, [])
        inhalt = (Path(self.tmp.name) / "zaehler.json").read_text()
        self.assertIn('"laenge"', inhalt)
        self.assertNotIn("Kurz vorweg", inhalt)


if __name__ == "__main__":
    unittest.main()
