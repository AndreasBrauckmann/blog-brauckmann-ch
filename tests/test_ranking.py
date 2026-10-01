"""Tests fuer das Artikel-Ranking der Verwaltung (Bewertung, Frontmatter,
LinkedIn-Import, Formularschutz). Laufen offline; schreibende Tests nutzen
ausschliesslich temporaere Verzeichnisse, nie data/ des Blogs.

    .venv/bin/python -m unittest discover -s tests -v
"""

import io
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import bewertung as bw  # noqa: E402
import linkedin_import as li  # noqa: E402
from ranking_daten import FrontmatterFehler, Speicher, setze_felder, vorschau_hash  # noqa: E402


def _png(w, h):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"


def _gif(w, h):
    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00" * 10


def _jpeg(w, h):
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\x00" * 9
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def _webp_vp8x(w, h):
    chunk = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


class TestSprache(unittest.TestCase):
    def test_silben(self):
        self.assertEqual(bw.silben("Haus"), 1)
        self.assertEqual(bw.silben("Lesbarkeit"), 3)
        self.assertEqual(bw.silben("Station"), 3)  # Sta-ti-on
        self.assertEqual(bw.silben("Eier"), 2)
        self.assertEqual(bw.silben("x"), 1)

    def test_saetze_mit_abkuerzungen(self):
        s = bw.saetze("Das ist z. B. gut. Und dann? Ja! Mehr bzw. weniger ca. 5 Stück.")
        self.assertEqual(len(s), 4)
        self.assertTrue(s[0].endswith("gut."))

    def test_amstad_einfacher_text(self):
        # 2 Saetze, 6 Woerter, Silben: Der(1) Hund(1) bellt(1) Die(1) Katze(2) schlaeft(1) = 7
        r = bw.amstad(["Der Hund bellt. Die Katze schläft."])
        self.assertEqual(r["saetze"], 2)
        self.assertEqual(r["woerter"], 6)
        self.assertAlmostEqual(r["index"], round(180 - 3 - 58.5 * 7 / 6, 1), places=1)

    def test_schwerer_text_schlechter(self):
        leicht = bw.amstad(["Wir bauen es. Es geht schnell. Das hilft."])["index"]
        schwer = bw.amstad(["Infrastrukturüberwachungsdienstleistungen ermöglichen kontinuierliche Sicherheitsüberprüfungen heterogener Unternehmensumgebungen."])["index"]
        self.assertGreater(leicht, schwer)

    def test_linear_und_band(self):
        self.assertEqual(bw.linear(10, 10, 20), 100.0)
        self.assertEqual(bw.linear(20, 10, 20), 0.0)
        self.assertEqual(bw.linear(15, 10, 20), 50.0)
        self.assertEqual(bw.linear(60, 50, 20), 100.0)  # Richtung umgekehrt
        self.assertEqual(bw.band(55, 40, 70, 15, 110), 100.0)
        self.assertEqual(bw.band(110, 40, 70, 15, 110), 0.0)
        self.assertEqual(bw.band(90, 40, 70, 15, 110), 50.0)

    def test_haken(self):
        self.assertFalse(bw.haken_in("In diesem Artikel zeige ich, wie Monitoring funktioniert und was es bringt.")[0])
        self.assertTrue(bw.haken_in("Drei Knöpfe, dutzende Male pro Stunde: Jetzt genügt ein Satz zu Siri.")[0])
        self.assertFalse(bw.haken_in("Eine Beschreibung der Lösung mit vielen Worten und allgemeinen Aussagen über alles.")[0])

    def test_nahwiederholung_und_ausnahmen(self):
        text = "Der Server startet. Danach startet der Server erneut, weil der Server hängt."
        n, top = bw.nahwiederholungen(text)
        self.assertGreaterEqual(n, 2)
        self.assertIn("server", top)
        n2, _ = bw.nahwiederholungen(text, ausnahmen={"server", "startet"})
        self.assertEqual(n2, 0)


class TestBildmasse(unittest.TestCase):
    def test_formate(self):
        with tempfile.TemporaryDirectory() as d:
            for name, daten, soll in [("a.png", _png(1200, 630), (1200, 630)), ("b.gif", _gif(640, 480), (640, 480)),
                                      ("c.jpg", _jpeg(1200, 627), (1200, 627)), ("d.webp", _webp_vp8x(1600, 838), (1600, 838))]:
                p = Path(d) / name
                p.write_bytes(daten)
                self.assertEqual(bw.bildmasse(p), soll, name)
            kaputt = Path(d) / "x.png"
            kaputt.write_bytes(b"kein bild")
            self.assertIsNone(bw.bildmasse(kaputt))

    def test_echte_bilder_des_blogs(self):
        p = ROOT / "static" / "img" / "og-monitoring-teil2-laptop-radar.jpg"
        if p.exists():
            self.assertEqual(bw.bildmasse(p), (1200, 630))


KOPF_OK = """<head>
<meta name="author" content="Andreas Brauckmann">
<meta property="og:type" content="article">
<meta name="title" property="og:title" content="Ein Titel">
<meta name="description" property="og:description" content="Eine Beschreibung">
<link rel="canonical" href="https://blog.example/artikel/x/">
<meta name="image" property="og:image" content="https://blog.example/static/img/a.jpg">
<meta property="og:image:alt" content="Ein Bild">
<script type="application/ld+json">
{"@type": "Article", "headline": "Ein Titel"}
</script>"""


class TestKopf(unittest.TestCase):
    def test_pflicht_meta_vollstaendig(self):
        k = bw.pruefe_kopf(KOPF_OK)
        self.assertEqual(k["fehlend"], [])
        self.assertEqual(k["og_image_alt"], "Ein Bild")
        self.assertEqual(k["jsonld"]["headline"], "Ein Titel")

    def test_pflicht_meta_fehlt_und_falsche_form(self):
        # getrennte Tags statt name+property in einem Tag zaehlen NICHT
        kopf = KOPF_OK.replace('<meta name="title" property="og:title" content="Ein Titel">',
                               '<meta property="og:title" content="Ein Titel">')
        kopf = kopf.replace('<meta name="author" content="Andreas Brauckmann">', "")
        self.assertEqual(bw.pruefe_kopf(kopf)["fehlend"], ["title/og:title", "author"])

    def test_jsonld_kaputt(self):
        k = bw.pruefe_kopf(KOPF_OK.replace('"headline": "Ein Titel"}', '"headline": }'))
        self.assertIsNone(k["jsonld"])
        self.assertTrue(k["jsonld_fehler"])


def _meta(**extra):
    m = {"slug": "test-artikel", "title": "Ein Testtitel mit genau passender Länge für Vorschauen",
         "description": "Drei Klicks statt einer Stunde: So spart ein kleines Skript jeden Tag Zeit beim Umschalten zwischen zwei Rechnern im Büro und zuhause.",
         "date": "2026-09-01", "updated": "2026-09-20", "tags": ["Skript", "Zeit"]}
    m.update(extra)
    return m


class TestBewertung(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.static = base / "static"
        (self.static / "img").mkdir(parents=True)
        (self.static / "img" / "og.png").write_bytes(_png(1200, 630))
        self.dist = base / "dist"

    def tearDown(self):
        self.tmp.cleanup()

    def _bew(self, html, **meta):
        return bw.bewerte(_meta(**meta), html, base_url="https://blog.example", static_dir=self.static,
                          dist_dir=self.dist, heute=date(2026, 10, 1))

    def test_bildabstand(self):
        p = "<p>" + " ".join(["wort"] * 100) + ".</p>"
        html = p * 3 + '<p><img src="/static/img/og.png" alt="Bild"></p>' + p * 8
        b = self._bew(html)
        self.assertEqual(b.kennzahlen["groesster_abstand"], 800)
        self.assertEqual(b.kriterium("d_abstand").status, "teils")  # 450 = 100 %, 1100 = 0 %
        html2 = (p * 3 + '<p><img src="/static/img/og.png" alt="Bild"></p>') * 3
        self.assertEqual(self._bew(html2).kennzahlen["groesster_abstand"], 300)
        self.assertEqual(self._bew(html2).kriterium("d_abstand").status, "ok")

    def test_alt_und_poster(self):
        html = '<p>Text hier.</p><p><img src="/static/img/og.png"></p><video src="v.mp4" controls></video>'
        b = self._bew(html)
        self.assertEqual(b.kriterium("d_alt").status, "nein")
        self.assertEqual(b.kriterium("d_poster").erfuellung, 0.0)
        b2 = self._bew('<p>Text.</p>')
        self.assertIsNone(b2.kriterium("d_poster").erfuellung)  # kein Video -> entfaellt

    def test_codeblock_und_tabelle_sind_visuell_aber_kein_fliesstext(self):
        html = '<p>Eins zwei drei.</p><div class="codehilite"><pre><code>a b c d e f</code></pre></div><table><tr><td>x y z</td></tr></table>'
        b = self._bew(html)
        self.assertEqual(b.kennzahlen["woerter"], 3)
        self.assertEqual(b.kennzahlen["visuell"], {"Codeblock": 1, "Tabelle": 1})

    def test_metalaengen(self):
        b = self._bew("<p>x</p>", title="Kurz", description="Zu kurz.")
        self.assertEqual(b.kriterium("a_titel").status, "nein")
        self.assertEqual(b.kriterium("a_beschr").status, "nein")
        b2 = self._bew("<p>x</p>")
        self.assertEqual(b2.kriterium("a_titel").status, "ok")
        self.assertEqual(b2.kriterium("a_beschr").status, "ok")

    def test_og_bild_geeignet(self):
        b = self._bew("<p>x</p>", og_image="/static/img/og.png")
        self.assertEqual(b.kriterium("a_bild").erfuellung, 100.0)
        (self.static / "img" / "q.png").write_bytes(_png(480, 480))
        self.assertEqual(self._bew("<p>x</p>", thumb="/static/img/q.png").kriterium("a_bild").status, "nein")

    def test_ohne_dist_fehlen_pflichtmeta(self):
        b = self._bew("<p>x</p>")
        self.assertFalse(b.pflicht_ok())
        self.assertEqual(b.kriterium("a_pflicht").messwert, "dist/-Seite fehlt")

    def test_gewichte_summieren_auf_100(self):
        self.assertEqual(sum(k["gewicht"] for k in bw.KATEGORIEN.values()), 100)
        for kat, info in bw.KATEGORIEN.items():
            self.assertEqual(sum(p for (k, _n, p, _s) in bw.KRITERIEN.values() if k == kat), info["gewicht"], kat)

    def test_gesamt_im_bereich_und_deterministisch(self):
        html = "<h2>Fazit</h2><p>Kurz und gut. Das reicht.</p>"
        a, b = self._bew(html), self._bew(html)
        self.assertEqual(a.gesamt, b.gesamt)
        self.assertTrue(0 <= a.gesamt <= 100)
        self.assertEqual(a.kriterium("b_fazit").status, "ok")


ARTIKEL = '''---
slogan: "Ein Slogan"
title: "Alter Titel"
slug: test
date: 2026-09-01
description: "Alte Beschreibung"
summary: >-
  Zeile eins
  Zeile zwei
tags: [A, B]
thumb: /static/img/t.jpg
draft: false
---
Text mit --- drin.
'''


class TestFrontmatter(unittest.TestCase):
    def test_ersetzen_und_einfuegen(self):
        neu = setze_felder(ARTIKEL, {"title": 'Neuer "Titel": mit Doppelpunkt', "og_image_alt": "Alt-Text"})
        self.assertIn('title: "Neuer \\"Titel\\": mit Doppelpunkt"', neu)
        self.assertIn('thumb: /static/img/t.jpg\nog_image_alt: "Alt-Text"\n', neu)
        self.assertTrue(neu.endswith("Text mit --- drin.\n"))
        self.assertIn("summary: >-\n  Zeile eins", neu)

    def test_nur_erlaubte_felder(self):
        with self.assertRaises(FrontmatterFehler):
            setze_felder(ARTIKEL, {"slug": "anders"})
        with self.assertRaises(FrontmatterFehler):
            setze_felder(ARTIKEL, {"description": ""})
        with self.assertRaises(FrontmatterFehler):
            setze_felder(ARTIKEL, {"title": "zwei\nzeilen"})

    def test_mehrzeilig_wird_abgelehnt(self):
        text = ARTIKEL.replace('description: "Alte Beschreibung"', "description: >-\n  lang\n  und mehrzeilig")
        with self.assertRaises(FrontmatterFehler):
            setze_felder(text, {"description": "neu"})


def _xlsx(blaetter: dict[str, list[list]]) -> bytes:
    """Minimal-XLSX mit Inline-Strings - genug fuer den Parser."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        sheets, rels = [], []
        for i, (name, zeilen) in enumerate(blaetter.items(), 1):
            sheets.append(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>')
            rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
            rows = []
            for r, zeile in enumerate(zeilen, 1):
                cells = []
                for c, wert in enumerate(zeile):
                    ref = chr(65 + c) + str(r)
                    if wert == "":
                        continue
                    if isinstance(wert, (int, float)):
                        cells.append(f'<c r="{ref}"><v>{wert}</v></c>')
                    else:
                        cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{wert}</t></is></c>')
                rows.append(f'<row r="{r}">{"".join(cells)}</row>')
            z.writestr(f"xl/worksheets/sheet{i}.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(rows) + "</sheetData></worksheet>")
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(sheets) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(rels) + "</Relationships>")
    return buf.getvalue()


class TestLinkedIn(unittest.TestCase):
    def test_zahlen(self):
        self.assertEqual(li.zahl("1,234"), 1234)
        self.assertEqual(li.zahl("1.234"), 1234)
        self.assertEqual(li.zahl("1'006"), 1006)
        self.assertEqual(li.zahl("12,5 %"), 12.5)
        self.assertEqual(li.zahl("1.234,5"), 1234.5)
        self.assertEqual(li.zahl(860.0), 860)
        self.assertIsNone(li.zahl("–"))

    def test_datum(self):
        self.assertEqual(li.datum("9/28/2026"), "2026-09-28")
        self.assertEqual(li.datum("28.09.2026"), "2026-09-28")
        self.assertEqual(li.datum("2026-09-28"), "2026-09-28")
        self.assertEqual(li.datum(46293), "2026-09-28")  # Excel-Seriennummer

    def test_beitrags_id(self):
        self.assertEqual(li.beitrags_id("https://www.linkedin.com/feed/update/urn:li:activity:7379000000000000001/"), "7379000000000000001")
        self.assertEqual(li.beitrags_id("https://www.linkedin.com/posts/andreas_titel-activity-7379000000000000001-AbCd"), "7379000000000000001")
        self.assertEqual(li.beitrags_id("https://www.linkedin.com/feed/update/urn%3Ali%3AugcPost%3A7379000000000000002"), "7379000000000000002")

    def test_einzelbeitrag_export(self):
        url = "https://www.linkedin.com/feed/update/urn:li:activity:7379000000000000001"
        blatt = [["Post URL", url], ["Post Date", "9/28/2026"], ["Impressions", 1234], ["Members reached", "987"],
                 ["Profile viewers from this post", 12], ["Followers gained from this post", 3], ["Social engagements", 60],
                 ["Reactions", 40], ["Comments", 8], ["Reposts", 2], ["Saves", 5], ["Sends on LinkedIn", 4], ["Link engagements", 30]]
        e = li.auswerten(li.lies_datei("x.xlsx", _xlsx({"Post analytics": blatt})))
        self.assertEqual(len(e["messungen"]), 1)
        m = e["messungen"][0]
        self.assertEqual((m["impressions"], m["mitglieder_erreicht"], m["reaktionen"], m["kommentare"], m["reposts"]), (1234, 987, 40, 8, 2))
        self.assertEqual((m["gespeichert"], m["gesendet"], m["profilansichten"], m["neue_follower"], m["link_klicks"]), (5, 4, 12, 3, 30))
        self.assertEqual(m["datum"], "2026-09-28")
        self.assertEqual(m["beitrag_url"], url)
        w = li.wirkung(m)
        self.assertEqual(w["rate"], round(100 * 50 / 1234, 2))

    def test_gesamt_export_top_posts_und_profil(self):
        u1 = "https://www.linkedin.com/feed/update/urn:li:activity:7379000000000000001"
        u2 = "https://www.linkedin.com/feed/update/urn:li:activity:7379000000000000002"
        top = [["Maximum of 50 posts available to include in this list"], [],
               ["Post URL", "Post publish date", "Engagements", "", "Post URL", "Post publish date", "Impressions"],
               [u1, "9/28/2026", 50, "", u2, "9/20/2026", 3000],
               [u2, "9/20/2026", 90, "", u1, "9/28/2026", 1500]]
        disc = [["Overall Performance", "9/1/2026 - 9/30/2026"], ["Impressions", 4500], ["Members reached", 2100]]
        fol = [["Total followers on 9/30/2026:", ""], ["Total followers", 812], [], ["Date", "New followers"], ["9/30/2026", 4]]
        e = li.auswerten(li.lies_datei("x.xlsx", _xlsx({"DISCOVERY": disc, "TOP POSTS": top, "FOLLOWERS": fol})))
        per = {m["beitrag_url"]: m for m in e["messungen"]}
        self.assertEqual(per[u1]["impressions"], 1500)
        self.assertEqual(per[u1]["interaktionen"], 50)
        self.assertEqual(per[u2]["impressions"], 3000)
        self.assertEqual(e["profil"]["follower_gesamt"], 812)
        self.assertEqual(e["profil"]["impressions_zeitraum"], 4500)
        self.assertEqual(li.wirkung(per[u1])["basis"], "Engagements laut Export")

    def test_eigene_csv(self):
        csv = "slug;datum;impressions;reaktionen;kommentare;reposts\nkvm-switch-per-sprache;30.09.2026;1.200;30;5;1\n".encode()
        e = li.auswerten(li.lies_datei("x.csv", csv))
        self.assertEqual(e["messungen"][0]["slug"], "kvm-switch-per-sprache")
        self.assertEqual(e["messungen"][0]["impressions"], 1200)

    def test_unbekannte_datei(self):
        e = li.auswerten(li.lies_datei("x.csv", b"a,b\n1,2\n"))
        self.assertEqual(e["messungen"], [])
        self.assertTrue(e["hinweise"])


class TestSpeicherUndSchutz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sp = Speicher(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_csrf(self):
        t = self.sp.csrf_token()
        self.assertTrue(self.sp.csrf_ok(t))
        self.assertFalse(self.sp.csrf_ok("falsch"))
        self.assertFalse(self.sp.csrf_ok(None))
        self.assertEqual(oct((Path(self.tmp.name) / "data/ranking/.csrf").stat().st_mode & 0o777), "0o600")

    def test_inspector_hash(self):
        h = vorschau_hash("T", "B", "I")
        self.sp.inspector_setzen("x", "2026-10-01", h)
        self.assertEqual(self.sp.inspector()["x"]["datum"], "2026-10-01")
        self.assertNotEqual(h, vorschau_hash("T2", "B", "I"))
        self.sp.inspector_setzen("x", None, "")
        self.assertEqual(self.sp.inspector(), {})

    def test_routen_schutz(self):
        import ranking_views as rv
        import gemeinsam
        import app as appmod
        alt, alt_g = rv.speicher, gemeinsam.speicher
        rv.speicher = gemeinsam.speicher = self.sp
        try:
            c = appmod.app.test_client()
            H = {"X-Blog-Verwaltung-Intern": "1"}
            ziel = "/verwaltung/ranking/kvm-switch-per-sprache/inspector"
            self.assertEqual(c.get("/verwaltung/ranking").status_code, 403)  # ohne edge-Header
            self.assertEqual(c.post(ziel, headers=H, data={"aktion": "setzen"}).status_code, 403)  # ohne Token
            tok = self.sp.csrf_token()
            fremd = {**H, "Origin": "https://boese.example"}
            self.assertEqual(c.post(ziel, headers=fremd, data={"aktion": "setzen", "csrf": tok}).status_code, 403)
            self.assertEqual(c.post("/verwaltung/ranking/gibt-es-nicht/inspector", headers=H, data={"csrf": tok}).status_code, 404)
            r = c.post(ziel, headers={**H, "Origin": "http://localhost"}, data={"aktion": "setzen", "csrf": tok, "datum": "2026-10-01"})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.sp.inspector()["kvm-switch-per-sprache"]["datum"], "2026-10-01")
        finally:
            rv.speicher, gemeinsam.speicher = alt, alt_g


class TestRepoHygiene(unittest.TestCase):
    def test_data_ist_ignoriert(self):
        r = subprocess.run(["git", "check-ignore", "-q", "data/ranking/linkedin.json"], cwd=ROOT)
        self.assertEqual(r.returncode, 0, "data/ muss von git ignoriert werden")


if __name__ == "__main__":
    unittest.main()
