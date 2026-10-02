"""Tests fuer die Regel „Titel und Beschreibung in einem Guss“: gemeinsames Modul, Metas-Auswahl,
Ranking-Kriterium und Build-Warnung (Wegwerf-Artikel unter tempfile)."""

import json
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
import metas_auswahl as ma  # noqa: E402
import titel_beschreibung as tb  # noqa: E402

TITEL = "Wirtschaftskalender: 84.000 Termine, kostenlos, ohne Login"
SCHLECHT = "Über 84.000 Konjunkturtermine seit 2010, ohne Login: kostenlose API, sechs Download-Formate, KI-Recherche per Klick und Link zur Originalquelle jedes Termins."
GUT = "Seit 2010 mit kostenloser API, sechs Download-Formaten und KI-Recherche per Klick; jeder Termin verlinkt zur Originalquelle."


class Ueberschneidung(unittest.TestCase):
    def test_schlechtes_beispiel(self):
        u = tb.ueberschneidung(TITEL, SCHLECHT)
        self.assertFalse(u["ok"])
        self.assertIn("84.000", u["wiederholt"])
        self.assertIn("ohne Login", u["wiederholt"])
        self.assertIn("‚84.000‘", u["hinweis"])
        self.assertIn("schon im Titel", u["hinweis"])

    def test_gutes_beispiel_mit_und_ohne_punkte(self):
        self.assertTrue(tb.ueberschneidung(TITEL, GUT)["ok"])
        self.assertTrue(tb.ueberschneidung(TITEL, "… " + GUT)["ok"])  # führende Punkte werden vor dem Messen entfernt

    def test_gegenbeispiele(self):
        # ein einzelnes gemeinsames Wort reicht nicht
        self.assertTrue(tb.ueberschneidung("Monitoring im Homelab: Firewall und KI", "Verbindet Security und Betrieb, damit Monitoring nie aufhört")["ok"])
        # zwei bedeutungstragende Woerter reichen
        self.assertFalse(tb.ueberschneidung("Monitoring im Homelab: Firewall und KI", "Firewall und Monitoring laufen zusammen")["ok"])
        # Zahlen: einstellige zaehlen nicht, mehrstellige schon
        self.assertTrue(tb.ueberschneidung("Teil 2: Der Anfang", "2 Wege zum Ziel")["ok"])
        self.assertFalse(tb.ueberschneidung("In 15 Minuten fertig", "Dauert 15 Minuten")["ok"])
        # leere Eingaben stuerzen nicht ab
        self.assertTrue(tb.ueberschneidung("", "")["ok"])

    def test_stamm_grob_normalisiert(self):
        self.assertFalse(tb.ueberschneidung("Kostenlos und Dashboards", "Kostenlose Dashboard-Ansichten")["ok"])

    def test_wortfolge(self):
        u = tb.ueberschneidung("Alles ohne Login", "Weiter geht es ohne Login weiter")
        self.assertFalse(u["ok"])
        self.assertIn("ohne Login", u["wiederholt"])
        # Folge aus Stoppwoertern allein zaehlt nicht
        self.assertTrue(tb.ueberschneidung("Das ist es nicht", "Das ist es")["ok"])

    def test_auslassungspunkte_werden_entfernt(self):
        self.assertEqual(tb.bereinige("… seit 2010"), "Seit 2010")
        self.assertEqual(tb.bereinige("...seit 2010"), "Seit 2010")
        self.assertEqual(tb.bereinige("  …  Seit 2010"), "Seit 2010")
        self.assertEqual(tb.bereinige("Seit 2010"), "Seit 2010")
        self.assertEqual(tb.bereinige(""), "")


class MetasKombination(unittest.TestCase):
    def test_zeichenzaehlung_ohne_punkte(self):
        text = "Seit 2010 " + "a" * 150  # 160 Zeichen
        self.assertEqual(len(ma.normalisiere_beschreibung(text)), 160)
        self.assertIsNone(ma.pruefe_meta("description", ma.normalisiere_beschreibung(text)))
        self.assertIn("zu lang um 1", ma.pruefe_meta("description", ma.normalisiere_beschreibung(text + "b")))
        # Vorschlag mit Auslassungspunkten: werden entfernt, bevor gemessen wird
        mit = "… " + text
        self.assertEqual(ma.normalisiere_beschreibung(mit), text)
        self.assertNotIn("…", ma.normalisiere_beschreibung(mit))

    def test_gespeicherte_beschreibung_beginnt_nie_mit_punkten(self):
        for roh in ("… Seit 2010 mit freier API", "...Seit 2010 mit freier API", "…seit 2010 mit freier API"):
            t = ma.normalisiere_beschreibung(roh)
            self.assertFalse(t.startswith(("…", "...")), t)
            self.assertTrue(t[0].isupper(), t)

    def test_nachfrage_nennt_ueberlaenge_und_zielwert(self):
        aufrufe = []

        def chat(system, nutzer, **kw):
            aufrufe.append(nutzer)
            lang = "Seit 2010 " + "a" * 172  # 182 Zeichen
            if len(aufrufe) < 3:
                return json.dumps({"titel": [], "beschreibung": [lang, lang + "b", lang + "c"], "og_image_alt": ""})
            return json.dumps({"titel": [], "beschreibung": [GUT + " Dazu der Rest des Artikels."], "og_image_alt": ""})
        meta = {"title": TITEL, "description": "alt", "og_image_alt": "", "tags": []}
        erg = ma.anfordern(chat, meta, "Text", {"description"})
        self.assertEqual(len(aufrufe), 3)  # erste Anfrage + zwei Nachfragen
        self.assertIn("32 Zeichen zu lang, auf höchstens 150 kürzen", aufrufe[1])
        self.assertEqual(erg["felder"]["description"]["gueltig"], 1)

    def test_wiederholung_wird_nicht_empfohlen(self):
        self.assertIn("wiederholt den Titel", ma.pruefe_meta("description", ma.normalisiere_beschreibung(SCHLECHT[:140]), "", TITEL))
        meta = {"title": TITEL, "description": "alt", "tags": []}
        vorschlag = {"felder": {"description": {"texte": [SCHLECHT[:150], GUT + " Mehr dazu im Artikel selbst."]}}}
        with tempfile.TemporaryDirectory() as td:
            modell = ma.auswahl(Path(td), meta, vorschlag, {"description"})
        g = modell["felder"]["description"]
        self.assertEqual(g["empfohlen"], 1 if g["karten"][1]["ok"] else None)
        self.assertFalse(g["karten"][0]["ok"])
        self.assertIn("84.000", g["karten"][0]["grund"])

    def test_aktuell_wird_bewertet(self):
        meta = {"title": TITEL, "description": SCHLECHT, "tags": []}
        with tempfile.TemporaryDirectory() as td:
            modell = ma.auswahl(Path(td), meta, None, None)
        self.assertFalse(modell["felder"]["description"]["aktuell"]["guss"]["ok"])

    def test_anfordern_nachfrage_nennt_titel_und_wiederholung(self):
        aufrufe = []

        def chat(system, nutzer, **kw):
            aufrufe.append(nutzer)
            if len(aufrufe) == 1:
                return json.dumps({"titel": [], "beschreibung": [SCHLECHT[:150]] * 1 + [SCHLECHT[:140], SCHLECHT[:145]], "og_image_alt": ""})
            return json.dumps({"titel": [], "beschreibung": [GUT + " Dazu der Rest des Artikels."], "og_image_alt": ""})
        meta = {"title": TITEL, "description": "alt", "og_image_alt": "", "tags": []}
        erg = ma.anfordern(chat, meta, "Text", {"description"})
        self.assertEqual(len(aufrufe), 2)
        self.assertIn("wiederholt den Titel", aufrufe[1])
        self.assertIn(TITEL, aufrufe[1])
        self.assertTrue(erg["nachgefragt"])

    def test_prompts_enthalten_regel_mit_beispiel(self):
        import llm
        self.assertIn("in einem Guss", llm.METAS_SYSTEM)
        self.assertIn("84.000", llm.METAS_SYSTEM)
        p = llm.metas_prompt({"title": "t", "description": "d"}, "x", "")
        self.assertIn("SETZT DEN TITEL FORT", p)
        self.assertIn("120-160", p)
        self.assertIn("OHNE Auslassungspunkte", p)
        self.assertNotIn("118-158", p)


class Ranking(unittest.TestCase):
    def test_kriterium_a_guss_ohne_gewichtsaenderung(self):
        self.assertEqual(sum(v[2] for v in bw.KRITERIEN.values() if v[0] == "A"), bw.KATEGORIEN["A"]["gewicht"])
        meta = {"slug": "x", "title": TITEL, "description": SCHLECHT, "tags": []}
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            b = bw.bewerte(meta, "<p>Text.</p>", base_url="https://e.invalid", static_dir=t / "static", dist_dir=t / "dist", heute=date(2026, 10, 1))
            k = b.kriterium("a_guss")
            self.assertNotEqual(k.status, "ok")
            self.assertIn("84.000", k.messwert)
            meta["description"] = GUT
            b = bw.bewerte(meta, "<p>Text.</p>", base_url="https://e.invalid", static_dir=t / "static", dist_dir=t / "dist", heute=date(2026, 10, 1))
            self.assertEqual(b.kriterium("a_guss").status, "ok")


class BuildWarnung(unittest.TestCase):
    def meta(self, titel, beschr):
        return {"title": titel, "description": beschr, "slug": "x", "body_md": "Text", "date": "2026-10-01"}

    def test_warnung_aber_kein_abbruch(self):
        w = build.pruefe_warnungen(self.meta(TITEL, SCHLECHT))
        treffer = [x for x in w if "wiederholt den Titel" in x]
        self.assertEqual(len(treffer), 1)
        self.assertIn("‚84.000‘", treffer[0])

    def test_keine_warnung_bei_gutem_paar(self):
        self.assertFalse([x for x in build.pruefe_warnungen(self.meta(TITEL, GUT)) if "wiederholt" in x])

    def test_build_laeuft_in_wegwerf_repo_durch_und_meldet(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            for d in ("scripts", "templates", "static", "public-root"):
                if (ROOT / d).exists() and d != "scripts":
                    shutil.copytree(ROOT / d, r / d)
            (r / "scripts").mkdir()
            shutil.copy(ROOT / "scripts" / "build.py", r / "scripts" / "build.py")
            shutil.copy(ROOT / "scripts" / "titel_beschreibung.py", r / "scripts" / "titel_beschreibung.py")
            shutil.copy(ROOT / "config.yaml", r / "config.yaml")
            (r / "articles").mkdir()
            (r / "static" / "img").mkdir(parents=True, exist_ok=True)
            shutil.copy(next((ROOT / "static" / "img").glob("*.jpg")), r / "static" / "img" / "b.jpg")
            (r / "articles" / "x.md").write_text(
                f'---\ntitle: "{TITEL}"\nslug: x\ndate: 2026-10-01\ndescription: "{SCHLECHT}"\nimage: /static/img/b.jpg\ntags: [A]\n---\n\nText.\n', encoding="utf-8")
            p = subprocess.run([sys.executable, str(r / "scripts" / "build.py")], cwd=r, capture_output=True, text=True, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr[-500:])
            self.assertIn("WARNUNG [x]: Beschreibung wiederholt den Titel", p.stdout)


if __name__ == "__main__":
    unittest.main()


class TitelZeilen(unittest.TestCase):
    ECHT = {  # mit Playwright an den gebauten Seiten gemessen (Handy 393 px, Desktop 1280 px)
        "„Hey Siri, Windows“: Samsung-Monitor mit eingebautem KVM-Switch per Sprache umschalten.": (5, 3),
        "Monitoring, Teil II: Cloudflare, Firewall, das große Ganze + Claude MCP-Server (read & write*)": None,
    }

    def test_ampel_grenzen(self):
        self.assertEqual(ma.titel_zeilen("Kurz")["ampel"], "gruen")
        self.assertEqual(ma.titel_zeilen("Kurz")["handy"], 1)
        z = ma.titel_zeilen("Wort " * 40)
        self.assertEqual(z["ampel"], "rot")
        self.assertGreaterEqual(z["handy"], 5)

    def test_gelb_bei_vier_zeilen(self):
        for n in range(1, 80):
            z = ma.titel_zeilen(" ".join(["Wortwort"] * n))
            if z["handy"] == 4:
                self.assertEqual(z["ampel"], "gelb")
                return
        self.fail("keine Vier-Zeilen-Variante gefunden")

    def test_kalibrierung_an_gemessenen_titeln(self):
        gemessen = [  # Titel (Stand 1.10.2026) und mit Playwright an der gebauten Seite gemessene Zeilen (Handy 393 px, Desktop 1280 px)
            ("„Hey Siri, Windows“: Samsung-Monitor mit eingebautem KVM-Switch per Sprache umschalten.", 5, 3),
            ("Monitoring für kleine Infrastrukturen in 15 Minuten: Netdata + Claude als MCP-Server (read & write*)", 5, 3),
            ("KI-Tempo, Nov.25 – Sep.26: Elf Monate, zwei Wellen — warum jetzt andere Regeln gelten", 4, 3),
            ("Der kostenlose, KI-gesteuerte Wirtschaftskalender von Kontor: über 84.000 Termine — modern, schnell, ohne Ballast und Kosten", 7, 4)]
        abweichung = 0
        for titel, handy, desktop in gemessen:
            z = ma.titel_zeilen(titel)
            abweichung += abs(z["handy"] - handy) + abs(z["desktop"] - desktop)
        self.assertLessEqual(abweichung, 1)

    def test_mehr_zeichen_nie_weniger_zeilen_und_desktop_nicht_mehr_als_handy(self):
        vorher = 0
        for n in range(1, 30):
            z = ma.titel_zeilen(" ".join(["Beispiel"] * n))
            self.assertGreaterEqual(z["handy"], vorher)
            self.assertLessEqual(z["desktop"], z["handy"])
            vorher = z["handy"]

    def test_empfehlung_bevorzugt_wenigste_handyzeilen_bei_gueltigen_titeln(self):
        lang = "Wirtschaftskalender Konjunkturdaten Archiv Schnittstelle Downloads"  # 68 Zeichen, mehr Zeilen
        kurz = "Wirtschaftskalender: Archiv, API und KI ohne Login"  # 51 Zeichen
        self.assertGreater(ma.titel_zeilen(lang)["handy"], ma.titel_zeilen(kurz)["handy"])
        meta = {"title": "t", "description": "d", "tags": []}
        vorschlag = {"felder": {"title": {"texte": [lang, kurz]}}}
        with tempfile.TemporaryDirectory() as td:
            modell = ma.auswahl(Path(td), meta, vorschlag, {"title"})
        g = modell["felder"]["title"]
        self.assertTrue(all(k["ok"] for k in g["karten"]))
        self.assertEqual(g["karten"][g["empfohlen"]]["text"], kurz)
        self.assertEqual(g["karten"][0]["zeilen"]["handy"], ma.titel_zeilen(lang)["handy"])

    def test_gleiche_zeilen_behalten_reihenfolge(self):
        a, b = "Monitoring im Homelab: Firewall, Tunnel und KI", "Firewall, Tunnel und KI im Homelab: Monitoring"
        self.assertTrue(40 <= len(a) <= 70 and 40 <= len(b) <= 70)
        self.assertEqual(ma.titel_zeilen(a)["handy"], ma.titel_zeilen(b)["handy"])
        meta = {"title": "t", "description": "d", "tags": []}
        with tempfile.TemporaryDirectory() as td:
            modell = ma.auswahl(Path(td), meta, {"felder": {"title": {"texte": [a, b]}}}, {"title"})
        self.assertEqual(modell["felder"]["title"]["empfohlen"], 0)  # Empfehlung, kein Zwang: der erste bleibt bei Gleichstand

    def test_meta_schluessel_bevorzugt_weniger_zeilen_bei_gleichem_score(self):
        import ordnung_engine as eng
        snap = {"kriterien": {}, "kategorien": {"A": {"score": 90.0}, "E": {"score": 80.0}}}
        self.assertLess(eng._meta_schluessel(snap, "Kurz und knapp"), eng._meta_schluessel(snap, "Wort " * 30))
        besser = {"kriterien": {}, "kategorien": {"A": {"score": 95.0}, "E": {"score": 80.0}}}
        self.assertLess(eng._meta_schluessel(besser, "Wort " * 30), eng._meta_schluessel(snap, "Kurz"))  # Score zaehlt vor Zeilen
