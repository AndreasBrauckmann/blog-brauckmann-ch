import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "admin"))

import kennzahlen as kz  # noqa: E402
import plattformen as pl  # noqa: E402

H = {"X-Blog-Verwaltung-Intern": "1"}


class Zaehlung(unittest.TestCase):
    def test_mastodon_link_23(self):
        self.assertEqual(pl.zaehle_mastodon("abc https://example.com/sehr/langer/pfad/der/nicht/zaehlt"), 4 + 23)
        self.assertEqual(pl.zaehle_mastodon("a" * 10), 10)

    def test_mastodon_schnitt(self):
        self.assertIsNone(pl.mastodon_schnitt("a" * 500))
        self.assertEqual(pl.mastodon_schnitt("a" * 501), 500)
        self.assertEqual(pl.mastodon_schnitt("a" * 490 + " https://x.example/abc"), 491)

    def test_bluesky_grapheme_bytes(self):
        self.assertEqual(pl.zaehle_bluesky("abc"), {"grapheme": 3, "bytes": 3})
        self.assertEqual(pl.zaehle_bluesky("é")["grapheme"], 1)  # kombinierendes Zeichen
        self.assertEqual(pl.zaehle_bluesky("\U0001F468‍\U0001F469‍\U0001F467")["grapheme"], 1)  # ZWJ-Familie
        self.assertEqual(pl.zaehle_bluesky("\U0001F1E9\U0001F1EA")["grapheme"], 1)  # Flagge
        self.assertEqual(pl.zaehle_bluesky("ä")["bytes"], 2)
        self.assertIsNone(pl.bluesky_schnitt("a" * 300))
        self.assertEqual(pl.bluesky_schnitt("a" * 301), 300)
        self.assertEqual(pl.bluesky_schnitt("ä" * 1600), 300)
        self.assertEqual(pl.bluesky_schnitt("ä" * 1600), 300)


class Karten(unittest.TestCase):
    def test_kartentyp(self):
        self.assertEqual(pl.kartentyp(1200, 630), "gross")
        self.assertEqual(pl.kartentyp(1200, 1200), "klein")
        self.assertEqual(pl.kartentyp(800, 418), "klein")
        self.assertEqual(pl.kartentyp(100, 100), "keine")
        self.assertEqual(pl.kartentyp(None, None), "keine")

    def test_linkedin_kachel(self):
        kurz = "x" * 200 + "\n\nhttps://a"
        k = pl.linkedin_kachel(kurz, True)
        self.assertTrue(k["karte_sichtbar"])
        self.assertTrue(k["mobil"]["gekuerzt"])
        self.assertLessEqual(len(k["mobil"]["sichtbar"]), 140)
        self.assertEqual(k["mobil"]["sichtbar"] + k["mobil"]["rest"].strip(), kurz.strip()[:len(k["mobil"]["sichtbar"])] + k["mobil"]["rest"].strip())
        lang = "wort " * 200
        k = pl.linkedin_kachel(lang, True)
        self.assertTrue(k["karte_verdeckt"])
        self.assertFalse(k["karte_sichtbar"])
        self.assertFalse(pl.linkedin_kachel("kurz", True)["desktop"]["gekuerzt"])


class Log(unittest.TestCase):
    def test_parser(self):
        log = ("# Publish-Log\n\n## 2026-09-07 10:16 UTC\n\n- a-b: mastodon: https://mastodon.social/@u/123\n"
               "## 2026-09-08 (Nachtrag)\n- a-b: bluesky: https://bsky.app/profile/h/post/abc (alt gelöscht)\n"
               "- a-b: bluesky: https://bsky.app/profile/h/post/def\n- c: linkedin: manuell (siehe manual-posts.md)\n- c: x: FEHLGESCHLAGEN - boom\n")
        e = pl.publish_log_parsen(log)
        self.assertEqual(e[("a-b", "mastodon")]["datum"], "2026-09-07")
        self.assertEqual(e[("a-b", "mastodon")]["uhrzeit"], "10:16")
        self.assertTrue(e[("a-b", "bluesky")]["url"].endswith("/def"))
        self.assertEqual(e[("a-b", "bluesky")]["anzahl"], 2)
        self.assertNotIn(("c", "linkedin"), e)
        self.assertNotIn(("c", "x"), e)


def _ctx(gesamt=100, a=100, typ="gross", beschr=140, titel=60, bytes_=1000, ms=False):
    og = {"vorhanden": True, "kartentyp": typ, "bytes": bytes_, "kb": 1, "breite": 1200, "hoehe": 630, "verhaeltnis": 1.9, "svg": False, "pfad": "/x.jpg"}
    return {"og": og, "image": dict(og), "beschreibung": "b" * beschr, "titel": "t" * titel, "gesamt": gesamt, "meta_a": a,
            "bild_masse_tags": True, "fedi": True, "dist": True, "fehlend": []}


class Eignung(unittest.TestCase):
    def test_grenzen(self):
        for p in pl.PLATTFORM_DEF:
            e = pl.eignung(p, _ctx(), "kurz", "titel" if p == "reddit" else None, None)
            self.assertTrue(0 <= e["score"] <= 100, p)
        self.assertEqual(pl.eignung("mastodon", _ctx(), "x" * 10)["score"], 100.0)
        schlecht = pl.eignung("mastodon", _ctx(0, 0, "keine", 300, 10), "x" * 900)
        self.assertEqual(schlecht["score"], 0.0)
        self.assertEqual(schlecht["ampel"], "rot")

    def test_ms_deckel_und_link(self):
        e = pl.eignung("microsoft_tech_community", _ctx(), "Frage ohne Link")
        self.assertEqual(e["score"], pl.MS_DECKEL)
        self.assertEqual(e["deckel"], pl.MS_DECKEL)
        e2 = pl.eignung("microsoft_tech_community", _ctx(), "mit https://blog.example/x")
        self.assertEqual(e2["teile"][0]["score"], 0.0)
        self.assertEqual(e["teile"][0]["score"], 100.0)

    def test_bluesky_thumb(self):
        gut = pl.eignung("bluesky", _ctx(), "x")["score"]
        c = _ctx(); c["image"]["bytes"] = 2_000_000
        self.assertLess(pl.eignung("bluesky", c, "x")["score"], gut)


class Ablage(unittest.TestCase):
    def test_pruefliste_und_posts(self):
        with tempfile.TemporaryDirectory() as t:
            a = pl.Ablage(Path(t))
            neu = pl.pruefliste_auswerten("linkedin", {"haken": "2026-01-01"}, ["haken", "kurz", "unbekannt"], "2026-10-01")
            self.assertEqual(neu, {"haken": "2026-01-01", "kurz": "2026-10-01"})
            a.pruefliste_setzen("linkedin", "s", neu)
            self.assertEqual(a.pruefliste("linkedin", "s"), neu)
            a.post_setzen("reddit", "s", {"datum": "2026-10-01", "url": "https://r"})
            self.assertEqual(a.posts("reddit")["s"]["url"], "https://r")
            a.post_setzen("reddit", "s", None)
            self.assertEqual(a.posts("reddit"), {})


class Kennzahlen(unittest.TestCase):
    def test_mastodon_bluesky_fake(self):
        def http(url):
            if "/api/v1/statuses/42" in url:
                return {"reblogs_count": 1, "favourites_count": 2, "replies_count": 3}
            if "resolveHandle" in url:
                return {"did": "did:plc:abc"}
            if "getPosts" in url:
                self.assertIn("did%3Aplc%3Aabc", url)
                return {"posts": [{"likeCount": 5, "repostCount": 1, "replyCount": 0, "quoteCount": 2}]}
            raise OSError("boom")
        m = kz.mastodon_zaehler("https://mastodon.social/@u/42", http=http)
        self.assertEqual((m["reblogs"], m["favourites"], m["replies"], m["quotes"]), (1, 2, 3, None))
        b = kz.bluesky_zaehler("https://bsky.app/profile/h.bsky.social/post/3abc", http=http)
        self.assertEqual((b["likes"], b["quotes"]), (5, 2))
        self.assertIn("fehler", kz.mastodon_zaehler("https://mastodon.social/@u/99", http=http))
        self.assertIn("fehler", kz.mastodon_zaehler("kein link", http=http))

    def test_aktualisieren_tolerant_und_speicher(self):
        with tempfile.TemporaryDirectory() as t:
            ks = kz.KennzahlenSpeicher(Path(t))
            def http(url):
                if "/42" in url:
                    return {"reblogs_count": 1, "favourites_count": 2, "replies_count": 3}
                raise OSError("x")
            d = ks.aktualisieren("mastodon", {"a": "https://mastodon.social/@u/42", "b": "https://mastodon.social/@u/43"}, http=http)
            self.assertNotIn("fehler", d["beitraege"]["a"])
            self.assertIn("fehler", d["beitraege"]["b"])
            self.assertIn("Favoriten 2", kz.wirkung_text("mastodon", "a", ks)["text"])

    def test_manuell_und_csv(self):
        with tempfile.TemporaryDirectory() as t:
            ks = kz.KennzahlenSpeicher(Path(t))
            self.assertIsNone(ks.messung_hinzufuegen("reddit", "s", {}, None))
            self.assertIsNone(ks.messung_hinzufuegen("reddit", "s", {"upvote_anteil": "150"}, None))
            m = ks.messung_hinzufuegen("reddit", "s", {"upvotes": "1.234", "upvote_anteil": "92"}, "2026-10-01")
            self.assertEqual(m["upvotes"], 1234)
            erg = ks.csv_importieren("facebook", b"slug,datum,reaktionen,kommentare\ns,2026-10-02,10,2\nxx,,1,1\n", {"s"})
            self.assertEqual(erg["gespeichert"], 1)
            self.assertEqual(len(erg["fehler"]), 1)
            self.assertEqual(ks.manuell("facebook")["s"]["messungen"][0]["reaktionen"], 10)
            self.assertTrue(ks.messung_loeschen("reddit", "s", 0))
            self.assertEqual(oct(ks.basis.joinpath("manuell.json").stat().st_mode & 0o777), "0o600")


class Routen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.c = app.app.test_client()

    def test_alle_seiten(self):
        for n in pl.PLATTFORM_DEF:
            r = self.c.get(f"/verwaltung/plattform/{n}", headers=H)
            self.assertEqual(r.status_code, 200, n)
        self.assertEqual(self.c.get("/verwaltung/plattform/linkedin?format=lang", headers=H).status_code, 200)

    def test_unbekannt_und_ohne_header(self):
        self.assertEqual(self.c.get("/verwaltung/plattform/nix", headers=H).status_code, 404)
        self.assertEqual(self.c.get("/verwaltung/plattform/linkedin").status_code, 403)

    def test_post_ohne_token(self):
        for pfad in ("pruefliste", "gepostet", "analyse", "kennzahlen", "kennzahlen/import"):
            r = self.c.post(f"/verwaltung/plattform/reddit/{pfad}", headers=H, data={"slug": "x"})
            self.assertEqual(r.status_code, 403, pfad)


if __name__ == "__main__":
    unittest.main()
