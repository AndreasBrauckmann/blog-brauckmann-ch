"""Plattformdefinitionen, Vorschau-/Kuerzungslogik, Pruefliste, Verbesserungsvorschlaege
und Eignungsscore fuer die Plattformseiten /verwaltung/plattform/<name>.

Reine Logik ohne Flask und ohne Netz - dadurch gut testbar. Laufzeitdaten
(Pruefliste, Posts, Analysen) liegen unter data/plattformen/ (in .gitignore).

Eignungsscore (0-100, je Artikel und Plattform), Formel auch auf der Seite:

    Eignung = 0,25 x Gesamtscore der Bewertung
            + 0,25 x Teilscore A (Vorschau/Meta)
            + 0,50 x Mittel der plattformspezifischen Pruefungen

Die gemessene Wirkung (Likes, Impressions ...) fliesst NICHT ein.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

POST_INSPECTOR = "https://www.linkedin.com/post-inspector/"
SHARING_DEBUGGER = "https://developers.facebook.com/tools/debug/"

GEWICHT_GESAMT = 0.25
GEWICHT_META = 0.25
GEWICHT_PLATTFORM = 0.50
MS_DECKEL = 40  # Blog-Link in der MS Tech Community unerwuenscht -> Eignung hoechstens 40

MASTODON_LINK = 23
MASTODON_LIMIT = 500
BLUESKY_GRAPHEME = 300
BLUESKY_BYTES = 3000
BLUESKY_THUMB_MAX = 1_000_000  # Bytes, Bluesky-Grenze fuer uploadBlob-Thumbs der Link-Karte
LINKEDIN_SICHTBAR_MOBIL = 140
LINKEDIN_SICHTBAR_DESKTOP = 210
LINKEDIN_KARTE_MAX = 300  # laengerer Text -> Karte erschien in der Profil-Uebersicht nicht (Praxis)
LINKEDIN_HART = 3000
REDDIT_TITEL_MAX = 300

# --------------------------------------------------------------------------
# Plattformdefinitionen
# --------------------------------------------------------------------------

# art: belegt | praxis | ungeprueft  (Makro etikett() in _makros.html)
PLATTFORM_DEF: dict[str, dict] = {
    "mastodon": {
        "karte": True, "manuell": False, "kanal": "mastodon", "bildquelle": "og",
        "post_url": "https://mastodon.social/",
        "regeln": [
            ("belegt", "500 Zeichen je Beitrag; jeder Link zählt pauschal 23 Zeichen (live bestätigt). config.yaml nutzt 480 als Sicherheitsabstand.", None),
            ("belegt", "Die Link-Karte holt der Server aus den Open-Graph-Tags der Artikelseite (og:title, og:description, og:image).", None),
            ("praxis", "Mit <meta name=\"fediverse:creator\" content=\"@user@instanz\"> im Artikelkopf zeigt die Karte den Autor als Fediverse-Konto.", None),
            ("belegt", "Zähler (Boosts, Favoriten, Antworten) sind ohne Login lesbar; Aufrufzahlen (Views) liefert Mastodon nicht.", None),
        ],
        "pruefliste": [
            ("karte", "Vorschau-Karte geprüft (Titel, Beschreibung, Bild stimmen)", None),
            ("fedi", "fediverse:creator im Artikelkopf vorhanden", None),
            ("laenge", "Text höchstens 480 Zeichen (Links als 23 gezählt)", None),
            ("karte_live", "Nach dem Posten: Karte erscheint unter dem Beitrag", None),
        ],
    },
    "bluesky": {
        "karte": True, "manuell": False, "kanal": "bluesky", "bildquelle": "image",
        "post_url": "https://bsky.app/",
        "regeln": [
            ("belegt", "Höchstens 300 Grapheme und 3000 Bytes (UTF-8) je Beitrag. Hier wird mit einer Annäherung gezählt; config.yaml nutzt 290.", None),
            ("belegt", "Die Link-Karte baut der Client selbst (app.bsky.embed.external); das Vorschaubild darf höchstens 1 MB groß sein (uploadBlob).", None),
            ("belegt", "publish.py nimmt für die Karte das Frontmatter-Feld image (nicht og_image). Fehlt image, erscheint die Karte ohne Bild.", None),
            ("belegt", "Links und Hashtags sind Facets mit UTF-8-Byte-Positionen.", None),
            ("belegt", "Zähler (Likes, Reposts, Antworten, Zitate) über public.api.bsky.app ohne Login; Views liefert Bluesky nicht.", None),
        ],
        "pruefliste": [
            ("karte", "Vorschau-Karte geprüft (Titel, Beschreibung, Bild)", None),
            ("thumb", "Vorschaubild der Karte höchstens 1 MB", None),
            ("laenge", "Text höchstens 290 Grapheme", None),
            ("karte_live", "Nach dem Posten: Karte mit Bild erscheint", None),
        ],
    },
    "linkedin": {
        "karte": True, "manuell": True, "kanal": "linkedin", "bildquelle": "og",
        "post_url": "https://www.linkedin.com/feed/",
        "regeln": [
            ("praxis", "Die Link-Karte erscheint nur bei kurzem Text (Praxisbefund): bei langen Beiträgen zeigte LinkedIn in der Profil-Übersicht keine Karte. Standard ist deshalb „Kurz mit Karte“.", None),
            ("praxis", "Vor „…mehr“ sind mobil etwa 140, am Desktop etwa 210 Zeichen sichtbar; der erste Satz zählt am meisten.", None),
            ("belegt", "Harte Grenze 3000 Zeichen je Beitrag (CLAUDE.md, Stand September 2026).", None),
            ("praxis", "Für die große Bildkarte: Bild mindestens 1200 × 627 px, etwa 1,91:1.", None),
            ("belegt", "Der Post Inspector vor dem Posten ist Pflicht (CLAUDE.md) und bleibt ein Schritt des Menschen.", POST_INSPECTOR),
        ],
        "pruefliste": [
            ("inspector", "LinkedIn Post Inspector ausgeführt (Live-URL eingegeben, Inspect, Titel/Bild/Beschreibung geprüft)", POST_INSPECTOR),
            ("haken", "Erste ~140 Zeichen tragen den Haken", None),
            ("kurz", "Format „Kurz mit Karte“ gewählt (Text höchstens 300 Zeichen)", None),
            ("karte_live", "Nach dem Posten: Karte in der Profil-Übersicht sichtbar", None),
        ],
    },
    "reddit": {
        "karte": False, "manuell": True, "kanal": "reddit", "bildquelle": "og",
        "post_url": "https://www.reddit.com/",
        "regeln": [
            ("belegt", "Titel höchstens 300 Zeichen (API-Dokumentation); Moderatoren können enger setzen.", "https://www.reddit.com/dev/api"),
            ("belegt", "Spam-Richtlinie (geändert 30.9.2026): bei Eigenwerbung „thoughtful about frequency“. Eine offizielle 9:1-Regel gibt es nicht.", None),
            ("praxis", "r/sysadmin behandelt Blogartikel als „Produkt“ (nicht direkt geprüft); dort stattdessen r/SysAdminBlogs nutzen.", None),
            ("praxis", "Regeln des Subreddits vor dem Posten lesen. Reddit-API nur mit Freigabe; Views per API unbelegt.", None),
        ],
        "pruefliste": [
            ("regeln", "Regeln des Ziel-Subreddits gelesen", None),
            ("sub", "Passendes Subreddit gewählt (r/SysAdminBlogs statt r/sysadmin)", None),
            ("haeufigkeit", "Eigenwerbung nicht gehäuft (Frequenz bedacht)", None),
            ("titel", "Titel höchstens 300 Zeichen", None),
        ],
    },
    "facebook": {
        "karte": True, "manuell": True, "kanal": "facebook", "bildquelle": "og",
        "post_url": "https://www.facebook.com/",
        "regeln": [
            ("belegt", "Link-Vorschau aus den og:-Tags. Bild mindestens 1200 × 630 (1,91:1), mindestens 200 × 200, höchstens 8 MB; og:image:width und og:image:height setzen.", SHARING_DEBUGGER),
            ("belegt", "Zwischenspeicher mit dem Sharing Debugger erneuern.", SHARING_DEBUGGER),
            ("belegt", "Insights nur für Seiten/Profimodus; eine API für persönliche Profile gibt es praktisch nicht.", None),
            ("praxis", "Zeichenlimit 63.206. Meta testet ein Limit von 2 Link-Posts/Monat für Profimodus ohne Verifizierung (nur Presse beobachtet).", None),
        ],
        "pruefliste": [
            ("debugger", "Sharing Debugger ausgeführt (Cache erneuert, Vorschau geprüft)", SHARING_DEBUGGER),
            ("masse", "og:image:width/height gesetzt, Bild mindestens 1200 × 630", None),
            ("karte_live", "Nach dem Posten: Karte erscheint wie in der Vorschau", None),
        ],
    },
    "youtube_community": {
        "karte": False, "manuell": True, "kanal": "youtube_community", "bildquelle": "og",
        "post_url": "https://studio.youtube.com/",
        "regeln": [
            ("belegt", "YouTube Posts (früher Community): Standard-Feature ohne Abo-Schwelle; Text, Bild, Video, Playlist, Umfrage (4 Optionen je 65 Zeichen) und Quiz.", None),
            ("ungeprueft", "Haupttext-Limit und Link-Regeln sind unbelegt; die 1000 Zeichen in config.yaml sind eine Annahme.", None),
            ("belegt", "Kennzahlen nur im Studio (Impressions, Likes, Abos); es gibt keine API für Posts.", None),
        ],
        "pruefliste": [
            ("text", "Text im Studio/App eingefügt und Vorschau geprüft", None),
            ("link", "Link-Darstellung nach dem Posten geprüft (Regeln unbelegt)", None),
        ],
    },
    "microsoft_tech_community": {
        "karte": False, "manuell": True, "kanal": "microsoft_tech_community", "bildquelle": "og",
        "post_url": "https://techcommunity.microsoft.com/",
        "warnung": ("Hier ist ein Link-Beitrag zum eigenen Blog riskant. Der Code of Conduct (v15.0, 4.2.2026) und die Guidelines "
                    "lehnen Links auf Inhalte ab, die nicht Microsoft gehören, und gehen gegen Spam ohne Toleranz bis zur Sperre vor. "
                    "Besser: eine Diskussion oder Frage mit Mehrwert OHNE Werbelink. Der vorgeschlagene Text unten ist deshalb eine Diskussionsfrage ohne Blog-Link."),
        "regeln": [
            ("belegt", "Links auf Inhalte, die nicht Microsoft gehören, sind unerwünscht; Spam ohne Toleranz bis zur Sperre (Code of Conduct v15.0, 4.2.2026).", "https://techcommunity.microsoft.com/"),
            ("belegt", "Blogs dort nur für Microsoft-Mitarbeiter; Gastbeiträge über techcommunity@microsoft.com.", None),
            ("belegt", "Likes und Antworten sind sichtbar; Views sind unbelegt. Die API antwortet anonym mit 403.", None),
        ],
        "pruefliste": [
            ("coc", "Code of Conduct gelesen", "https://techcommunity.microsoft.com/"),
            ("kein_link", "Text enthält keinen Link auf den eigenen Blog", None),
            ("rubrik", "Passende Rubrik für die Diskussion gewählt", None),
        ],
    },
}

# Felder der manuellen Erfassung (LinkedIn nutzt linkedin_import.FELDER_BEITRAG)
MANUELLE_FELDER: dict[str, dict[str, str]] = {
    "reddit": {"upvotes": "Upvotes", "kommentare": "Kommentare", "upvote_anteil": "Upvote-Anteil (%)", "views": "Views (falls angezeigt)"},
    "facebook": {"reaktionen": "Reaktionen", "kommentare": "Kommentare", "shares": "Shares",
                 "link_klicks": "Link-Klicks (nur Profimodus/Insights)", "reichweite": "Reichweite (nur Profimodus/Insights)"},
    "youtube_community": {"impressions": "Impressions (Studio)", "likes": "Likes", "kommentare": "Kommentare", "abos": "Neue Abos"},
    "microsoft_tech_community": {"likes": "Likes/Kudos", "antworten": "Antworten", "views": "Views (falls sichtbar)"},
}
PROZENT_FELDER = {"upvote_anteil"}


# --------------------------------------------------------------------------
# Zaehlen
# --------------------------------------------------------------------------

_URL = re.compile(r"https?://\S+")


def zaehle_mastodon(text: str) -> int:
    """Mastodon-Laenge: jeder Link zaehlt 23 Zeichen, Rest Zeichen fuer Zeichen."""
    return sum(MASTODON_LINK if t.startswith(("http://", "https://")) else len(t)
               for t in re.split(r"(https?://\S+)", text) if t)


def mastodon_schnitt(text: str, limit: int = MASTODON_LIMIT) -> int | None:
    """Index im Rohtext, ab dem das Limit ueberschritten wird (None = passt)."""
    n = 0
    pos = 0
    for t in re.split(r"(https?://\S+)", text):
        if not t:
            continue
        if t.startswith(("http://", "https://")):
            n += MASTODON_LINK
            if n > limit:
                return pos
        else:
            if n + len(t) > limit:
                return pos + (limit - n)
            n += len(t)
        pos += len(t)
    return None


def graphemes(text: str) -> list[str]:
    """Naeherung an Grapheme-Cluster ohne Zusatzpaket: kombinierende Zeichen,
    Variation Selectors, ZWJ-Sequenzen, Hautton-Modifier, Regionalindikator-Paare
    und CRLF werden dem vorigen Zeichen zugeschlagen."""
    cluster: list[str] = []
    out: list[str] = []
    for ch in text:
        if not cluster:
            cluster = [ch]
            continue
        prev = cluster[-1]
        o = ord(ch)
        ri = 0x1F1E6 <= o <= 0x1F1FF
        verbinden = (
            unicodedata.category(ch) in ("Mn", "Me", "Mc")
            or ch in ("‍", "️", "︎")
            or 0x1F3FB <= o <= 0x1F3FF
            or 0xE0020 <= o <= 0xE007F
            or prev == "‍"
            or (ch == "\n" and prev == "\r")
            or (ri and len(cluster) == 1 and 0x1F1E6 <= ord(prev) <= 0x1F1FF)
        )
        if verbinden:
            cluster.append(ch)
        else:
            out.append("".join(cluster))
            cluster = [ch]
    if cluster:
        out.append("".join(cluster))
    return out


def zaehle_bluesky(text: str) -> dict:
    g = graphemes(text)
    return {"grapheme": len(g), "bytes": len(text.encode("utf-8"))}


def bluesky_schnitt(text: str) -> int | None:
    """Index im Rohtext, ab dem 300 Grapheme oder 3000 Bytes ueberschritten sind."""
    pos = 0
    n = 0
    b = 0
    for g in graphemes(text):
        gb = len(g.encode("utf-8"))
        if n + 1 > BLUESKY_GRAPHEME or b + gb > BLUESKY_BYTES:
            return pos
        n += 1
        b += gb
        pos += len(g)
    return None


def schnitt_einfach(text: str, limit: int) -> int | None:
    return limit if len(text) > limit else None


def zaehlung(plattform: str, text: str, cfg: dict | None = None, format: str = "kurz") -> dict:
    """Einheitliches Ergebnis: n, limit, einheit, ok, schnitt (Rohtext-Index oder None), extra."""
    ch = ((cfg or {}).get("channels") or {}).get(plattform, {})
    if plattform == "mastodon":
        n = zaehle_mastodon(text)
        soll = ch.get("max_chars", 480)
        return {"n": n, "limit": MASTODON_LIMIT, "soll": soll, "einheit": "Zeichen (Link = 23)", "ok": n <= MASTODON_LIMIT,
                "schnitt": mastodon_schnitt(text), "extra": []}
    if plattform == "bluesky":
        z = zaehle_bluesky(text)
        soll = ch.get("max_chars", 290)
        return {"n": z["grapheme"], "limit": BLUESKY_GRAPHEME, "soll": soll, "einheit": "Grapheme (Näherung)",
                "ok": z["grapheme"] <= BLUESKY_GRAPHEME and z["bytes"] <= BLUESKY_BYTES, "schnitt": bluesky_schnitt(text),
                "extra": [f'{z["bytes"]} / {BLUESKY_BYTES} Bytes (UTF-8)']}
    if plattform == "linkedin":
        n = len(text)
        if format == "lang":
            soll = ch.get("lang_max_chars", 1800)
        else:
            soll = LINKEDIN_KARTE_MAX
        return {"n": n, "limit": LINKEDIN_HART, "soll": soll, "einheit": "Zeichen", "ok": n <= LINKEDIN_HART,
                "schnitt": schnitt_einfach(text, LINKEDIN_HART), "extra": []}
    limit = {"reddit": ch.get("max_chars", 40000), "facebook": ch.get("max_chars", 63206),
             "youtube_community": ch.get("max_chars", 1000), "microsoft_tech_community": ch.get("max_chars", 5000)}[plattform]
    n = len(text)
    return {"n": n, "limit": limit, "soll": limit, "einheit": "Zeichen", "ok": n <= limit, "schnitt": schnitt_einfach(text, limit), "extra": []}


# --------------------------------------------------------------------------
# Karten
# --------------------------------------------------------------------------


def kartentyp(breite: int | None, hoehe: int | None) -> str:
    """gross: >= 1200x627 und etwa 1,91:1; klein: mindestens 200x200 aber nicht gross; keine: zu klein/unbekannt."""
    if not breite or not hoehe:
        return "keine"
    verh = breite / hoehe
    if breite >= 1200 and hoehe >= 627 and 1.6 <= verh <= 2.2:
        return "gross"
    if breite >= 200 and hoehe >= 200:
        return "klein"
    return "keine"


KARTENTYP_TEXT = {"gross": "große Bildkarte", "klein": "kleine Karte (Bild seitlich)", "keine": "keine Bildkarte"}


def kuerze_sichtbar(text: str, zeichen: int, zeilen: int = 3) -> dict:
    """Sichtbarer Teil bis `zeichen` Zeichen bzw. `zeilen` Zeilen (je Zeilenumbruch eine Zeile)."""
    teile = text.split("\n")
    sichtbar_zeilen = "\n".join(teile[:zeilen])
    grenze = min(zeichen, len(sichtbar_zeilen))
    gekuerzt = len(text) > grenze
    if gekuerzt and grenze == zeichen and zeichen < len(text) and not text[zeichen].isspace():
        # nicht mitten im Wort: auf letzte Wortgrenze zuruecknehmen, falls eine nahe liegt
        w = text.rfind(" ", max(0, zeichen - 15), zeichen)
        if w > 0:
            grenze = w
    return {"sichtbar": text[:grenze].rstrip(), "rest": text[grenze:], "gekuerzt": gekuerzt, "ab": grenze}


def linkedin_kachel(text: str, hat_karte: bool) -> dict:
    """Profil-Uebersicht: Beitragstext auf ~3 Zeilen gekuerzt mit „…mehr“; Karte nur bei kurzem Text sichtbar."""
    karte_sichtbar = hat_karte and len(text) <= LINKEDIN_KARTE_MAX
    return {
        "mobil": kuerze_sichtbar(text, LINKEDIN_SICHTBAR_MOBIL),
        "desktop": kuerze_sichtbar(text, LINKEDIN_SICHTBAR_DESKTOP),
        "karte_sichtbar": karte_sichtbar,
        "karte_verdeckt": hat_karte and not karte_sichtbar,
        "laenge": len(text),
    }


# --------------------------------------------------------------------------
# publish-log.md
# --------------------------------------------------------------------------

_LOG_ZEILE = re.compile(r"^-\s+([a-z0-9][a-z0-9-]*):\s+([a-z_]+):\s+(https?://\S+)(?:\s+\((.*)\))?\s*$")


def publish_log_parsen(text: str) -> dict[tuple[str, str], dict]:
    """(slug, kanal) -> juengster Eintrag {datum, uhrzeit, url, hinweis, anzahl}.
    Zeilen „- <slug>: mastodon: <url>“ unter „## <Datum>“-Ueberschriften; Fehlschlaege und
    manuelle Eintraege (ohne URL) werden uebersprungen."""
    erg: dict[tuple[str, str], dict] = {}
    datum, uhr = "", ""
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            m = re.match(r"##\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?", zeile)
            datum, uhr = (m.group(1), m.group(2) or "") if m else ("", "")
            continue
        m = _LOG_ZEILE.match(zeile.strip())
        if not m:
            continue
        slug, kanal, url, hinweis = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        alt = erg.get((slug, kanal))
        erg[(slug, kanal)] = {"datum": datum, "uhrzeit": uhr, "url": url, "hinweis": hinweis, "anzahl": (alt["anzahl"] + 1) if alt else 1}
    return erg


def gepostet_aus_log(root: Path) -> dict[tuple[str, str], dict]:
    p = root / "publish-log.md"
    try:
        return publish_log_parsen(p.read_text(encoding="utf-8"))
    except OSError:
        return {}


def token_status(plattform: str) -> dict | None:
    """Nur pruefen, ob die Umgebungsvariablen gesetzt sind (Werte werden nie gelesen/ausgegeben)."""
    var = {"mastodon": ["MASTODON_ACCESS_TOKEN"], "bluesky": ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"]}.get(plattform)
    if not var:
        return None
    fehlt = [v for v in var if not os.environ.get(v)]
    return {"verbunden": not fehlt, "fehlt": fehlt}


# --------------------------------------------------------------------------
# Ablage unter data/plattformen/
# --------------------------------------------------------------------------


class Ablage:
    def __init__(self, root: Path):
        self.basis = root / "data" / "plattformen"

    def lesen(self, *teile: str, standard=None):
        p = self.basis.joinpath(*teile)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return standard

    def schreiben(self, daten, *teile: str) -> None:
        p = self.basis.joinpath(*teile)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, p)

    # Pruefliste: {plattform: {slug: {punkt: datum}}}
    def pruefliste(self, plattform: str, slug: str) -> dict:
        return ((self.lesen("pruefliste.json", standard={}) or {}).get(plattform) or {}).get(slug) or {}

    def pruefliste_setzen(self, plattform: str, slug: str, erledigt: dict[str, str]) -> None:
        d = self.lesen("pruefliste.json", standard={}) or {}
        d.setdefault(plattform, {})[slug] = erledigt
        self.schreiben(d, "pruefliste.json")

    # Posts (manuelle Plattformen): {plattform: {slug: {datum, url}}}
    def posts(self, plattform: str) -> dict:
        return (self.lesen("posts.json", standard={}) or {}).get(plattform) or {}

    def post_setzen(self, plattform: str, slug: str, eintrag: dict | None) -> None:
        d = self.lesen("posts.json", standard={}) or {}
        if eintrag:
            d.setdefault(plattform, {})[slug] = eintrag
        else:
            d.get(plattform, {}).pop(slug, None)
        self.schreiben(d, "posts.json")

    # Auto-Analyse
    def analyse(self, plattform: str, slug: str):
        return self.lesen("analyse", plattform, f"{slug}.json")

    def analyse_speichern(self, plattform: str, slug: str, daten: dict) -> None:
        self.schreiben(daten, "analyse", plattform, f"{slug}.json")


def pruefliste_auswerten(plattform: str, gespeichert: dict, angekreuzt: list[str], heute: str) -> dict[str, str]:
    """Neu angekreuzte Punkte bekommen das heutige Datum, bereits erledigte behalten ihres,
    abgewaehlte entfallen. Nur Punkte der Plattform sind erlaubt."""
    erlaubt = {p[0] for p in PLATTFORM_DEF[plattform]["pruefliste"]}
    return {k: gespeichert.get(k) or heute for k in angekreuzt if k in erlaubt}


# --------------------------------------------------------------------------
# Texte je Plattform
# --------------------------------------------------------------------------


def _gespeicherter_linkedin_text(meta: dict, url: str) -> str | None:
    """Von Hand (oder von Claude) geschriebener Beitragstext je Artikel aus data/linkedin_texte.json:
    {"<slug>": {"text": "...", "hashtags": ["#A", "#B"]}}. Format: Text + Leerzeichen + Adresse, Leerzeile, Hashtags.
    Fehlt die Datei oder der Artikel, gilt der erzeugte Text (summarize.py)."""
    import json
    pfad = Path(__file__).resolve().parents[2] / "data" / "linkedin_texte.json"
    try:
        eintrag = json.loads(pfad.read_text(encoding="utf-8")).get(str(meta.get("slug")))
    except (OSError, ValueError):
        return None
    if not eintrag or not str(eintrag.get("text", "")).strip():
        return None
    text = f"{str(eintrag['text']).strip()} {url}"
    tags = " ".join(h for h in (eintrag.get("hashtags") or []) if h)
    return f"{text}\n\n{tags}" if tags else text


def texte(meta: dict, cfg: dict, format: str | None = None) -> dict[str, dict]:
    """plattform -> {"text": str, "titel": str|None}. Wie app.py/summarize.py; MS Tech Community als
    Diskussionsfrage ohne Blog-Link."""
    from summarize import headline, linkedin_text, summarize_all  # spaet: build/yaml erst bei Bedarf

    alle = summarize_all(meta, cfg)
    url = f"{cfg['site']['base_url']}/artikel/{meta['slug']}/"
    out: dict[str, dict] = {}
    for p in ("mastodon", "bluesky"):
        out[p] = {"text": alle.get(p, ""), "titel": None}
    out["linkedin"] = {"text": linkedin_text(meta, cfg, format) if format else alle.get("linkedin", ""), "titel": None}
    eigener = _gespeicherter_linkedin_text(meta, url)
    if eigener and (format in (None, "kurz")):
        out["linkedin"]["text"] = eigener
    r = alle.get("reddit")
    out["reddit"] = {"text": r["body"] if isinstance(r, dict) else str(r or ""), "titel": r["title"] if isinstance(r, dict) else meta["title"]}
    standard = f"{headline(meta)}\n\n{meta['description']}\n\n{url}"
    out["facebook"] = {"text": standard, "titel": None}
    out["youtube_community"] = {"text": standard, "titel": None}
    frage = str(meta.get("slogan") or meta["title"]).strip().rstrip("?.!")
    out["microsoft_tech_community"] = {
        "text": (f"Frage an die Community: {frage} – wie geht ihr damit um?\n\n{meta['description']}\n\n"
                 "Ich habe damit eigene Erfahrungen gemacht und teile gern Details und Fallstricke, wenn Interesse besteht."),
        "titel": None}
    return out


# --------------------------------------------------------------------------
# Kontext, Vorschlaege, Eignung
# --------------------------------------------------------------------------


def _band(wert: float, lo: float, hi: float, lo0: float, hi0: float) -> float:
    if lo <= wert <= hi:
        return 100.0
    if wert < lo:
        return round(max(0.0, min(1.0, (wert - lo0) / (lo - lo0))) * 100, 1) if lo != lo0 else 0.0
    return round(max(0.0, min(1.0, (hi0 - wert) / (hi0 - hi))) * 100, 1) if hi0 != hi else 0.0


def _linear_ab(wert: float, gut: float, schlecht: float) -> float:
    """100 bis `gut`, 0 ab `schlecht`, dazwischen linear (steigende Werte schlechter)."""
    if wert <= gut:
        return 100.0
    if wert >= schlecht:
        return 0.0
    return round(100 * (schlecht - wert) / (schlecht - gut), 1)


def bild_info(root: Path, bildpfad: str | None, bewertungs_masse=None) -> dict:
    """Bild aus dem Frontmatter-Pfad (/static/img/...): Datei, Masse (Dateikopf), KB, Verhaeltnis, Kartentyp."""
    info = {"pfad": bildpfad or "", "rel": "", "vorhanden": False, "breite": None, "hoehe": None, "bytes": 0, "kb": 0,
            "verhaeltnis": None, "kartentyp": "keine", "svg": False}
    if not bildpfad:
        return info
    datei = root / bildpfad.lstrip("/")
    if bildpfad.startswith("/static/img/"):
        info["rel"] = bildpfad[len("/static/img/"):]
    if not datei.is_file():
        return info
    info["vorhanden"] = True
    info["bytes"] = datei.stat().st_size
    info["kb"] = round(info["bytes"] / 1024)
    info["svg"] = datei.suffix.lower() == ".svg"
    from bewertung import bildmasse
    m = bildmasse(datei)
    if m:
        info["breite"], info["hoehe"] = m
        info["verhaeltnis"] = round(m[0] / m[1], 2) if m[1] else None
        info["kartentyp"] = "keine" if info["svg"] else kartentyp(*m)
    return info


def kontext(root: Path, meta: dict, bew, cfg: dict) -> dict:
    """Alles, was Vorschau, Vorschlaege und Eignung je Artikel brauchen."""
    kopf = (bew.kennzahlen.get("kopf") or {})
    pf = kopf.get("pflicht") or {}
    og = bew.kennzahlen.get("og_bild")
    seite = root / cfg["paths"]["dist_dir"] / "artikel" / meta["slug"] / "index.html"
    kopf_text = ""
    try:
        t = seite.read_text(encoding="utf-8")
        kopf_text = t[: t.find("</head>")]
    except OSError:
        pass
    return {
        "slug": meta["slug"],
        "titel": pf.get("title/og:title") or str(meta.get("title", "")),
        "beschreibung": pf.get("description/og:description") or str(meta.get("description", "")),
        "pflicht": pf,
        "fehlend": kopf.get("fehlend") or [],
        "dist": bool(kopf),
        "og": bild_info(root, og),
        "image": bild_info(root, meta.get("image")),  # Bluesky-Karte nimmt meta["image"]
        "bild_masse_tags": ('property="og:image:width"' in kopf_text and 'property="og:image:height"' in kopf_text) if kopf_text else None,
        "fedi": ('name="fediverse:creator"' in kopf_text) if kopf_text else None,
        "domain": re.sub(r"^https?://", "", cfg["site"]["base_url"]).split("/")[0],
        "live_url": f"{cfg['site']['base_url']}/artikel/{meta['slug']}/",
        "woerter": bew.kennzahlen.get("woerter", 0),
        "gesamt": bew.gesamt,
        "meta_a": bew.kategorie_score("A"),
    }


def vorschlaege(plattform: str, ctx: dict, text: str, titel: str | None = None, cfg: dict | None = None, format: str = "kurz") -> list[dict]:
    """Regelbasierte, konkrete Vorschlaege: [{"stufe": "fehler|warn|ok|info", "text": ...}]."""
    v: list[dict] = []

    def add(stufe, t):
        v.append({"stufe": stufe, "text": t})

    d = len(ctx["beschreibung"])
    t_len = len(ctx["titel"])
    og = ctx["og"]
    z = zaehlung(plattform, text, cfg, format)
    karte = PLATTFORM_DEF[plattform]["karte"]

    if karte:
        if not og["vorhanden"]:
            add("fehler", "Kein Vorschaubild gefunden – Karte ohne Bild. og_image (1200×630) im Frontmatter setzen.")
        else:
            maße = f'{og["breite"]}×{og["hoehe"]}' if og["breite"] else "Maße unbekannt"
            if og["svg"]:
                add("fehler", "Vorschaubild ist ein SVG – wird von den Plattformen nicht unterstützt. Als JPG/PNG exportieren.")
            elif og["kartentyp"] == "klein":
                if og["verhaeltnis"] and abs(og["verhaeltnis"] - 1.91) > 0.3:
                    add("warn", f"Bild {maße} (Verhältnis {str(og['verhaeltnis']).replace('.', ',')}:1) → nur kleine Karte. Für die große Karte 1200×630 (1,91:1) anlegen.")
                else:
                    add("warn", f"Bild {maße} → kleine Karte. Für die große Karte mindestens 1200×627 anlegen.")
            elif og["kartentyp"] == "keine":
                add("fehler", f"Bild {maße} ist zu klein für eine Karte (mindestens 200×200, besser 1200×630).")
            else:
                add("ok", f"Bild {maße}, {og['kb']} KB → große Bildkarte.")
    if plattform == "linkedin":
        if d > 160:
            add("warn", f"Beschreibung {d} Zeichen – LinkedIn zeigt sie in der Feed-Karte meist nicht, Google und Slack kürzen bei etwa 155–160; auf 120–160 kürzen.")
        elif d < 120:
            add("warn", f"Beschreibung nur {d} Zeichen; auf 120–160 ausbauen (Problem, Nutzen).")
        if t_len > 70:
            add("warn", f"Titel {t_len} Zeichen – LinkedIn schneidet in der Karte nach zwei Zeilen ab (etwa 70–90 Zeichen am Desktop); auf 40–70 kürzen.")
        if format == "lang" and len(text) > LINKEDIN_KARTE_MAX:
            add("warn", f"Langform ({len(text)} Zeichen): in der Profil-Übersicht zeigte LinkedIn bei langen Beiträgen keine Karte. Für Reichweite per Link „Kurz mit Karte“ nutzen.")
        first = text.split("\n")[0]
        if len(first) > LINKEDIN_SICHTBAR_MOBIL:
            add("info", f"Erste Zeile {len(first)} Zeichen – mobil sind nur ~{LINKEDIN_SICHTBAR_MOBIL} sichtbar; den Haken in den ersten Satz ziehen.")
        if format != "lang" and len(text) > LINKEDIN_KARTE_MAX:
            add("warn", f"Text {len(text)} Zeichen – über {LINKEDIN_KARTE_MAX}: Karte könnte in der Profil-Übersicht fehlen.")
    elif plattform == "mastodon":
        if z["n"] > MASTODON_LIMIT:
            add("fehler", f"Text zählt {z['n']} Zeichen (Link = 23) – über dem Limit von {MASTODON_LIMIT}.")
        elif z["n"] > z["soll"]:
            add("warn", f"Text zählt {z['n']} Zeichen – über dem Sicherheitsabstand ({z['soll']}).")
        if ctx["fedi"] is False:
            add("warn", "fediverse:creator fehlt im Artikelkopf – die Karte zeigt dann keinen Autor.")
        elif ctx["fedi"]:
            add("ok", "fediverse:creator vorhanden – die Karte zeigt den Autor.")
        if d > 200:
            add("info", f"Beschreibung {d} Zeichen – Mastodon-Karten zeigen nur wenige Zeilen; 120–160 sind sicher.")
    elif plattform == "bluesky":
        if not z["ok"]:
            add("fehler", f"Text hat {z['n']} Grapheme / {z['extra'][0]} – über dem Limit (300 Grapheme, 3000 Bytes).")
        elif z["n"] > z["soll"]:
            add("warn", f"Text hat {z['n']} Grapheme – über dem Sicherheitsabstand ({z['soll']}).")
        im = ctx["image"]
        if not im["vorhanden"]:
            add("warn", "Frontmatter-Feld image fehlt oder Datei nicht gefunden – publish.py baut die Bluesky-Karte dann ohne Bild. image setzen (Datei ≤ 1 MB).")
        elif im["bytes"] > BLUESKY_THUMB_MAX:
            add("fehler", f"Karten-Bild {im['kb']} KB – über 1 MB, Bluesky lehnt den Thumb ab. Bild verkleinern (JPG, 1200 px breit).")
        else:
            add("ok", f"Karten-Bild {im['kb']} KB – unter 1 MB.")
        if og["vorhanden"] and im["vorhanden"] and og["pfad"] != im["pfad"]:
            add("info", "Die Bluesky-Karte nutzt image, die anderen Plattformen og_image – die Bilder unterscheiden sich.")
    elif plattform == "reddit":
        tl = len(titel or "")
        if tl > REDDIT_TITEL_MAX:
            add("fehler", f"Titel {tl} Zeichen – über 300.")
        add("info", "Subreddit-Regeln vorher lesen; in r/sysadmin gilt ein Blogartikel als Produkt – r/SysAdminBlogs nutzen.")
        add("info", "Eigenwerbung sparsam und mit Mehrwert (Spam-Richtlinie: „thoughtful about frequency“).")
    elif plattform == "facebook":
        if ctx["bild_masse_tags"] is False:
            add("warn", "og:image:width/height fehlen im Artikelkopf – Facebook lädt das Bild dann verzögert. Im Build ergänzen.")
        if og["vorhanden"] and og["bytes"] > 8 * 1024 * 1024:
            add("fehler", "Bild über 8 MB – Facebook lehnt es ab.")
        add("info", "Nach Änderungen an Titel/Bild den Sharing Debugger ausführen, sonst bleibt die alte Vorschau im Cache.")
    elif plattform == "youtube_community":
        add("warn", "Haupttext-Limit und Link-Regeln für YouTube Posts sind unbelegt – das 1000-Zeichen-Limit ist eine Annahme.")
        if z["n"] > z["limit"]:
            add("warn", f"Text {z['n']} Zeichen – über der angenommenen Grenze von {z['limit']}.")
    elif plattform == "microsoft_tech_community":
        add("fehler", "Link-Beitrag zum eigenen Blog ist hier riskant (Code of Conduct v15.0). Diskussion/Frage mit Mehrwert ohne Werbelink posten.")
        if re.search(r"https?://", text):
            add("fehler", "Der Text enthält einen Link – für diese Plattform entfernen.")
    if plattform in ("mastodon", "bluesky", "facebook") and t_len > 90:
        add("info", f"Titel {t_len} Zeichen – in der Karte wird er gekürzt; 40–70 sind sicher.")
    if ctx["fehlend"]:
        add("fehler", "Pflicht-Meta-Tags fehlen in dist/: " + ", ".join(ctx["fehlend"]) + ". Neu bauen.")
    if not ctx["dist"]:
        add("warn", "Keine gebaute Artikelseite in dist/ – Meta-Tags konnten nicht geprüft werden.")
    return v


def eignung(plattform: str, ctx: dict, text: str, titel: str | None = None, cfg: dict | None = None, format: str = "kurz") -> dict:
    """Eignungsscore 0-100 mit Teilen. Siehe Modul-Docstring fuer die Formel."""
    z = zaehlung(plattform, text, cfg, format)
    teile: list[dict] = []

    def add(name, score, hinweis):
        teile.append({"name": name, "score": round(score, 1), "hinweis": hinweis})

    og = ctx["og"]
    karte = PLATTFORM_DEF[plattform]["karte"]
    if plattform == "mastodon":
        add("Textlänge im Limit", _linear_ab(z["n"], MASTODON_LIMIT, 650), f"{z['n']} von {MASTODON_LIMIT} Zeichen")
    elif plattform == "bluesky":
        ueber = max(z["n"] / BLUESKY_GRAPHEME, int(z["extra"][0].split()[0]) / BLUESKY_BYTES)
        add("Textlänge im Limit", _linear_ab(ueber, 1.0, 1.5), f"{z['n']} Grapheme, {z['extra'][0]}")
    elif plattform == "linkedin":
        add("Textlänge für Karte", _linear_ab(len(text), LINKEDIN_KARTE_MAX, 900) if format != "lang" else 50.0,
            f"{len(text)} Zeichen (Karte sichtbar bis {LINKEDIN_KARTE_MAX})" if format != "lang" else "Langform: Karte in der Profil-Übersicht unsicher")
    elif plattform == "reddit":
        tl = len(titel or "")
        add("Titel höchstens 300 Zeichen", _linear_ab(tl, REDDIT_TITEL_MAX, 400), f"{tl} Zeichen")
        add("Titellänge lesbar (30–150)", _band(tl, 30, 150, 10, 300), f"{tl} Zeichen")
    elif plattform == "facebook":
        add("Bildgewicht höchstens 8 MB", 100.0 if og["bytes"] <= 8 * 1024 * 1024 else 0.0, f"{og['kb']} KB")
        add("og:image:width/height gesetzt", {True: 100.0, False: 40.0, None: 50.0}[ctx["bild_masse_tags"]], "im Artikelkopf")
    elif plattform == "youtube_community":
        add("Textlänge (angenommen 1000)", _linear_ab(z["n"], z["limit"], z["limit"] * 1.5), f"{z['n']} Zeichen – Limit unbelegt")
    elif plattform == "microsoft_tech_community":
        add("Kein Blog-Link im Text", 0.0 if re.search(r"https?://", text) else 100.0, "Links auf fremde Inhalte unerwünscht")
    if karte:
        add("Bild-Kartentyp", {"gross": 100.0, "klein": 55.0, "keine": 0.0}[og["kartentyp"]], KARTENTYP_TEXT[og["kartentyp"]])
        add("Beschreibung 120–160", _band(len(ctx["beschreibung"]), 120, 160, 50, 260), f"{len(ctx['beschreibung'])} Zeichen")
        add("Titel 40–70", _band(len(ctx["titel"]), 40, 70, 15, 110), f"{len(ctx['titel'])} Zeichen")
    if plattform == "bluesky":
        im = ctx["image"]
        if not im["vorhanden"]:
            add("Thumb höchstens 1 MB", 40.0, "kein image im Frontmatter – Karte ohne Bild")
        else:
            add("Thumb höchstens 1 MB", 100.0 if im["bytes"] <= BLUESKY_THUMB_MAX else 0.0, f"{im['kb']} KB")
    plattform_mittel = sum(t["score"] for t in teile) / len(teile) if teile else 0.0
    score = GEWICHT_GESAMT * ctx["gesamt"] + GEWICHT_META * ctx["meta_a"] + GEWICHT_PLATTFORM * plattform_mittel
    deckel = None
    if plattform == "microsoft_tech_community" and score > MS_DECKEL:
        score, deckel = MS_DECKEL, MS_DECKEL
    score = round(max(0.0, min(100.0, score)), 1)
    return {"score": score, "ampel": "gruen" if score >= 80 else ("gelb" if score >= 60 else "rot"),
            "teile": teile, "plattform_mittel": round(plattform_mittel, 1), "deckel": deckel,
            "gesamt": ctx["gesamt"], "meta_a": ctx["meta_a"]}


MS_THEMEN_STANDARD = ["Microsoft", "Azure", "Entra", "Intune", "M365", "Microsoft 365", "Defender",
                      "Power Platform", "Copilot", "SharePoint", "Exchange", "PowerShell", "Microsoft Teams"]


def ms_sperre(meta: dict, cfg: dict) -> str | None:
    """Grund, warum der Artikel fuer die Microsoft Tech Community GESPERRT ist (sonst None).
    Dort sind Links auf fremde Inhalte unerwuenscht und Spam fuehrt bis zur Sperre des Kontos
    (Code of Conduct v15.0). Deshalb sind alle Artikel ohne Microsoft-Bezug gesperrt: lieber
    ausgegraut als ein gesperrtes Konto."""
    themen = (cfg.get("channels", {}).get("microsoft_tech_community", {}) or {}).get("themen") or MS_THEMEN_STANDARD
    tags = [str(t) for t in (meta.get("tags") or [])]
    text = " ".join(tags + [str(meta.get("title", ""))]).lower()
    treffer = [t for t in themen if re.search(r"(?<![a-z0-9])" + re.escape(str(t).lower()) + r"(?![a-z0-9])", text)]
    if treffer:
        return None
    return ("Gesperrt: Der Artikel hat keinen Microsoft-Bezug (Tags: " + (", ".join(tags) or "keine") +
            "). Die Microsoft Tech Community lehnt Links auf fremde Inhalte ab und sperrt bei Spam. "
            "Zugelassen sind nur Artikel, deren Tags oder Titel eines dieser Themen nennen: " + ", ".join(themen) + ".")


def ampel(score: float) -> str:
    return "gruen" if score >= 80 else ("gelb" if score >= 60 else "rot")


def jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")
