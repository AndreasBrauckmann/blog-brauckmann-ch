"""Tests: Kriterium F (Satz & Layout), Zwischenspeicher der Messung, CSS-Entwurf, Gutachten (Claude) mit gestubbter CLI.
Keine Playwright-/CLI-Aufrufe, keine echten Dateien."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import bewertung as bw  # noqa: E402
import gutachten as gt  # noqa: E402
import in_ordnung as io  # noqa: E402
import llm  # noqa: E402
import satz_views  # noqa: E402
import satzmessung as sm  # noqa: E402
from ranking_daten import Speicher  # noqa: E402


def zustand(**kw):
    basis = {"schrift_px": 18.0, "zeilenhoehe": 1.7, "absatz_abstand_zeilen": 1.2, "spaltenbreite_px": 600, "zeichen_je_zeile": 66,
             "kontrast_text": 17.0, "kontrast_link": 8.0, "kontrast_gedaempft": 7.5, "h1": {"zeilen": 2, "px": 36, "lh": 40, "mt": 0, "mb": 10},
             "h2": {"zeilen": 1, "px": 25, "lh": 30, "mt": 70, "mb": 15}, "absatz_mb": 30, "seite_ueberlauf": False,
             "breite": {"tabellen_frei": 0, "tabellen_box": 0, "code_frei": 0, "code_box": 0, "bilder": 0},
             "liste": {"einzug_em": 1.5, "abstand_zeilen": 0.4}, "bilder_gesamt": 2, "bilder_ohne_alt": 0}
    basis.update(kw)
    return basis


def roh(desktop=None, handy=None):
    d, h = zustand(**(desktop or {})), zustand(**{"zeichen_je_zeile": 45, "h1": {"zeilen": 3, "px": 30, "lh": 35, "mt": 0, "mb": 10}, **(handy or {})})
    return {"kontexte": {"hell|desktop": d, "hell|handy": h, "dunkel|desktop": d, "dunkel|handy": h}}


class FKriterien(unittest.TestCase):
    def status(self, r):
        return {k.id: k.status for k in bw.bewerte_satz(r)}

    def test_guter_satz_ist_gruen(self):
        s = self.status(roh())
        for kid in ("f_schrift", "f_zeilenhoehe", "f_zeilenlaenge", "f_absatz", "f_kontrast", "f_h1", "f_ueberschrift", "f_scroll", "f_listen"):
            self.assertEqual(s[kid], "ok", kid)
        self.assertEqual(s["f_alt"], "na")

    def test_maengel_werden_erkannt(self):
        s = self.status(roh(desktop={"schrift_px": 16.0, "zeichen_je_zeile": 85, "absatz_abstand_zeilen": 0.62, "kontrast_link": 6.4,
                                     "liste": {"einzug_em": 2.5, "abstand_zeilen": 0.0}, "h1": {"zeilen": 4, "px": 30, "lh": 35, "mt": 0, "mb": 0}},
                            handy={"seite_ueberlauf": True}))
        self.assertEqual(s["f_schrift"], "teils")
        self.assertIn(s["f_zeilenlaenge"], ("teils", "nein"))
        self.assertIn(s["f_absatz"], ("teils", "nein"))
        self.assertEqual(s["f_kontrast"], "teils")
        self.assertEqual(s["f_listen"], "nein")
        self.assertEqual(s["f_scroll"], "nein")
        self.assertNotEqual(s["f_h1"], "ok")

    def test_kontrast_grenzen(self):
        self.assertEqual(self.status(roh(desktop={"kontrast_gedaempft": 7.0}))["f_kontrast"], "ok")
        self.assertEqual(self.status(roh(desktop={"kontrast_gedaempft": 4.6}))["f_kontrast"], "teils")
        self.assertEqual(self.status(roh(desktop={"kontrast_gedaempft": 3.0}))["f_kontrast"], "nein")

    def test_h1_zeilen(self):
        for handy_zeilen, erwartet in ((3, "ok"), (4, "teils"), (5, "nein"), (7, "nein")):
            r = roh(handy={"h1": {"zeilen": handy_zeilen, "px": 30, "lh": 35, "mt": 0, "mb": 0}})
            self.assertEqual(self.status(r)["f_h1"], erwartet, handy_zeilen)

    def test_scroll_in_eigener_box_ist_teilweise(self):
        r = roh(handy={"breite": {"tabellen_frei": 0, "tabellen_box": 1, "code_frei": 0, "code_box": 1, "bilder": 0}})
        k = {x.id: x for x in bw.bewerte_satz(r)}["f_scroll"]
        self.assertEqual(k.status, "teils")
        self.assertIn("eigener Box", k.messwert)

    def test_gewichte_mit_und_ohne_f(self):
        class B:  # Gesamtscore-Gewichte der Bewertung
            pass
        mit = bw.Bewertung("x", "x", [bw.Kriterium("a_titel", "A", "t", 3, "", 100.0, "")] + bw.bewerte_satz(roh()))
        w = mit.gewichte()
        self.assertAlmostEqual(sum(w.values()), 100.0)
        self.assertEqual(w["F"], 10)
        self.assertAlmostEqual(w["A"], 22.5)
        ohne = bw.Bewertung("x", "x", [bw.Kriterium("a_titel", "A", "t", 3, "", 100.0, "")])
        self.assertEqual(ohne.gewichte(), {k: bw.KATEGORIEN[k]["gewicht"] for k in bw.KATEGORIEN})
        self.assertAlmostEqual(sum(ohne.gewichte().values()), 100.0)

    def test_f_nur_mit_messung_im_gesamtscore(self):
        kr = [bw.Kriterium("a_titel", "A", "t", 3, "", 100.0, "")]
        self.assertEqual(bw.Bewertung("x", "x", kr).gesamt, 22.5 / 22.5 * 25 * 1.0)  # nur A: 25 von 100
        schlecht = bw.Bewertung("x", "x", kr + bw.bewerte_satz(roh(desktop={"schrift_px": 12.0})))
        self.assertLess(schlecht.gesamt, 25 * 0.9 + 10)


class Zwischenspeicher(unittest.TestCase):
    def test_hash_wechsel_macht_eintrag_ungueltig(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seite = root / "dist" / "artikel" / "a" / "index.html"
            seite.parent.mkdir(parents=True)
            seite.write_text("<html>eins</html>", encoding="utf-8")
            h = sm.seiten_hash(root, "a")
            sm._speichern(root, "a", h, roh())
            self.assertIsNotNone(sm.gespeichert(root, "a"))
            seite.write_text("<html>zwei</html>", encoding="utf-8")  # neuer Build
            self.assertIsNone(sm.gespeichert(root, "a"))
            self.assertEqual(sm.seiten_hash(root, "fehlt"), "")

    def test_uebersicht_zaehlt_betroffene(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for slug, px in (("a", 16.0), ("b", 16.0), ("c", 18.0)):
                seite = root / "dist" / "artikel" / slug / "index.html"
                seite.parent.mkdir(parents=True)
                seite.write_text("x" + slug, encoding="utf-8")
                sm._speichern(root, slug, sm.seiten_hash(root, slug), roh(desktop={"schrift_px": px}))
            u = sm.uebersicht(root, ["a", "b", "c", "d"])
            self.assertEqual((u["f_schrift"]["betroffen"], u["f_schrift"]["gemessen"]), (2, 3))
            self.assertIsNone(u["f_schrift"]["artikel"]["d"])  # nicht gemessen

    def test_hintergrund_misst_nur_veraltete_und_nie_doppelt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seite = root / "dist" / "artikel" / "a" / "index.html"
            seite.parent.mkdir(parents=True)
            seite.write_text("x", encoding="utf-8")
            sm._messend.clear()
            with mock.patch.object(sm, "messlauf", return_value=roh()) as m:
                self.assertEqual(sm.im_hintergrund(root, ["a"]), 1)
                for _ in range(100):
                    if not sm.wird_gemessen("a"):
                        break
                    import time
                    time.sleep(0.02)
                self.assertTrue(sm.gespeichert(root, "a"))
                self.assertEqual(sm.im_hintergrund(root, ["a"]), 0)  # aktuell: nichts zu tun
                self.assertEqual(m.call_count, 1)


class CssEntwurf(unittest.TestCase):
    def test_anhaengen_und_nie_verdoppeln(self):
        alt = "body { color: black; }\n"
        v1 = satz_views.css_mit_entwurf(alt, "p { margin: 0 0 1.2em; }", "01.10.2026 12:00")
        self.assertTrue(v1.startswith(alt.rstrip()))
        self.assertIn("p { margin: 0 0 1.2em; }", v1)
        v2 = satz_views.css_mit_entwurf(v1, "p { margin: 0 0 1.3em; }", "01.10.2026 13:00")
        self.assertEqual(v2.count("Typografie-Entwurf (übernommen"), 1)
        self.assertIn("1.3em", v2)
        self.assertNotIn("1.2em", v2)
        self.assertTrue(v2.startswith(alt.rstrip()))  # Bestand davor bleibt unveraendert


class GutachtenLauf(unittest.TestCase):
    def ausgabe(self, inhalt, **kw):
        return json.dumps({"type": "result", "is_error": False, "result": json.dumps(inhalt), "num_turns": 4, "duration_ms": 12000,
                           "modelUsage": {"claude-opus-5-5": {}}, **kw})

    def test_befehl_nur_lesen(self):
        c = gt.befehl("/x/claude", "Prompt")
        self.assertEqual(c[c.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(c[c.index("--allowedTools") + 1], "Read,Grep,Glob")
        verboten = c[c.index("--disallowedTools") + 1]
        for w in ("Bash", "Edit", "Write", "WebFetch", "WebSearch", "Read(./.env)"):
            self.assertIn(w, verboten)
        self.assertEqual(c[c.index("--max-turns") + 1], "12")
        self.assertEqual(c[c.index("--model") + 1], "opus")
        self.assertEqual(c[c.index("--permission-mode") + 1], "dontAsk")

    def test_umgebung_ohne_schluessel(self):
        with mock.patch.dict(os.environ, {"BLOG_LLM_API_KEY": "geheim", "MASTODON_ACCESS_TOKEN": "geheim2", "HOME": "/h", "PATH": "/p"}):
            env = gt.minimale_umgebung()
        self.assertEqual(env.get("HOME"), "/h")
        self.assertNotIn("BLOG_LLM_API_KEY", env)
        self.assertNotIn("MASTODON_ACCESS_TOKEN", env)

    def test_auswerten(self):
        e = gt.auswerten(self.ausgabe({"zusammenfassung": "Gut.", "befunde": [{"kriterium": "Lesefluss", "schwere": "Hoch", "fundstelle": "Abschnitt „A“, Absatz 2", "vorschlag": "Kürzen."}]}))
        self.assertEqual(e["turns"], 4)
        self.assertEqual(e["modell"], "claude-opus-5-5")
        self.assertEqual(e["befunde"][0]["schwere"], "hoch")
        with self.assertRaises(llm.LLMFehler) as c:
            gt.auswerten(json.dumps({"is_error": True, "result": "Please login to continue"}))
        self.assertIn("nicht angemeldet", str(c.exception))
        with self.assertRaises(llm.LLMFehler):
            gt.auswerten("kein json")

    def test_fehlende_cli_klare_meldung(self):
        with mock.patch.object(gt.shutil, "which", return_value=None), mock.patch.object(gt.Path, "exists", return_value=False):
            ok, text = gt.pruefe_cli()
        self.assertFalse(ok)
        self.assertIn("nicht gefunden", text)

    def ctx(self, root):
        return io.Kontext(root=root, speicher=Speicher(root), chat=lambda *a, **k: "{}", bewerte=lambda s: (None, None), baue=lambda: (True, ""))

    def test_lauf_speichert_ergebnis_und_schreibt_nichts_in_den_artikel(self):
        class Proc:
            returncode = 0

            def __init__(self, *a, **k):
                self.kommando = a[0]

            def communicate(self, timeout=None):
                return GutachtenLauf.ausgabe(self, {"zusammenfassung": "ok", "befunde": []}), ""

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "articles").mkdir()
            art = root / "articles" / "a.md"
            art.write_text("---\ntitle: x\n---\nText", encoding="utf-8")
            ctx = self.ctx(root)
            z = {"slug": "a", "status": "laeuft"}
            with mock.patch.object(gt, "pruefe_cli", return_value=(True, "/x/claude")), mock.patch.object(gt.satzmessung, "bilder_fuer_gutachten", return_value=[]):
                gt.lauf(ctx, "a", z, 9e18, popen=Proc)
            self.assertEqual(z["status"], "fertig")
            self.assertEqual(ctx.speicher.lesen("gutachten", "a.json")["zusammenfassung"], "ok")
            self.assertEqual(art.read_text(encoding="utf-8"), "---\ntitle: x\n---\nText")

    def test_abbrechen_beendet_den_prozess(self):
        class Haengt:
            returncode = None
            tot = False

            def __init__(self, *a, **k):
                pass

            def communicate(self, timeout=None):
                if Haengt.tot:
                    return "", ""
                io.abbruch_anfordern("a")  # der Nutzer klickt „Abbrechen“, waehrend Claude laeuft
                raise subprocess.TimeoutExpired("claude", timeout)

            def kill(self):
                Haengt.tot = True

        with tempfile.TemporaryDirectory() as td:
            ctx = self.ctx(Path(td))
            io.sperre_nehmen("a")
            with mock.patch.object(gt, "pruefe_cli", return_value=(True, "/x/claude")), mock.patch.object(gt.satzmessung, "bilder_fuer_gutachten", return_value=[]):
                with self.assertRaises(io.AuftragFehler):
                    gt.lauf(ctx, "a", {"slug": "a"}, 9e18, popen=Haengt)
            io.sperre_freigeben("a")
            self.assertTrue(Haengt.tot)

    def test_timeout(self):
        class Haengt:
            returncode = None
            tot = False

            def __init__(self, *a, **k):
                pass

            def communicate(self, timeout=None):
                if Haengt.tot:
                    return "", ""
                raise subprocess.TimeoutExpired("claude", timeout)

            def kill(self):
                Haengt.tot = True

        with tempfile.TemporaryDirectory() as td:
            ctx = self.ctx(Path(td))
            with mock.patch.object(gt, "pruefe_cli", return_value=(True, "/x/claude")), mock.patch.object(gt.satzmessung, "bilder_fuer_gutachten", return_value=[]), \
                    mock.patch.object(gt, "TIMEOUT", -1):
                with self.assertRaises(llm.LLMFehler) as c:
                    gt.lauf(ctx, "a", {"slug": "a"}, 9e18, popen=Haengt)
            self.assertIn("Zeitüberschreitung", str(c.exception))
            self.assertTrue(Haengt.tot)

    def test_sperre_je_artikel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "articles").mkdir()
            (root / "articles" / "a.md").write_text("x", encoding="utf-8")
            (root / "dist" / "artikel" / "a").mkdir(parents=True)
            (root / "dist" / "artikel" / "a" / "index.html").write_text("x", encoding="utf-8")
            io.sperre_nehmen("a")
            with mock.patch.object(gt, "pruefe_cli", return_value=(True, "/x/claude")):
                ok, info = gt.starte(self.ctx(root), "a")
            io.sperre_freigeben("a")
            self.assertFalse(ok)
            self.assertIn("läuft bereits", info)


if __name__ == "__main__":
    unittest.main()
