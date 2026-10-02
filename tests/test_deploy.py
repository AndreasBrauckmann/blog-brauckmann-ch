"""Tests fuer Deploy-Panel (deploy.py) und eigenen Inspector (inspector.py).

Git-Tests laufen ausschliesslich in einem Wegwerf-Repo mit eigenem
Bare-Remote unter tempfile - nie gegen das echte origin. Der Inspector wird
mit einer Fake-Abruffunktion getestet (kein Netz).

    .venv/bin/python -m unittest discover -s tests -v
"""

import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import deploy as dp  # noqa: E402
import inspector  # noqa: E402


def _sh(cwd, *cmd):
    return subprocess.run(list(cmd), cwd=cwd, check=True, capture_output=True, text=True)


class WegwerfRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        basis = Path(self.tmp.name)
        _sh(basis, "git", "init", "-q", "--bare", "-b", "master", "origin.git")
        _sh(basis, "git", "clone", "-q", str(basis / "origin.git"), "w")
        self.r = basis / "w"
        _sh(self.r, "git", "config", "user.name", "Test")
        _sh(self.r, "git", "config", "user.email", "test@example.invalid")
        _sh(self.r, "git", "checkout", "-q", "-b", "master")
        for p, inhalt in {"articles/a.md": "alt", "dist/a.html": "alt", "static/img/alt.png": "x", "config.yaml": "a: 1"}.items():
            (self.r / p).parent.mkdir(parents=True, exist_ok=True)
            (self.r / p).write_text(inhalt)
        _sh(self.r, "git", "add", "-A")
        _sh(self.r, "git", "commit", "-qm", "init")
        _sh(self.r, "git", "push", "-q", "origin", "master")

    def tearDown(self):
        self.tmp.cleanup()

    def schreib(self, p, inhalt):
        (self.r / p).parent.mkdir(parents=True, exist_ok=True)
        (self.r / p).write_text(inhalt)

    def remote_log(self):
        return _sh(self.r.parent / "origin.git", "git", "log", "--format=%s", "master").stdout.split("\n")


class TestKlassifizierung(WegwerfRepo):
    def test_whitelist_und_sperren(self):
        self.schreib("articles/a.md", "neu ![b](/static/img/neu.png)")
        self.schreib("static/img/neu.png", "n")
        self.schreib("static/img/fremd.png", "f")
        self.schreib("manual-posts.md", "m")
        self.schreib("data/ranking/x.json", "{}")
        self.schreib(".env", "TOKEN=1")
        self.schreib("scripts/s.py", "print(1)")
        (self.r / "static/img/alt.png").unlink()
        st = {a.pfad: a for a in dp.klassifiziere(self.r, dp.status(self.r))}
        self.assertTrue(st["articles/a.md"].standard)
        self.assertTrue(st["static/img/neu.png"].standard)
        self.assertFalse(st["static/img/fremd.png"].standard)
        self.assertTrue(st["static/img/fremd.png"].erlaubt)
        self.assertFalse(st["manual-posts.md"].erlaubt)
        self.assertFalse(st[".env"].erlaubt)
        self.assertNotIn("data/ranking/x.json", st) if (self.r / ".gitignore").exists() else self.assertFalse(st["data/ranking/x.json"].erlaubt)
        self.assertFalse(st["scripts/s.py"].standard)
        self.assertEqual(st["static/img/alt.png"].art, "geloescht")
        self.assertFalse(st["static/img/alt.png"].standard)
        self.assertEqual(dp.geaenderte_slugs(list(st.values())), ["a"])


class TestVeroeffentlichen(WegwerfRepo):
    def test_commit_nur_auswahl_und_push(self):
        self.schreib("articles/a.md", "neu")
        self.schreib("dist/a.html", "neu")
        self.schreib("config.yaml", "a: 2")
        self.schreib("templates/fremd.html", "gestaged")
        _sh(self.r, "git", "add", "templates/fremd.html")  # jemand anders hat das schon in den Index gelegt
        stand = dp.stand_fingerabdruck(self.r)
        erg = dp.veroeffentlichen(self.r, ["articles/a.md", "dist/a.html"], "Blog: Test", erwarteter_fingerabdruck=stand,
                                  verbotene_begriffe=[], log_zeilen=["deploy: Blog: Test"])
        self.assertTrue(erg["push_ok"])
        self.assertTrue(erg["dist_geaendert"])
        dateien = _sh(self.r, "git", "show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(sorted(dateien), ["articles/a.md", "dist/a.html", "publish-log.md"])
        self.assertIn("Blog: Test", self.remote_log())
        rest = _sh(self.r, "git", "status", "--porcelain").stdout
        self.assertIn("A  templates/fremd.html", rest)  # bleibt gestaged, nicht mitcommittet
        self.assertIn(" M config.yaml", rest)
        self.assertIn("deploy: Blog: Test", (self.r / "publish-log.md").read_text())

    def test_geloeschte_datei_nur_wenn_ausgewaehlt(self):
        (self.r / "static/img/alt.png").unlink()
        self.schreib("articles/a.md", "neu")
        stand = dp.stand_fingerabdruck(self.r)
        dp.veroeffentlichen(self.r, ["articles/a.md"], "ohne Loeschung", erwarteter_fingerabdruck=stand, verbotene_begriffe=[], push=False)
        self.assertIn(" D static/img/alt.png", _sh(self.r, "git", "status", "--porcelain").stdout)
        stand = dp.stand_fingerabdruck(self.r)
        dp.veroeffentlichen(self.r, ["static/img/alt.png"], "mit Loeschung", erwarteter_fingerabdruck=stand, verbotene_begriffe=[], push=False)
        self.assertNotIn("alt.png", _sh(self.r, "git", "status", "--porcelain").stdout)

    def test_stand_geaendert_bricht_ab(self):
        self.schreib("articles/a.md", "neu")
        stand = dp.stand_fingerabdruck(self.r)
        self.schreib("articles/a.md", "noch neuer")
        with self.assertRaises(dp.DeployFehler):
            dp.veroeffentlichen(self.r, ["articles/a.md"], "x", erwarteter_fingerabdruck=stand, verbotene_begriffe=[], push=False)
        self.assertEqual(self.remote_log()[0], "init")

    def test_gesperrte_datei_und_geheimnis(self):
        self.schreib("manual-posts.md", "m")
        stand = dp.stand_fingerabdruck(self.r)
        with self.assertRaises(dp.DeployFehler):
            dp.veroeffentlichen(self.r, ["manual-posts.md"], "x", erwarteter_fingerabdruck=stand, verbotene_begriffe=[], push=False)
        self.schreib("articles/a.md", "api_key = 'abcdefghijklmnopqrstuvwxyz123456'")
        stand = dp.stand_fingerabdruck(self.r)
        with self.assertRaises(dp.DeployFehler):
            dp.veroeffentlichen(self.r, ["articles/a.md"], "x", erwarteter_fingerabdruck=stand, verbotene_begriffe=[], push=False)
        self.schreib("articles/a.md", "Kunde GEHEIMKUNDE")
        stand = dp.stand_fingerabdruck(self.r)
        with self.assertRaises(dp.DeployFehler):
            dp.veroeffentlichen(self.r, ["articles/a.md"], "x", erwarteter_fingerabdruck=stand, verbotene_begriffe=["geheimkunde"], push=False)

    def test_remote_voraus_bricht_ab(self):
        anderer = self.r.parent / "anderer"
        _sh(self.r.parent, "git", "clone", "-q", str(self.r.parent / "origin.git"), "anderer")
        _sh(anderer, "git", "-c", "user.name=X", "-c", "user.email=x@x", "commit", "-q", "--allow-empty", "-m", "fremd")
        _sh(anderer, "git", "push", "-q", "origin", "HEAD:master")
        self.schreib("articles/a.md", "neu")
        stand = dp.stand_fingerabdruck(self.r)
        with self.assertRaises(dp.DeployFehler) as ctx:
            dp.veroeffentlichen(self.r, ["articles/a.md"], "x", erwarteter_fingerabdruck=stand, verbotene_begriffe=[])
        self.assertIn("hinter", str(ctx.exception))


def _png(w, h):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00" + b"\0" * 64


SEITE = """<!doctype html><html><head>
<meta name="title" property="og:title" content="Ein Titel, der zwischen vierzig und siebzig Zeichen lang ist">
<meta property="og:type" content="article">
<meta name="image" property="og:image" content="https://blog.example/static/img/og.png">
<meta name="description" property="og:description" content="{beschr}">
<meta name="author" content="Andreas Brauckmann">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<link rel="canonical" href="https://blog.example/artikel/x/">
</head><body>Text</body></html>"""


class TestInspector(unittest.TestCase):
    def fake(self, seite, bild=_png(1200, 630), bild_status=200):
        def abruf(url, ua, limit, timeout):
            if url.endswith(".png"):
                return bild_status, {"content-type": "image/png", "content-length": str(len(bild))}, bild, None
            return 200, {"cache-control": "max-age=600", "age": "12"}, seite.encode(), None
        return abruf

    def test_alles_gruen(self):
        seite = SEITE.format(beschr="B" * 140)
        e = inspector.pruefe_url("https://blog.example/artikel/x/", dist_html=seite, abruf=self.fake(seite))
        self.assertEqual(e["ampel"], "gruen", e["befunde"])
        self.assertTrue(e["gleich_build"])
        self.assertEqual(e["bild"]["kartentyp"], "gross")

    def test_abweichung_und_kleine_karte(self):
        live = SEITE.format(beschr="B" * 140)
        build = SEITE.format(beschr="C" * 140)
        e = inspector.pruefe_url("https://blog.example/artikel/x/", dist_html=build, abruf=self.fake(live, _png(480, 480)))
        self.assertEqual(e["ampel"], "rot")
        self.assertEqual(e["abweichungen"], ["Beschreibung"])
        self.assertEqual(e["bild"]["kartentyp"], "klein")

    def test_pflicht_fehlt_und_bild_404(self):
        seite = SEITE.format(beschr="B" * 140).replace('<meta name="author" content="Andreas Brauckmann">', "")
        e = inspector.pruefe_url("https://blog.example/artikel/x/", abruf=self.fake(seite, b"", 404))
        self.assertEqual(e["ampel"], "rot")
        self.assertIn("author", e["meta"]["pflicht_fehlend"])

    def test_kartentyp_und_url(self):
        self.assertEqual(inspector.kartentyp(1200, 630), "gross")
        self.assertEqual(inspector.kartentyp(1400, 1400), "klein")
        self.assertEqual(inspector.kartentyp(150, 150), "keine")
        self.assertTrue(inspector.post_inspector_url("https://blog.brauckmann.ch/artikel/x/").startswith(
            "https://www.linkedin.com/post-inspector/inspect/https%3A%2F%2Fblog.brauckmann.ch"))


class TestLinkedInKurz(unittest.TestCase):
    def test_kurzform(self):
        from summarize import summarize_linkedin_kurz
        meta = {"title": "T", "slogan": "Ein Satz mit Haken. Noch einer.",
                "description": "Beschreibung eins. Beschreibung zwei ist etwas laenger. Drei.",
                "tags": ["KI", "Zero Trust", "Monitoring"], "slug": "x"}
        text = summarize_linkedin_kurz(meta, "https://blog.example/artikel/x/", 150, 300)
        absaetze = text.split("\n\n")
        self.assertEqual(len(absaetze), 2)
        self.assertTrue(absaetze[0].endswith(" https://blog.example/artikel/x/"))   # Adresse direkt hinter dem Text
        self.assertEqual(absaetze[1], "#KI #ZeroTrust")                              # Hashtags gesammelt zuletzt
        self.assertNotIn("#Monitoring", text)
        self.assertLessEqual(len(text), 300)
        self.assertTrue(text.startswith("Ein Satz mit Haken."))

    def test_config_kurz(self):
        import yaml
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        li = cfg["channels"]["linkedin"]
        self.assertEqual((li["min_chars"], li["max_chars"], li["format"]), (150, 300, "kurz"))


if __name__ == "__main__":
    unittest.main()
