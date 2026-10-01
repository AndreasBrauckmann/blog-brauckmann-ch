"""Regelbasierte redaktionelle Bewertung der Blog-Artikel (Artikel-Ranking).

Alles hier laeuft offline und deterministisch: gleiche Eingabe, gleiches
Ergebnis. Kein LLM, kein Netz. Das optionale Lektorat per LLM liegt in
llm.py und fliesst NICHT in die Punktzahl ein.

Fuenf Kategorien, Gewichte summieren sich auf 100 (siehe KATEGORIEN):
  A Vorschau/Meta (25)       - was Leser in Google/LinkedIn zuerst sehen
  B Lesbarkeit & Fluss (25)  - Lektor/Copy Editor
  C Struktur (15)            - Redakteur
  D Grafiken/Auflockerung (15) - Content Editor
  E SEO/Erfolgstraechtigkeit (20) - Content Strategist

Jedes Kriterium hat Punkte innerhalb seiner Kategorie (die Punkte einer
Kategorie ergeben deren Gewicht). Ein Kriterium erreicht 0-100 %; der
Gesamtscore ist die Summe Punkte x Erfuellungsgrad. Kriterien, die fuer einen
Artikel nicht zutreffen (z. B. Video-Poster ohne Video), fallen heraus, ihre
Punkte werden innerhalb der Kategorie auf die anderen verteilt.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import struct
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

# --------------------------------------------------------------------------
# Kategorien und Kriterien (sichtbar auf der Seite - nichts versteckt)
# --------------------------------------------------------------------------

KATEGORIEN = {
    "A": {"name": "Vorschau/Meta", "gewicht": 25, "rolle": "Content Strategist / Lektor"},
    "B": {"name": "Lesbarkeit & Fluss", "gewicht": 25, "rolle": "Lektor / Copy Editor"},
    "C": {"name": "Struktur", "gewicht": 15, "rolle": "Redakteur"},
    "D": {"name": "Grafiken/Auflockerung", "gewicht": 15, "rolle": "Content Editor"},
    "E": {"name": "SEO/Erfolgsträchtigkeit", "gewicht": 20, "rolle": "Content Strategist"},
}

# id -> (Kategorie, Name, Punkte, Soll-Beschreibung)
KRITERIEN = {
    "a_titel": ("A", "Titellänge", 3, "40–70 Zeichen (Google kürzt ab ca. 60 Zeichen, LinkedIn-Karten nach 1–2 Zeilen)"),
    "a_beschr": ("A", "Beschreibungslänge", 3, "120–160 Zeichen"),
    "a_hook": ("A", "Haken vorn in der Beschreibung", 3, "In den ersten ~100 Zeichen Problem/Nutzen statt Floskel"),
    "a_bild": ("A", "Vorschaubild für og:image geeignet", 4, "Datei vorhanden, ≥ 1200 px breit, Verhältnis ≈ 1,91:1 (1200×630), ≤ 5 MB, kein SVG"),
    "a_alt": ("A", "og:image:alt", 2, "Alternativtext des Vorschaubilds im Kopf der Seite"),
    "a_autor": ("A", "Autor", 1, '<meta name="author"> vorhanden'),
    "a_canonical": ("A", "Canonical", 1, "Canonical zeigt auf die Live-URL des Artikels"),
    "a_jsonld": ("A", "JSON-LD gültig", 2, "Article mit headline, description, image, datePublished, author"),
    "a_pflicht": ("A", "Fünf Pflicht-Meta-Tags in dist/", 4, "title/og:title, og:type, image/og:image, description/og:description, author"),
    "a_dist": ("A", "dist/ entspricht dem Frontmatter", 2, "Titel und Beschreibung in dist/ = Frontmatter (sonst neu bauen)"),
    "b_amstad": ("B", "Lesbarkeitsindex (Flesch/Amstad)", 5, "≥ 50 (Fachpublikum; 60+ leicht, < 30 sehr schwer)"),
    "b_satzlaenge": ("B", "Mittlere Satzlänge", 3, "≤ 17 Wörter pro Satz"),
    "b_lange_saetze": ("B", "Anteil sehr langer Sätze (> 25 Wörter)", 3, "≤ 10 %"),
    "b_absaetze": ("B", "Absatzlängen", 3, "Höchstens 10 % der Absätze über 100 Wörter"),
    "b_wiederholung": ("B", "Wortwiederholungen", 2, "≤ 6 Nahwiederholungen je 1000 Wörter (gleiches Inhaltswort innerhalb von 15 Wörtern)"),
    "b_fuellwoerter": ("B", "Füllwörter", 2, "≤ 1,0 % der Wörter"),
    "b_einleitung": ("B", "Einleitung mit Haken", 3, "Erster Satz kurz (≤ 25 Wörter) und konkret: Zahl, Frage, Problem oder Nutzen"),
    "b_fazit": ("B", "Fazit/Zusammenfassung am Ende", 2, "Abschnitt „Fazit“, „Zusammenfassung“, „Ausblick“ o. ä."),
    "b_uebergaenge": ("B", "Übergänge/Zusammenhang", 2, "≥ 25 % der Absätze knüpfen mit Verbindungs- oder Bezugswort an"),
    "c_hierarchie": ("C", "Überschriftenhierarchie H2/H3", 3, "≥ 2 H2, kein H1 im Text, kein Sprung (H2→H4), kein H3 vor dem ersten H2"),
    "c_abschnitte": ("C", "Abschnittslängen", 3, "Kein Abschnitt (zwischen H2/H3) über 450 Wörter"),
    "c_listen": ("C", "Listen/Tabellen", 2, "Mindestens eine Liste oder Tabelle"),
    "c_zusammenfassung": ("C", "Zusammenfassung oben", 3, "Frontmatter-Feld summary (Zusammenfassungs-Box) vorhanden"),
    "c_laenge": ("C", "Länge angemessen", 2, "600–2500 Wörter Fliesstext"),
    "c_textwueste": ("C", "Keine Textwüste", 2, "Höchstens 350 Wörter am Stück ohne Überschrift, Liste oder Grafik"),
    "d_dichte": ("D", "Dichte visueller Elemente", 4, "≤ 350 Wörter je visuellem Element (Bild, Grafik, Tabelle, Code, Box, Video)"),
    "d_abstand": ("D", "Größter Abstand zwischen Grafiken", 4, "Spätestens alle ~450 Wörter ein visuelles Element"),
    "d_alt": ("D", "Alt-Texte", 3, "Jedes Bild hat einen Alt-Text (Videos/Grafiken: aria-label)"),
    "d_gewicht": ("D", "Bildgewichte", 2, "Bilder ≤ 500 KB, GIF-Animationen ≤ 3 MB"),
    "d_poster": ("D", "Videos mit Poster", 2, "Jedes <video> hat ein poster-Bild"),
    "e_fokus": ("E", "Schlüsselbegriffe in Titel/Beschreibung", 4, "≥ 50 % der Tags stehen in Titel oder Beschreibung"),
    "e_fokus_h2": ("E", "Schlüsselbegriffe in Zwischenüberschriften", 2, "Mindestens ein Tag in einer H2"),
    "e_tags": ("E", "Tags", 2, "3–6 Tags"),
    "e_intern": ("E", "Interne Links", 3, "Mindestens ein Link auf einen anderen Blog-Artikel"),
    "e_extern": ("E", "Externe Links/Quellen", 2, "Mindestens zwei externe Links"),
    "e_aktuell": ("E", "Aktualität", 3, "updated jünger als 90 Tage"),
    "e_historie": ("E", "Änderungshistorie", 2, "Frontmatter-Feld changelog vorhanden"),
    "e_slug": ("E", "Slug", 2, "Kleinbuchstaben/Ziffern/Bindestriche, ≤ 60 Zeichen"),
}


def ampel(score: float) -> str:
    if score >= 80:
        return "gruen"
    if score >= 60:
        return "gelb"
    return "rot"


def linear(wert: float, gut: float, schlecht: float) -> float:
    """100 bei `gut` (oder besser), 0 bei `schlecht` (oder schlechter),
    dazwischen linear. Funktioniert in beide Richtungen."""
    if gut == schlecht:
        return 100.0 if wert == gut else 0.0
    anteil = (wert - schlecht) / (gut - schlecht)
    return round(max(0.0, min(1.0, anteil)) * 100, 1)


def band(wert: float, lo: float, hi: float, lo0: float, hi0: float) -> float:
    """100 im Bereich [lo, hi], linear auf 0 bis lo0 bzw. hi0."""
    if lo <= wert <= hi:
        return 100.0
    if wert < lo:
        return linear(wert, lo, lo0)
    return linear(wert, hi, hi0)


# --------------------------------------------------------------------------
# Text- und Sprachwerkzeuge (Deutsch)
# --------------------------------------------------------------------------

_ABKUERZUNGEN = [
    "z. B.", "z.B.", "d. h.", "d.h.", "u. a.", "u.a.", "z. T.", "u. U.", "v. a.", "i. d. R.", "o. ä.",
    "bzw.", "ca.", "etc.", "usw.", "vgl.", "Nr.", "Dr.", "inkl.", "ggf.", "evtl.", "bspw.", "Abs.",
    "Mio.", "Mrd.", "Std.", "Min.", "zzgl.", "ggü.", "sog.", "max.", "min.", "Jan.", "Feb.", "Apr.",
    "Aug.", "Sep.", "Sept.", "Okt.", "Nov.", "Dez.", "Prof.", "St.", "Co.", "u.ä.",
]
_PLATZHALTER = "․"
_SATZENDE = re.compile(r"(?<=[.!?…])[\"“”»)]*\s+(?=[„\"«(\[A-ZÄÖÜ0-9])")
_WORT = re.compile(r"[A-Za-zÄÖÜäöüßÀ-ÿ0-9]+(?:[-'’][A-Za-zÄÖÜäöüßÀ-ÿ0-9]+)*")
_VOKALGRUPPE = re.compile(r"[aeiouyäöü]+")
_EIN_LAUT = {"ei", "ie", "au", "eu", "äu", "ai", "aa", "ee", "oo", "ey", "ay", "oi"}

FUELLWOERTER = {
    "eigentlich", "eben", "halt", "quasi", "sozusagen", "wirklich", "einfach", "natürlich",
    "ziemlich", "durchaus", "irgendwie", "gewissermaßen", "letztendlich", "schlussendlich",
    "tatsächlich", "wohl", "mal", "total", "absolut", "völlig", "echt", "relativ", "praktisch",
    "regelrecht", "überaus", "ungemein", "gänzlich", "selbstverständlich", "offensichtlich",
    "zweifellos", "bestimmt", "jedenfalls", "sicherlich", "vielleicht", "gerade", "schlichtweg",
}

STOPPWOERTER = {
    "aber", "alle", "allem", "allen", "aller", "alles", "also", "andere", "anderen", "auch", "auf",
    "aus", "bei", "beim", "bereits", "bevor", "beiden", "bis", "bitte", "damit", "dann", "darauf",
    "daran", "darin", "darum", "dass", "dabei", "dafür", "dadurch", "davon", "dazu", "dein", "deine",
    "dem", "den", "denn", "der", "deren", "des", "dessen", "die", "dies", "diese", "diesem", "diesen",
    "dieser", "dieses", "doch", "dort", "durch", "eine", "einem", "einen", "einer", "eines", "einmal",
    "etwas", "euch", "für", "gegen", "geht", "gibt", "habe", "haben", "hatte", "hätte", "hier",
    "hinter", "ihre", "ihrem", "ihren", "ihrer", "immer", "jede", "jedem", "jeden", "jeder", "jedes",
    "jetzt", "kann", "kein", "keine", "keinen", "können", "könnte", "machen", "macht", "mehr",
    "mein", "meine", "meinem", "meinen", "meiner", "mich", "muss", "müssen", "nach", "neben", "nicht",
    "nichts", "noch", "nur", "oben", "oder", "ohne", "schon", "sehr", "sein", "seine", "seinem",
    "seinen", "seiner", "selbst", "sich", "sind", "soll", "sollte", "sondern", "statt", "über",
    "unter", "unsere", "viel", "viele", "vom", "von", "vor", "während", "wann", "warum", "weil",
    "weiter", "welche", "wenn", "werden", "wieder", "wird", "wurde", "wurden", "würde", "zum", "zur",
    "zwei", "drei", "vier", "fünf", "zwischen", "erst", "ersten", "eigene", "eigenen", "einen",
    "ganz", "gleich", "genau", "dafür", "sowie", "beide", "kommt", "steht", "stehen", "wird",
    "wenig", "weniger", "heute", "seit", "unten", "darf", "lässt", "liegt", "welcher", "welches",
    "wieso", "worden", "zudem", "außer", "wäre", "waren", "einfach", "solche", "solchen",
}

UEBERGANGSWOERTER = {
    "dabei", "deshalb", "daher", "darum", "deswegen", "außerdem", "zudem", "ebenso", "damit", "so",
    "denn", "trotzdem", "dennoch", "doch", "aber", "allerdings", "jedoch", "danach", "anschließend",
    "zunächst", "zuerst", "dann", "schließlich", "zuletzt", "erstens", "zweitens", "drittens",
    "gleichzeitig", "stattdessen", "dafür", "dazu", "hier", "dort", "das", "dies", "diese", "dieser",
    "dieses", "diesen", "genau", "kurz", "also", "folglich", "somit", "umgekehrt", "hinzu", "nebenbei",
    "übrigens", "vorher", "seither", "seitdem", "inzwischen", "mittlerweile", "sobald", "nachdem",
    "ebenfalls", "entsprechend", "insgesamt", "letztlich", "auch", "erst", "jetzt", "nun", "dagegen",
    "hingegen", "darauf", "daraus", "davon", "dahinter", "darüber", "wichtig", "ergebnis", "fazit",
    "zum", "im", "unterm", "praktisch", "konkret", "zusätzlich", "parallel", "später", "vorab",
}

_FLOSKELN = (
    "in diesem artikel", "dieser artikel", "in diesem beitrag", "dieser beitrag", "hier erfahren sie",
    "heute geht es", "heute zeige ich", "willkommen", "ein überblick", "alles über", "alles was sie",
    "in diesem blog", "lesen sie", "erfahren sie hier", "ich möchte ihnen",
)
_HAKEN_SIGNALE = re.compile(
    r"(\d|\?|:|–|—|--|\bohne\b|\bstatt\b|\bkostenlos|\bgratis\b|\bspart\b|\bsparen\b|\bschnell|"
    r"\bfehlt|\bproblem|\bfehler|\bwarum\b|\bwie\b|\bso\b|\bgenügt\b|\breicht\b|\bjetzt\b|\bnie\b|"
    r"\bkeine?n?\b|\bsie\b|\bihr(e|en)?\b|\bdu\b|\bmein\b|\bich\b)",
    re.I,
)


def woerter(text: str) -> list[str]:
    return _WORT.findall(text)


def silben(wort: str) -> int:
    """Silbenschaetzung fuer deutsche Woerter ueber Vokalgruppen.
    Diphthonge (ei, au, eu, ie ...) zaehlen als eine Silbe, andere
    Zweiergruppen (Hiatus wie in „Station“, „aktuell“) als zwei. Keine
    Silbentrennung im Wortsinn - fuer Lesbarkeitsindizes genuegt die
    Schaetzung (Fehler mitteln sich ueber viele Woerter aus)."""
    w = wort.lower()
    if w.isdigit():
        return max(1, min(len(w), 3))
    n = 0
    for g in _VOKALGRUPPE.findall(w):
        if len(g) == 1 or g in _EIN_LAUT:
            n += 1
        elif len(g) == 2:
            n += 2
        else:
            n += 2 if len(g) == 3 else len(g) - 1
    return max(1, n)


def saetze(text: str) -> list[str]:
    t = text
    for abk in _ABKUERZUNGEN:
        t = t.replace(abk, abk.replace(".", _PLATZHALTER))
    # Initialen/Einzelbuchstaben wie „A. Brauckmann“
    t = re.sub(r"\b([A-ZÄÖÜ])\.(?=\s)", lambda m: m.group(1) + _PLATZHALTER, t)
    teile = _SATZENDE.split(t)
    return [s.replace(_PLATZHALTER, ".").strip() for s in teile if woerter(s)]


def amstad(text_bloecke: list[str]) -> dict:
    """Flesch-Lesbarkeitsindex fuer Deutsch nach Amstad (1978):
    FRE = 180 − ASL − 58,5 × ASW
    ASL = mittlere Satzlaenge in Woertern, ASW = mittlere Silben je Wort."""
    alle_saetze = [s for b in text_bloecke for s in saetze(b)]
    alle_woerter = [w for s in alle_saetze for w in woerter(s)]
    if not alle_saetze or not alle_woerter:
        return {"index": 0.0, "asl": 0.0, "asw": 0.0, "saetze": 0, "woerter": 0}
    asl = len(alle_woerter) / len(alle_saetze)
    asw = sum(silben(w) for w in alle_woerter) / len(alle_woerter)
    return {
        "index": round(180 - asl - 58.5 * asw, 1),
        "asl": round(asl, 1),
        "asw": round(asw, 2),
        "saetze": len(alle_saetze),
        "woerter": len(alle_woerter),
    }


def nahwiederholungen(text: str, fenster: int = 15, ausnahmen: set[str] | None = None) -> tuple[int, dict]:
    """Zaehlt, wie oft ein Inhaltswort (≥ 5 Buchstaben, kein Stoppwort)
    innerhalb der naechsten `fenster` Woerter erneut auftaucht. Woerter aus
    `ausnahmen` (Themenbegriffe aus Titel und Tags) zaehlen nicht - das
    Thema eines Artikels darf und muss oft vorkommen."""
    ausnahmen = ausnahmen or set()
    ws = [w.lower() for w in woerter(text)]
    treffer = 0
    zaehler: dict[str, int] = {}
    letzte: dict[str, int] = {}
    for i, w in enumerate(ws):
        if len(w) < 5 or w in STOPPWOERTER or w.isdigit() or w in ausnahmen:
            continue
        if w in letzte and i - letzte[w] <= fenster:
            treffer += 1
            zaehler[w] = zaehler.get(w, 0) + 1
        letzte[w] = i
    return treffer, dict(sorted(zaehler.items(), key=lambda kv: -kv[1])[:6])


def haken_in(text: str) -> tuple[bool, str]:
    """Heuristik: beginnt der Text mit Problem/Nutzen statt einer Floskel?"""
    vorn = text[:100].lower()
    for f in _FLOSKELN:
        if vorn.startswith(f) or vorn.startswith("„" + f):
            return False, f"beginnt mit der Floskel „{f}“"
    if _HAKEN_SIGNALE.search(text[:100]):
        return True, "konkretes Signal (Zahl, Frage, Gegensatz, Nutzen oder direkte Ansprache) vorn"
    return False, "kein konkretes Problem-/Nutzensignal in den ersten 100 Zeichen"


# --------------------------------------------------------------------------
# Bildmasse aus dem Dateikopf (PNG, GIF, JPEG, WebP) - ohne Pillow
# --------------------------------------------------------------------------


def bildmasse(pfad) -> tuple[int, int] | None:
    """Breite/Hoehe aus dem Dateikopf; `pfad` ist ein Pfad oder die Bytes der Datei."""
    import io
    try:
        with (io.BytesIO(pfad) if isinstance(pfad, (bytes, bytearray)) else open(pfad, "rb")) as f:
            kopf = f.read(32)
            if kopf.startswith(b"\x89PNG\r\n\x1a\n") and kopf[12:16] == b"IHDR":
                return struct.unpack(">II", kopf[16:24])
            if kopf[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", kopf[6:10])
            if kopf[:4] == b"RIFF" and kopf[8:12] == b"WEBP":
                f.seek(12)
                chunk = f.read(30)
                art = chunk[:4]
                if art == b"VP8X":
                    b = chunk[12:18]
                    return (1 + int.from_bytes(b[0:3], "little"), 1 + int.from_bytes(b[3:6], "little"))
                if art == b"VP8 ":
                    w, h = struct.unpack("<HH", chunk[18:22])
                    return (w & 0x3FFF, h & 0x3FFF)
                if art == b"VP8L":
                    b = chunk[9:13]
                    bits = int.from_bytes(b, "little")
                    return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
                return None
            if kopf[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    while marker[1] == 0xFF:
                        marker = marker[:1] + f.read(1)
                    typ = marker[1]
                    if typ in (0xD8, 0x01) or 0xD0 <= typ <= 0xD7:
                        continue
                    laenge = struct.unpack(">H", f.read(2))[0]
                    if typ in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        daten = f.read(5)
                        h, w = struct.unpack(">HH", daten[1:5])
                        return (w, h)
                    f.seek(laenge - 2, 1)
    except (OSError, struct.error):
        return None
    return None


# --------------------------------------------------------------------------
# HTML des Artikels zerlegen: Fliesstext, Ueberschriften, visuelle Elemente
# --------------------------------------------------------------------------

_IGNORIEREN = {"script", "style", "noscript", "template", "head"}
_CONTAINER = {"figure": "Grafik", "table": "Tabelle", "pre": "Codeblock", "video": "Video",
              "iframe": "Einbettung", "svg": "Grafik", "canvas": "Grafik", "audio": "Audio"}
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "blockquote"}
_BOX_KLASSEN = re.compile(r"\b(callout|admonition|box|hinweis|kr-hervor|note|tipp|warnung)\b")


class _Zerleger(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ereignisse: list[tuple] = []  # ("text", art, text) | ("visuell", art, attrs) | ("h", level, text) | ("liste",)
        self.bilder: list[dict] = []
        self.videos: list[dict] = []
        self.grafiken_ohne_label: list[str] = []
        self.links: list[str] = []
        self._ign_tag = None
        self._ign_tiefe = 0
        self._con_tag = None
        self._con_tiefe = 0
        self._puffer: list[str] = []
        self._block_art = "p"
        self._listen_tiefe = 0

    # -- Hilfen
    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._puffer)).strip()
        self._puffer = []
        if not text:
            return
        if self._block_art.startswith("h") and self._block_art[1:].isdigit():
            self.ereignisse.append(("h", int(self._block_art[1:]), text))
        else:
            self.ereignisse.append(("text", self._block_art, text))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._ign_tag:
            if tag == self._ign_tag:
                self._ign_tiefe += 1
            return
        if tag in _IGNORIEREN:
            self._ign_tag, self._ign_tiefe = tag, 1
            return
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "img":
            self.bilder.append({"src": a.get("src", ""), "alt": (a.get("alt") or "").strip()})
            if not self._con_tag:
                self._flush()
                self.ereignisse.append(("visuell", "Bild", a))
            return
        if self._con_tag:
            if tag == self._con_tag:
                self._con_tiefe += 1
            if tag == "video":
                self.videos.append({"poster": a.get("poster", ""), "label": a.get("aria-label", "")})
            return
        if tag in _CONTAINER:
            # Pygments-Codeblock: <div class="codehilite"><pre> - das pre zaehlt
            self._flush()
            art = _CONTAINER[tag]
            if tag == "video":
                self.videos.append({"poster": a.get("poster", ""), "label": a.get("aria-label", "")})
            if tag in ("svg", "canvas") and not (a.get("aria-label") or a.get("role") == "img"):
                if a.get("aria-hidden") != "true":
                    self.grafiken_ohne_label.append(tag)
            self.ereignisse.append(("visuell", art, a))
            self._con_tag, self._con_tiefe = tag, 1
            return
        if tag in ("ul", "ol"):
            self._flush()
            if self._listen_tiefe == 0:
                self.ereignisse.append(("liste",))
            self._listen_tiefe += 1
            return
        klasse = a.get("class", "")
        if tag in ("div", "p", "aside", "blockquote") and (tag == "blockquote" or _BOX_KLASSEN.search(klasse)):
            self._flush()
            self.ereignisse.append(("visuell", "Box", a))
        if tag in _BLOCK:
            self._flush()
            self._block_art = "li" if tag == "li" else tag if tag.startswith("h") else "p"
        elif tag in ("div", "section", "br", "hr"):
            self._flush()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("video", "svg", "canvas", "iframe") and self._con_tag == tag:
            self._con_tag, self._con_tiefe = None, 0

    def handle_endtag(self, tag):
        if self._ign_tag:
            if tag == self._ign_tag:
                self._ign_tiefe -= 1
                if self._ign_tiefe == 0:
                    self._ign_tag = None
            return
        if self._con_tag:
            if tag == self._con_tag:
                self._con_tiefe -= 1
                if self._con_tiefe == 0:
                    self._con_tag = None
            return
        if tag in ("ul", "ol"):
            self._flush()
            self._listen_tiefe = max(0, self._listen_tiefe - 1)
            return
        if tag in _BLOCK or tag in ("div", "section", "aside"):
            self._flush()
            self._block_art = "li" if self._listen_tiefe else "p"

    def handle_data(self, data):
        if self._ign_tag or self._con_tag:
            return
        self._puffer.append(data)

    def close(self):
        super().close()
        self._flush()


def zerlege_html(html_text: str) -> _Zerleger:
    z = _Zerleger()
    z.feed(html_text)
    z.close()
    return z


# --------------------------------------------------------------------------
# Ergebnisstrukturen
# --------------------------------------------------------------------------


@dataclass
class Kriterium:
    id: str
    kategorie: str
    name: str
    punkte: float
    soll: str
    erfuellung: float | None  # 0-100, None = trifft nicht zu
    messwert: str
    vorschlag: str = ""

    @property
    def status(self) -> str:
        if self.erfuellung is None:
            return "na"
        if self.erfuellung >= 75:
            return "ok"
        if self.erfuellung >= 40:
            return "teils"
        return "nein"


@dataclass
class Bewertung:
    slug: str
    titel: str
    kriterien: list[Kriterium]
    kennzahlen: dict = field(default_factory=dict)
    vorschau_urteil: dict = field(default_factory=dict)

    def kategorie_score(self, kat: str) -> float:
        ks = [k for k in self.kriterien if k.kategorie == kat and k.erfuellung is not None]
        summe = sum(k.punkte for k in ks)
        if not summe:
            return 0.0
        return round(sum(k.punkte * k.erfuellung for k in ks) / summe, 1)

    @property
    def gesamt(self) -> float:
        return round(sum(KATEGORIEN[k]["gewicht"] * self.kategorie_score(k) / 100 for k in KATEGORIEN), 1)

    @property
    def ampel(self) -> str:
        return ampel(self.gesamt)

    def kriterium(self, kid: str) -> Kriterium | None:
        return next((k for k in self.kriterien if k.id == kid), None)

    def pflicht_ok(self) -> bool:
        k = self.kriterium("a_pflicht")
        return bool(k and k.erfuellung == 100)


def _k(kid: str, erfuellung, messwert: str, vorschlag: str = "") -> Kriterium:
    kat, name, punkte, soll = KRITERIEN[kid]
    if erfuellung is not None and erfuellung >= 75:
        vorschlag = ""
    return Kriterium(kid, kat, name, punkte, soll, erfuellung, messwert, vorschlag)


# --------------------------------------------------------------------------
# Kopf der fertigen Seite in dist/ pruefen
# --------------------------------------------------------------------------

PFLICHT_META = (
    ("title/og:title", re.compile(r'<meta name="title" property="og:title" content="([^"]+)">')),
    ("og:type", re.compile(r'<meta property="og:type" content="([^"]+)">')),
    ("image/og:image", re.compile(r'<meta name="image" property="og:image" content="([^"]+)">')),
    ("description/og:description", re.compile(r'<meta name="description" property="og:description" content="([^"]+)">')),
    ("author", re.compile(r'<meta name="author" content="([^"]+)">')),
)
_JSONLD = re.compile(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S)


def pruefe_kopf(kopf: str) -> dict:
    """Liest die relevanten Angaben aus dem <head> einer fertigen Seite."""
    erg = {"pflicht": {}, "fehlend": []}
    for name, muster in PFLICHT_META:
        m = muster.search(kopf)
        erg["pflicht"][name] = html_mod.unescape(m.group(1)) if m else None
        if not m:
            erg["fehlend"].append(name)
    m = re.search(r'<meta property="og:image:alt" content="([^"]*)">', kopf)
    erg["og_image_alt"] = html_mod.unescape(m.group(1)) if m else None
    m = re.search(r'<link rel="canonical" href="([^"]+)">', kopf)
    erg["canonical"] = m.group(1) if m else None
    m = _JSONLD.search(kopf)
    erg["jsonld"] = None
    erg["jsonld_fehler"] = None
    if m:
        try:
            erg["jsonld"] = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            erg["jsonld_fehler"] = str(exc)
    else:
        erg["jsonld_fehler"] = "kein JSON-LD-Block"
    return erg


# --------------------------------------------------------------------------
# Hauptfunktion
# --------------------------------------------------------------------------


def _fmt(x: float, nachkomma: int = 0) -> str:
    s = f"{x:.{nachkomma}f}"
    return s.replace(".", ",")


def _datum(wert) -> date | None:
    if isinstance(wert, date):
        return wert
    try:
        return date.fromisoformat(str(wert)[:10])
    except ValueError:
        return None


def bewerte(meta: dict, body_html: str, *, base_url: str, static_dir: Path, dist_dir: Path,
            heute: date, alle_slugs: list[str] | None = None) -> Bewertung:
    """Bewertet einen Artikel. `meta` ist das Frontmatter (wie parse_article),
    `body_html` der gerenderte Artikelkoerper (ohne Seitenrahmen)."""
    slug = meta["slug"]
    titel = str(meta.get("title", ""))
    beschr = str(meta.get("description", ""))
    tags = [str(t) for t in meta.get("tags", []) or []]
    kriterien: list[Kriterium] = []
    kz: dict = {}

    z = zerlege_html(body_html)
    ereignisse = list(z.ereignisse)
    if meta.get("image"):
        # Eyecatcher steht im Template vor dem Inhalt
        ereignisse.insert(0, ("visuell", "Titelbild", {"src": meta["image"]}))
        z.bilder.insert(0, {"src": meta["image"], "alt": titel})

    absaetze = [e[2] for e in ereignisse if e[0] == "text" and e[1] == "p"]
    prosa = [e[2] for e in ereignisse if e[0] == "text"]
    ueberschriften = [(e[1], e[2]) for e in ereignisse if e[0] == "h"]
    prosa_woerter = sum(len(woerter(t)) for t in prosa)
    kz["woerter"] = prosa_woerter

    # ---------------- A: Vorschau/Meta ----------------
    tl = len(titel)
    kriterien.append(_k("a_titel", band(tl, 40, 70, 15, 110), f"{tl} Zeichen",
                        "Titel auf 40–70 Zeichen bringen: Kernaussage und Schlüsselbegriff nach vorn, Details in die Beschreibung." if tl > 70
                        else "Titel ausbauen (mindestens 40 Zeichen): konkreter Nutzen oder Ergebnis nennen."))
    bl = len(beschr)
    kriterien.append(_k("a_beschr", band(bl, 120, 160, 50, 260), f"{bl} Zeichen",
                        "Beschreibung auf 120–160 Zeichen kürzen; was danach kommt, schneiden Google und LinkedIn ab." if bl > 160
                        else "Beschreibung auf 120–160 Zeichen ausbauen: Problem, Lösung, Nutzen."))
    hat_haken, grund = haken_in(beschr)
    kriterien.append(_k("a_hook", 100.0 if hat_haken else 20.0, ("ja – " if hat_haken else "nein – ") + grund,
                        "Beschreibung mit dem Problem oder dem Nutzen beginnen (Zahl, Gegensatz, konkrete Folge), keine Einleitungsfloskel."))

    og_bild = meta.get("og_image") or meta.get("image") or meta.get("thumb")
    kz["og_bild"] = og_bild
    kz["og_bild_masse"] = None
    if not og_bild:
        kriterien.append(_k("a_bild", 0.0, "kein Bild im Frontmatter", "og_image (1200×630 JPG/PNG) im Frontmatter setzen."))
    else:
        pfad = static_dir.parent / og_bild.lstrip("/")
        if not pfad.exists():
            kriterien.append(_k("a_bild", 0.0, f"Datei fehlt: {og_bild}", "Bilddatei unter static/ ablegen oder Pfad korrigieren."))
        elif pfad.suffix.lower() == ".svg":
            kriterien.append(_k("a_bild", 10.0, "SVG – von LinkedIn/Facebook nicht unterstützt", "Als JPG/PNG 1200×630 exportieren und als og_image setzen."))
        else:
            groesse = pfad.stat().st_size
            masse = bildmasse(pfad)
            kz["og_bild_masse"] = masse
            kz["og_bild_kb"] = round(groesse / 1024)
            teile, notizen = [], []
            if masse:
                w, h = masse
                verh = w / h if h else 0
                teile.append(linear(abs(verh - 1.91), 0.08, 0.9))
                teile.append(linear(w, 1200, 400))
                messung = f"{w}×{h} px, Verhältnis {_fmt(verh, 2)}:1, {round(groesse / 1024)} KB"
                if abs(verh - 1.91) > 0.08:
                    notizen.append("Verhältnis weicht von 1,91:1 ab – LinkedIn beschneidet das Bild in der Karte")
                if w < 1200:
                    notizen.append("unter 1200 px Breite – wirkt auf großen Bildschirmen unscharf")
            else:
                teile += [50.0, 50.0]
                messung = f"Maße nicht lesbar, {round(groesse / 1024)} KB"
            teile.append(100.0 if groesse <= 5 * 1024 * 1024 else 0.0)
            if groesse > 5 * 1024 * 1024:
                notizen.append("über 5 MB – LinkedIn lädt es nicht")
            quelle = "og_image" if meta.get("og_image") else ("image" if meta.get("image") else "thumb")
            kriterien.append(_k("a_bild", round(sum(teile) / len(teile), 1), f"{messung} ({quelle})",
                                "Eigenes Vorschaubild 1200×630 px als og_image anlegen" + (": " + "; ".join(notizen) if notizen else "") + "."))

    # dist/ pruefen
    dist_seite = dist_dir / "artikel" / slug / "index.html"
    kopf_info = None
    if dist_seite.exists():
        seite = dist_seite.read_text(encoding="utf-8")
        kopf_info = pruefe_kopf(seite[: seite.find("</head>")])
    kz["dist"] = bool(kopf_info)
    kz["kopf"] = kopf_info

    if kopf_info is None:
        for kid in ("a_alt", "a_autor", "a_canonical", "a_jsonld", "a_pflicht", "a_dist"):
            kriterien.append(_k(kid, 0.0, "dist/-Seite fehlt", "Blog bauen (scripts/build.py), dann erneut prüfen."))
    else:
        alt = kopf_info["og_image_alt"]
        if alt:
            kriterien.append(_k("a_alt", 100.0 if len(alt) >= 20 else 60.0, f"{len(alt)} Zeichen: „{alt[:80]}{'…' if len(alt) > 80 else ''}“",
                                "Alt-Text konkreter formulieren (was ist zu sehen, ≥ 20 Zeichen)."))
        else:
            kriterien.append(_k("a_alt", 0.0, "fehlt",
                                "og_image (1200×630) und og_image_alt im Frontmatter setzen – build.py gibt og:image:alt nur zusammen mit og_image aus."))
        autor = kopf_info["pflicht"].get("author")
        kriterien.append(_k("a_autor", 100.0 if autor else 0.0, autor or "fehlt", "site.author in config.yaml setzen."))
        soll_url = f"{base_url}/artikel/{slug}/"
        can = kopf_info["canonical"]
        kriterien.append(_k("a_canonical", 100.0 if can == soll_url else 0.0, can or "fehlt",
                            f"Canonical auf {soll_url} setzen (Template article.html)."))
        ld = kopf_info["jsonld"]
        if ld is None:
            kriterien.append(_k("a_jsonld", 0.0, kopf_info["jsonld_fehler"] or "fehlt", "JSON-LD reparieren (build_jsonld)."))
        else:
            noetig = ["headline", "description", "image", "datePublished", "author"]
            fehlt = [f for f in noetig if not ld.get(f)]
            typ_ok = ld.get("@type") in ("Article", "BlogPosting", "TechArticle")
            erf = 100.0 if (not fehlt and typ_ok) else max(0.0, 100 - 25 * len(fehlt) - (40 if not typ_ok else 0))
            kriterien.append(_k("a_jsonld", erf, "gültig, vollständig" if erf == 100 else f"fehlt: {', '.join(fehlt) or '@type'}",
                                "Fehlende JSON-LD-Felder über das Frontmatter ergänzen (Bild: og_image/image/thumb)."))
        fehlend = kopf_info["fehlend"]
        kriterien.append(_k("a_pflicht", 100.0 if not fehlend else 0.0, "alle 5 vorhanden" if not fehlend else f"fehlt: {', '.join(fehlend)}",
                            "Frontmatter prüfen (title, description, image/thumb) und neu bauen – siehe CLAUDE.md."))
        dist_titel = kopf_info["pflicht"].get("title/og:title")
        dist_beschr = kopf_info["pflicht"].get("description/og:description")
        abw = []
        if dist_titel != titel:
            abw.append("Titel")
        if dist_beschr != beschr:
            abw.append("Beschreibung")
        kriterien.append(_k("a_dist", 100.0 if not abw else 0.0, "aktuell" if not abw else f"veraltet: {', '.join(abw)}",
                            "Blog neu bauen und deployen, danach Post Inspector ausführen."))

    # Vorschau-Urteil
    probleme = [k for k in kriterien if k.id in ("a_titel", "a_beschr", "a_hook", "a_bild", "a_alt", "a_pflicht") and k.status != "ok"]
    schwer = [k for k in probleme if k.id in ("a_bild", "a_pflicht", "a_hook") and k.status == "nein"]
    if not probleme:
        urteil, text = "ja", "Titel, Beschreibung, Haken und Vorschaubild erfüllen die Kriterien."
    elif schwer or len(probleme) >= 3:
        urteil, text = "nein", "Schwächen: " + "; ".join(f"{k.name} ({k.messwert})" for k in probleme) + "."
    else:
        urteil, text = "eingeschraenkt", "Gut, aber: " + "; ".join(f"{k.name} ({k.messwert})" for k in probleme) + "."
    vorschau_urteil = {"urteil": urteil, "begruendung": text}

    # ---------------- B: Lesbarkeit & Fluss ----------------
    lb = amstad(prosa)
    kz["amstad"] = lb
    kriterien.append(_k("b_amstad", linear(lb["index"], 50, 20), f"{_fmt(lb['index'], 1)} (Ø {_fmt(lb['asw'], 2)} Silben/Wort)",
                        "Kürzere Sätze und kürzere Wörter: Komposita auflösen („Infrastruktur-Überwachungsdienst“ → „Dienst, der die Infrastruktur überwacht“)."))
    kriterien.append(_k("b_satzlaenge", linear(lb["asl"], 17, 28), f"{_fmt(lb['asl'], 1)} Wörter",
                        "Lange Sätze am Komma oder Gedankenstrich teilen; je Satz ein Gedanke."))
    alle_s = [s for t in prosa for s in saetze(t)]
    lang = [s for s in alle_s if len(woerter(s)) > 25]
    anteil_lang = 100 * len(lang) / len(alle_s) if alle_s else 0
    beispiel = ""
    if lang:
        l0 = max(lang, key=lambda s: len(woerter(s)))
        beispiel = f" Längster Satz ({len(woerter(l0))} Wörter): „{l0[:120]}…“"
    kz["lange_saetze"] = [s[:160] for s in sorted(lang, key=lambda s: -len(woerter(s)))[:3]]
    kriterien.append(_k("b_lange_saetze", linear(anteil_lang, 10, 35), f"{_fmt(anteil_lang, 0)} % ({len(lang)} von {len(alle_s)})",
                        "Sätze über 25 Wörter teilen." + beispiel))
    alen = [len(woerter(a)) for a in absaetze]
    lange_abs = [n for n in alen if n > 100]
    anteil_la = 100 * len(lange_abs) / len(alen) if alen else 0
    kriterien.append(_k("b_absaetze", linear(anteil_la, 10, 40),
                        f"{len(lange_abs)} von {len(alen)} Absätzen > 100 Wörter, längster {max(alen) if alen else 0}",
                        "Absätze über 100 Wörter teilen; ein Absatz = ein Gedanke, gern mit einem fetten Kernsatz vorn."))
    voll = " ".join(prosa)
    themen = {w.lower() for w in woerter(titel + " " + " ".join(tags))}
    wdh, top = nahwiederholungen(voll, ausnahmen=themen)
    rate = 1000 * wdh / prosa_woerter if prosa_woerter else 0
    kriterien.append(_k("b_wiederholung", linear(rate, 6, 20), f"{_fmt(rate, 1)} je 1000 Wörter" + (f" (häufig: {', '.join(list(top)[:4])})" if top else ""),
                        "Wiederholte Begriffe durch Pronomen, Synonyme oder Umstellung ersetzen" + (f": {', '.join(list(top)[:4])}" if top else "") + "."))
    alle_w = [w.lower() for w in woerter(voll)]
    fuell = [w for w in alle_w if w in FUELLWOERTER]
    anteil_f = 100 * len(fuell) / len(alle_w) if alle_w else 0
    haeufig_f = sorted({w: fuell.count(w) for w in set(fuell)}.items(), key=lambda kv: -kv[1])[:5]
    kriterien.append(_k("b_fuellwoerter", linear(anteil_f, 1.0, 3.0), f"{_fmt(anteil_f, 1)} % ({len(fuell)})" + (f": {', '.join(f'{w} {n}×' for w, n in haeufig_f)}" if haeufig_f else ""),
                        "Füllwörter streichen (" + ", ".join(w for w, _ in haeufig_f) + ")." if haeufig_f else ""))
    # Einleitung
    erster = next((t for t in absaetze if len(woerter(t)) >= 5), "")
    s1 = saetze(erster)[0] if erster and saetze(erster) else ""
    n1 = len(woerter(s1))
    sig = bool(_HAKEN_SIGNALE.search(s1))
    erf_e = (60 if n1 and n1 <= 25 else 20 if n1 <= 35 else 0) + (40 if sig else 0)
    kriterien.append(_k("b_einleitung", float(erf_e) if s1 else 0.0, f"erster Satz {n1} Wörter{', mit konkretem Signal' if sig else ', ohne konkretes Signal'}: „{s1[:90]}{'…' if len(s1) > 90 else ''}“",
                        "Mit einem kurzen, konkreten Satz einsteigen: Problem, überraschende Zahl oder das Ergebnis vorweg."))
    fazit_muster = re.compile(r"\b(fazit|zusammenfassung|zum schluss|ausblick|was bleibt|kurz gesagt|takeaways?|unterm strich|schluss|resümee|in kürze)\b", re.I)
    fazit = [t for _l, t in ueberschriften if fazit_muster.search(t)]
    kriterien.append(_k("b_fazit", 100.0 if fazit else 0.0, f"„{fazit[0]}“" if fazit else "kein Fazit-Abschnitt gefunden",
                        "Abschnitt „Fazit“ mit 2–4 Sätzen ergänzen: Was hat der Leser jetzt, was ist der nächste Schritt?"))
    # Uebergaenge: Absaetze, die nicht direkt nach einer Ueberschrift stehen
    anknuepf, gesamt_ue = 0, 0
    vorher_h = True
    for e in ereignisse:
        if e[0] == "h":
            vorher_h = True
            continue
        if e[0] == "text" and e[1] == "p":
            if not vorher_h:
                gesamt_ue += 1
                erstes = (woerter(e[2]) or [""])[0].lower()
                if erstes in UEBERGANGSWOERTER:
                    anknuepf += 1
            vorher_h = False
    anteil_ue = 100 * anknuepf / gesamt_ue if gesamt_ue else 100
    kz["uebergaenge"] = round(anteil_ue)
    kriterien.append(_k("b_uebergaenge", linear(anteil_ue, 25, 5), f"{_fmt(anteil_ue, 0)} % ({anknuepf} von {gesamt_ue} Folgeabsätzen)",
                        "Absätze ausdrücklich verbinden („Deshalb …“, „Dabei …“, „Genau hier …“), damit der rote Faden sichtbar wird."))

    # ---------------- C: Struktur ----------------
    ebenen = [l for l, _t in ueberschriften]
    probleme_h = []
    if ebenen.count(2) < 2:
        probleme_h.append(f"nur {ebenen.count(2)} H2")
    if 1 in ebenen:
        probleme_h.append("H1 im Text")
    if ebenen and ebenen[0] > 2:
        probleme_h.append(f"beginnt mit H{ebenen[0]}")
    for a, b in zip(ebenen, ebenen[1:]):
        if b > a + 1:
            probleme_h.append(f"Sprung H{a}→H{b}")
            break
    kriterien.append(_k("c_hierarchie", max(0.0, 100 - 35 * len(probleme_h)),
                        f"{ebenen.count(2)}× H2, {ebenen.count(3)}× H3" + (f"; {', '.join(probleme_h)}" if probleme_h else ""),
                        "Gliederung mit H2 für Hauptabschnitte, H3 nur darunter; keine Ebene überspringen."))
    abschnitte: list[tuple[str, int]] = []
    akt_name, akt_w = "(Anfang)", 0
    laengste_strecke, strecke = 0, 0
    for e in ereignisse:
        if e[0] == "h":
            abschnitte.append((akt_name, akt_w))
            akt_name, akt_w = e[2], 0
            laengste_strecke = max(laengste_strecke, strecke)
            strecke = 0
        elif e[0] == "text":
            n = len(woerter(e[2]))
            akt_w += n
            if e[1] == "p":
                strecke += n
            else:
                laengste_strecke = max(laengste_strecke, strecke)
                strecke = 0
        elif e[0] in ("visuell", "liste"):
            laengste_strecke = max(laengste_strecke, strecke)
            strecke = 0
    abschnitte.append((akt_name, akt_w))
    laengste_strecke = max(laengste_strecke, strecke)
    max_ab = max(abschnitte, key=lambda x: x[1]) if abschnitte else ("", 0)
    kriterien.append(_k("c_abschnitte", linear(max_ab[1], 450, 900), f"längster Abschnitt {max_ab[1]} Wörter („{max_ab[0][:50]}“)",
                        f"Abschnitt „{max_ab[0][:50]}“ mit H3-Zwischenüberschriften teilen."))
    n_listen = sum(1 for e in ereignisse if e[0] == "liste")
    n_tab = sum(1 for e in ereignisse if e[0] == "visuell" and e[1] == "Tabelle")
    kriterien.append(_k("c_listen", 100.0 if (n_listen + n_tab) else 0.0, f"{n_listen} Listen, {n_tab} Tabellen",
                        "Aufzählbares (Schritte, Voraussetzungen, Vergleiche) als Liste oder Tabelle setzen."))
    summ = str(meta.get("summary") or "")
    kriterien.append(_k("c_zusammenfassung", 100.0 if len(woerter(summ)) >= 25 else (50.0 if summ else 0.0),
                        f"{len(woerter(summ))} Wörter" if summ else "fehlt",
                        "summary im Frontmatter mit 3–5 Sätzen ergänzen (erscheint als Zusammenfassungs-Box oben)."))
    kriterien.append(_k("c_laenge", band(prosa_woerter, 600, 2500, 200, 4500), f"{prosa_woerter} Wörter Fliesstext",
                        "Artikel straffen oder in zwei Teile aufteilen (Teil II verlinken)." if prosa_woerter > 2500 else "Inhalt vertiefen: Beispiel, Ergebnis, Stolpersteine."))
    kriterien.append(_k("c_textwueste", linear(laengste_strecke, 350, 800), f"längste Strecke {laengste_strecke} Wörter",
                        "Lange Textstrecke mit Zwischenüberschrift, Liste, Grafik oder Box unterbrechen."))

    # ---------------- D: Grafiken/Auflockerung ----------------
    visuell = [e for e in ereignisse if e[0] == "visuell"]
    kz["visuell"] = {}
    for e in visuell:
        kz["visuell"][e[1]] = kz["visuell"].get(e[1], 0) + 1
    w_je_v = prosa_woerter / len(visuell) if visuell else prosa_woerter
    kriterien.append(_k("d_dichte", linear(w_je_v, 350, 900),
                        f"{len(visuell)} Elemente, {_fmt(w_je_v, 0)} Wörter je Element ({', '.join(f'{v}× {k}' for k, v in kz['visuell'].items()) or 'keine'})",
                        "Mehr visuelle Elemente: Schaubild, Screenshot, Tabelle oder Hinweis-Box an den dichtesten Stellen."))
    # groesster Abstand (Woerter) zwischen visuellen Elementen inkl. Anfang/Ende
    pos, abstaende, lauf = 0, [], 0
    start_w = 0
    for e in ereignisse:
        if e[0] == "text":
            lauf += len(woerter(e[2]))
        elif e[0] == "visuell":
            abstaende.append((lauf - start_w, start_w))
            start_w = lauf
    abstaende.append((lauf - start_w, start_w))
    groesst = max(abstaende, key=lambda x: x[0]) if abstaende else (prosa_woerter, 0)
    kz["groesster_abstand"] = groesst[0]
    kriterien.append(_k("d_abstand", linear(groesst[0], 450, 1100),
                        f"{groesst[0]} Wörter (ab Wort {groesst[1]})",
                        f"Zwischen Wort {groesst[1]} und {groesst[1] + groesst[0]} ein visuelles Element einfügen."))
    ohne_alt = [b["src"] for b in z.bilder if not b["alt"]]
    videos_ohne = [v for v in z.videos if not v["label"]]
    n_el = len(z.bilder) + len(z.videos) + len(z.grafiken_ohne_label)
    fehl = len(ohne_alt) + len(videos_ohne) + len(z.grafiken_ohne_label)
    if n_el == 0:
        kriterien.append(_k("d_alt", None, "keine Bilder"))
    else:
        kriterien.append(_k("d_alt", round(100 * (n_el - fehl) / n_el, 1), f"{n_el - fehl} von {n_el} mit Alt-Text/Label",
                            "Alt-Text ergänzen für: " + ", ".join(Path(s).name for s in ohne_alt[:4]) + (" (+ Videos/Grafiken ohne aria-label)" if videos_ohne or z.grafiken_ohne_label else "")))
    schwer_b = []
    gepr = 0
    for b in z.bilder:
        src = b["src"]
        if not src.startswith("/static/"):
            continue
        p = static_dir.parent / src.lstrip("/")
        if not p.exists():
            continue
        gepr += 1
        kb = p.stat().st_size / 1024
        grenze = 3072 if p.suffix.lower() == ".gif" else 500
        if kb > grenze:
            schwer_b.append(f"{p.name} ({round(kb)} KB)")
    if gepr == 0:
        kriterien.append(_k("d_gewicht", None, "keine lokalen Bilder"))
    else:
        kriterien.append(_k("d_gewicht", round(100 * (gepr - len(schwer_b)) / gepr, 1),
                            f"{gepr - len(schwer_b)} von {gepr} im Rahmen" + (f"; zu schwer: {', '.join(schwer_b[:3])}" if schwer_b else ""),
                            "Bilder verkleinern/komprimieren (PNG → WebP/JPG, Breite ≤ 1600 px): " + ", ".join(schwer_b[:3])))
    if not z.videos:
        kriterien.append(_k("d_poster", None, "keine Videos"))
    else:
        mit = sum(1 for v in z.videos if v["poster"])
        kriterien.append(_k("d_poster", round(100 * mit / len(z.videos), 1), f"{mit} von {len(z.videos)} mit Poster",
                            "poster=\"…\" für jedes Video setzen (Standbild, sonst schwarze Fläche bis zum Laden)."))

    # ---------------- E: SEO ----------------
    tl_low, bl_low = titel.lower(), beschr.lower()
    h2_low = " ".join(t.lower() for l, t in ueberschriften if l == 2)

    def _drin(tag: str, text: str) -> bool:
        teile = [t for t in re.split(r"[\s/-]+", tag.lower()) if t]
        if not teile:
            return False
        # kurze Begriffe (KI, API, MCP) nur als ganzes Wort, laengere auch
        # als Wortbestandteil (Monitoring in „KI-Monitoring“)
        return all(re.search(rf"(?<![a-zäöüß]){re.escape(t)}(?![a-zäöüß])", text) if len(t) <= 3 else t in text
                   for t in teile)

    in_tb = [t for t in tags if _drin(t, tl_low) or _drin(t, bl_low)]
    in_h2 = [t for t in tags if _drin(t, h2_low)]
    if not tags:
        kriterien.append(_k("e_fokus", 0.0, "keine Tags", "Tags als Fokusbegriffe setzen und in Titel/Beschreibung verwenden."))
        kriterien.append(_k("e_fokus_h2", 0.0, "keine Tags", "Fokusbegriff in eine H2 aufnehmen."))
    else:
        anteil_t = 100 * len(in_tb) / len(tags)
        fehlend_t = [t for t in tags if t not in in_tb]
        kriterien.append(_k("e_fokus", linear(anteil_t, 50, 0), f"{len(in_tb)} von {len(tags)} Tags ({', '.join(in_tb) or '–'})",
                            "Fokusbegriffe in Titel oder Beschreibung aufnehmen: " + ", ".join(fehlend_t[:3]) + "."))
        kriterien.append(_k("e_fokus_h2", 100.0 if in_h2 else 0.0, ", ".join(in_h2) if in_h2 else "kein Tag in einer H2",
                            f"Einen Fokusbegriff (z. B. „{tags[0]}“) in eine Zwischenüberschrift aufnehmen."))
    kriterien.append(_k("e_tags", band(len(tags), 3, 6, 0, 10), f"{len(tags)} Tags", "3–6 treffende Tags setzen."))
    host = re.sub(r"^https?://", "", base_url).rstrip("/")
    intern = [l for l in z.links if (l.startswith("/artikel/") or host in l) and f"/artikel/{slug}/" not in l]
    extern = [l for l in z.links if l.startswith("http") and host not in l]
    kz["links_intern"], kz["links_extern"] = len(intern), len(extern)
    andere = [s for s in (alle_slugs or []) if s != slug]
    kriterien.append(_k("e_intern", 100.0 if intern else 0.0, f"{len(intern)} interne Links",
                        "Auf verwandte Artikel verlinken" + (f" (z. B. /artikel/{andere[0]}/)" if andere else "") + " – hält Leser im Blog und stärkt das SEO."))
    kriterien.append(_k("e_extern", 100.0 if len(extern) >= 2 else (50.0 if extern else 0.0), f"{len(extern)} externe Links",
                        "Quellen und Werkzeuge verlinken (Hersteller-Doku, Studien) – erhöht Glaubwürdigkeit."))
    upd = _datum(meta.get("updated") or meta.get("date"))
    alter = (heute - upd).days if upd else 9999
    kriterien.append(_k("e_aktuell", linear(alter, 90, 365), f"zuletzt aktualisiert vor {alter} Tagen" if upd else "kein Datum",
                        "Inhalt prüfen und aktualisieren (updated + changelog-Eintrag)."))
    cl = meta.get("changelog") or []
    kriterien.append(_k("e_historie", 100.0 if cl else 0.0, f"{len(cl)} Einträge" if cl else "fehlt",
                        "changelog im Frontmatter anlegen – zeigt wiederkehrenden Lesern, was neu ist."))
    slug_ok = bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug))
    kriterien.append(_k("e_slug", (100.0 if slug_ok else 30.0) if len(slug) <= 60 else 50.0, f"{len(slug)} Zeichen" + ("" if slug_ok else ", unzulässige Zeichen"),
                        "Slug kurz halten (ändern nur mit Weiterleitung, sonst brechen Links)."))

    # Thementreue: Inhaltswoerter des Titels, die im Artikeltext wirklich vorkommen
    titel_w = {w.lower() for w in woerter(titel) if len(w) >= 4 and w.lower() not in STOPPWOERTER and not w.isdigit()}
    text_low = voll.lower() + " " + " ".join(t.lower() for _l, t in ueberschriften)
    gefunden = sorted(w for w in titel_w if w in text_low)
    kz["themen_treue"] = round(100 * len(gefunden) / len(titel_w)) if titel_w else 100
    kz["titel_woerter_fehlen"] = sorted(titel_w - set(gefunden))

    return Bewertung(slug=slug, titel=titel, kriterien=kriterien, kennzahlen=kz, vorschau_urteil=vorschau_urteil)


def auffaelligkeiten(b: Bewertung, durchschnitt: float | None = None) -> list[dict]:
    """Gut sichtbare Kennzeichnung fuer Ranking und Deploy-Pruefung.
    art: "thema" (Thema verfehlt?), "design" (Design schwach), "auffaellig"."""
    erg: list[dict] = []

    def st(kid: str) -> str:
        k = b.kriterium(kid)
        return k.status if k else "na"

    kz = b.kennzahlen
    if kz.get("themen_treue", 100) < 50:
        erg.append({"art": "thema", "text": f"Thema verfehlt? Nur {kz['themen_treue']} % der Titelbegriffe kommen im Text vor"
                    + (f" (fehlen: {', '.join(kz.get('titel_woerter_fehlen', [])[:4])})" if kz.get("titel_woerter_fehlen") else "")})
    if st("e_fokus") == "nein" and st("e_fokus_h2") == "nein":
        erg.append({"art": "thema", "text": "Thema unscharf: Fokusbegriffe (Tags) stehen weder in Titel/Beschreibung noch in einer Zwischenüberschrift"})
    if b.kategorie_score("D") < 50:
        erg.append({"art": "design", "text": f"Design schwach: kaum Auflockerung (Grafiken/Auflockerung {b.kategorie_score('D'):.0f}/100)"})
    if st("c_textwueste") == "nein" or st("d_abstand") == "nein":
        erg.append({"art": "design", "text": f"Textwüste: {kz.get('groesster_abstand', '?')} Wörter am Stück ohne visuelles Element"})
    if st("b_satzlaenge") == "nein" or st("b_lange_saetze") == "nein":
        a = kz.get("amstad", {})
        erg.append({"art": "auffaellig", "text": f"Zu lange Sätze (Ø {str(a.get('asl', '?')).replace('.', ',')} Wörter)"})
    if b.vorschau_urteil.get("urteil") == "nein" or b.kategorie_score("A") < 50:
        erg.append({"art": "auffaellig", "text": "Schwache Vorschau (Titel/Beschreibung/Bild für Link-Karten)"})
    if not b.pflicht_ok():
        erg.append({"art": "auffaellig", "text": "Pflicht-Meta-Tags fehlen in dist/"})
    for k, kat in KATEGORIEN.items():
        s = b.kategorie_score(k)
        if s < 40:
            erg.append({"art": "auffaellig", "text": f"Sehr niedriger Teilscore {kat['name']}: {s:.0f}/100"})
    if durchschnitt is not None and b.gesamt < durchschnitt - 10:
        erg.append({"art": "auffaellig", "text": f"Deutlich unter Durchschnitt ({b.gesamt:.0f} gegenüber Ø {durchschnitt:.0f})"})
    return erg


def lesetext(body_html: str, meta: dict, max_zeichen: int = 30000) -> str:
    """Klartext des Artikels fuer das Lektorat: Ueberschriften als ##,
    Listenpunkte mit -, visuelle Elemente als [Bild: Alt-Text] an ihrer
    Stelle - so kann das Lektorat auch Auflockerung und Fluss beurteilen."""
    z = zerlege_html(body_html)
    zeilen = []
    if meta.get("image"):
        zeilen.append("[Titelbild]")
    for e in z.ereignisse:
        if e[0] == "h":
            zeilen.append("\n" + "#" * e[1] + " " + e[2])
        elif e[0] == "text":
            zeilen.append(("- " if e[1] == "li" else "") + e[2])
        elif e[0] == "visuell":
            label = e[2].get("alt") or e[2].get("aria-label") or ""
            zeilen.append(f"[{e[1]}{': ' + label[:120] if label else ''}]")
    text = "\n".join(zeilen)
    if len(text) > max_zeichen:
        text = text[:max_zeichen] + "\n[… gekürzt]"
    return text
