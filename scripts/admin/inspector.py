"""Eigener Link-Vorschau-Inspector (serverseitig, nur lesend).

Ruft die Live-URL eines Artikels mit einem crawleraehnlichen User-Agent ab
(Standard: LinkedInBot) und prueft, was eine Plattform fuer die Link-Karte
sieht: Statuscode, die fuenf Pflicht-Meta-Tags in genau der Form aus
CLAUDE.md, og:image erreichbar (200, Content-Type, < 5 MB, Masse aus dem
Dateikopf, Verhaeltnis), Laengen, Canonical, og:image:width/height, ob die
Live-Seite dem lokalen Build (dist/) entspricht, Cache-Hinweise.

Ersetzt NICHT den LinkedIn Post Inspector (der erneuert LinkedIns eigenen
Zwischenspeicher und ist ein Menschen-Schritt) - er zeigt nur vorab, ob
alles stimmt. Ergebnisse liegen unter data/ranking/inspector/<slug>.json.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

import bewertung as bw

LINKEDIN_UA = "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)"
POST_INSPECTOR = "https://www.linkedin.com/post-inspector/"
MAX_SEITE = 3 * 1024 * 1024
MAX_BILD = 8 * 1024 * 1024
BILD_GRENZE_LINKEDIN = 5 * 1024 * 1024


def post_inspector_url(live_url: str) -> str:
    """Direktlink in den LinkedIn Post Inspector. Das Muster
    /post-inspector/inspect/<url-kodiert> ist nicht offiziell dokumentiert,
    wird aber verbreitet genutzt (z. B. von SEO-Plugins); schlaegt es fehl,
    die Live-URL von Hand in https://www.linkedin.com/post-inspector/ eingeben."""
    return POST_INSPECTOR + "inspect/" + urllib.parse.quote(live_url, safe="")


def kartentyp(breite: int | None, hoehe: int | None) -> str:
    """Praxiswerte LinkedIn/Facebook: grosse Bildkarte ab 1200x627 bei ~1,91:1,
    darunter (oder anderes Verhaeltnis) kleine Karte mit Vorschaubild links,
    unter 200x200 gar kein Bild."""
    if not breite or not hoehe:
        return "keine"
    if breite < 200 or hoehe < 200:
        return "keine"
    # Breitformat ab 1200x627 wird als grosse Karte gezeigt (bei Abweichung
    # von 1,91:1 beschnitten); Quadrat/Hochformat landet als kleines Bild links.
    if breite >= 1200 and hoehe >= 627 and 1.5 <= breite / hoehe <= 2.6:
        return "gross"
    return "klein"


class _MetaLeser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.titel = ""
        self._im_titel = False
        self._im_head = True

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "body":
            self._im_head = False
        if not self._im_head:
            return
        if tag == "meta":
            for schluessel in (a.get("property"), a.get("name")):
                if schluessel and schluessel not in self.meta:
                    self.meta[schluessel] = a.get("content", "")
        elif tag == "link" and a.get("rel"):
            self.links.setdefault(a["rel"], a.get("href", ""))
        elif tag == "title":
            self._im_titel = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._im_titel = False
        if tag == "head":
            self._im_head = False

    def handle_data(self, data):
        if self._im_titel:
            self.titel += data


def kopf_auswerten(seite: str) -> dict:
    kopf = seite[: seite.find("</head>")] if "</head>" in seite else seite
    exakt = bw.pruefe_kopf(kopf)
    leser = _MetaLeser()
    leser.feed(kopf)
    m = leser.meta
    return {
        "pflicht": exakt["pflicht"],
        "pflicht_fehlend": exakt["fehlend"],
        "title": m.get("og:title") or m.get("title") or leser.titel.strip(),
        "description": m.get("og:description") or m.get("description") or "",
        "image": m.get("og:image") or m.get("image") or "",
        "og_type": m.get("og:type", ""),
        "author": m.get("author", ""),
        "og_url": m.get("og:url", ""),
        "og_site_name": m.get("og:site_name", ""),
        "og_image_width": m.get("og:image:width", ""),
        "og_image_height": m.get("og:image:height", ""),
        "og_image_alt": m.get("og:image:alt", ""),
        "twitter_card": m.get("twitter:card", ""),
        "fediverse_creator": m.get("fediverse:creator", ""),
        "canonical": leser.links.get("canonical", ""),
        "html_title": html_mod.unescape(leser.titel.strip()),
    }


def _abruf(url: str, ua: str, limit: int, timeout: float) -> tuple[int | None, dict, bytes, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            daten = r.read(limit + 1)
            return r.status, {k.lower(): v for k, v in r.headers.items()}, daten, None
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, b"", f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {}, b"", f"nicht erreichbar ({type(exc).__name__})"


def pruefe_url(url: str, *, ua: str = LINKEDIN_UA, dist_html: str | None = None, timeout: float = 15,
               abruf=_abruf) -> dict:
    befunde: list[dict] = []

    def b(stufe: str, text: str) -> None:
        befunde.append({"stufe": stufe, "text": text})

    erg: dict = {"url": url, "ua": ua.split(" ")[0], "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
                 "status": None, "fehler": None, "meta": {}, "bild": None, "cache": {}, "gleich_build": None,
                 "abweichungen": [], "befunde": befunde}
    status, kopfzeilen, daten, fehler = abruf(url, ua, MAX_SEITE, timeout)
    erg["status"], erg["fehler"] = status, fehler
    erg["cache"] = {k: kopfzeilen.get(k, "") for k in ("cache-control", "age", "x-cache", "cf-cache-status",
                                                      "last-modified", "server")}
    if status != 200 or not daten:
        b("fehler", f"Seite liefert {fehler or status} statt 200 – Plattformen zeigen keine Karte.")
        erg["ampel"] = "rot"
        return erg
    b("ok", "Seite antwortet mit 200.")
    seite = daten.decode("utf-8", "replace")
    m = kopf_auswerten(seite)
    erg["meta"] = m
    if m["pflicht_fehlend"]:
        b("fehler", "Pflicht-Meta-Tags fehlen oder haben nicht die vorgeschriebene Form: " + ", ".join(m["pflicht_fehlend"]))
    else:
        b("ok", "Alle fünf Pflicht-Meta-Tags in der vorgeschriebenen Form vorhanden.")
    tl, dl = len(m["title"]), len(m["description"])
    b("ok" if 40 <= tl <= 70 else "warn", f"Titel {tl} Zeichen (Soll 40–70; Karten kürzen nach 1–2 Zeilen).")
    b("ok" if 120 <= dl <= 160 else "warn", f"Beschreibung {dl} Zeichen (Soll 120–160).")
    if m["canonical"] and m["canonical"].rstrip("/") == url.rstrip("/"):
        b("ok", "Canonical zeigt auf diese URL.")
    else:
        b("warn", f"Canonical {m['canonical'] or 'fehlt'} – erwartet {url}.")
    if m["og_image_width"] and m["og_image_height"]:
        b("ok", f"og:image:width/height gesetzt ({m['og_image_width']}×{m['og_image_height']}).")
    else:
        b("warn", "og:image:width/height fehlen – Facebook/LinkedIn müssen das Bild erst laden, die erste Vorschau kann ohne Bild erscheinen.")

    # Vorschaubild
    bild_url = m["pflicht"].get("image/og:image") or m["image"]
    if not bild_url:
        b("fehler", "Kein og:image.")
    else:
        bild_url = urllib.parse.urljoin(url, bild_url)
        bstatus, bkopf, bdaten, bfehler = abruf(bild_url, ua, MAX_BILD, timeout)
        groesse = int(bkopf.get("content-length") or len(bdaten) or 0)
        masse = bw.bildmasse(bdaten) if bdaten else None
        info = {"url": bild_url, "status": bstatus, "content_type": bkopf.get("content-type", ""),
                "bytes": groesse, "breite": masse[0] if masse else None, "hoehe": masse[1] if masse else None}
        info["verhaeltnis"] = round(masse[0] / masse[1], 2) if masse and masse[1] else None
        info["kartentyp"] = kartentyp(info["breite"], info["hoehe"])
        erg["bild"] = info
        if bstatus != 200:
            b("fehler", f"og:image liefert {bfehler or bstatus} – keine Bildkarte.")
        else:
            ct = info["content_type"]
            if not ct.startswith("image/") or "svg" in ct:
                b("fehler", f"og:image hat Content-Type {ct or '?'} – erwartet JPG/PNG/WebP/GIF.")
            else:
                b("ok", f"og:image erreichbar ({ct}, {round(groesse / 1024)} KB).")
            if groesse > BILD_GRENZE_LINKEDIN:
                b("fehler", f"og:image {round(groesse / 1024 / 1024, 1)} MB – LinkedIn lädt nur bis 5 MB.")
            if masse:
                txt = f"Bild {masse[0]}×{masse[1]} px, Verhältnis {info['verhaeltnis']}:1 → "
                if info["kartentyp"] == "gross" and abs(info["verhaeltnis"] - 1.91) > 0.1:
                    b("warn", txt + "große Bildkarte, aber auf 1,91:1 beschnitten – Bildrand prüfen (ideal 1200×630).")
                elif info["kartentyp"] == "gross":
                    b("ok", txt + "große Bildkarte.")
                elif info["kartentyp"] == "klein":
                    b("warn", txt + "nur kleine Karte (Vorschaubild links); für die große Karte ≥ 1200×627 bei ~1,91:1.")
                else:
                    b("fehler", txt + "zu klein für ein Vorschaubild.")
                if m["og_image_width"] and m["og_image_height"]:
                    if (str(masse[0]), str(masse[1])) != (str(m["og_image_width"]), str(m["og_image_height"])):
                        b("warn", f"og:image:width/height ({m['og_image_width']}×{m['og_image_height']}) passen nicht zur Datei ({masse[0]}×{masse[1]}).")
            else:
                b("warn", "Bildmaße nicht lesbar.")

    # Live = Build?
    if dist_html is not None:
        live_hash = hashlib.sha256(daten).hexdigest()
        build_bytes = dist_html.encode("utf-8")
        if hashlib.sha256(build_bytes).hexdigest() == live_hash:
            erg["gleich_build"] = True
            b("ok", "Live-Seite ist byte-gleich mit dem lokalen Build (dist/).")
        else:
            erg["gleich_build"] = False
            lokal = kopf_auswerten(dist_html)
            for feld, name in (("title", "Titel"), ("description", "Beschreibung"), ("image", "Bild")):
                if lokal[feld] != m[feld]:
                    erg["abweichungen"].append(name)
            if erg["abweichungen"]:
                b("fehler", "Live weicht vom lokalen Build ab in: " + ", ".join(erg["abweichungen"])
                  + " – noch nicht deployt oder Cache (GitHub Pages max-age 600 s) noch alt.")
            else:
                b("warn", "Live-Seite unterscheidet sich vom lokalen Build (Vorschau-Angaben gleich) – lokale Änderungen noch nicht deployt oder Cache noch alt.")
    cc = erg["cache"].get("cache-control", "")
    if cc:
        b("ok" if "max-age=600" in cc or "max-age" not in cc else "warn",
          f"Cache: {cc}" + (f", Alter {erg['cache']['age']} s" if erg["cache"].get("age") else "")
          + (f", x-cache {erg['cache']['x-cache']}" if erg["cache"].get("x-cache") else "")
          + (f", cf-cache-status {erg['cache']['cf-cache-status']}" if erg["cache"].get("cf-cache-status") else "")
          + " – nach einem Deploy bis zu 10 Minuten warten.")
    stufen = {x["stufe"] for x in befunde}
    erg["ampel"] = "rot" if "fehler" in stufen else ("gelb" if "warn" in stufen else "gruen")
    return erg


# --------------------------------------------------------------------------
# Artikelbezogen + Zwischenspeicher
# --------------------------------------------------------------------------


def _speicher():
    from gemeinsam import speicher
    return speicher


def pruefe_artikel(slug: str, cfg: dict, *, speichern: bool = True, abruf=_abruf) -> dict:
    from build import ROOT
    url = f"{cfg['site']['base_url']}/artikel/{slug}/"
    dist = ROOT / cfg["paths"]["dist_dir"] / "artikel" / slug / "index.html"
    dist_html = dist.read_text(encoding="utf-8") if dist.exists() else None
    erg = pruefe_url(url, dist_html=dist_html, abruf=abruf)
    erg["slug"] = slug
    if speichern:
        _speicher().schreiben(erg, "inspector", f"{slug}.json")
    return erg


def letztes_ergebnis(slug: str) -> dict | None:
    return _speicher().lesen("inspector", f"{slug}.json")
