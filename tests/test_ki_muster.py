"""Zaehlregeln von „Klingt menschlich (KI-Muster)“ (ki_muster.py), Gewichtung in B und Schutzpruefung beim Umschreiben."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import bewertung as bw  # noqa: E402
import in_ordnung as io  # noqa: E402
import ki_muster as km  # noqa: E402


def anzahl(text, regel):
    return km.messe([text])[regel]["anzahl"]


class Zaehlregeln(unittest.TestCase):
    def test_gedankenstrich_positiv_und_negativ(self):
        self.assertEqual(anzahl("Das geht — und das auch -- sowie das – drei Striche.", "gedankenstrich"), 3)
        for negativ in ("Von 2010–2026 läuft das.", "Ein Wort-Teil mit Bindestrich.", "Preis 5—10 Euro.", "Rubrik - Titel mit Bindestrich.",
                        "Nur-Lesen und Ein-/Ausgabe.", "Zeitraum 2010 – 2026"[:0] + "Kein Strich."):
            self.assertEqual(anzahl(negativ, "gedankenstrich"), 0, negativ)

    def test_zitate_und_code_zaehlen_nicht(self):
        self.assertEqual(anzahl("Er sagte „Das — und jenes“ und ging.", "gedankenstrich"), 0)
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            meta = {"slug": "x", "title": "Titel", "description": "Beschr", "tags": []}
            b = bw.bewerte(meta, "<p>Normaler Text ohne Strich.</p><pre><code>a -- b — c</code></pre>", base_url="https://e.invalid",
                           static_dir=t / "s", dist_dir=t / "d", heute=date(2026, 10, 1))
            self.assertEqual(b.kennzahlen["ki_muster"]["gedankenstrich"]["anzahl"], 0)
            b = bw.bewerte(meta, "<p>Text — mit Strich.</p>", base_url="https://e.invalid", static_dir=t / "s", dist_dir=t / "d", heute=date(2026, 10, 1))
            self.assertEqual(b.kennzahlen["ki_muster"]["gedankenstrich"]["anzahl"], 1)

    def test_kontrast(self):
        self.assertEqual(anzahl("Das ist nicht schnell, sondern zuverlässig.", "kontrast"), 1)
        self.assertEqual(anzahl("Es ist nicht nur schnell, sondern auch sicher.", "kontrast"), 1)
        self.assertEqual(anzahl("Es gibt keinen Grund, sondern nur Zufall.", "kontrast"), 1)
        self.assertEqual(anzahl("Das ist nicht gut. Sondern schlecht.", "kontrast"), 0)
        self.assertEqual(anzahl("Das ist gut, sondern gibt es nicht ohne nicht.", "kontrast"), 0)

    def test_floskeln(self):
        self.assertEqual(anzahl("Kurz vorweg: es geht los. Der Punkt ist klar. Im Grunde einfach.", "floskel"), 3)
        self.assertEqual(anzahl("Die Grundlage und die Vorabversion bleiben.", "floskel"), 0)  # Wortgrenzen
        self.assertEqual(anzahl("Das ist der eigentliche Kern.", "floskel"), 1)

    def test_verstaerker(self):
        self.assertEqual(anzahl("Das ist ganz einfach und wirklich genau so.", "verstaerker"), 4)
        self.assertEqual(anzahl("Die ganze Eigentümerin hat es getestet.", "verstaerker"), 0)  # ganze/Eigentümerin sind keine Verstärker

    def test_rhythmus(self):
        gleich = "Der erste Satz hat sechs Wörter. Der zweite Satz hat sieben Wörter. Der dritte Satz hat auch sieben Wörter."
        self.assertEqual(anzahl(gleich, "rhythmus"), 1)
        variiert = "Kurz. Dieser Satz ist dagegen deutlich länger und trägt mehr Information als der erste. Mittel lang ist der dritte."
        self.assertEqual(anzahl(variiert, "rhythmus"), 0)
        kurz = "Das geht. Das auch. Das ebenso."
        self.assertEqual(anzahl(kurz, "rhythmus"), 0)  # unter 5 Wörtern zählt nicht

    def test_frage_mit_gleich_antwort(self):
        self.assertEqual(anzahl("Warum ist das so? Weil es funktioniert.", "frage"), 1)
        self.assertEqual(anzahl("Warum ist das so? Weil es mit sehr vielen Wörtern im Detail erklärt werden muss.", "frage"), 0)
        self.assertEqual(anzahl("Warum? Wie? Was?", "frage"), 0)

    def test_passiv_ist_nur_hinweis(self):
        m = km.messe(["Der Server wurde neu gestartet. Wir prüfen den Dienst."])
        self.assertEqual(m["passiv"]["anzahl"], 1)
        e_mit, _, _ = km.erfuellung(m)
        e_ohne, _, _ = km.erfuellung(km.messe(["Wir starteten den Server neu. Wir prüfen den Dienst."]))
        self.assertEqual(e_mit, e_ohne)

    def test_erfuellung(self):
        e, text, _ = km.erfuellung(km.messe(["Ein ruhiger Text mit normalem Rhythmus. Er kommt ohne Muster aus, auch wenn er etwas länger wird."]))
        self.assertEqual(e, 100.0)
        schlecht = " — ".join(["Satz"] * 40)
        e2, text2, tipp = km.erfuellung(km.messe([schlecht]))
        self.assertLessEqual(e2, 75)
        self.assertIn("Gedankenstriche", text2)
        self.assertIn("Punkt, Komma", tipp)

    def test_regeln_sind_dokumentiert_und_erweiterbar(self):
        for r in km.REGELN:
            self.assertTrue(r["id"] and r["name"] and r["beschreibung"] and r["vorschlag"] and "soll" in r)
        self.assertIn("stop-slop", km.QUELLE)

    def test_gewicht_in_b_unveraendert(self):
        self.assertEqual(sum(v[2] for v in bw.KRITERIEN.values() if v[0] == "B"), bw.KATEGORIEN["B"]["gewicht"])
        self.assertEqual(sum(v[2] for v in bw.KRITERIEN.values() if v[0] == "A"), bw.KATEGORIEN["A"]["gewicht"])
        self.assertEqual(sum(g["gewicht"] for g in bw.KATEGORIEN.values()), 100)
        self.assertIn("b_menschlich", io.AUTOMATISCH)

    def test_funde_mit_fundstelle(self):
        text = "---\ntitle: x\nslug: x\ndate: 2026-01-01\ndescription: y\n---\n\n## Abschnitt Eins\n\nEin Satz — mit Strich. Das ist ganz einfach.\n"
        funde = km.funde(io.finde_bloecke(text))
        self.assertEqual(len(funde), 1)
        self.assertEqual((funde[0]["abschnitt"], funde[0]["absatz"]), ("Abschnitt Eins", 1))
        self.assertTrue(any(t["regel"] == "Gedankenstriche" for t in funde[0]["treffer"]))


class Schutzpruefung(unittest.TestCase):
    ALT = "Der Dienst läuft seit 2010–2026 stabil — und das ist ganz einfach so. Er sagte „Das — bleibt“ wörtlich."

    def test_gedankenstrich_ersetzen_und_fuellwort_streichen_ist_erlaubt(self):
        neu = "Der Dienst läuft seit 2010–2026 stabil, und das ist so. Er sagte „Das — bleibt“ wörtlich."
        self.assertEqual(io.schutzpruefung_stelle(self.ALT, neu, ["ki_muster"]), [])

    def test_zitate_zahlen_und_bereiche_bleiben_geschuetzt(self):
        self.assertTrue(any("Zitate" in v for v in io.schutzpruefung_stelle(self.ALT, self.ALT.replace("„Das — bleibt“", "„Das bleibt“").replace(" — und", ", und"), ["ki_muster"])))
        self.assertTrue(any("Zahlen" in v for v in io.schutzpruefung_stelle(self.ALT, self.ALT.replace("2010–2026", "2010 bis 2025").replace(" — und", ", und"), ["ki_muster"])))

    def test_ohne_weniger_muster_wird_abgelehnt(self):
        neu = self.ALT.replace("stabil", "zuverlässig")
        g = io.schutzpruefung_stelle(self.ALT, neu, ["ki_muster"])
        self.assertTrue(g and "keine Verbesserung" in g[0])


if __name__ == "__main__":
    unittest.main()


class Lektorat_Deploy_Prompts(unittest.TestCase):
    def test_lektorat_kennt_das_kriterium_und_die_regeln(self):
        import llm
        self.assertIn("klingt_menschlich", llm.LEKTORAT_KRITERIEN)
        p = llm.lektorat_prompt({"title": "t", "description": "d", "tags": []}, "Text", "Messwerte")
        self.assertIn('"klingt_menschlich"', p)
        self.assertIn("Keine Gedankenstriche", p)
        self.assertIn("Fundstellen im Wortlaut", p)

    def test_metas_prompt_verbietet_gedankenstriche_und_floskeln(self):
        import llm
        self.assertIn("Keine Gedankenstriche", llm.METAS_SYSTEM)
        self.assertIn("Floskeln", llm.METAS_SYSTEM)

    def test_text_prompt_hat_die_regeln(self):
        s = {"id": 1, "zweck": ["kuerzen"], "hinweise": [], "alt_inner": "Text.", "abschnitt": "", "davor": ""}
        p = io.text_prompt([s])
        self.assertIn("keine neuen Gedankenstriche", p)
        s["zweck"] = ["ki_muster"]
        self.assertIn("Gedankenstriche", io.text_prompt([s]))

    def test_metas_grenzpruefung_lehnt_gedankenstrich_ab(self):
        import metas_auswahl as ma
        titel = "Monitoring im Homelab — Firewall, Tunnel und KI im Zusammenspiel"
        self.assertIn("Gedankenstrich", ma.pruefe_meta("title", titel) or "")
        self.assertIsNone(ma.pruefe_meta("title", "Monitoring im Homelab: Firewall, Tunnel und KI im Zusammenspiel"))
        self.assertIsNone(ma.pruefe_meta("title", "Zahlen von 2010–2026: Archiv, API und KI-Recherche ohne Login"))  # Zahlenbereich ist erlaubt

    def test_deploy_hinweis_ist_nie_ein_sperrgrund(self):
        import deploy_views
        import tempfile
        meta = {"slug": "x", "title": "Ein Titel mit genug Zeichen für den Test hier", "description": "Beschreibung " * 8, "tags": ["a"]}
        text = "<p>" + " — ".join(["Satz mit Strich"] * 30) + "</p>"
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            b = bw.bewerte(meta, text, base_url="https://e.invalid", static_dir=t / "s", dist_dir=t / "d", heute=date(2026, 10, 1))
            zeilen = deploy_views.vorab_pruefung(["x"], {"site": {"base_url": "https://e.invalid"}}, {"x": dict(meta, body_md="x", source=Path("x.md"))}, {"x": b})
        p = next(x for x in zeilen[0]["pruefungen"] if x["name"] == "Klingt menschlich")
        self.assertEqual(p["stufe"], "warn")
        self.assertIn("Gedankenstriche", p["text"])
        self.assertIn("/verwaltung/ranking/x", p["link"])
        self.assertFalse(any(x["stufe"] == "fehler" and x["name"] == "Klingt menschlich" for x in zeilen[0]["pruefungen"]))
