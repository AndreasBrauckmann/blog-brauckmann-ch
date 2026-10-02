"""Tests fuer den Versionsverlauf (versionen.py) und das Wiederherstellen (in_ordnung.wiederherstellen).

Nur Wegwerf-Verzeichnisse/-Repos unter tempfile; nie articles/ oder data/ des echten Blogs.
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import in_ordnung as io  # noqa: E402
import versionen as vz  # noqa: E402
from ranking_daten import Speicher  # noqa: E402


def art(titel="Titel", text="Ein Absatz mit fuenf Woertern.", slug="a"):
    return f'---\ntitle: "{titel}"\nslug: {slug}\ndate: 2026-09-28\ndescription: "Beschreibung"\n---\n\n{text}\n'


def sh(cwd, *cmd):
    return subprocess.run(list(cmd), cwd=cwd, check=True, capture_output=True, text=True)


class Basis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "articles").mkdir()
        self.pfad = self.root / "articles" / "a.md"
        self.pfad.write_text(art(), encoding="utf-8")
        io._aktiv.clear()

    def tearDown(self):
        io._aktiv.clear()
        self.tmp.cleanup()

    def git_init(self):
        sh(self.root, "git", "init", "-q", "-b", "master")
        sh(self.root, "git", "config", "user.name", "T")
        sh(self.root, "git", "config", "user.email", "t@example.invalid")

    def commit(self, msg):
        sh(self.root, "git", "add", "articles/a.md")
        sh(self.root, "git", "commit", "-q", "-m", msg)


class Schnappschuesse(Basis):
    def test_erste_erfassung_und_dedup(self):
        e = vz.abgleich(self.root, "a")
        self.assertEqual(e["grund"], "start")
        self.assertIsNone(vz.abgleich(self.root, "a"))  # unveraendert: nichts Neues
        self.assertEqual(len(vz.alle(self.root, "a")), 1)

    def test_externe_aenderung_wird_erkannt(self):
        vz.abgleich(self.root, "a")
        self.pfad.write_text(art(text="Von Hand geaendert, mit mehr Woertern als vorher."), encoding="utf-8")
        e = vz.abgleich(self.root, "a")
        self.assertEqual(e["grund"], "extern")
        zeilen = vz.alle(self.root, "a")
        self.assertEqual(len(zeilen), 2)
        self.assertTrue(zeilen[0]["aktuell"])
        self.assertFalse(zeilen[1]["aktuell"])
        self.assertGreater(zeilen[0]["d_woerter"], 0)
        self.assertFalse(zeilen[0]["titel_geaendert"])

    def test_titel_flag(self):
        vz.abgleich(self.root, "a")
        self.pfad.write_text(art(titel="Neu"), encoding="utf-8")
        vz.abgleich(self.root, "a")
        self.assertTrue(vz.alle(self.root, "a")[0]["titel_geaendert"])

    def test_gesperrt_kein_abgleich(self):
        vz.abgleich(self.root, "a")
        self.pfad.write_text(art(text="Mitten im Schreibvorgang."), encoding="utf-8")
        io.sperre_nehmen("a")
        self.assertIsNone(vz.abgleich(self.root, "a"))
        io.sperre_freigeben("a")
        self.assertIsNotNone(vz.abgleich(self.root, "a"))

    def test_backups_werden_einsortiert_nicht_doppelt(self):
        vz.abgleich(self.root, "a")
        bdir = self.root / "data" / "backups" / "artikel"
        bdir.mkdir(parents=True)
        (bdir / "a.20260101-101010.md").write_text(art(text="Uralt."), encoding="utf-8")
        (bdir / "a.20260102-101010.md").write_text(art(), encoding="utf-8")  # gleicher Inhalt wie aktuell
        vz.abgleich(self.root, "a")
        vz.abgleich(self.root, "a")
        zeilen = vz.alle(self.root, "a")
        self.assertEqual(len(zeilen), 2)
        self.assertEqual(zeilen[-1]["grund"], "backup")
        self.assertEqual(zeilen[-1]["zeit"][:10], "2026-01-01")

    def test_aufbewahrung_200_und_geschuetzte_fassung(self):
        self.git_init()
        self.commit("alt")
        geschuetzt = self.pfad.read_text(encoding="utf-8")
        vz.abgleich(self.root, "a")
        for i in range(205):
            vz.sichere(self.root, "a", art(text=f"Version {i} " + "w " * i), "extern", datetime.now())
        d = vz._lade(self.root, "a")
        self.assertEqual(len(d["eintraege"]), 200)
        hashes = {e["hash"] for e in d["eintraege"]}
        self.assertIn(vz.hash_text(geschuetzt), hashes)  # zuletzt committete Fassung bleibt
        dateien = list((self.root / "data" / "versions" / "a").glob("*.md"))
        self.assertEqual(len(dateien), 200)


class GitDedup(Basis):
    def test_commit_und_schnappschuss_eine_zeile(self):
        self.git_init()
        self.commit("Erster Stand")
        vz.abgleich(self.root, "a")
        self.pfad.write_text(art(text="Zweiter Stand, geaendert."), encoding="utf-8")
        vz.abgleich(self.root, "a")
        self.commit("Zweiter Stand")
        self.pfad.write_text(art(text="Dritter Stand, nur lokal."), encoding="utf-8")
        vz.abgleich(self.root, "a")
        zeilen = vz.alle(self.root, "a")
        self.assertEqual(len(zeilen), 3)  # 3 Inhalte, Commits mit Schnappschuessen zusammengelegt
        mit_commit = [z["commit"]["meldung"] for z in zeilen if z["commit"]]
        self.assertEqual(sorted(mit_commit), ["Erster Stand", "Zweiter Stand"])
        self.assertIsNone(zeilen[0]["commit"])
        self.assertTrue(zeilen[0]["aktuell"])

    def test_commit_ohne_schnappschuss_wird_eigene_zeile_und_wiederherstellbar(self):
        self.git_init()
        self.commit("Alt")
        alt_text = self.pfad.read_text(encoding="utf-8")
        self.pfad.write_text(art(text="Neu."), encoding="utf-8")
        self.commit("Neu")
        zeilen = vz.alle(self.root, "a")
        self.assertEqual([z["quelle"] for z in zeilen], ["git", "git"])
        self.assertTrue(zeilen[0]["aktuell"])
        self.assertEqual(vz.text_von(self.root, "a", zeilen[1]["vid"]), alt_text)

    def test_ungueltige_vid(self):
        self.assertIsNone(vz.text_von(self.root, "a", "s-../../etc/passwd"))
        self.assertIsNone(vz.text_von(self.root, "a", "g-nichtsha"))


class Wiederherstellen(Basis):
    def ctx(self, build_ok=True, pflicht=None):
        self.builds = []

        def baue():
            self.builds.append(self.pfad.read_text(encoding="utf-8"))
            return build_ok, "ok" if build_ok else "Fehler: kaputt"

        def bewerte(slug):
            import bewertung as bw
            import build
            meta = build.parse_article(self.pfad)
            b = bw.bewerte(meta, build.render_markdown(meta["body_md"]), base_url="https://example.invalid", static_dir=self.root / "static",
                           dist_dir=self.root / "dist", heute=datetime(2026, 10, 1).date(), alle_slugs=["a"])
            return meta, b
        return io.Kontext(root=self.root, speicher=Speicher(self.root), chat=lambda *a, **k: "{}", bewerte=bewerte, baue=baue,
                          pflicht_fehlt=lambda s: list(pflicht or []))

    def zwei_versionen(self):
        vz.abgleich(self.root, "a")
        alt = self.pfad.read_text(encoding="utf-8")
        self.pfad.write_text(art(titel="Neuer Titel", text="Ganz anderer Text."), encoding="utf-8")
        vz.abgleich(self.root, "a")
        alt_vid = [z for z in vz.alle(self.root, "a") if not z["aktuell"]][0]["vid"]
        return alt, alt_vid

    def test_erfolg(self):
        alt, vid = self.zwei_versionen()
        neu = self.pfad.read_text(encoding="utf-8")
        erg = io.wiederherstellen(self.ctx(), "a", vid)
        self.assertTrue(erg["ok"], erg)
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), alt)
        self.assertEqual(len(self.builds), 1)
        zeilen = vz.alle(self.root, "a")
        self.assertEqual(zeilen[0]["grund"], "wiederhergestellt")
        # die vorherige Fassung steht als Version da: Wiederherstellen laesst sich zuruecknehmen
        self.assertTrue(any(vz.text_von(self.root, "a", z["vid"]) == neu for z in zeilen))
        self.assertFalse(io.ist_gesperrt("a"))
        z = Speicher(self.root).lesen("inordnung", "a.json")
        self.assertEqual(z["status"], "wiederhergestellt")
        self.assertIsNotNone(z["nachher"])

    def test_build_fehler_rollback(self):
        alt, vid = self.zwei_versionen()
        neu = self.pfad.read_text(encoding="utf-8")
        erg = io.wiederherstellen(self.ctx(build_ok=False), "a", vid)
        self.assertFalse(erg["ok"])
        self.assertTrue(erg["zurueckgespielt"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), neu)
        self.assertEqual(len(self.builds), 2)
        self.assertEqual(self.builds[1], neu)
        self.assertNotEqual(vz.alle(self.root, "a")[0]["grund"], "wiederhergestellt")

    def test_pflicht_tag_rollback(self):
        alt, vid = self.zwei_versionen()
        neu = self.pfad.read_text(encoding="utf-8")
        erg = io.wiederherstellen(self.ctx(pflicht=["image/og:image"]), "a", vid)
        self.assertFalse(erg["ok"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), neu)

    def test_ungueltige_fassung_und_gleiche_fassung(self):
        alt, vid = self.zwei_versionen()
        # Version mit falschem Slug darf nicht zurueckgespielt werden
        vz.sichere(self.root, "a", art(slug="b", text="Anderer Slug."), "extern", datetime.now())
        zeilen = vz.alle(self.root, "a")
        vid_b = next(z["vid"] for z in zeilen if z["hash"] == vz.hash_text(art(slug="b", text="Anderer Slug.")))
        erg = io.wiederherstellen(self.ctx(), "a", vid_b)
        self.assertFalse(erg["ok"])
        self.assertIn("Slug", erg["meldung"])
        aktuell_vid = vz.alle(self.root, "a")
        self.assertFalse(io.wiederherstellen(self.ctx(), "a", "s-99999999-999999__x")["ok"])

    def test_sperre(self):
        alt, vid = self.zwei_versionen()
        io.sperre_nehmen("a")
        neu = self.pfad.read_text(encoding="utf-8")
        erg = io.wiederherstellen(self.ctx(), "a", vid)
        self.assertFalse(erg["ok"])
        self.assertEqual(self.pfad.read_text(encoding="utf-8"), neu)


class SchreibwegeSichern(Basis):
    """Jeder Schreibweg der Verwaltung legt vorher und nachher eine Version an."""

    def test_uebernehmen_legt_versionen_an(self):
        import test_in_ordnung as t  # Wegwerf-Aufbau wiederverwenden
        x = t.Uebernehmen("test_erfolg_backup_schreiben_bauen")
        x.setUp()
        try:
            x.vorschlag_zustand()
            self.assertTrue(io.uebernehmen(x.ctx(), "test-artikel", {"title": t.TITEL_OK}, {1})["ok"])
            zeilen = vz.alle(x.root, "test-artikel")
            self.assertEqual([z["grund"] for z in zeilen][:2], ["ordnung", "start"])
            erg = io.rueckgaengig(x.ctx(), "test-artikel")
            self.assertTrue(erg["ok"])
            zeilen = vz.alle(x.root, "test-artikel")
            self.assertEqual(zeilen[0]["grund"], "rueckgaengig")
            self.assertTrue(zeilen[0]["aktuell"] or zeilen[0]["hash"] == zeilen[-1]["hash"])
        finally:
            x.tearDown()

    def test_build_fehler_laesst_ausgangsstand_als_version(self):
        import test_in_ordnung as t
        x = t.Uebernehmen("test_erfolg_backup_schreiben_bauen")
        x.setUp()
        try:
            x.vorschlag_zustand()
            x.build_ok = False
            io.uebernehmen(x.ctx(), "test-artikel", {"title": t.TITEL_OK}, {1})
            zeilen = vz.alle(x.root, "test-artikel")
            self.assertEqual(len(zeilen), 1)  # nur der Ausgangsstand, keine halbe Version
            self.assertTrue(zeilen[0]["aktuell"])
        finally:
            x.tearDown()


if __name__ == "__main__":
    unittest.main()
