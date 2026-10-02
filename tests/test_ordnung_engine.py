"""Tests fuer die Mehrrunden-Engine (ordnung_engine.py): gestubbtes LLM, Wegwerf-Artikel, keine echten Dateien."""

import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import bewertung as bw  # noqa: E402
import build  # noqa: E402
import in_ordnung as io  # noqa: E402
import ordnung_engine as eng  # noqa: E402
from ranking_daten import Speicher  # noqa: E402

LANG1 = ("Das ist ein erster Satz mit sehr vielen Wörtern, der immer weiter geht, weil er noch einen Nebensatz hat, und dann noch einen, "
         "damit er sicher deutlich über fünfundzwanzig Wörter kommt und trotzdem harmlos bleibt.")
LANG2 = ("Der zweite Absatz hat ebenfalls einen sehr langen Satz, der kein Ende kennt, weil immer weitere Gedanken dranhängen, "
         "die man eigentlich in eigene Sätze packen sollte, damit der Text leichter lesbar wird, und so weiter und so fort.")
ARTIKEL = f"""---
title: "Ein sehr langer Titel, der weit über die erlaubten siebzig Zeichen hinausgeht und daher gekürzt werden muss"
slug: test-artikel
date: 2026-09-28
description: "kurz"
tags: [Monitoring, Firewall]
---

## Erster Abschnitt

<p>{LANG1}</p>
<p>{LANG2}</p>

## Zweiter Abschnitt

<p>Der dritte Absatz ist kurz. Er handelt vom Monitoring der Firewall in einem Homelab mit vielen Geräten und Diensten.</p>
"""
TITEL_OK = "Monitoring im Homelab: Firewall, Tunnel und KI im Zusammenspiel"
BESCHR_OK = "Offene Ports, volle Speicher, ablaufende Zertifikate: ein KI-Server erkennt, priorisiert und behebt, bevor ein Mensch eingreifen muss."


def kuerzen(alt: str) -> str:
    return alt.replace(", weil", ". Es gilt, weil", 1).replace(", damit", ". Damit", 1).replace(", die man", ". Die man", 1).replace(", und dann", ". Dann", 1)


class Wegwerf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "articles").mkdir()
        (self.root / "static" / "img").mkdir(parents=True)
        (self.root / "dist" / "artikel" / "test-artikel").mkdir(parents=True)
        self.pfad = self.root / "articles" / "test-artikel.md"
        self.pfad.write_text(ARTIKEL, encoding="utf-8")
        self.speicher = Speicher(self.root)
        io._aktiv.clear()

    def tearDown(self):
        io._aktiv.clear()
        self.tmp.cleanup()

    def bewerte_text(self, text):
        p = self.root / "entwurf.md"
        p.write_text(text, encoding="utf-8")
        meta = build.parse_article(p)
        return bw.bewerte(meta, build.render_markdown(meta["body_md"]), base_url="https://example.invalid", static_dir=self.root / "static",
                          dist_dir=self.root / "dist", heute=date(2026, 10, 1), alle_slugs=["test-artikel", "anderer"])

    def ctx(self, chat, simuliere=True, quellen=None):
        aufrufe = {"sim": 0}

        def sim(slug, text):
            aufrufe["sim"] += 1
            return self.bewerte_text(text)
        self.aufrufe = aufrufe
        return io.Kontext(root=self.root, speicher=self.speicher, chat=chat, bewerte=lambda slug: (build.parse_article(self.pfad), self.bewerte_text(self.pfad.read_text(encoding="utf-8"))),
                          simuliere=sim if simuliere else (lambda s, t: None), baue=lambda: (True, "ok"),
                          quellen=(lambda: quellen or {}))


def text_antworten(prompt: str, aendern=kuerzen) -> dict:
    stellen = []
    for m in re.finditer(r"### Stelle (\d+)\n.*?Text:\n<<<\n(.*?)\n>>>", prompt, re.S):
        alt = m.group(2)
        stellen.append({"id": int(m.group(1)), "alt": " ".join(alt.split()[:8]), "neu": aendern(alt)})
    return {"stellen": stellen}


class Runden(Wegwerf):
    def chat_basis(self):
        self.prompts = []

        def chat(system, nutzer, **kw):
            self.prompts.append(nutzer)
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps(text_antworten(nutzer))
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        return chat

    def test_mehrere_runden_bis_lange_saetze_gruen(self):
        ok, _ = io.starte(self.ctx(self.chat_basis()), "test-artikel", hintergrund=False)
        self.assertTrue(ok)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(z["status"], "vorschlag", z.get("meldung"))
        self.assertGreaterEqual(len(z["runden"]), 2)  # Bewerten -> Verbessern -> erneut bewerten
        vorher, erwartet = z["vorher"]["kriterien"], z["erwartet"]["kriterien"]
        self.assertNotEqual(vorher["b_lange_saetze"]["status"], "ok")
        self.assertEqual(erwartet["b_lange_saetze"]["status"], "ok")
        self.assertEqual(erwartet["a_titel"]["status"], "ok")
        self.assertEqual(erwartet["a_beschr"]["status"], "ok")
        self.assertGreater(z["erwartet"]["gesamt"], z["vorher"]["gesamt"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), ARTIKEL)  # nichts geschrieben

    def test_gruppen_und_stellen_haben_ort(self):
        io.starte(self.ctx(self.chat_basis()), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertTrue(z["stellen"])
        for s in z["stellen"]:
            self.assertIn(s["gruppe"], [g for g, _n in eng.GRUPPEN])
            self.assertTrue(s["abschnitt"])
            self.assertEqual(s["alt"], ARTIKEL[s["start"]:s["ende"]])

    def test_abbruch_bei_fehlendem_fortschritt(self):
        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps(text_antworten(nutzer, aendern=lambda alt: alt))  # unveraendert -> abgelehnt
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertLessEqual(len(z["runden"]), 3)  # Metas in Runde 1, danach kein Fortschritt mehr
        self.assertTrue(z["stellen_abgelehnt"])
        self.assertIn("unverändert", z["stellen_abgelehnt"][0]["grund"])
        self.assertTrue(any(o["id"] == "b_lange_saetze" for o in z["offen_erwartet"]))

    def test_nachversuch_mit_konkreter_rueckmeldung(self):
        aufrufe = []

        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                aufrufe.append(nutzer)
                if "ACHTUNG, dein letzter Versuch" not in nutzer:
                    return json.dumps(text_antworten(nutzer, aendern=lambda alt: kuerzen(alt).replace("fünfundzwanzig", "dreissig").replace("so weiter", "so fort 99")))
                return json.dumps(text_antworten(nutzer))
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertTrue(any("ACHTUNG, dein letzter Versuch" in a for a in aufrufe))
        self.assertTrue(any("Zahlen" in a or "Fachbegriffe" in a for a in aufrufe if "ACHTUNG" in a))
        self.assertTrue(z["stellen"])

    def test_ungueltiges_json_wird_einmal_wiederholt(self):
        zaehler = {"n": 0}

        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                zaehler["n"] += 1
                if zaehler["n"] == 1:
                    return "das ist kein json {"
                return json.dumps(text_antworten(nutzer))
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertTrue(z["stellen"])

    def test_ohne_simulation_eine_runde(self):
        io.starte(self.ctx(self.chat_basis(), simuliere=False), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(len(z["runden"]), 1)
        self.assertIn(z["status"], ("vorschlag", "keine_vorschlaege"))

    def test_frist_liefert_zwischenstand(self):
        ctx = self.ctx(self.chat_basis())
        ctx.frist = 0.0001
        io.starte(ctx, "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertIn(z["status"], ("vorschlag", "keine_vorschlaege", "abgebrochen"))
        self.assertFalse(io.ist_gesperrt("test-artikel"))

    def test_metas_bestbewertete_kombination(self):
        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps({"stellen": []})
            return json.dumps({"titel": [TITEL_OK, "Monitoring und Firewall im Homelab: der KI-Server, der mitdenkt"],
                               "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertIn("title", z["meta_standard"])
        self.assertIn("description", z["meta_standard"])
        self.assertFalse(z["meta_standard"]["description"].startswith(("…", "...")))


class Links(Wegwerf):
    QUELLEN = {"anderer": {"slug": "anderer", "title": "Monitoring mit Netdata", "tags": ["Monitoring"], "description": "Netdata im Homelab.", "date": "2026-09-01"},
               "test-artikel": {"slug": "test-artikel", "title": "x", "tags": ["Monitoring"], "description": "y", "date": "2026-09-28"}}

    def test_fuege_link_ein_html_und_md(self):
        h = eng.fuege_link_ein("html", "Das Monitoring der <strong>Firewall</strong> läuft.", "Monitoring der", "/artikel/anderer/")
        self.assertEqual(h, 'Das <a href="/artikel/anderer/">Monitoring der</a> <strong>Firewall</strong> läuft.')
        m = eng.fuege_link_ein("md", "Das Monitoring der Firewall läuft.", "Monitoring der Firewall", "/artikel/anderer/")
        self.assertEqual(m, "Das [Monitoring der Firewall](/artikel/anderer/) läuft.")

    def test_fuege_link_ein_lehnt_unklare_stellen_ab(self):
        self.assertIsNone(eng.fuege_link_ein("html", "Monitoring und noch mal Monitoring.", "Monitoring", "/artikel/a/"))  # zweimal
        self.assertIsNone(eng.fuege_link_ein("html", 'Siehe <a href="/x/">Monitoring heute</a>.', "Monitoring heute", "/artikel/a/"))  # schon Link
        self.assertIsNone(eng.fuege_link_ein("html", "Text <code>Monitoring Tool</code> hier.", "Monitoring Tool", "/artikel/a/"))
        self.assertIsNone(eng.fuege_link_ein("html", "Kein Treffer hier.", "Nichts davon", "/artikel/a/"))
        self.assertIsNone(eng.fuege_link_ein("md", "Ein `Monitoring Tool` hier.", "Monitoring Tool", "/artikel/a/"))

    def test_verwandte_artikel_nie_selbst(self):
        v = eng.verwandte_artikel(self.QUELLEN["test-artikel"], self.QUELLEN)
        self.assertEqual([x["slug"] for x in v], ["anderer"])

    def test_schutzpruefung_erlaubt_nur_neue_interne_links(self):
        alt = 'Das Monitoring läuft, siehe <a href="https://x.example/a">Quelle</a>.'
        mit = 'Das <a href="/artikel/anderer/">Monitoring</a> läuft, siehe <a href="https://x.example/a">Quelle</a>.'
        self.assertEqual(io.schutzpruefung_stelle(alt, mit, ["link"], links=("/artikel/anderer/",)), [])
        # ohne ausdrueckliche Erlaubnis: abgelehnt
        self.assertTrue(io.schutzpruefung_stelle(alt, mit, ["link"]))
        # anderer Link als erlaubt
        self.assertTrue(io.schutzpruefung_stelle(alt, mit.replace("anderer", "fremd"), ["link"], links=("/artikel/anderer/",)))
        # bestehenden Link entfernt
        self.assertTrue(io.schutzpruefung_stelle(alt, 'Das <a href="/artikel/anderer/">Monitoring</a> läuft, siehe Quelle.', ["link"], links=("/artikel/anderer/",)))
        # neuer externer Link
        self.assertTrue(io.schutzpruefung_stelle(alt, mit.replace("/artikel/anderer/", "https://neu.example/"), ["link"], links=("/artikel/anderer/",)))

    def test_links_runde_setzt_link_im_durchlauf(self):
        def chat(system, nutzer, **kw):
            if "Setze 1 bis" in nutzer:
                return json.dumps({"links": [{"id": 3, "ankertext": "Monitoring der Firewall", "artikel": "anderer"},
                                             {"id": 1, "ankertext": "gibt es nicht", "artikel": "anderer"},
                                             {"id": 2, "ankertext": "Nebensatz", "artikel": "test-artikel"}]})
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps({"stellen": []})
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat, quellen=self.QUELLEN), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        links = [s for s in z["stellen"] if "link" in s["zweck"]]
        self.assertEqual(len(links), 1)
        self.assertIn('<a href="/artikel/anderer/">Monitoring der Firewall</a>', links[0]["neu"])
        self.assertEqual(links[0]["gruppe"], "links")
        self.assertEqual(z["erwartet"]["kriterien"]["e_intern"]["status"], "ok")
        self.assertNotIn("test-artikel/", links[0]["neu"])


class Gruppen(unittest.TestCase):
    def test_behebbar_und_mensch(self):
        snap = {"kriterien": {"b_lange_saetze": {"status": "nein"}, "d_alt": {"status": "nein"}, "a_alt": {"status": "nein"},
                              "e_intern": {"status": "nein"}, "a_dist": {"status": "nein"}, "a_titel": {"status": "ok"}}}
        self.assertEqual(sorted(eng.behebbar(snap, hat_bild=True)), ["a_alt", "b_lange_saetze", "e_intern"])
        self.assertEqual(sorted(eng.behebbar(snap, hat_bild=False)), ["b_lange_saetze", "e_intern"])

    def test_offen_nach_lauf_trennt_behebbar_und_mensch(self):
        snap = {"kriterien": {"b_lange_saetze": {"status": "teils", "name": "x", "messwert": "m", "kat": "B"},
                              "d_alt": {"status": "nein", "name": "Alt-Texte", "messwert": "0 von 3", "kat": "D"}}}
        offen = eng.offen_nach_lauf(snap, True, True)
        arten = {o["id"]: o["art"] for o in offen}
        self.assertEqual(arten, {"b_lange_saetze": "behebbar", "d_alt": "mensch"})
        self.assertIn("Alt-Text", next(o for o in offen if o["id"] == "d_alt")["grund"])


if __name__ == "__main__":
    unittest.main()


class Modellwahl(Wegwerf):
    UMGEBUNG = ("BLOG_LLM_MODEL", "BLOG_LLM_MODEL_STARK", "BLOG_LLM_MODEL_MAX")

    def setUp(self):
        super().setUp()
        import os
        self.alt = {k: os.environ.get(k) for k in self.UMGEBUNG}
        for k in self.UMGEBUNG:
            os.environ.pop(k, None)

    def tearDown(self):
        import os
        for k, v in self.alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def test_stufen_und_fallback(self):
        import llm
        import os
        self.assertEqual(llm.modell_fuer("metas"), llm.STANDARD_MODELL)
        self.assertEqual(llm.modell_fuer(None), llm.STANDARD_MODELL)  # Altaufruf ohne Aufgabe
        self.assertEqual(llm.modell_fuer("lektorat"), "claude-opus-4-6")  # Vorgabe der starken Stufe
        self.assertEqual(llm.modell_fuer("text_umschreiben"), "claude-opus-4-6")
        self.assertEqual(llm.modell_fuer("tiefenanalyse"), "claude-opus-4-6")  # max leer -> naechstniedrigere
        os.environ["BLOG_LLM_MODEL_MAX"] = "claude-fable"
        self.assertEqual(llm.modell_fuer("tiefenanalyse"), "claude-fable")
        os.environ["BLOG_LLM_MODEL"] = "claude-sonnet-x"
        self.assertEqual(llm.modell_fuer("plattform"), "claude-sonnet-x")
        os.environ["BLOG_LLM_MODEL_STARK"] = "claude-opus-x"
        self.assertEqual(llm.modell_fuer("gegenlesen"), "claude-opus-x")

    def test_eskalation_nur_nach_oben(self):
        import llm
        import os
        self.assertEqual(llm.eskalations_modell("metas")[0], "claude-opus-4-6")
        self.assertIsNone(llm.eskalations_modell("lektorat"))  # max = stark: keine hoehere Stufe, nie nach unten
        self.assertIsNone(llm.eskalations_modell("text_umschreiben"))
        os.environ["BLOG_LLM_MODEL_MAX"] = "claude-fable"
        self.assertEqual(llm.eskalations_modell("text_umschreiben"), ("claude-fable", "max"))
        self.assertIsNone(llm.eskalations_modell("tiefenanalyse"))

    def test_metas_eskaliert_einmal_und_protokolliert(self):
        modelle = []
        zu_lang = "Seit 2010 " + "a" * 190

        def chat(system, nutzer, **kw):
            modelle.append(kw.get("modell") or "standard")
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps({"stellen": []})
            if kw.get("modell"):  # hoehere Stufe liefert Gueltiges
                return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [zu_lang, zu_lang + "b", zu_lang + "c"], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertIn("claude-opus-4-6", modelle)
        self.assertEqual(sum(1 for m in modelle if m == "claude-opus-4-6") >= 1, True)
        self.assertTrue(any("eskaliert von" in p and "Grund" in p for p in z["protokoll"]), z.get("protokoll"))
        self.assertTrue(z["meta_standard"].get("description"))
        # genau eine Eskalation je Aufgabe
        self.assertEqual(len([p for p in z["protokoll"] if p.startswith("metas:")]), 1)

    def test_text_wird_nie_nach_unten_gewechselt_und_ohne_hoehere_stufe_nicht_eskaliert(self):
        modelle = []

        def chat(system, nutzer, **kw):
            modelle.append(kw.get("modell"))
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps(text_antworten(nutzer, aendern=lambda alt: alt))  # scheitert immer
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertFalse([p for p in z.get("protokoll", []) if p.startswith("text_umschreiben")])  # max == stark: nichts hoeher
        self.assertEqual(z["modelle"]["text"], "claude-opus-4-6")

    def test_text_eskaliert_wenn_hoehere_stufe_existiert(self):
        import os
        os.environ["BLOG_LLM_MODEL_MAX"] = "claude-fable"
        modelle = []

        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                modelle.append(kw.get("modell"))
                if kw.get("modell") == "claude-fable":
                    return json.dumps(text_antworten(nutzer))
                return json.dumps(text_antworten(nutzer, aendern=lambda alt: alt))
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertIn("claude-fable", modelle)
        self.assertEqual(len([p for p in z["protokoll"] if p.startswith("text_umschreiben")]), 1)
        self.assertTrue(z["stellen"])

    def test_abgeschnittene_antwort_wird_geteilt(self):
        import llm
        aufrufe = []

        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                n = len(re.findall(r"### Stelle", nutzer))
                aufrufe.append(n)
                if n > 1:
                    raise llm.LLMAbgeschnitten("LLM-Antwort enthielt kein gültiges JSON (abgeschnitten)")
                return json.dumps(text_antworten(nutzer))
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertIn(1, aufrufe)
        self.assertTrue(z["stellen"])  # trotz Abschneiden Ergebnis durch Teilen

    def test_json_aus_text_meldet_abgeschnitten(self):
        import llm
        with self.assertRaises(llm.LLMAbgeschnitten):
            llm.json_aus_text('{"stellen": [{"id": 1, "neu": "halber Sa')
        with self.assertRaises(llm.LLMFehler):
            try:
                llm.json_aus_text("kein json")
            except llm.LLMAbgeschnitten:
                self.fail("kein Abschneiden")


class Auswahl(Wegwerf):
    def lauf(self):
        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps(text_antworten(nutzer))
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        ctx = self.ctx(chat)
        io.starte(ctx, "test-artikel", hintergrund=False)
        return ctx

    def test_wirkung_bei_abwahl_zeigt_wieder_rote_kriterien(self):
        ctx = self.lauf()
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        alle = {s["id"] for s in z["stellen"]}
        self.assertTrue(alle)
        voll = io.wirkung(ctx, "test-artikel", dict(z["meta_standard"]), alle)
        self.assertTrue(voll["ok"], voll)
        w = self.speicher.lesen("inordnung", "test-artikel.json")["wirkung_auswahl"]
        self.assertEqual(w["rot"], [])  # alles an = so gruen wie erwartet
        ohne = io.wirkung(ctx, "test-artikel", dict(z["meta_standard"]), set())
        self.assertTrue(ohne["ok"])
        w = self.speicher.lesen("inordnung", "test-artikel.json")["wirkung_auswahl"]
        self.assertIn("b_lange_saetze", [r["id"] for r in w["rot"]])
        self.assertLess(w["snap"]["gesamt"], z["erwartet"]["gesamt"])
        self.assertEqual(w["ids"], [])
        # der Artikel selbst bleibt unberuehrt
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), ARTIKEL)

    def test_wirkung_ohne_vorschlag_oder_bei_geaendertem_artikel(self):
        ctx = self.ctx(lambda *a, **k: "{}")
        self.assertFalse(io.wirkung(ctx, "test-artikel", {}, set())["ok"])
        ctx = self.lauf()
        self.pfad.write_text(ARTIKEL + "\nNachtrag.\n", encoding="utf-8")
        self.assertFalse(io.wirkung(ctx, "test-artikel", {}, set())["ok"])

    def test_uebernehmen_mit_links_und_absatz_stellen_validiert_neu(self):
        ctx = self.lauf()
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        s = z["stellen"][0]
        s["neu_inner"] = s["neu_inner"].replace("Wörter", "Wörter 77")  # Zahl eingeschmuggelt
        self.speicher.schreiben(z, "inordnung", "test-artikel.json")
        erg = io.uebernehmen(ctx, "test-artikel", {}, {s["id"]})
        self.assertFalse(erg["ok"])
        self.assertIn("Zahlen", erg["meldung"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), ARTIKEL)


class Warteschlange(Wegwerf):
    def test_nur_ein_auftrag_gleichzeitig_und_reihenfolge(self):
        import threading
        import time
        (self.root / "articles" / "zweiter.md").write_text(ARTIKEL.replace("test-artikel", "zweiter"), encoding="utf-8")
        gleichzeitig = {"jetzt": 0, "max": 0}
        sperre = threading.Lock()
        reihenfolge = []

        def chat(system, nutzer, **kw):
            with sperre:
                gleichzeitig["jetzt"] += 1
                gleichzeitig["max"] = max(gleichzeitig["max"], gleichzeitig["jetzt"])
            time.sleep(0.05)
            with sperre:
                gleichzeitig["jetzt"] -= 1
            if "Überarbeite die folgenden Stellen" in nutzer:
                return json.dumps({"stellen": []})
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        for slug in ("test-artikel", "zweiter"):
            ctx = self.ctx(chat)
            ctx.bewerte = (lambda s: (lambda slug: reihenfolge.append(s) or (build.parse_article(self.root / "articles" / f"{s}.md"),
                                                                           self.bewerte_text((self.root / "articles" / f"{s}.md").read_text(encoding="utf-8")))))(slug)
            ok, _ = io.starte(ctx, slug)
            self.assertTrue(ok)
        z = self.speicher.lesen("inordnung", "zweiter.json")
        self.assertIn(z["status"], ("wartet", "laeuft"))  # zweiter Auftrag wartet
        for _ in range(200):
            if all((self.speicher.lesen("inordnung", f"{s}.json") or {}).get("status") not in ("wartet", "laeuft") for s in ("test-artikel", "zweiter")):
                break
            time.sleep(0.1)
        self.assertEqual(gleichzeitig["max"], 1)
        self.assertEqual(reihenfolge[0], "test-artikel")
        for s in ("test-artikel", "zweiter"):
            self.assertIn(self.speicher.lesen("inordnung", f"{s}.json")["status"], ("vorschlag", "keine_vorschlaege"))
        self.assertFalse(io.ist_gesperrt("test-artikel") or io.ist_gesperrt("zweiter"))


class Verbindung(Wegwerf):
    def ctx_mit(self, chat, **kw):
        c = self.ctx(chat)
        c.gesundheit_takt = 0.001
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def basis(self, text_verhalten):
        def chat(system, nutzer, **kw):
            if "Überarbeite die folgenden Stellen" in nutzer:
                return text_verhalten(nutzer)
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ""})
        return chat

    def test_verbindungsfehler_ist_kein_ablehnungsgrund_und_wird_nachgeholt(self):
        import llm
        zustand = {"ausfall": True}

        def text(nutzer):
            if zustand["ausfall"]:
                raise llm.LLMVerbindung("LLM-Dienst nicht erreichbar (ConnectionResetError)")
            return json.dumps(text_antworten(nutzer))
        c = self.ctx_mit(self.basis(text), gesundheit=lambda: not zustand["ausfall"], gesundheit_frist=0.01)
        io.starte(c, "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(z["status"], "fehler")  # Dienst gleich zu Beginn nicht erreichbar: wartet, dann klare Meldung
        self.assertIn("nicht erreichbar", z["meldung"])
        self.assertTrue(any(s["name"] == "Warte auf LLM-Dienst" for s in z["schritte"]))

        # Dienst faellt erst waehrend der Textueberarbeitung aus
        zaehler = {"n": 0}

        def text2(nutzer):
            zaehler["n"] += 1
            if zustand["ausfall"]:
                raise llm.LLMVerbindung("LLM-Dienst nicht erreichbar (ConnectionResetError)")
            return json.dumps(text_antworten(nutzer))
        zustand["ausfall"] = True
        gesund = {"ok": True}
        c = self.ctx_mit(self.basis(text2), gesundheit=lambda: gesund["ok"], gesundheit_frist=0.01)
        gesund["ok"] = True
        io.starte(c, "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(z["status"], "vorschlag")
        self.assertTrue(z["nicht_bearbeitet"], "Stellen muessen als nicht bearbeitet gelten")
        self.assertFalse([a for a in z["stellen_abgelehnt"] if "nicht erreichbar" in a.get("grund", "")])
        anzahl = len(z["nicht_bearbeitet"])
        # Dienst wieder da: nur diese Stellen nochmals
        zustand["ausfall"] = False
        ok, info = io.starte(c, "test-artikel", hintergrund=False, modus="nachholen")
        self.assertTrue(ok, info)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(z["status"], "vorschlag", z.get("meldung"))
        self.assertFalse(z["nicht_bearbeitet"])
        self.assertGreaterEqual(len(z["stellen"]), anzahl)
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), ARTIKEL)

    def test_nachholen_ohne_offene_teile(self):
        c = self.ctx_mit(self.basis(lambda n: json.dumps(text_antworten(n))))
        io.starte(c, "test-artikel", hintergrund=False)
        ok, info = io.starte(c, "test-artikel", hintergrund=False, modus="nachholen")
        self.assertFalse(ok)
        self.assertFalse(io.ist_gesperrt("test-artikel"))

    def test_warten_auf_dienst_und_weiter(self):
        antworten = iter([False, False, True])
        c = self.ctx_mit(self.basis(lambda n: json.dumps(text_antworten(n))), gesundheit=lambda: next(antworten, True), gesundheit_frist=5)
        io.starte(c, "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(z["status"], "vorschlag")
        schritt = next(s for s in z["schritte"] if s["name"] == "Warte auf LLM-Dienst")
        self.assertEqual(schritt["status"], "ok")
