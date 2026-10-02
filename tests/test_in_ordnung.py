"""Tests fuer „Alles in Ordnung bringen“ (in_ordnung.py), die Metas-Auswahl
(metas_auswahl.py) und die Deploy-Vorauswahl je Artikel.

Alles laeuft offline in Wegwerf-Verzeichnissen unter tempfile; es werden nie
articles/, dist/ oder data/ des echten Blogs angefasst. Das LLM und der Build
sind Attrappen.

    .venv/bin/python -m unittest discover -s tests -v
"""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import deploy as dp  # noqa: E402
import in_ordnung as io  # noqa: E402
import metas_auswahl as ma  # noqa: E402
from ranking_daten import Speicher, setze_felder  # noqa: E402

TITEL_OK = "Monitoring im Homelab: Firewall, Tunnel und KI im Zusammenspiel"  # 64
BESCHR_OK = ("Security sieht den Angriff, Betrieb den Fehler: 6 Dashboards verbinden beide Welten und "
             "zeigen auf einen Blick, was heute alles überwacht wird.")  # 120-160
ALT_OK = "Laptop mit Radar-Animation: KI-gestütztes Monitoring erfasst Bedrohungen wie Brute-Force und ablaufende Zertifikate."

ARTIKEL = """---
title: "Ein sehr langer Titel, der weit über die erlaubten siebzig Zeichen hinausgeht und daher gekürzt werden sollte"
slug: test-artikel
date: 2026-09-28
description: "kurz"
og_image: /static/img/x.png
og_image_alt: "alt"
tags: [Monitoring, Firewall]
---

Erster Absatz mit einem sehr langen Satz, der kein Ende nehmen will, weil er immer noch einen weiteren Nebensatz anhängt, und dann noch einen, damit er sicher über zwanzig Wörter kommt. Kurz.

## Abschnitt

Zweiter Absatz mit 42 Prozent und der URL https://example.org/a und einem Bild ![Alt](/static/img/x.png) sowie `code` darin.

```
Code mit Zahl 99 und langem langen langen Satz der nie endet und dennoch bleiben muss wie er ist ohne Änderung
```

<p class="x">Dritter Absatz als HTML mit <strong>Fett</strong> und einem weiteren, extrem langen Satz, der sich über viele Wörter erstreckt und dabei nie zum Punkt kommen will, obwohl er könnte.</p>

<style>
p { color: red; }

p.b { color: blue; }
</style>

<figure><p>Text in Figure bleibt unberührt und ist trotzdem ziemlich lang und ausführlich geschrieben worden.</p></figure>
"""


class Bloecke(unittest.TestCase):
    def test_findet_nur_absaetze(self):
        b = [x for x in io.finde_bloecke(ARTIKEL) if x.art in ("md", "html")]
        texte = [x.klar[:20] for x in b]
        self.assertEqual(len(b), 3, texte)
        self.assertTrue(b[0].klar.startswith("Erster Absatz"))
        self.assertEqual(b[2].art, "html")
        self.assertTrue(b[2].oeffner.startswith('<p class="x">'))
        self.assertFalse(any("Code mit Zahl" in x.klar or "Figure" in x.klar or "color" in x.klar for x in b))

    def test_offsets_stimmen(self):
        for x in io.finde_bloecke(ARTIKEL):
            self.assertEqual(ARTIKEL[x.start:x.ende], x.text)

    def test_ueberschrift_und_nach_ueberschrift(self):
        b = [x for x in io.finde_bloecke(ARTIKEL) if x.art in ("md", "html")]
        self.assertTrue(b[1].nach_ueberschrift)
        self.assertFalse(b[2].nach_ueberschrift)
        self.assertEqual(b[1].abschnitt, "Abschnitt")


class Schutz(unittest.TestCase):
    ALT = 'Der Dienst läuft seit 15 Minuten auf Port 8090 und meldet <strong>CrowdSec</strong> Treffer, siehe <a href="https://x.example/a">Quelle</a>.'

    def test_harmlose_kuerzung_ok(self):
        neu = 'Der Dienst läuft seit 15 Minuten. Er hört auf Port 8090 und meldet <strong>CrowdSec</strong> Treffer, siehe <a href="https://x.example/a">Quelle</a>.'
        self.assertEqual(io.schutzpruefung_stelle(self.ALT, neu, []), [])

    def test_url_zahl_tag_name_werden_abgelehnt(self):
        pruefe = lambda neu: io.schutzpruefung_stelle(self.ALT, neu, [])
        self.assertTrue(any("URL" in v for v in pruefe(self.ALT.replace("x.example/a", "x.example/b"))))
        self.assertTrue(any("Zahlen" in v for v in pruefe(self.ALT.replace("15", "20"))))
        self.assertTrue(any("Zahlen" in v for v in pruefe(self.ALT.replace("auf Port 8090 und", "und"))))
        self.assertTrue(any("HTML" in v for v in pruefe(self.ALT.replace("<strong>", "<em>").replace("</strong>", "</em>"))))
        self.assertTrue(any("Fachbegriffe" in v for v in pruefe(self.ALT.replace("CrowdSec", "Fail2ban"))))

    def test_bild_code_ueberschrift_absatzwechsel(self):
        alt = "Text mit ![Bild](/static/img/a.png) und `code`."
        self.assertTrue(any("Bildverweise" in v for v in io.schutzpruefung_stelle(alt, "Text und `code`.", [])))
        self.assertTrue(any("Code" in v for v in io.schutzpruefung_stelle(alt, "Text mit ![Bild](/static/img/a.png) und `kode`.", [])))
        self.assertTrue(any("Überschrift" in v for v in io.schutzpruefung_stelle("Ein Satz hier", "## Neuer Titel\nEin Satz hier", [])))
        self.assertTrue(any("Absatzwechsel" in v for v in io.schutzpruefung_stelle("Ein Satz hier und mehr Text", "Ein Satz.\n\nhier und mehr Text", [])))

    def test_zahlen_als_multiset(self):
        self.assertEqual(io.schutzpruefung_stelle("Es sind 5 und 5 Dinge", "Es sind 5 Dinge und 5 Stück", []), [])
        self.assertTrue(io.schutzpruefung_stelle("Es sind 5 und 5 Dinge", "Es sind 5 Dinge", []))

    def test_keine_verbesserung_und_unveraendert(self):
        lang = "Dies ist ein Satz mit mehr als zwanzig Wörtern, der aber nicht kürzer wird, weil nichts passiert, wenn man nur ein Wort ändert und sonst alles lässt."
        self.assertTrue(io.schutzpruefung_stelle(lang, lang, ["kuerzen"])[0].startswith("unverändert"))
        self.assertTrue(any("keine Verbesserung" in v for v in io.schutzpruefung_stelle(lang, lang.replace("Dies", "Das"), ["kuerzen"])))
        geteilt = lang.replace(", der aber", ". Er wird aber").replace(", weil", ". Es passiert nichts, weil")
        self.assertEqual(io.schutzpruefung_stelle(lang, geteilt, ["kuerzen"]), [])

    def test_dokumentpruefung(self):
        neu = ARTIKEL.replace("Erster Absatz", "Der erste Absatz")
        self.assertEqual(io.schutzpruefung_dokument(ARTIKEL, neu), [])
        self.assertTrue(io.schutzpruefung_dokument(ARTIKEL, ARTIKEL.replace("## Abschnitt", "## Anderer")))
        self.assertTrue(io.schutzpruefung_dokument(ARTIKEL, ARTIKEL.replace("Zahl 99", "Zahl 98")))
        self.assertTrue(io.schutzpruefung_dokument(ARTIKEL, ARTIKEL.replace("example.org/a", "example.org/b")))
        self.assertTrue(io.schutzpruefung_dokument(ARTIKEL, ARTIKEL.replace("42 Prozent", "43 Prozent")))


class MetasGrenzen(unittest.TestCase):
    def test_titel(self):
        self.assertIsNone(ma.pruefe_meta("title", TITEL_OK))
        self.assertIn("zu lang um 1", ma.pruefe_meta("title", "x" * 71))
        self.assertIsNone(ma.pruefe_meta("title", "x" * 70))
        self.assertIn("zu kurz um 1", ma.pruefe_meta("title", "x" * 39))

    def test_beschreibung_grenzen_und_haken(self):
        self.assertTrue(120 <= len(BESCHR_OK) <= 160, len(BESCHR_OK))
        self.assertIsNone(ma.pruefe_meta("description", BESCHR_OK))
        self.assertIn("zu lang um 29", ma.pruefe_meta("description", "Warum " + "a" * 183))  # ohne Fortsetzungs-Punkte direkt gemessen
        self.assertIn("zu kurz", ma.pruefe_meta("description", "Warum fehlt das? " + "a" * 90))
        # ohne Signal in den ersten 90 Zeichen
        stumpf = ("Eine ruhige und sachliche Darstellung der gesamten Infrastruktur im Überblick mit allen Komponenten "
                  "der Anlage in geordneter Reihenfolge und Form")[:140]
        self.assertTrue(120 <= len(stumpf) <= 160, len(stumpf))
        self.assertIn("Haken", ma.pruefe_meta("description", stumpf) or "")

    def test_alt_unveraendert_url_html(self):
        self.assertIsNone(ma.pruefe_meta("og_image_alt", ALT_OK))
        self.assertIn("unverändert", ma.pruefe_meta("og_image_alt", ALT_OK, ALT_OK))
        self.assertIn("URL", ma.pruefe_meta("og_image_alt", "x" * 70 + " https://a.example"))
        self.assertIn("HTML", ma.pruefe_meta("og_image_alt", "<b>" + "x" * 70))

    def test_ampel(self):
        self.assertEqual(ma.grenze_ampel("title", 70), "gruen")
        self.assertEqual(ma.grenze_ampel("title", 75), "gelb")
        self.assertEqual(ma.grenze_ampel("title", 94), "rot")
        self.assertEqual(ma.grenze_ampel("description", 187), "rot")
        self.assertEqual(ma.grenze_ampel("description", 165), "gelb")

    def test_anfordern_fragt_einmal_mit_rueckmeldung_nach(self):
        zu_lang = "Warum " + "a" * 183  # 189 Zeichen
        aufrufe = []

        def chat(system, nutzer, **kw):
            aufrufe.append(nutzer)
            if len(aufrufe) == 1:
                return json.dumps({"titel": [TITEL_OK], "beschreibung": [zu_lang, zu_lang + "b", zu_lang + "c"], "og_image_alt": ALT_OK})
            return json.dumps({"titel": [], "beschreibung": [BESCHR_OK], "og_image_alt": ""})

        meta = {"title": "t", "description": "d", "og_image_alt": "", "tags": ["Monitoring"]}
        erg = ma.anfordern(chat, meta, "Text", {"title", "description"})
        self.assertEqual(len(aufrufe), 2)
        self.assertIn("zu lang um 29 Zeichen", aufrufe[1])
        self.assertTrue(erg["nachgefragt"])
        self.assertEqual(erg["felder"]["description"]["texte"], [ma.normalisiere_beschreibung(BESCHR_OK)])
        self.assertEqual(erg["felder"]["title"]["gueltig"], 1)
        self.assertEqual(len([a for a in erg["abgewiesen"] if a["feld"] == "description"]), 3)

    def test_nie_empfohlen_wenn_ausserhalb(self):
        zu_lang = "Warum " + "a" * 183

        def chat(system, nutzer, **kw):
            return json.dumps({"titel": [], "beschreibung": [zu_lang, zu_lang + "b"], "og_image_alt": ""})

        meta = {"title": "t" * 94, "description": "d" * 187, "og_image_alt": "", "tags": []}
        erg = ma.anfordern(chat, meta, "Text", {"description"})
        with tempfile.TemporaryDirectory() as td:
            modell = ma.auswahl(Path(td), meta, erg, {"description"})
        g = modell["felder"]["description"]
        self.assertIsNone(g["empfohlen"])
        self.assertTrue(all(not k["ok"] for k in g["karten"]))
        self.assertEqual(ma.standard_werte(modell), {})
        # „Aktuell“ wird gekennzeichnet, wenn es ausserhalb liegt
        self.assertTrue(g["aktuell"]["ausserhalb"])
        self.assertTrue(modell["felder"]["title"]["aktuell"]["ausserhalb"])

    def test_erste_gueltige_wird_empfohlen(self):
        def chat(system, nutzer, **kw):
            return json.dumps({"titel": ["x" * 80, TITEL_OK, TITEL_OK + "!"], "beschreibung": [], "og_image_alt": ""})

        meta = {"title": "t", "description": "d", "tags": []}
        erg = ma.anfordern(chat, meta, "Text", {"title"})
        self.assertEqual(erg["felder"]["title"]["texte"], [TITEL_OK, TITEL_OK + "!"])
        with tempfile.TemporaryDirectory() as td:
            modell = ma.auswahl(Path(td), meta, erg, {"title"})
        self.assertEqual(modell["felder"]["title"]["empfohlen"], 0)
        self.assertEqual(ma.standard_werte(modell), {"title": TITEL_OK})

    def test_harte_pruefung_fuer_nutzerwerte(self):
        self.assertIsNone(ma.pruefe_wert_hart("title", "kurz"))  # Laenge ist nur eine Warnung
        self.assertIsNotNone(ma.pruefe_wert_hart("title", ""))
        self.assertIsNotNone(ma.pruefe_wert_hart("title", "a\nb"))
        self.assertIsNotNone(ma.pruefe_wert_hart("description", "siehe https://x.example"))


class Wegwerf(unittest.TestCase):
    """Wegwerf-Wurzel mit articles/, dist/, static/img/ und data/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "articles").mkdir()
        (self.root / "dist" / "artikel" / "test-artikel").mkdir(parents=True)
        (self.root / "static" / "img").mkdir(parents=True)
        (self.root / "static" / "img" / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.root / "static" / "img" / "y.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.pfad = self.root / "articles" / "test-artikel.md"
        self.pfad.write_text(ARTIKEL, encoding="utf-8")
        self.speicher = Speicher(self.root)
        self.builds = []
        self.build_ok = True
        self.pflicht = []
        io._aktiv.clear()

    def tearDown(self):
        io._aktiv.clear()
        self.tmp.cleanup()

    def baue(self):
        self.builds.append(self.pfad.read_text(encoding="utf-8"))
        return self.build_ok, "Fehler: kaputt" if not self.build_ok else "ok"

    def ctx(self, chat=None):
        return io.Kontext(root=self.root, speicher=self.speicher, chat=chat or (lambda *a, **k: "{}"),
                          bewerte=self.bewerte, baue=self.baue, pflicht_fehlt=lambda slug: list(self.pflicht))

    def bewerte(self, slug):
        import bewertung as bw
        import build
        meta = build.parse_article(self.pfad)
        b = bw.bewerte(meta, build.render_markdown(meta["body_md"]), base_url="https://example.invalid", static_dir=self.root / "static",
                       dist_dir=self.root / "dist", heute=__import__("datetime").date(2026, 10, 1), alle_slugs=["test-artikel"])
        return meta, b

    def vorschlag_zustand(self, stellen=None, meta_werte=None):
        text = self.pfad.read_text(encoding="utf-8")
        import hashlib
        bl = [b for b in io.finde_bloecke(text) if b.art in ("md", "html")]
        b0 = bl[0]
        neu_inner = "Erster Absatz mit einem sehr langen Satz. Er will kein Ende nehmen, weil er einen Nebensatz anhängt. Dann kommt noch einer, damit er über zwanzig Wörter kommt. Kurz."
        stelle = {"id": 1, "start": b0.start, "ende": b0.ende, "zeile": b0.zeile, "abschnitt": "", "zweck": ["kuerzen"], "hinweise": [],
                  "alt": b0.text, "alt_inner": b0.inner, "neu_inner": neu_inner, "neu": neu_inner}
        z = {"id": "t", "slug": "test-artikel", "status": "vorschlag", "gestartet": "2026-10-01T00:00:00", "schritte": [],
             "datei_hash": hashlib.sha256(text.encode()).hexdigest(), "stellen": [stelle] if stellen is None else stellen}
        self.speicher.schreiben(z, "inordnung", "test-artikel.json")
        return z


class Uebernehmen(Wegwerf):
    def test_erfolg_backup_schreiben_bauen(self):
        self.vorschlag_zustand()
        original = self.pfad.read_text(encoding="utf-8")
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK, "description": BESCHR_OK}, {1})
        self.assertTrue(erg["ok"], erg)
        neu = self.pfad.read_text(encoding="utf-8")
        self.assertIn(TITEL_OK, neu)
        self.assertIn("Er will kein Ende nehmen", neu)
        self.assertEqual(len(self.builds), 1)
        backups = list((self.root / "data" / "backups" / "artikel").glob("test-artikel.*.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
        self.assertEqual(self.speicher.lesen("inordnung", "test-artikel.json")["status"], "uebernommen")
        self.assertFalse(io.ist_gesperrt("test-artikel"))

    def test_build_fehler_rollt_zurueck(self):
        self.vorschlag_zustand()
        original = self.pfad.read_text(encoding="utf-8")
        self.build_ok = False
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK}, {1})
        self.assertFalse(erg["ok"])
        self.assertTrue(erg["zurueckgespielt"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), original)
        self.assertEqual(len(self.builds), 2)  # Build + Neubau nach dem Zurueckspielen
        self.assertEqual(self.builds[1], original)
        self.assertEqual(self.speicher.lesen("inordnung", "test-artikel.json")["status"], "vorschlag")
        self.assertFalse(io.ist_gesperrt("test-artikel"))

    def test_fehlendes_pflicht_meta_rollt_zurueck(self):
        self.vorschlag_zustand()
        original = self.pfad.read_text(encoding="utf-8")
        self.pflicht = ["description/og:description"]
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK}, {1})
        self.assertFalse(erg["ok"])
        self.assertIn("Pflicht-Meta", erg["meldung"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), original)

    def test_build_ausnahme_rollt_zurueck(self):
        self.vorschlag_zustand()
        original = self.pfad.read_text(encoding="utf-8")
        ctx = self.ctx()
        zaehler = {"n": 0}

        def baue():
            zaehler["n"] += 1
            if zaehler["n"] == 1:
                raise RuntimeError("Zeitueberschreitung")
            return True, "ok"
        ctx.baue = baue
        erg = io.uebernehmen(ctx, "test-artikel", {}, {1})
        self.assertFalse(erg["ok"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), original)
        self.assertEqual(zaehler["n"], 2)

    def test_geaenderter_artikel_wird_nicht_angefasst(self):
        self.vorschlag_zustand()
        self.pfad.write_text(ARTIKEL + "\nNachtrag.\n", encoding="utf-8")
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK}, {1})
        self.assertFalse(erg["ok"])
        self.assertIn("geändert", erg["meldung"])
        self.assertEqual(self.builds, [])

    def test_schutzverletzung_in_gespeicherter_stelle_schreibt_nichts(self):
        z = self.vorschlag_zustand()
        z["stellen"][0]["neu_inner"] = z["stellen"][0]["alt_inner"].replace("zwanzig", "dreissig").replace("Kurz.", "Kurz 7.")
        self.speicher.schreiben(z, "inordnung", "test-artikel.json")
        original = self.pfad.read_text(encoding="utf-8")
        erg = io.uebernehmen(self.ctx(), "test-artikel", {}, {1})
        self.assertFalse(erg["ok"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), original)
        self.assertEqual(self.builds, [])

    def test_nichts_gewaehlt(self):
        self.vorschlag_zustand()
        erg = io.uebernehmen(self.ctx(), "test-artikel", {}, set())
        self.assertFalse(erg["ok"])
        self.assertEqual(self.builds, [])

    def test_abwaehlen_einzelner_stellen(self):
        self.vorschlag_zustand()
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK}, set())
        self.assertTrue(erg["ok"])
        self.assertIn(TITEL_OK, self.pfad.read_text(encoding="utf-8"))
        self.assertNotIn("Er will kein Ende nehmen", self.pfad.read_text(encoding="utf-8"))

    def test_bild_nur_aus_static_img(self):
        self.vorschlag_zustand()
        for schlecht in ("/etc/passwd", "/static/img/../../x", "/static/img/gibt-es-nicht.png"):
            erg = io.uebernehmen(self.ctx(), "test-artikel", {"og_image": schlecht}, set())
            self.assertFalse(erg["ok"], schlecht)
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"og_image": "/static/img/y.png"}, set())
        self.assertTrue(erg["ok"], erg)
        self.assertIn("og_image: \"/static/img/y.png\"", self.pfad.read_text(encoding="utf-8"))

    def test_nur_erlaubte_felder(self):
        self.vorschlag_zustand()
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"slug": "anders"}, set())
        self.assertFalse(erg["ok"])


class Rueckgaengig(Wegwerf):
    def test_stellt_backup_wieder_her_und_baut(self):
        self.vorschlag_zustand()
        original = self.pfad.read_text(encoding="utf-8")
        self.assertTrue(io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK}, {1})["ok"])
        self.assertNotEqual(self.pfad.read_text(encoding="utf-8"), original)
        erg = io.rueckgaengig(self.ctx(), "test-artikel")
        self.assertTrue(erg["ok"], erg)
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), original)
        self.assertEqual(self.speicher.lesen("inordnung", "test-artikel.json")["status"], "rueckgaengig")
        # das Rueckgaengig-Backup enthaelt den uebernommenen Stand (selbst umkehrbar)
        stande = [p.read_text(encoding="utf-8") for p in (self.root / "data" / "backups" / "artikel").glob("test-artikel.*.md")]
        self.assertEqual(len(stande), 2)
        self.assertTrue(any(TITEL_OK in s for s in stande))

    def test_ohne_uebernahme_nichts(self):
        erg = io.rueckgaengig(self.ctx(), "test-artikel")
        self.assertFalse(erg["ok"])

    def test_letzte_sicherung_und_keine_ueberschreibung(self):
        s = self.speicher
        a = s.artikel_sichern(self.pfad)
        b = s.artikel_sichern(self.pfad)  # gleiche Sekunde: darf a nicht ueberschreiben
        self.assertNotEqual(a, b)
        self.assertEqual(s.letzte_sicherung(self.pfad), b)


class Sperre(Wegwerf):
    def test_zweiter_start_wird_abgewiesen(self):
        self.assertTrue(io.sperre_nehmen("test-artikel"))
        ok, grund = io.starte(self.ctx(), "test-artikel", hintergrund=False)
        self.assertFalse(ok)
        self.assertIn("läuft bereits", grund)
        io.sperre_freigeben("test-artikel")
        self.assertTrue(io.sperre_nehmen("test-artikel"))

    def test_uebernehmen_waehrend_auftrag_gesperrt(self):
        self.vorschlag_zustand()
        io.sperre_nehmen("test-artikel")
        erg = io.uebernehmen(self.ctx(), "test-artikel", {"title": TITEL_OK}, {1})
        self.assertFalse(erg["ok"])
        self.assertEqual(self.builds, [])

    def test_threads_nur_einer_gewinnt(self):
        gewinner = []
        start = threading.Barrier(8)

        def versuche():
            start.wait()
            if io.sperre_nehmen("test-artikel"):
                gewinner.append(1)
        ts = [threading.Thread(target=versuche) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(gewinner), 1)

    def test_verwaister_lauf_wird_als_abgebrochen_erkannt(self):
        self.speicher.schreiben({"status": "laeuft", "schritte": []}, "inordnung", "test-artikel.json")
        z = io.zustand(self.ctx(), "test-artikel")
        self.assertEqual(z["status"], "abgebrochen")

    def test_ohne_llm_kein_start(self):
        ctx = self.ctx()
        ctx.llm_aktiv = lambda: False
        ok, _ = io.starte(ctx, "test-artikel", hintergrund=False)
        self.assertFalse(ok)
        self.assertFalse(io.ist_gesperrt("test-artikel"))


class Durchlauf(Wegwerf):
    """Ganzer Auftrag mit Attrappen; der Artikel darf dabei NIE geschrieben werden."""

    def chat_attrappe(self):
        aufrufe = []

        def chat(system, nutzer, **kw):
            aufrufe.append(nutzer)
            if "Überarbeite die folgenden Stellen" in nutzer:
                stellen = []
                import re
                for m in re.finditer(r"### Stelle (\d+)\n.*?Text:\n<<<\n(.*?)\n>>>", nutzer, re.S):
                    alt = m.group(2)
                    erste = " ".join(alt.split()[:8])
                    neu = alt.replace(", weil", ". Es", 1).replace(", und dann", ". Dann", 1).replace(", obwohl", ". Er", 1)
                    stellen.append({"id": int(m.group(1)), "alt": erste, "neu": neu})
                return json.dumps({"stellen": stellen})
            return json.dumps({"titel": [TITEL_OK], "beschreibung": [BESCHR_OK], "og_image_alt": ALT_OK})
        return chat, aufrufe

    def test_schreibt_nie_in_den_artikel(self):
        chat, aufrufe = self.chat_attrappe()
        original = self.pfad.read_text(encoding="utf-8")
        ok, _ = io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        self.assertTrue(ok)
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), original)
        self.assertEqual(self.builds, [])
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertIn(z["status"], ("vorschlag", "keine_vorschlaege"), z.get("meldung"))
        self.assertEqual(z["vorher"]["kategorien"].keys(), {"A", "B", "C", "D", "E"})
        self.assertFalse(io.ist_gesperrt("test-artikel"))
        self.assertTrue(z["metas"]["felder"]["title"]["texte"])

    def test_llm_ausfall_wird_sauber_gemeldet(self):
        import llm

        def chat(*a, **k):
            raise llm.LLMFehler("LLM-Dienst nicht erreichbar (URLError)")
        ok, _ = io.starte(self.ctx(chat), "test-artikel", hintergrund=False)
        self.assertTrue(ok)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertNotEqual(z["status"], "laeuft")
        self.assertFalse(io.ist_gesperrt("test-artikel"))
        self.assertTrue(any(s["status"] == "fehler" for s in z["schritte"]))

    def test_abbruch_und_frist(self):
        chat, _ = self.chat_attrappe()
        ctx = self.ctx(chat)
        ctx.frist = -1  # Frist sofort abgelaufen
        ok, _ = io.starte(ctx, "test-artikel", hintergrund=False)
        z = self.speicher.lesen("inordnung", "test-artikel.json")
        self.assertEqual(z["status"], "abgebrochen")
        self.assertIn("Zeitlimit", z["meldung"])
        self.assertFalse(io.ist_gesperrt("test-artikel"))


class Stellenantwort(unittest.TestCase):
    def test_zuordnung_ueber_id_und_ablehnung(self):
        stellen = [{"id": 1, "start": 0, "ende": 10, "zeile": 1, "abschnitt": "", "zweck": ["kuerzen"], "hinweise": [], "art": "md", "oeffner": "",
                    "alt": "x", "alt_inner": "Das ist ein langer Satz mit genau 25 Wörtern, der hier nur dazu dient, die Prüfung auszulösen, weil er eben viel zu lang ist, nicht wahr."},
                   {"id": 2, "start": 20, "ende": 30, "zeile": 3, "abschnitt": "", "zweck": ["kuerzen"], "hinweise": [], "art": "md", "oeffner": "",
                    "alt": "y", "alt_inner": "Ein zweiter Satz bleibt unangetastet und wird vom Modell vergessen."}]
        antwort = {"stellen": [{"id": 1, "alt": "Das ist ein langer Satz mit genau", "neu": "Das ist ein langer Satz mit genau 26 Wörtern. Er löst die Prüfung aus."}]}
        ok, abg = io.verarbeite_antwort(stellen, antwort)
        self.assertEqual(ok, [])
        gruende = {a["id"]: a["grund"] for a in abg}
        self.assertIn("Zahlen", gruende[1])
        self.assertIn("keine Antwort", gruende[2])

    def test_falsche_stelle_wird_erkannt(self):
        stellen = [{"id": 1, "start": 0, "ende": 10, "zeile": 1, "abschnitt": "", "zweck": [], "hinweise": [], "art": "md", "oeffner": "",
                    "alt": "x", "alt_inner": "Alpha Beta Gamma Delta."}]
        ok, abg = io.verarbeite_antwort(stellen, {"stellen": [{"id": 1, "alt": "Ganz anderer Anfang", "neu": "Alpha Beta. Gamma Delta."}]})
        self.assertEqual(ok, [])
        self.assertIn("gehört nicht", abg[0]["grund"])

    def test_html_stelle_behaelt_oeffner(self):
        stellen = [{"id": 1, "start": 0, "ende": 10, "zeile": 1, "abschnitt": "", "zweck": [], "hinweise": [], "art": "html", "oeffner": '<p class="x">',
                    "alt": "<p>", "alt_inner": "Alpha <strong>Beta</strong> Gamma Delta Epsilon Zeta Eta Theta."}]
        ok, abg = io.verarbeite_antwort(stellen, {"stellen": [{"id": 1, "alt": "Alpha Beta Gamma", "neu": "Alpha <strong>Beta</strong> Gamma. Delta Epsilon Zeta Eta Theta."}]})
        self.assertEqual(abg, [])
        self.assertTrue(ok[0]["neu"].startswith('<p class="x">Alpha'))
        self.assertTrue(ok[0]["neu"].endswith("</p>"))


class DeployVorauswahl(unittest.TestCase):
    def test_fokus_auf_einen_artikel(self):
        def a(pfad, standard=True, ref=None):
            x = dp.Aenderung(pfad=pfad, code=" M", art="geaendert")
            x.standard, x.referenziert_von = standard, ref or []
            return x
        liste = [a("articles/x.md"), a("articles/y.md"), a("dist/artikel/x/index.html"), a("dist/artikel/y/index.html"),
                 a("dist/index.html"), a("dist/sitemap.xml"), a("templates/article.html"), a("static/img/b.png", ref=["x"]),
                 a("static/img/c.png", ref=["y"]), a("scripts/foo.py", standard=False)]
        dp.fokus_auf_artikel(liste, "x")
        an = {x.pfad for x in liste if x.standard}
        self.assertEqual(an, {"articles/x.md", "dist/artikel/x/index.html", "dist/index.html", "dist/sitemap.xml", "static/img/b.png"})


MD_HTML = """---
title: "T"
slug: test-artikel
date: 2026-09-28
description: "d"
---

## Erster Abschnitt
<p>Kurzer Satz eins. Dieser zweite Satz ist deutlich länger und enthält <strong>Fettes</strong> sowie <code>code()</code> und Zahlen wie 42. Dritter Satz. Vierter Satz hier.</p>
<p>Zweiter Absatz.</p>

## Zweiter Abschnitt

Markdown-Absatz mit **Fett** und `Code`. Noch ein Satz danach.
"""


class Anzeige(unittest.TestCase):
    def test_ueberschrift_klebt_nicht_am_absatz(self):
        bl = io.finde_bloecke(MD_HTML)
        arten = [(b.art, b.klar[:20]) for b in bl]
        self.assertEqual([a for a, _ in arten], ["h", "html", "html", "h", "md"], arten)
        absaetze = [b for b in bl if b.art in ("html", "md")]
        self.assertEqual(absaetze[0].abschnitt, "Erster Abschnitt")
        self.assertEqual(absaetze[0].abschnitt_id, "erster-abschnitt")
        self.assertEqual([b.absatz_nr for b in absaetze], [1, 2, 1])
        self.assertEqual(absaetze[2].abschnitt, "Zweiter Abschnitt")
        self.assertNotIn("Kurzer Satz", absaetze[0].abschnitt)

    def test_ort_fuer(self):
        b = [x for x in io.finde_bloecke(MD_HTML) if x.art == "html"][1]
        o = io.ort_fuer(MD_HTML, b.start)
        self.assertEqual((o["abschnitt"], o["absatz_nr"]), ("Erster Abschnitt", 2))

    def test_saetze_behalten_formatierung(self):
        h = "Kurzer Satz eins. Dieser zweite Satz ist <strong>fett. Und weiter</strong> geht es. Dr. Müller kam z. B. heute."
        teile = io.satz_teile(h)
        self.assertEqual(" ".join(teile).replace("  ", " "), h)
        self.assertTrue(teile[1].startswith("Dieser zweite"))

    def test_satz_hervorhebung_mit_kontext_und_ellipse(self):
        alt = "Satz A ist kurz. Satz B ist kurz. Satz C ist der lange Satz mit vielen Wörtern. Satz D ist kurz. Satz E ist kurz. Satz F ist kurz."
        neu = alt.replace("Satz C ist der lange Satz mit vielen Wörtern.", "Satz C ist lang. Er hat viele Wörter.")
        a = io.stelle_ansicht("html", alt, neu)
        k = a["kontext"]
        self.assertEqual(k.count('<mark class="treffer">'), 1)
        self.assertIn('<mark class="treffer">Satz C ist der lange', k)
        self.assertIn("Satz B", k)
        self.assertIn("Satz D", k)
        self.assertNotIn("Satz A", k)
        self.assertNotIn("Satz F", k)
        self.assertTrue(k.startswith("…") and k.endswith("…"))
        self.assertEqual(len(a["aenderungen"]), 1)
        self.assertIn("Satz C ist lang. Er hat", a["aenderungen"][0]["nachher"])

    def test_formatierung_im_vorher_nachher(self):
        alt = "Ein <strong>langer</strong> Satz mit <code>x()</code>, der noch weitergeht und weitergeht."
        neu = "Ein <strong>langer</strong> Satz mit <code>x()</code>. Er geht weiter."
        a = io.stelle_ansicht("html", alt, neu)
        self.assertIn("<strong>langer</strong>", a["aenderungen"][0]["vorher"])
        self.assertIn("<code>x()</code>", a["aenderungen"][0]["nachher"])

    def test_sicher_html(self):
        self.assertEqual(io.sicher_html("<script>alert(1)</script>Text"), "alert(1)Text")
        self.assertNotIn("onclick", io.sicher_html('<a href="https://x.example" onclick="x()">l</a>'))
        self.assertNotIn("javascript", io.sicher_html('<a href="javascript:x()">l</a>'))
        self.assertEqual(io.sicher_html("<strong>offen"), "<strong>offen</strong>")
        self.assertEqual(io.sicher_html("ende</strong>"), "ende")

    def test_markdown_block_wird_gerendert(self):
        a = io.stelle_ansicht("md", "Ein **fetter** Satz, der lang ist und weitergeht und weitergeht.", "Ein **fetter** Satz. Er geht weiter.")
        self.assertIn("<strong>fetter</strong>", a["kontext"])


class Zahlwort(unittest.TestCase):
    def pruefe(self, alt, neu):
        return io.schutzpruefung_stelle(alt, neu, [])

    def test_gleichwertig(self):
        self.assertEqual(self.pruefe("Limit (1× pro Stunde, 4× mit Schlüssel) gilt.", "Limit: einmal pro Stunde, viermal mit Schlüssel, gilt."), [])
        self.assertEqual(self.pruefe("Es gibt 2 Wege und 12 Knöpfe hier.", "Es gibt zwei Wege und zwölf Knöpfe hier."), [])
        self.assertEqual(self.pruefe("Es gibt zwei Wege und elf Knöpfe hier.", "Es gibt 2 Wege und 11 Knöpfe hier."), [])

    def test_echte_zahlenfehler_bleiben_verboten(self):
        for neu in ("Limit: einmal pro Stunde, fünfmal mit Schlüssel, gilt.", "Limit: zweimal pro Stunde, viermal mit Schlüssel, gilt.",
                    "Limit: einmal pro Stunde, mit Schlüssel, gilt."):
            g = self.pruefe("Limit (1× pro Stunde, 4× mit Schlüssel) gilt.", neu)
            self.assertTrue(g and "Zahlen" in g[0], (neu, g))
        self.assertTrue(self.pruefe("Es gibt 2 Wege.", "Es gibt drei Wege."))
        self.assertTrue(self.pruefe("Es gibt 13 Wege.", "Es gibt dreizehn Wege."))  # nur 2 bis 12 sind gleichwertig
        self.assertTrue(self.pruefe("Es gibt 1 Weg.", "Es gibt keinen Weg."))
        self.assertTrue(self.pruefe("Es kostet 4,5 Euro.", "Es kostet 45 Euro."))

    def test_ein_als_artikel_bleibt_unberuehrt(self):
        self.assertEqual(self.pruefe("Das ist ein langer Test mit Text.", "Das ist ein Test. Er ist lang."), [])

    def test_grund_nennt_konkrete_zahlen(self):
        g = self.pruefe("Preis 100 Euro und 7 Tage hier.", "Preis 90 Euro und 7 Tage hier.")[0]
        self.assertIn("„100“", g)
        self.assertIn("„90“", g)

    def test_fachbegriff_pruefung_ignoriert_reine_zahlen(self):
        self.assertEqual(self.pruefe("Das Limit (1× pro Stunde) gilt immer und überall.", "Das Limit gilt einmal pro Stunde, immer und überall."), [])


if __name__ == "__main__":
    unittest.main()


class JsonToleranzTest(unittest.TestCase):
    """Modelle liefern gern JSON mit Kommentaren, Kommas vor Klammern oder Zeilenumbruechen."""

    def test_toleranz(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "admin"))
        import llm
        self.assertEqual(llm.json_aus_text('{"a":1, // Notiz\n "b":2}'), {"a": 1, "b": 2})
        self.assertEqual(llm.json_aus_text('{"a":[1,2,],"b":{"c":3,},}'), {"a": [1, 2], "b": {"c": 3}})
        self.assertEqual(llm.json_aus_text('{"a":"x\ny"}'), {"a": "x\ny"})
        self.assertEqual(llm.json_aus_text('{"u":"http://x.ch/a//b"}'), {"u": "http://x.ch/a//b"})

    def test_abgeschnitten_meldet_grund(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "admin"))
        import llm
        with self.assertRaises(llm.LLMFehler) as cm:
            llm.json_aus_text('{"a":{"b":"ohne ende')
        self.assertIn("abgeschnitten", str(cm.exception))
