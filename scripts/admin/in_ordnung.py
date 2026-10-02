"""„Alles in Ordnung bringen“: ein Durchlauf fuer alle nicht gruenen Teilnoten.

Kern der Logik, frei von Flask (testbar mit Wegwerf-Verzeichnissen):

  1. Hintergrundauftrag (Thread, Sperre je Artikel): Ist-Zustand pruefen,
     Lektorat, Metas, Textvorschlaege fuer markierte Stellen, Schutzpruefung,
     Vorschau der erwarteten Wirkung. Der Auftrag SCHREIBT NIE in articles/.
  2. Vorschlaege liegen nur als JSON unter data/ranking/inordnung/<slug>.json.
  3. uebernehmen(): erst nach ausdruecklicher Bestaetigung durch den Nutzer:
     Backup nach data/backups/artikel/, schreiben, bauen. Schlaegt der Build
     fehl oder fehlt danach ein Pflicht-Meta-Tag, wird das Backup zurueck-
     gespielt (und neu gebaut). Danach neu einlesen und neu bewerten.
  4. rueckgaengig(): stellt das Backup der letzten Uebernahme wieder her.

Die KI aendert nie ungeprueft einen Artikel. Gebaut wird nur in uebernehmen()
und rueckgaengig(), committet/gepusht/deployt wird hier nie. Alle LLM-Aufrufe
laufen ueber llm.py (BLOG_LLM_* aus der .env; der Schluessel wird nie
ausgegeben). Die Bewertung (Schwellen, Gewichte) wird hier nicht veraendert.
"""

from __future__ import annotations

import difflib
import hashlib
import html as html_mod
import math
import os
import re
import shutil
import threading
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

import bewertung as bw
import llm
import metas_auswahl as ma
import versionen
from ranking_daten import FrontmatterFehler, Speicher, _teile, setze_felder

# --------------------------------------------------------------------------
# Konstanten
# --------------------------------------------------------------------------

LANG_SATZ = 20            # Saetze ueber ~20 Woerter gelten als zu lang (Vorgabe des Nutzers)
MAX_UEBERGAENGE = 4       # Stellen, die nur wegen fehlender Uebergaenge angefasst werden
MAX_STELLEN = 12          # hoechstens so viele Textstellen je Durchlauf (Rest: naechster Durchlauf)
STAPEL = 4                # Stellen je LLM-Aufruf
LLM_TIMEOUT = 300         # Sekunden je LLM-Aufruf (Laufzeit ist zweitrangig, Gruendlichkeit zaehlt)
GESAMT_FRIST = 45 * 60    # Sekunden fuer den ganzen Auftrag
MAX_RUNDEN = 8            # Bewerten -> Verbessern -> neu Bewerten, hoechstens so oft
BUILD_TIMEOUT = 300

SCHRITTE = [
    ("pruefen", "Ist-Zustand prüfen"),
    ("lektorat", "Lektorat"),
]  # danach hängt die Engine je Runde weitere Schritte an (ordnung_engine.py)

# Kriterium -> Bereich, der es beheben kann
AUTOMATISCH = {
    "a_titel": "metas", "a_beschr": "metas", "a_hook": "metas", "a_guss": "metas", "a_alt": "metas", "e_fokus": "metas",
    "a_dist": "build", "a_pflicht": "build",
    "b_amstad": "text", "b_satzlaenge": "text", "b_lange_saetze": "text", "b_uebergaenge": "text",
    "b_wiederholung": "text", "b_fuellwoerter": "text", "b_absaetze": "text", "b_menschlich": "text",
    "e_intern": "links",
}
TEXT_KRITERIEN = ("b_amstad", "b_satzlaenge", "b_lange_saetze")

MENSCH = {
    "a_bild": "Das Vorschaubild muss ein Mensch erstellen oder tauschen (1200×630 px).",
    "a_autor": "Autor kommt aus config.yaml (site.author) – von Hand setzen.",
    "a_canonical": "Canonical kommt aus dem Template – von Hand prüfen.",
    "a_jsonld": "JSON-LD speist sich aus dem Frontmatter (Bild, Beschreibung) – von Hand ergänzen.",
    "b_einleitung": "Der Einstieg ist eine redaktionelle Entscheidung: macht ein Mensch.",
    "b_fazit": "Ein Fazit schreibt ein Mensch.",
    "c_hierarchie": "Überschriften umbauen ist Redaktionsarbeit (der Durchlauf ändert nie Überschriften).",
    "c_abschnitte": "Abschnitte teilen ist Redaktionsarbeit.",
    "c_listen": "Listen oder Tabellen ergänzen: macht ein Mensch.",
    "c_zusammenfassung": "Die Zusammenfassung oben (Frontmatter summary) schreibt ein Mensch.",
    "c_laenge": "Die Artikellänge ist eine inhaltliche Entscheidung.",
    "c_textwueste": "Grafiken, Listen oder Überschriften einfügen: macht ein Mensch.",
    "d_dichte": "Grafiken und Auflockerung muss ein Mensch ergänzen (der Durchlauf erzeugt keine Bilder).",
    "d_abstand": "Grafiken und Auflockerung muss ein Mensch ergänzen (der Durchlauf erzeugt keine Bilder).",
    "d_alt": "Alt-Texte für Bilder beschreiben, was zu sehen ist: macht ein Mensch.",
    "d_gewicht": "Bilder verkleinern: macht ein Mensch.",
    "d_poster": "Poster-Bild für Videos: macht ein Mensch.",
    "e_fokus_h2": "Überschriften ändert der Durchlauf nie – Schlüsselbegriff in eine H2 setzt ein Mensch.",
    "e_tags": "Tags festlegen ist eine redaktionelle Entscheidung.",
    "e_extern": "Externe Quellen brauchen eine inhaltliche Entscheidung (der Durchlauf ändert nie Links).",
    "e_aktuell": "Aktualität: Inhalt prüfen und updated bewusst setzen.",
    "e_historie": "Die Änderungshistorie (changelog) pflegt ein Mensch.",
    "e_slug": "Der Slug darf nicht ohne Weiteres geändert werden (URL).",
}


class AuftragFehler(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Sperre je Artikel (ein Auftrag, eine Uebernahme oder ein Rueckgaengig gleichzeitig)
# --------------------------------------------------------------------------

_sperre = threading.Lock()
_aktiv: set[str] = set()
_abbruch: set[str] = set()


def ist_gesperrt_(slug: str) -> bool:  # fuer versionen.abgleich: waehrend eines Schreibvorgangs nichts als „extern“ werten
    with _sperre:
        return slug in _aktiv


versionen.gesperrt_fn = ist_gesperrt_


def sperre_nehmen(slug: str) -> bool:
    with _sperre:
        if slug in _aktiv:
            return False
        _aktiv.add(slug)
        _abbruch.discard(slug)
        return True


def sperre_freigeben(slug: str) -> None:
    with _sperre:
        _aktiv.discard(slug)
        _abbruch.discard(slug)


def ist_gesperrt(slug: str) -> bool:
    with _sperre:
        return slug in _aktiv


def abbruch_anfordern(slug: str) -> bool:
    with _sperre:
        if slug in _aktiv:
            _abbruch.add(slug)
            return True
        return False


def abbruch_angefordert(slug: str) -> bool:
    with _sperre:
        return slug in _abbruch


# --------------------------------------------------------------------------
# Kontext (alles Externe austauschbar - Tests setzen Attrappen ein)
# --------------------------------------------------------------------------


class Kontext:
    """Buendelt, was von aussen kommt.

    root          Repo-Wurzel (Tests: Wegwerf-Verzeichnis)
    speicher      Speicher(root)
    chat          (system, nutzer, *, timeout, max_tokens) -> str   (llm.chat)
    llm_aktiv     () -> bool
    bewerte       (slug) -> (meta, Bewertung)   mit echtem dist/
    simuliere     (slug, neuer_text) -> Bewertung | None   Bewertung des Entwurfs (Wegwerf-Build)
    lektorat      (meta, bewertung) -> dict    LLM-Lektorat (speichert selbst)
    lektorat_alt  (slug) -> dict | None        gespeichertes Lektorat
    lesetext      (meta) -> str
    vale          (Path) -> dict
    baue          () -> (ok, log)
    pflicht_fehlt (slug) -> list[str]          fehlende Pflicht-Meta-Tags in dist/
    """

    def __init__(self, **kw):
        self.root: Path = kw["root"]
        self.speicher: Speicher = kw.get("speicher") or Speicher(self.root)
        self.chat = kw["chat"]
        self.llm_aktiv = kw.get("llm_aktiv", lambda: True)
        self.bewerte = kw["bewerte"]
        self.simuliere = kw.get("simuliere", lambda slug, text: None)
        self.lektorat = kw.get("lektorat")
        self.lektorat_alt = kw.get("lektorat_alt", lambda slug: None)
        self.lesetext = kw.get("lesetext", lambda meta: meta.get("body_md", ""))
        self.vale = kw.get("vale", lambda p: {"verfuegbar": False, "befunde": []})
        self.baue = kw["baue"]
        self.pflicht_fehlt = kw.get("pflicht_fehlt", lambda slug: [])
        self.frist = kw.get("frist", GESAMT_FRIST)
        self.gesundheit = kw.get("gesundheit", lambda: True)      # () -> bool: LLM-Dienst erreichbar?
        self.gesundheit_frist = kw.get("gesundheit_frist", 180)    # Sekunden Wartezeit auf den Dienst vor dem Start
        self.gesundheit_takt = kw.get("gesundheit_takt", 5)
        self.quellen = kw.get("quellen", lambda: {})  # () -> {slug: meta} aller Artikel (fuer interne Links)

    def artikel_pfad(self, slug: str) -> Path:
        return self.root / "articles" / f"{slug}.md"


# --------------------------------------------------------------------------
# Zustand
# --------------------------------------------------------------------------


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def zustand(ctx: Kontext, slug: str) -> dict | None:
    z = ctx.speicher.lesen("inordnung", f"{slug}.json")
    if z and z.get("status") in ("laeuft", "wartet") and not ist_gesperrt(slug):
        # Prozess wurde waehrend des Laufs beendet (z. B. Neustart): sauber als abgebrochen kennzeichnen
        z["status"] = "abgebrochen"
        z["meldung"] = "Der Auftrag wurde unterbrochen (Neustart der Verwaltung). Bitte neu starten."
        ctx.speicher.schreiben(z, "inordnung", f"{slug}.json")
    return z


def _sichern(ctx: Kontext, slug: str, z: dict) -> None:
    ctx.speicher.schreiben(z, "inordnung", f"{slug}.json")


def verwerfen(ctx: Kontext, slug: str) -> None:
    p = ctx.speicher.basis / "inordnung" / f"{slug}.json"
    if p.exists() and not ist_gesperrt(slug):
        p.unlink()


# --------------------------------------------------------------------------
# Bewertung -> Schnappschuss
# --------------------------------------------------------------------------


def schnappschuss(b: bw.Bewertung) -> dict:
    kat = {}
    for k in bw.KATEGORIEN:
        s = b.kategorie_score(k)
        kat[k] = {"score": s, "ampel": bw.ampel(s), "name": bw.KATEGORIEN[k]["name"]}
    return {
        "gesamt": b.gesamt, "ampel": b.ampel, "kategorien": kat,
        "kriterien": {k.id: {"name": k.name, "kat": k.kategorie, "status": k.status, "erfuellung": k.erfuellung,
                             "messwert": k.messwert, "vorschlag": k.vorschlag} for k in b.kriterien},
    }


def offene_punkte(b: bw.Bewertung) -> dict:
    """Fuer den Knopf im Kopf: was ist nicht gruen, was kann der Durchlauf, was nicht."""
    s = schnappschuss(b)
    kats = [(k, v["score"]) for k, v in s["kategorien"].items() if v["ampel"] != "gruen"]
    offen = [(kid, v) for kid, v in s["kriterien"].items() if v["status"] in ("teils", "nein")]
    auto = [kid for kid, _v in offen if kid in AUTOMATISCH]
    return {"kategorien": kats, "kriterien": offen, "automatisch": auto, "mensch": [kid for kid, _v in offen if kid not in AUTOMATISCH]}


# --------------------------------------------------------------------------
# Text: Klartext, Bloecke, Schutzpruefung
# --------------------------------------------------------------------------


def klartext(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = html_mod.unescape(s)
    s = re.sub(r"[*`]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


_ROH = r"style|script|svg|pre|figure|table|video|iframe|canvas|noscript|template"
_ROH_AUF = re.compile(rf"<({_ROH})\b", re.I)
_ROH_ZU = re.compile(rf"</({_ROH})\s*>", re.I)
_P_BLOCK = re.compile(r"^(<p\b[^>]*>)(.*)</p>$", re.S)
_ZAHL = re.compile(r"\d+(?:[.,:/]\d+)*×?")
_FACH = re.compile(r"\b(?=\w*[A-Za-zÄÖÜäöü])(?=\w*[A-Z]\w*[A-Z]|\w*[a-z]\w*[A-Z]|\w*\d)\w+\b")
_URL = re.compile(r"https?://[^\s)\"'<>\]]+")
_ATTR_URL = re.compile(r"""(?:href|src|srcset|data-src|poster)\s*=\s*["']([^"']*)["']""", re.I)
_MD_LINK = re.compile(r"\]\(([^)\s]+)")
_BILD = re.compile(r"!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_INLINE_CODE = re.compile(r"`[^`\n]+`|<code\b[^>]*>.*?</code>", re.S | re.I)
_FENCE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.M | re.S)
_UEBERSCHRIFT = re.compile(r"^#{1,6}[ \t]+[^\n]*$|<h[1-6]\b[^>]*>.*?</h[1-6]>", re.M | re.S | re.I)


class Block:
    def __init__(self, start: int, ende: int, text: str, art: str, zeile: int, zeile_ende: int):
        self.start, self.ende, self.text, self.art = start, ende, text, art  # art: html | md | h | andere
        self.zeile, self.zeile_ende = zeile, zeile_ende
        self.oeffner = ""
        self.inner = text
        if art == "html":
            m = _P_BLOCK.match(text)
            self.oeffner, self.inner = m.group(1), m.group(2)
        self.klar = klartext(self.inner) if art in ("html", "md") else ""
        self.abschnitt = ""
        self.abschnitt_id = ""
        self.absatz_nr = 0
        self.nach_ueberschrift = False


def ueberschrift_id(zeile: str) -> tuple[str, str]:
    """(Text, Anker-ID) einer Ueberschriftzeile wie der Blog sie rendert (markdown-toc-Slug bzw. id-Attribut)."""
    from markdown.extensions.toc import slugify
    m = re.search(r"""id\s*=\s*["']([^"']+)["']""", zeile)
    a = re.search(r"\{#([\w-]+)\}\s*$", zeile)
    text = klartext(re.sub(r"\{[^}]*\}\s*$", "", re.sub(r"^#+\s*", "", zeile)).rstrip("# "))
    return text, (m.group(1) if m else (a.group(1) if a else slugify(text, "-")))


def finde_bloecke(text: str) -> list[Block]:
    """Teilt die Artikeldatei in Absatzbloecke. Ueberspringt Frontmatter,
    Code-Zaeune, Kommentare und Roh-HTML-Container (style, script, svg, pre,
    figure, table ...). Bearbeitbar sind nur Absaetze (`<p>…</p>` und
    Markdown-Fliesstext); Ueberschriften werden als Marker mitgefuehrt."""
    kopf, _rest = _teile(text)
    pos = len(kopf) + 3  # hinter der schliessenden ---
    zeilen = []
    off = 0
    for z in text.splitlines(keepends=True):
        zeilen.append((off, z))
        off += len(z)
    bloecke: list[Block] = []
    akt: list[tuple[int, int, str, int]] = []  # (offset, nr, text)
    in_zaun = None
    in_kommentar = False
    tiefe = 0
    abschnitt = ""
    abschnitt_id = ""
    absatz_zaehler = 0
    letzte_war_ueberschrift = True

    def abschliessen():
        nonlocal akt, abschnitt, abschnitt_id, absatz_zaehler, letzte_war_ueberschrift
        if not akt:
            return
        start = akt[0][0] + (len(akt[0][2]) - len(akt[0][2].lstrip()))
        letzte = akt[-1]
        ende = letzte[0] + len(letzte[2].rstrip("\r\n"))
        roh = text[start:ende].rstrip()
        ende = start + len(roh)
        s = roh
        art = "andere"
        if re.match(r"<h[1-6]\b", s, re.I) or s.startswith("#"):
            art = "h"
        elif _P_BLOCK.match(s) and len(re.findall(r"<p\b", s, re.I)) == 1:
            art = "html"
        elif s and not s.startswith(("<", "#", ">", "|", "!", "-", "*", "+", "[", ":", "    ", "\t")) and not re.match(r"\d+[.)]\s", s):
            art = "md"
        b = Block(start, ende, roh, art, akt[0][1], akt[-1][1])
        if art == "h":
            abschnitt, abschnitt_id = ueberschrift_id(s)
            absatz_zaehler = 0
            letzte_war_ueberschrift = True
        elif art in ("html", "md"):
            absatz_zaehler += 1
            b.abschnitt, b.abschnitt_id, b.absatz_nr = abschnitt, abschnitt_id, absatz_zaehler
            b.nach_ueberschrift = letzte_war_ueberschrift
            letzte_war_ueberschrift = False
        bloecke.append(b)
        akt = []

    nr_start = 0
    for i, (o, z) in enumerate(zeilen):
        if o < pos:
            continue
        if o < pos + 0 and False:
            continue
        s = z.strip()
        if in_zaun:
            if s.startswith(in_zaun):
                in_zaun = None
            continue
        if in_kommentar:
            if "-->" in z:
                in_kommentar = False
            continue
        if s.startswith(("```", "~~~")):
            abschliessen()
            in_zaun = s[:3]
            continue
        if "<!--" in z:
            abschliessen()
            if "-->" not in z.split("<!--", 1)[1]:
                in_kommentar = True
            continue
        auf, zu = len(_ROH_AUF.findall(z)), len(_ROH_ZU.findall(z))
        if tiefe > 0 or auf or zu:
            abschliessen()
            tiefe = max(0, tiefe + auf - zu)
            continue
        if s == "":
            abschliessen()
            continue
        if s == "---" and o == len(kopf):
            continue
        if akt and re.match(r"<p\b", s) and akt[-1][2].rstrip().endswith("</p>"):
            abschliessen()  # zwei <p> ohne Leerzeile dazwischen sind zwei Absaetze
        if re.match(r"#{1,6}\s", s) or re.match(r"<h[1-6]\b.*</h[1-6]>\s*$", s, re.I):
            abschliessen()  # eine Ueberschriftzeile ist immer ein eigener Block (nie mit dem Absatz darunter verkleben)
            akt.append((o, i + 1, z))
            abschliessen()
            continue
        akt.append((o, i + 1, z))
    abschliessen()
    return bloecke


def _saetze_woerter(klar: str) -> list[int]:
    return [len(bw.woerter(s)) for s in bw.saetze(klar)]


_MAL = {"einmal": 1, "zweimal": 2, "dreimal": 3, "viermal": 4, "fünfmal": 5, "sechsmal": 6, "siebenmal": 7, "achtmal": 8,
        "neunmal": 9, "zehnmal": 10, "elfmal": 11, "zwölfmal": 12}
_ZAHLWORT = {"zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12}
_WORT_ZAHL = re.compile(r"\b(" + "|".join(list(_MAL) + list(_ZAHLWORT)) + r")\b", re.I)


def _zahl_normal(s: str) -> str:
    """Gleichwertige Schreibweisen vereinheitlichen: „4×“ = „viermal“, „2“ = „zwei“ (nur 2 bis 12; „ein“ bleibt
    unberuehrt, weil es meist der Artikel ist). Der Wert bleibt erhalten - „4×“ und „fünfmal“ bleiben verschieden."""
    s = klartext(s)
    s = re.sub(r"(\d+)\s*×", lambda m: f"{m.group(1)}×", s)
    def ersetze(m):
        w = m.group(1).lower()
        return f"{_MAL[w]}×" if w in _MAL else str(_ZAHLWORT[w])
    return _WORT_ZAHL.sub(ersetze, s)


def _zahlen(s: str) -> Counter:
    return Counter(_ZAHL.findall(_zahl_normal(s)))


def _zahlen_anzeige(c) -> str:
    return ", ".join(f"„{z}“" for z in sorted(c.elements()))


def _urls(s: str) -> Counter:
    c = Counter(_URL.findall(s))
    c.update(_ATTR_URL.findall(s))
    c.update(_MD_LINK.findall(s))
    return c


def _liste(c, n: int = 4) -> str:
    items = sorted(c.elements()) if hasattr(c, "elements") else sorted(c)
    return ", ".join(f"„{x}“" for x in items[:n]) + (" …" if len(items) > n else "")


def schutzpruefung_stelle(alt: str, neu: str, zweck: list[str], links: tuple = (), vorher: str | None = None) -> list[str]:
    """Gruende (in einfacher Sprache), warum eine Textstelle abgelehnt wird. Leer = in Ordnung.
    `alt` ist immer der ORIGINAL-Absatz (mehrere Runden pruefen gegen das Original). `links` = die ausdruecklich
    erlaubten NEU hinzugekommenen internen Links (URLs); nur diese duerfen zusaetzlich vorkommen, kein bestehender
    Link darf fehlen oder sich aendern. `vorher` = Fassung vor diesem Schritt (fuer „Satz wirklich kuerzer“)."""
    v: list[str] = []
    if not neu.strip():
        return ["Das Modell hat keinen Text geliefert."]
    if neu.strip() == alt.strip() and not links:
        return ["unverändert – das Modell hat nichts verbessert."]
    if vorher is not None and neu.strip() == vorher.strip():
        return ["unverändert – das Modell hat nichts verbessert."]
    absatz = "absatz" in zweck
    if "\n\n" in neu.strip() and not absatz:
        v.append("Die Stelle enthält einen Absatzwechsel; sie muss ein einzelner Absatz bleiben.")
    if absatz:
        neu = re.sub(r"</p>\s*<p\b[^>]*>", " ", neu.replace("\n\n", " "))
    ua, un = _urls(alt), _urls(neu)
    for l in links:
        ua[l] += 1
    if ua != un:
        v.append("Links/URLs verändert (" + (f"entfernt: {_liste(ua - un)}" if ua - un else "") + ("; " if ua - un and un - ua else "")
                 + (f"neu: {_liste(un - ua)}" if un - ua else "") + ") – Links dürfen nicht angefasst werden.")
    if _BILD.findall(alt) != _BILD.findall(neu):
        v.append("Bildverweise verändert – Bilder dürfen nicht angefasst werden.")
    if "```" in neu or "~~~" in neu:
        v.append("Das Modell hat einen Code-Block eingefügt.")
    ca, cn = Counter(_INLINE_CODE.findall(alt)), Counter(_INLINE_CODE.findall(neu))
    if ca != cn:
        v.append(f"Code-Ausdrücke verändert (entfernt: {_liste(ca - cn) or '–'}; neu: {_liste(cn - ca) or '–'}) – Code bleibt unverändert.")
    if _UEBERSCHRIFT.search(neu) or re.match(r"\s*#", neu):
        v.append("Das Modell hat eine Überschrift eingefügt.")
    za, zn = _zahlen(alt), _zahlen(neu)
    if za != zn:
        teile = []
        if za - zn:
            teile.append(f"fehlen: {_zahlen_anzeige(za - zn)}")
        if zn - za:
            teile.append(f"neu dazugekommen: {_zahlen_anzeige(zn - za)}")
        v.append("Zahlen verändert (" + "; ".join(teile) + ") – Zahlen dürfen nicht weggelassen, ergänzt oder geändert werden "
                 "(gleichwertig sind nur „4×“/„viermal“ und „2“/„zwei“ bis „12“/„zwölf“).")
    zi_a, zi_n = Counter(re.findall(r"„[^“]{1,400}“", klartext(alt))), Counter(re.findall(r"„[^“]{1,400}“", klartext(neu)))
    if zi_a != zi_n:
        v.append(f"Wörtliche Zitate verändert (fehlen: {_liste(zi_a - zi_n) or '–'}; neu: {_liste(zi_n - zi_a) or '–'}) – Zitate in „…“ bleiben unverändert.")
    ta, tn = Counter(_TAG.findall(alt)), Counter(_TAG.findall(neu))
    for l in links:  # erlaubte neue Links: <a href="…"> samt </a>
        for tag in (f'<a href="{l}">', "</a>"):
            if tn.get(tag, 0) > ta.get(tag, 0):
                ta[tag] += 1
    if ta != tn:
        v.append(f"HTML-Auszeichnung verändert (fehlt: {_liste(ta - tn) or '–'}; neu: {_liste(tn - ta) or '–'}) – Fett, Kursiv, Links müssen so oft vorkommen wie vorher.")
    fa, fn = set(_FACH.findall(klartext(alt))), set(_FACH.findall(klartext(neu)))
    if fa != fn:
        v.append(f"Namen/Fachbegriffe verändert (fehlen: {_liste(fa - fn) or '–'}; neu: {_liste(fn - fa) or '–'}) – Eigennamen und Fachbegriffe bleiben wie im Original.")
    wa, wn = len(bw.woerter(klartext(alt))), len(bw.woerter(klartext(neu)))
    if wn > 1.3 * wa + 6:
        v.append(f"Der Text ist deutlich länger geworden ({wa} → {wn} Wörter); das Modell könnte etwas Neues hinzugefügt haben.")
    if wn < 0.6 * wa - 2:
        v.append(f"Der Text ist deutlich kürzer geworden ({wa} → {wn} Wörter); es könnte Inhalt verloren gegangen sein.")
    if "ki_muster" in zweck and not v:
        import ki_muster
        basis = vorher if vorher is not None else alt
        if ki_muster.treffer_summe(klartext(neu)) >= ki_muster.treffer_summe(klartext(basis)):
            v.append("keine Verbesserung: die KI-Muster (Gedankenstriche, Floskeln, Verstärker …) sind nicht weniger geworden.")
    if "kuerzen" in zweck and not v:
        basis = vorher if vorher is not None else alt
        la, ln = max(_saetze_woerter(klartext(basis)) or [0]), max(_saetze_woerter(klartext(neu)) or [0])
        if ln >= la:
            v.append(f"keine Verbesserung: der längste Satz ist nicht kürzer geworden ({la} → {ln} Wörter).")
    return v


def schutzpruefung_dokument(alt: str, neu: str, links: tuple = ()) -> list[str]:
    """Gesamtpruefung vor/nach: URLs, Bildverweise, Code-Zaeune samt Inhalt,
    Ueberschriften (Anzahl und Text) und alle Zahlen (Multiset) im Text."""
    ka, ra = _teile(alt)
    kn, rn = _teile(neu)
    v = []
    erwartet = _urls(ra)
    for l in links:  # nur die ausdruecklich gewollten neuen internen Links
        erwartet[l] += 1
    if erwartet != _urls(rn):
        v.append("Menge der URLs/Links hat sich verändert")
    if Counter(_BILD.findall(ra)) != Counter(_BILD.findall(rn)):
        v.append("Bildverweise haben sich verändert")
    if [m.group(0) for m in _FENCE.finditer(ra)] != [m.group(0) for m in _FENCE.finditer(rn)]:
        v.append("Code-Blöcke haben sich verändert")
    ua = [klartext(m.group(0)) for m in _UEBERSCHRIFT.finditer(ra)]
    un = [klartext(m.group(0)) for m in _UEBERSCHRIFT.finditer(rn)]
    if ua != un:
        v.append("Überschriften (Anzahl oder Text) haben sich verändert")
    if _zahlen(ra) != _zahlen(rn):
        v.append("Zahlen im Text haben sich verändert")
    return v


# --------------------------------------------------------------------------
# Textstellen
# --------------------------------------------------------------------------

TEXT_SYSTEM = """Du bist Lektorin und Redakteur für einen deutschsprachigen IT-Fachblog (Zielgruppe: IT-Fachleute, Entscheider in KMU).
Du überarbeitest ausschließlich die dir übergebenen Absätze, damit sie flüssiger und leichter lesbar werden.
Du erfindest nichts, du lässt nichts weg. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."""


def text_prompt(stellen: list[dict]) -> str:
    teile = []
    for s in stellen:
        zweck = []
        if "kuerzen" in s["zweck"]:
            zweck.append("Sätze über 20 Wörter in kürzere Sätze teilen oder straffen")
        if "uebergang" in s["zweck"]:
            zweck.append("mit einem kurzen, inhaltlich passenden Verbindungswort oder Halbsatz an den vorigen Absatz anknüpfen "
                         "(z. B. Deshalb, Dabei, Genau hier, Gleichzeitig, Damit, Trotzdem) – nur wenn es sachlich stimmt")
        if "woerter" in s["zweck"]:
            zweck.append("Füllwörter streichen und Wortwiederholungen durch Pronomen, Synonyme oder Umstellung auflösen"
                         + (f" (konkret: {s['woerter_hinweis']})" if s.get("woerter_hinweis") else ""))
        if "ki_muster" in s["zweck"]:
            zweck.append("menschlicher klingen (KI-Muster entfernen): Gedankenstriche (—, –, --) durch Punkt, Komma, Doppelpunkt oder Klammer ersetzen, ohne den Sinn zu ändern; "
                         "Einleiter und Floskeln streichen („Kurz vorweg“, „Der Punkt ist“, „Und genau das“, „im Grunde“, „sozusagen“ …); „nicht X, sondern Y“ direkt formulieren; "
                         "Verstärker wie genau, ganz, wirklich, echt, durchaus, schlicht, einfach, eigentlich, tatsächlich meist streichen; "
                         "Satzrhythmus variieren (nie drei gleich lange Sätze hintereinander, kurze und längere mischen); aktive Sprache mit menschlichem Subjekt; "
                         "konkret statt vage; keine rhetorische Frage mit sofortiger Antwort; keine zitierfähig klingenden Sprüche. "
                         "Wörtliche Zitate in „…“, Code und Zahlenbereiche wie 2010–2026 bleiben unverändert")
        if "absatz" in s["zweck"]:
            zweck.append("diesen zu langen Absatz in 2 oder 3 Absätze teilen, getrennt durch eine Leerzeile (\\n\\n im JSON-Text); jeder Teil ein Gedanke, sonst nichts ändern")
        if s.get("hinweise"):
            zweck.append("auffällig laut Prüfung: " + "; ".join(s["hinweise"])[:300])
        if s.get("rueckmeldung"):
            zweck.append("ACHTUNG, dein letzter Versuch wurde abgelehnt: " + s["rueckmeldung"][:400] + " – bitte genau das beheben")
        teile.append(f"### Stelle {s['id']}\nAbschnitt: {s.get('abschnitt') or '(Einleitung)'}\n"
                     f"Vorheriger Absatz (nur Kontext, NICHT ändern): {s.get('davor') or '(keiner)'}\n"
                     f"Aufgabe: {'; '.join(zweck) or 'flüssiger formulieren'}\n"
                     f"Text:\n<<<\n{s['alt_inner']}\n>>>")
    return f"""Überarbeite die folgenden Stellen eines Blogartikels.

Regeln (verbindlich):
- Sinn, Ton, Fakten, Zahlen, Namen, Fachbegriffe unverändert. Keine neuen Behauptungen, nichts weglassen.
- Überschriften, Code, Links (URLs), Bilder und HTML-Auszeichnung (z. B. <strong>, <em>, <a href=…>, <code>) bleiben exakt erhalten: jedes Tag mit allen Attributen kommt genauso oft vor wie vorher.
- Kürzere Sätze, Ziel 15 bis 18 Wörter im Mittel, ein Gedanke je Satz. Verbindende Übergänge, wo gefordert.
- Schreibregeln gegen KI-Muster: keine neuen Gedankenstriche (—, –, --), keine Floskeln oder Einleiter („Kurz vorweg“, „Der Punkt ist“, „im Grunde“), keine neuen Verstärker (genau, ganz, wirklich, einfach …), kein „nicht X, sondern Y“; Satzrhythmus mischen; aktiv mit klarem Subjekt.
- Gleiche Sprache und Anrede wie das Original (Deutsch). Gleiche Schreibweise von Bindestrichen und Anführungszeichen.
- Jede Stelle bleibt ein einzelner Absatz (kein Leerzeilen-Wechsel, keine Aufzählung) – außer bei der Aufgabe, einen Absatz zu teilen.
- Gib den Text einer Stelle so zurück, wie er in den Absatz gehört (ohne umschließendes <p>).
- Kannst du eine Stelle nicht sicher verbessern, gib sie unverändert zurück.

{chr(10).join(teile)}

Antworte nur mit diesem JSON:
{{"stellen": [{{"id": 1, "alt": "die ersten 8 Wörter der Stelle zur Kontrolle", "neu": "überarbeiteter Text"}}]}}"""


def _lektorat_zitate(lek: dict | None) -> list[str]:
    zit = []
    if lek:
        for v in (lek.get("ergebnis") or lek).get("verbesserungen") or []:
            zit += re.findall(r"[„\"“»]([^„“\"«»]{20,220})[“\"”«]", str(v))
    return [re.sub(r"\s+", " ", z).strip().lower() for z in zit]


def sammle_stellen(text: str, offene: set[str], vale: dict | None, lek: dict | None) -> list[dict]:
    """Waehlt die zu ueberarbeitenden Bloecke aus (nur markierte Stellen)."""
    bloecke = finde_bloecke(text)
    absaetze = [b for b in bloecke if b.art in ("html", "md")]
    kuerzen_aktiv = bool(offene & set(TEXT_KRITERIEN))
    uebergang_aktiv = "b_uebergaenge" in offene
    vale_zeilen = [(f["zeile"], f.get("regel", "")) for f in (vale or {}).get("befunde", [])]
    zitate = _lektorat_zitate(lek)

    kandidaten: dict[int, dict] = {}
    for idx, b in enumerate(absaetze):
        woerter_je_satz = _saetze_woerter(b.klar)
        lang = [n for n in woerter_je_satz if n > LANG_SATZ]
        sehr_lang = [n for n in woerter_je_satz if n > 25]
        hinweise = []
        vale_hits = [r for z, r in vale_zeilen if b.zeile <= z <= b.zeile_ende]
        if vale_hits:
            hinweise.append("Vale: " + ", ".join(sorted(set(vale_hits))))
        kl = b.klar.lower()
        lek_hits = [z for z in zitate if z in kl]
        if lek_hits:
            hinweise.append("Lektorat nennt diese Stelle")
        zweck = []
        if kuerzen_aktiv and lang:
            zweck.append("kuerzen")
        elif kuerzen_aktiv and (vale_hits or lek_hits):
            zweck.append("kuerzen")
        if not zweck and not (vale_hits or lek_hits):
            continue
        if not zweck:
            continue
        prio = 10 * len(sehr_lang) + 3 * len(lang) + 2 * len(vale_hits) + 2 * len(lek_hits)
        kandidaten[idx] = {"idx": idx, "zweck": zweck, "hinweise": hinweise, "prio": prio}

    ue_idx: list[int] = []
    if uebergang_aktiv:
        folge = [i for i, b in enumerate(absaetze) if not b.nach_ueberschrift and i > 0]
        verbunden = [i for i in folge if (bw.woerter(absaetze[i].klar) or [""])[0].lower() in bw.UEBERGANGSWOERTER]
        offen_folge = [i for i in folge if i not in verbunden and len(bw.woerter(absaetze[i].klar)) >= 8]
        brauche = max(1, min(MAX_UEBERGAENGE, math.ceil(0.25 * len(folge)) - len(verbunden) + 1))
        if offen_folge:
            schritt = max(1, len(offen_folge) // brauche)
            ue_idx = offen_folge[::schritt][:brauche]
            for i in ue_idx:
                k = kandidaten.setdefault(i, {"idx": i, "zweck": [], "hinweise": [], "prio": 1})
                if "uebergang" not in k["zweck"]:
                    k["zweck"].append("uebergang")

    # Uebergangsstellen sind gesetzt; der Rest der Plaetze geht an die Stellen mit den laengsten Saetzen
    pflicht = [kandidaten[i] for i in ue_idx]
    rest = sorted((k for k in kandidaten.values() if k["idx"] not in ue_idx), key=lambda k: -k["prio"])
    auswahl = pflicht + rest[:max(0, MAX_STELLEN - len(pflicht))]
    auswahl.sort(key=lambda k: k["idx"])
    erg = []
    for n, k in enumerate(auswahl, 1):
        b = absaetze[k["idx"]]
        davor = absaetze[k["idx"] - 1].klar[-300:] if k["idx"] > 0 else ""
        erg.append({"id": n, "start": b.start, "ende": b.ende, "zeile": b.zeile, "abschnitt": b.abschnitt,
                    "abschnitt_id": b.abschnitt_id, "absatz_nr": b.absatz_nr,
                    "art": b.art, "oeffner": b.oeffner, "alt": b.text, "alt_inner": b.inner, "davor": davor,
                    "zweck": k["zweck"], "hinweise": k["hinweise"]})
    erg_total = len(kandidaten)
    for s in erg:
        s["kandidaten_gesamt"] = erg_total
    return erg


def _neu_block(s: dict, neu_inner: str) -> str:
    neu_inner = neu_inner.strip()
    if s["art"] == "html":
        return f"{s['oeffner']}{neu_inner}</p>"
    return neu_inner


def verarbeite_antwort(stellen: list[dict], antwort: dict) -> tuple[list[dict], list[dict]]:
    """(angenommen, abgelehnt) nach Schutzpruefung. Zuordnung ueber die Stellen-ID."""
    nach_id = {s["id"]: s for s in stellen}
    angenommen, abgelehnt = [], []
    gesehen = set()
    for e in (antwort.get("stellen") or []):
        try:
            sid = int(e.get("id"))
        except (TypeError, ValueError):
            continue
        s = nach_id.get(sid)
        if not s or sid in gesehen:
            continue
        gesehen.add(sid)
        neu_inner = str(e.get("neu") or "")
        kontrolle = " ".join(bw.woerter(klartext(s["alt_inner"]))[:3]).lower()
        gemeldet = " ".join(bw.woerter(str(e.get("alt") or ""))[:3]).lower()
        verstoesse = []
        if gemeldet and kontrolle and gemeldet != kontrolle:
            verstoesse.append("Die Antwort gehört nicht zu dieser Stelle (der Anfang stimmt nicht).")
        verstoesse += schutzpruefung_stelle(s["alt_inner"], neu_inner, s["zweck"])
        rec = {k: s.get(k) for k in ("id", "start", "ende", "zeile", "abschnitt", "abschnitt_id", "absatz_nr", "art", "zweck", "hinweise", "alt", "alt_inner")}
        rec["neu_inner"] = neu_inner.strip()
        rec["neu"] = _neu_block(s, neu_inner)
        if verstoesse:
            rec["grund"] = "; ".join(verstoesse)
            abgelehnt.append(rec)
        else:
            rec["uebergang_erkannt"] = ((bw.woerter(klartext(neu_inner)) or [""])[0].lower() in bw.UEBERGANGSWOERTER) if "uebergang" in s["zweck"] else None
            angenommen.append(rec)
    for sid, s in nach_id.items():
        if sid not in gesehen:
            rec = {k: s.get(k) for k in ("id", "start", "ende", "zeile", "abschnitt", "abschnitt_id", "absatz_nr", "art", "zweck", "hinweise", "alt", "alt_inner")}
            rec["neu_inner"], rec["neu"], rec["grund"] = "", "", "Das Modell hat für diese Stelle keine Antwort geliefert."
            abgelehnt.append(rec)
    return angenommen, abgelehnt


# --------------------------------------------------------------------------
# Anzeige einer Textstelle: nur der betroffene Absatz, Satz hervorgehoben, Struktur erhalten
# --------------------------------------------------------------------------

_SATZ_ENDE = re.compile(r"[.!?…](?:</\w+>)*[\"“”»)]*(?=\s+(?:<\w[^>]*>)*[„\"«(\[A-ZÄÖÜ0-9])")
_ERLAUBT_TAGS = {"strong", "em", "b", "i", "code", "a", "br", "sub", "sup", "kbd", "mark", "abbr", "span", "small", "u", "s", "del", "ins"}
_MARK_AUF, _MARK_ZU = "\ue000", "\ue001"


def block_html(art: str, inner: str) -> str:
    """Inhalt eines Absatzes als HTML, wie der Blog ihn ausgibt (Markdown wird gerendert, `<p>` entfaellt)."""
    if art == "html":
        return inner.strip()
    import build
    h = build.render_markdown(inner.strip()).strip()
    m = re.fullmatch(r"<p>(.*)</p>", h, re.S)
    return m.group(1) if m else h


def satz_teile(h: str) -> list[str]:
    """Saetze eines HTML-Absatzes; Tags bleiben an ihrem Satz, nichts geht verloren."""
    t = h
    for abk in bw._ABKUERZUNGEN:
        t = t.replace(abk, abk.replace(".", bw._PLATZHALTER))
    t = re.sub(r"\b([A-ZÄÖÜ])\.(?=\s)", lambda m: m.group(1) + bw._PLATZHALTER, t)
    teile, start = [], 0
    for m in _SATZ_ENDE.finditer(t):
        teile.append(t[start:m.end()])
        start = m.end()
        while start < len(t) and t[start].isspace():
            start += 1
    teile.append(t[start:])
    return [x.replace(bw._PLATZHALTER, ".").strip() for x in teile if x.strip()]


def sicher_html(h: str) -> str:
    """Nur harmlose Inline-Tags durchlassen, Tags immer sauber schliessen; Treffer-Marker werden zu <mark>."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self.stack = [], []

        def _schliesse_bis(self, name):
            if name not in self.stack:
                return False
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == name:
                    break
            return True

        def handle_starttag(self, tag, attrs):
            if tag == "br":
                self.out.append("<br>")
            elif tag in _ERLAUBT_TAGS and tag != "mark":
                a = ""
                if tag == "a":
                    href = dict(attrs).get("href") or ""
                    if re.match(r"(https?://|/|#)", href):
                        a = f' href="{html_mod.escape(href, quote=True)}" target="_blank" rel="noopener"'
                self.out.append(f"<{tag}{a}>")
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in _ERLAUBT_TAGS and tag not in ("br", "mark"):
                self._schliesse_bis(tag)

        def handle_data(self, data):
            for ch in re.split(f"([{_MARK_AUF}{_MARK_ZU}])", data):
                if ch == _MARK_AUF:
                    self.out.append('<mark class="treffer">')
                    self.stack.append("mark")
                elif ch == _MARK_ZU:
                    self._schliesse_bis("mark")
                elif ch:
                    self.out.append(html_mod.escape(ch))

    p = P()
    p.feed(h)
    p.close()
    while p.stack:
        p.out.append(f"</{p.stack.pop()}>")
    return "".join(p.out)


def stelle_ansicht(art: str, alt_inner: str, neu_inner: str = "") -> dict:
    """Darstellung einer Stelle: {kontext: HTML mit hervorgehobenem Satz und je einem Satz Umgebung,
    aenderungen: [{vorher, nachher}] satzweise, mit erhaltener Formatierung}."""
    a = satz_teile(block_html(art, alt_inner))
    n = satz_teile(block_html(art, neu_inner)) if neu_inner.strip() else []
    ka, kn = [klartext(x) for x in a], [klartext(x) for x in n]
    ops = [o for o in difflib.SequenceMatcher(None, ka, kn, autojunk=False).get_opcodes() if o[0] != "equal"] if n else []
    betroffen: set[int] = set()
    for _op, i1, i2, _j1, _j2 in ops:
        betroffen |= set(range(i1, i2)) or ({min(i1, len(a) - 1)} if a else set())
    if not n:  # abgelehnt ohne Text: die laengsten Saetze zeigen
        betroffen = {max(range(len(a)), key=lambda i: len(bw.woerter(ka[i])))} if a else set()
    sichtbar = set()
    for i in betroffen:
        sichtbar |= {i - 1, i, i + 1}
    sichtbar = {i for i in sichtbar if 0 <= i < len(a)}
    teile, letzte = [], -1
    for i in range(len(a)):
        if i not in sichtbar:
            continue
        if i - 1 != letzte:
            teile.append("…")
        teile.append(f"{_MARK_AUF}{a[i]}{_MARK_ZU}" if i in betroffen else a[i])
        letzte = i
    if letzte != len(a) - 1:
        teile.append("…")
    aenderungen = [{"vorher": sicher_html(" ".join(a[i1:i2])) if i2 > i1 else "", "nachher": sicher_html(" ".join(n[j1:j2])) if j2 > j1 else ""}
                   for _op, i1, i2, j1, j2 in ops]
    return {"kontext": sicher_html(" ".join(teile)), "aenderungen": aenderungen}


def ort_fuer(text: str, start: int) -> dict | None:
    """Verortung des Blocks, der an `start` beginnt: Abschnitt, Absatznummer, Anker (aus der aktuellen Datei)."""
    for b in finde_bloecke(text):
        if b.start == start and b.art in ("html", "md"):
            return {"abschnitt": b.abschnitt, "abschnitt_id": b.abschnitt_id, "absatz_nr": b.absatz_nr, "zeile": b.zeile}
    return None


def nachpruefen(ctx: Kontext, slug: str, z: dict) -> bool:
    """Gespeicherte Vorschlaege mit den heutigen Pruefregeln neu bewerten (z. B. nach einer Regelverbesserung):
    abgelehnte Stellen, die nun bestehen, wandern zu den Vorschlaegen. Nur wenn der Artikel unveraendert ist."""
    if z.get("status") != "vorschlag" or not z.get("stellen_abgelehnt"):
        return False
    pfad = ctx.artikel_pfad(slug)
    text = pfad.read_text(encoding="utf-8")
    if hashlib.sha256(text.encode()).hexdigest() != z.get("datei_hash"):
        return False
    uebrig, geaendert = [], False
    for s in z["stellen_abgelehnt"]:
        if not s.get("neu_inner"):
            uebrig.append(s)
            continue
        art = s.get("art") or "html"
        oeffner = ""
        if art == "html":
            m = _P_BLOCK.match(s["alt"])
            oeffner = m.group(1) if m else "<p>"
        grund = schutzpruefung_stelle(s["alt_inner"], s["neu_inner"], s["zweck"])
        neu_block = (f"{oeffner}{s['neu_inner'].strip()}</p>" if art == "html" else s["neu_inner"].strip())
        if grund:
            s["grund"] = " ".join(grund)
            uebrig.append(s)
            continue
        probe = dict(s, neu=neu_block)
        _t, fehler = entwurf(text, {}, [probe])
        if fehler:
            s["grund"] = "; ".join(fehler)
            uebrig.append(s)
            continue
        probe["uebergang_erkannt"] = ((bw.woerter(klartext(s["neu_inner"])) or [""])[0].lower() in bw.UEBERGANGSWOERTER) if "uebergang" in s["zweck"] else None
        z["stellen"].append(probe)
        geaendert = True
    if geaendert:
        z["stellen"].sort(key=lambda x: x["start"])
        z["stellen_abgelehnt"] = uebrig
        z["nachgeprueft"] = True
        _sichern(ctx, slug, z)
    return geaendert


def wortdiff(alt: str, neu: str) -> list[tuple[str, str]]:
    """[(op, text)] mit op in {'=', '-', '+'} auf Wortebene (fuer die gemeinsame Diff-Ansicht)."""
    a, n = alt.split(), neu.split()
    sm = difflib.SequenceMatcher(None, a, n, autojunk=False)
    erg = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            erg.append(("=", " ".join(a[i1:i2])))
        else:
            if i2 > i1:
                erg.append(("-", " ".join(a[i1:i2])))
            if j2 > j1:
                erg.append(("+", " ".join(n[j1:j2])))
    return erg


# --------------------------------------------------------------------------
# Auftrag (Hintergrund)
# --------------------------------------------------------------------------


def _schritt(ctx: Kontext, slug: str, z: dict, key: str, status: str, text: str = "") -> None:
    for s in z["schritte"]:
        if s["key"] == key:
            s["status"] = status
            s["text"] = text
            if status == "laeuft":
                s.setdefault("start", time.time())
            elif "start" in s:
                s["dauer"] = round(time.time() - s["start"], 1)
    _sichern(ctx, slug, z)


def _pruefe_abbruch(slug: str, frist_ende: float) -> None:
    if abbruch_angefordert(slug):
        raise AuftragFehler("Vom Nutzer abgebrochen.")
    if time.time() > frist_ende:
        raise AuftragFehler("Zeitlimit des Auftrags überschritten – abgebrochen.")


_warteschlange: "collections.deque" = None  # (ctx, slug, z) - es laeuft immer nur EIN Auftrag gleichzeitig
_wache = threading.Lock()
_arbeiter_aktiv = False


def warteschlange_laenge() -> int:
    with _wache:
        return len(_warteschlange) if _warteschlange is not None else 0


def _arbeiter() -> None:
    global _arbeiter_aktiv
    while True:
        with _wache:
            if not _warteschlange:
                _arbeiter_aktiv = False
                return
            ctx, slug, z, runner = _warteschlange.popleft()
        if runner is None:
            z["status"] = "laeuft"
            z["gestartet"] = _jetzt()
            z.pop("warteplatz", None)
            _sichern(ctx, slug, z)
            _lauf(ctx, slug, z)
        else:  # anderer Auftrag (z. B. Gutachten) in derselben Warteschlange
            try:
                runner(ctx, slug, z)
            except Exception:
                sperre_freigeben(slug)


def _einreihen(ctx: Kontext, slug: str, z: dict, runner=None) -> None:
    global _warteschlange, _arbeiter_aktiv
    import collections
    with _wache:
        if _warteschlange is None:
            _warteschlange = collections.deque()
        z["warteplatz"] = len(_warteschlange) + (1 if _arbeiter_aktiv else 0)
        _warteschlange.append((ctx, slug, z, runner))
        starten = not _arbeiter_aktiv
        _arbeiter_aktiv = True
    if starten:
        threading.Thread(target=_arbeiter, daemon=True, name="inordnung-arbeiter").start()


def starte(ctx: Kontext, slug: str, *, hintergrund: bool = True, modus: str = "neu") -> tuple[bool, str]:
    """Startet den Auftrag. Gibt (False, Grund) zurueck, wenn schon einer laeuft oder es nicht geht.
    Im Hintergrund laeuft immer nur ein Auftrag gleichzeitig; weitere warten in der Warteschlange."""
    if not ctx.llm_aktiv():
        return False, "LLM nicht konfiguriert (BLOG_LLM_API_KEY fehlt)."
    pfad = ctx.artikel_pfad(slug)
    if not pfad.exists():
        return False, "Nur Markdown-Artikel (articles/<slug>.md) werden unterstützt."
    if not sperre_nehmen(slug):
        return False, "Für diesen Artikel läuft bereits ein Auftrag."
    if modus == "nachholen":  # nur die wegen Verbindungsproblemen nicht bearbeiteten Teile des vorhandenen Vorschlags
        z = zustand(ctx, slug)
        if not z or z.get("status") != "vorschlag" or not (z.get("nicht_bearbeitet") or z.get("nicht_bearbeitet_bereiche")):
            sperre_freigeben(slug)
            return False, "Es gibt nichts nachzuholen."
        z.update(modus="nachholen", status="wartet" if hintergrund else "laeuft", gestartet=_jetzt())
        z.pop("beendet", None)
    else:
        z = {"id": uuid.uuid4().hex[:12], "slug": slug, "status": "wartet" if hintergrund else "laeuft", "gestartet": _jetzt(),
             "schritte": [{"key": k, "name": n, "status": "offen", "text": ""} for k, n in SCHRITTE]}
    _sichern(ctx, slug, z)
    if hintergrund:
        _einreihen(ctx, slug, z)
    else:
        _lauf(ctx, slug, z)
    return True, z["id"]


def _lauf(ctx: Kontext, slug: str, z: dict) -> None:
    frist_ende = time.time() + ctx.frist
    try:
        _auftrag(ctx, slug, z, frist_ende)
    except AuftragFehler as exc:
        z["status"] = "vorschlag" if z.get("modus") == "nachholen" else "abgebrochen"
        z["meldung"] = str(exc)
        if z.get("modus") == "nachholen":
            z["letzter_fehler"] = str(exc)
    except llm.LLMFehler as exc:  # z. B. Dienst auch nach allen Wiederholungen nicht erreichbar
        z["status"] = "vorschlag" if z.get("modus") == "nachholen" else "fehler"
        z["meldung"] = str(exc)
        if z.get("modus") == "nachholen":
            z["letzter_fehler"] = str(exc)
    except Exception as exc:  # unerwartet: sauber melden, nie den Thread sterben lassen
        z["status"] = "fehler"
        z["meldung"] = f"Unerwarteter Fehler: {type(exc).__name__}: {str(exc)[:200]}"
    finally:
        for s in z["schritte"]:
            if s["status"] == "laeuft":
                s["status"] = "fehler"
        z["beendet"] = _jetzt()
        try:
            _sichern(ctx, slug, z)
        finally:
            sperre_freigeben(slug)


def _auftrag(ctx: Kontext, slug: str, z: dict, frist_ende: float) -> None:
    import ordnung_engine
    if z.get("modus") == "nachholen":
        ordnung_engine.nachholen_lauf(ctx, slug, z, frist_ende)
        z.pop("modus", None)
    else:
        ordnung_engine.lauf(ctx, slug, z, frist_ende)


def entwurf(text: str, meta_werte: dict[str, str], stellen: list[dict]) -> tuple[str, list[str]]:
    """Setzt gewaehlte Metas und Stellen auf `text` an. Gibt (neuer Text, Fehlerliste) zurueck.
    Prueft zusaetzlich das ganze Dokument (URLs, Bilder, Code, Ueberschriften, Zahlen)."""
    neu = text
    for s in sorted(stellen, key=lambda x: -x["start"]):
        if neu[s["start"]:s["ende"]] != s["alt"]:
            return text, [f"Stelle {s['id']}: Text an dieser Position hat sich verändert"]
        neu = neu[:s["start"]] + s["neu"] + neu[s["ende"]:]
    try:
        if meta_werte:
            neu = setze_felder(neu, dict(meta_werte))
    except FrontmatterFehler as exc:
        return text, [str(exc)]
    return neu, schutzpruefung_dokument(text, neu, tuple(l for s_ in stellen for l in (s_.get("links") or ())))


# --------------------------------------------------------------------------
# Uebernehmen / Rueckgaengig
# --------------------------------------------------------------------------


def _schreibe_atomar(pfad: Path, inhalt: str) -> None:
    tmp = pfad.with_suffix(pfad.suffix + ".tmp")
    tmp.write_text(inhalt, encoding="utf-8")
    try:
        shutil.copymode(pfad, tmp)
    except OSError:
        pass
    os.replace(tmp, pfad)


def _wiederherstellen(ctx: Kontext, pfad: Path, backup: Path) -> tuple[bool, str]:
    """Spielt das Backup zurueck und baut neu, damit dist/ wieder zum Artikel passt."""
    shutil.copy2(backup, pfad)
    try:
        ok, log = ctx.baue()
    except Exception as exc:
        return False, f"Neubau nach Rückspielen fehlgeschlagen ({type(exc).__name__})"
    return ok, "" if ok else "Neubau nach Rückspielen fehlgeschlagen: " + log[-400:]


ERLAUBT = ("title", "description", "og_image_alt", "og_image")


def _frontmatter_werte(text: str) -> dict:
    import yaml
    kopf, _ = _teile(text)
    return yaml.safe_load(kopf.strip("-\n")) or {}


def _pruefe_bild(root: Path, pfad: str) -> str | None:
    """og_image darf nur auf eine vorhandene Datei unter static/img zeigen."""
    if not pfad.startswith("/static/img/") or ".." in pfad:
        return "Bild muss unter /static/img/ liegen"
    if not (root / pfad.lstrip("/")).is_file():
        return "Bilddatei nicht gefunden"
    return None


def meta_aenderungen(ctx: Kontext, alt_text: str, meta_werte: dict) -> tuple[dict, str]:
    """Nur Felder, die sich gegenueber der Datei aendern; Werte hart pruefen (Laengen sind nur eine Warnung).
    Gibt (Aenderungen, Fehlertext) zurueck."""
    aktuell_meta = _frontmatter_werte(alt_text)
    mv = {}
    for f, wert in (meta_werte or {}).items():
        if f not in ERLAUBT:
            return {}, f"Feld {f} darf nicht geändert werden"
        wert = " ".join(str(wert).split())
        if wert == str(aktuell_meta.get(f) or "").strip() or (f == "og_image" and not wert):
            continue
        grund = _pruefe_bild(ctx.root, wert) if f == "og_image" else ma.pruefe_wert_hart(f, wert)
        if grund:
            return {}, f"{f}: {grund}"
        mv[f] = wert
    return mv, ""


def wirkung(ctx: Kontext, slug: str, meta_werte: dict, stellen_ids: set) -> dict:
    """Wirkung einer Auswahl (z. B. nach Abwahl einzelner Stellen) neu rechnen - nur Simulation, nichts wird geschrieben.
    Speichert das Ergebnis im Zustand: welche Kriterien waeren (gegenueber der vollen Auswahl) wieder rot?"""
    z = zustand(ctx, slug)
    if not z or z.get("status") != "vorschlag":
        return {"ok": False, "meldung": "Kein offener Vorschlag."}
    text = ctx.artikel_pfad(slug).read_text(encoding="utf-8")
    if hashlib.sha256(text.encode()).hexdigest() != z.get("datei_hash"):
        return {"ok": False, "meldung": "Der Artikel wurde seit dem Vorschlag geändert – bitte neu starten."}
    mv, fehler = meta_aenderungen(ctx, text, meta_werte)
    if fehler:
        return {"ok": False, "meldung": fehler}
    st = [s for s in (z.get("stellen") or []) if s["id"] in stellen_ids]
    neu, fehler_liste = entwurf(text, mv, st)
    if fehler_liste:
        return {"ok": False, "meldung": "Schutzprüfung: " + "; ".join(fehler_liste)}
    b2 = ctx.simuliere(slug, neu)
    if b2 is None:
        return {"ok": False, "meldung": "Die Wirkung lässt sich hier nicht berechnen."}
    snap = schnappschuss(b2)
    voll = z.get("erwartet") or {}
    rot = [{"id": k, "name": v["name"], "messwert": v["messwert"]} for k, v in snap["kriterien"].items()
           if v["status"] in ("teils", "nein") and (voll.get("kriterien", {}).get(k, {}).get("status") == "ok")]
    z["wirkung_auswahl"] = {"snap": snap, "ids": sorted(stellen_ids), "meta": mv, "meta_form": dict(meta_werte), "rot": rot}
    _sichern(ctx, slug, z)
    return {"ok": True, "meldung": "Wirkung neu berechnet."}


def uebernehmen(ctx: Kontext, slug: str, meta_werte: dict[str, str], stellen_ids: set[int]) -> dict:
    """Schreibt die vom Nutzer gewaehlte Kombination (meta_werte = Feld -> Text, nur geaenderte Felder zaehlen) und Stellen: Backup -> schreiben -> bauen -> pruefen -> neu bewerten.
    Bei Fehlern wird das Backup zurueckgespielt. Gibt {ok, meldung, ...} zurueck."""
    if not sperre_nehmen(slug):
        return {"ok": False, "meldung": "Für diesen Artikel läuft bereits ein Auftrag."}
    try:
        z = zustand(ctx, slug)
        if not z or z.get("status") != "vorschlag":
            return {"ok": False, "meldung": "Kein offener Vorschlag – bitte den Durchlauf neu starten."}
        pfad = ctx.artikel_pfad(slug)
        alt = pfad.read_text(encoding="utf-8")
        if hashlib.sha256(alt.encode()).hexdigest() != z.get("datei_hash"):
            return {"ok": False, "meldung": "Der Artikel wurde seit dem Vorschlag geändert – bitte den Durchlauf neu starten."}
        mv, fehler_mv = meta_aenderungen(ctx, alt, meta_werte)
        if fehler_mv:
            return {"ok": False, "meldung": fehler_mv + " – nichts geändert."}
        st = [s for s in (z.get("stellen") or []) if s["id"] in stellen_ids]
        if not mv and not st:
            return {"ok": False, "meldung": "Nichts ausgewählt oder keine Änderung – nichts geändert."}
        for s in st:
            verstoesse = schutzpruefung_stelle(s["alt_inner"], s["neu_inner"], s["zweck"], links=tuple(s.get("links") or ()))
            if verstoesse:
                return {"ok": False, "meldung": f"Stelle {s['id']}: {'; '.join(verstoesse)} – nichts geändert."}
        neu, fehler = entwurf(alt, mv, st)
        if fehler:
            return {"ok": False, "meldung": "Schutzprüfung: " + "; ".join(fehler) + " – nichts geändert."}
        # ---- Backup, schreiben, bauen
        versionen.vor_schreiben(ctx.root, slug)
        backup = ctx.speicher.artikel_sichern(pfad)
        _schreibe_atomar(pfad, neu)
        grund_rollback = ""
        try:
            ok, log = ctx.baue()
        except Exception as exc:
            ok, log = False, f"{type(exc).__name__}: {exc}"
        if not ok:
            grund_rollback = "Build fehlgeschlagen: " + log[-600:]
        else:
            fehlt = ctx.pflicht_fehlt(slug)
            if fehlt:
                grund_rollback = "Pflicht-Meta-Tag(s) fehlen nach dem Bauen: " + ", ".join(fehlt)
        if grund_rollback:
            ok2, f2 = _wiederherstellen(ctx, pfad, backup)
            z["status"] = "vorschlag"
            z["letzter_fehler"] = grund_rollback
            _sichern(ctx, slug, z)
            return {"ok": False, "zurueckgespielt": True, "backup": str(backup),
                    "meldung": grund_rollback + " – Backup wurde automatisch zurückgespielt." + ("" if ok2 else " " + f2)}
        versionen.nach_schreiben(ctx.root, slug, "ordnung", f"{len(mv)} Meta-Feld(er), {len(st)} Textstelle(n)")
        # ---- neu einlesen und bewerten
        nachher = None
        try:
            _m, b = ctx.bewerte(slug)
            nachher = schnappschuss(b)
        except Exception as exc:
            z["nachher_fehler"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        z.update(status="uebernommen", uebernommen_am=_jetzt(), backup=str(backup), nachher=nachher,
                 uebernommen={"meta": sorted(mv), "stellen": sorted(s["id"] for s in st), "werte": mv},
                 datei_hash_neu=hashlib.sha256(neu.encode()).hexdigest())
        _sichern(ctx, slug, z)
        return {"ok": True, "meldung": "Übernommen, gebaut und neu bewertet.", "backup": str(backup)}
    finally:
        sperre_freigeben(slug)


def rueckgaengig(ctx: Kontext, slug: str) -> dict:
    """Stellt das Backup der letzten Uebernahme wieder her (und baut neu)."""
    if not sperre_nehmen(slug):
        return {"ok": False, "meldung": "Für diesen Artikel läuft bereits ein Auftrag."}
    try:
        z = zustand(ctx, slug)
        if not z or z.get("status") != "uebernommen" or not z.get("backup"):
            return {"ok": False, "meldung": "Es gibt keine Übernahme, die sich rückgängig machen lässt."}
        backup = Path(z["backup"])
        # nur Backups aus dem eigenen Backup-Ordner zulassen
        erlaubt = (ctx.root / "data" / "backups" / "artikel").resolve()
        if not backup.exists() or erlaubt not in backup.resolve().parents:
            return {"ok": False, "meldung": "Das Backup wurde nicht gefunden."}
        pfad = ctx.artikel_pfad(slug)
        versionen.vor_schreiben(ctx.root, slug)
        inhalt = backup.read_bytes()  # zuerst lesen: das Rueckgaengig-Backup darf es nie ueberschreiben
        aktuell_sicherung = ctx.speicher.artikel_sichern(pfad)  # Rueckgaengig ist selbst umkehrbar
        pfad.write_bytes(inhalt)
        try:
            ok, log = ctx.baue()
        except Exception as exc:
            ok, log = False, f"{type(exc).__name__}: {exc}"
        if not ok:
            shutil.copy2(aktuell_sicherung, pfad)
            try:
                ctx.baue()
            except Exception:
                pass
            return {"ok": False, "meldung": "Build nach dem Rückgängigmachen fehlgeschlagen – vorheriger Stand wiederhergestellt: " + log[-400:]}
        versionen.nach_schreiben(ctx.root, slug, "rueckgaengig")
        z["status"] = "rueckgaengig"
        z["rueckgaengig_am"] = _jetzt()
        try:
            _m, b = ctx.bewerte(slug)
            z["nachher"] = schnappschuss(b)
        except Exception:
            pass
        _sichern(ctx, slug, z)
        return {"ok": True, "meldung": "Rückgängig gemacht: Backup zurückgespielt und neu gebaut.", "backup": str(aktuell_sicherung)}
    finally:
        sperre_freigeben(slug)


# --------------------------------------------------------------------------
# Auswertung Vorher/Nachher
# --------------------------------------------------------------------------


def vergleich(vorher: dict, nachher: dict | None) -> list[dict]:
    zeilen = []
    for k, v in vorher["kategorien"].items():
        n = (nachher or {}).get("kategorien", {}).get(k)
        zeilen.append({"kat": k, "name": v["name"], "vorher": v["score"], "vorher_ampel": v["ampel"],
                       "nachher": n["score"] if n else None, "nachher_ampel": n["ampel"] if n else None})
    return zeilen


def kriterien_aenderungen(vorher: dict, nachher: dict | None) -> list[dict]:
    if not nachher:
        return []
    erg = []
    for kid, v in vorher["kriterien"].items():
        n = nachher["kriterien"].get(kid)
        if n and (n["status"] != v["status"] or n["messwert"] != v["messwert"]):
            erg.append({"id": kid, "name": v["name"], "kat": v["kat"], "vorher": v["status"], "nachher": n["status"],
                        "messwert_vorher": v["messwert"], "messwert_nachher": n["messwert"]})
    return erg


def was_fehlt(z: dict, nachher: dict | None) -> list[dict]:
    """Ehrliche Liste: was bleibt nicht gruen und warum. art = behebbar (ein weiterer Durchlauf kann es versuchen) | mensch."""
    if not nachher:
        return []
    erg = []
    for kid, v in nachher["kriterien"].items():
        if v["status"] not in ("teils", "nein"):
            continue
        bereich = AUTOMATISCH.get(kid)
        if bereich == "build":
            grund, art = "Wird durch Bauen behoben – nach dem Bauen weiterhin offen: bitte Deploy-Seite prüfen.", "mensch"
        elif bereich in ("metas", "text", "links"):
            art = "behebbar"
            grund = ("Der Durchlauf hat es nicht ganz erreicht, oder du hast Vorschläge abgewählt. "
                     "„Noch ein Durchlauf“ versucht es erneut; verbleibende Reste sind Handarbeit.")
            if kid == "a_alt":
                grund += " Der Alt-Text wirkt nur mit gesetztem og_image."
        else:
            art, grund = "mensch", MENSCH.get(kid, "Nicht automatisch behebbar – bitte von Hand prüfen.")
        erg.append({"id": kid, "name": v["name"], "kat": v["kat"], "status": v["status"], "messwert": v["messwert"], "grund": grund, "art": art})
    return erg


# --------------------------------------------------------------------------
# Frueher Version wiederherstellen
# --------------------------------------------------------------------------


def wiederherstellen(ctx: Kontext, slug: str, vid: str) -> dict:
    """Stellt eine fruehere Fassung (Frontmatter und Text) wieder her. Ablauf wie uebernehmen():
    aktuelle Fassung als Version sichern -> schreiben -> bauen -> pruefen -> neu bewerten.
    Bei Build-Fehler oder fehlendem Pflicht-Meta-Tag wird zurueckgerollt."""
    if not sperre_nehmen(slug):
        return {"ok": False, "meldung": "Für diesen Artikel läuft bereits ein Auftrag."}
    try:
        pfad = ctx.artikel_pfad(slug)
        zeile = versionen.zeile(ctx.root, slug, vid)
        text = versionen.text_von(ctx.root, slug, vid)
        if zeile is None or text is None:
            return {"ok": False, "meldung": "Diese Version wurde nicht gefunden."}
        fehler = versionen.frontmatter_gueltig(text, slug)
        if fehler:
            return {"ok": False, "meldung": f"Nicht wiederherstellbar: {fehler}."}
        alt = pfad.read_text(encoding="utf-8")
        if alt == text:
            return {"ok": False, "meldung": "Das ist bereits die aktuelle Fassung."}
        try:
            vorher = schnappschuss(ctx.bewerte(slug)[1])
        except Exception:
            vorher = None
        versionen.vor_schreiben(ctx.root, slug)
        backup = ctx.speicher.artikel_sichern(pfad)
        _schreibe_atomar(pfad, text)
        grund = ""
        try:
            ok, log = ctx.baue()
        except Exception as exc:
            ok, log = False, f"{type(exc).__name__}: {exc}"
        if not ok:
            grund = "Build fehlgeschlagen: " + log[-600:]
        else:
            fehlt = ctx.pflicht_fehlt(slug)
            if fehlt:
                grund = "Pflicht-Meta-Tag(s) fehlen nach dem Bauen: " + ", ".join(fehlt)
        if grund:
            ok2, f2 = _wiederherstellen(ctx, pfad, backup)
            return {"ok": False, "zurueckgespielt": True,
                    "meldung": grund + " – die bisherige Fassung wurde automatisch zurückgespielt." + ("" if ok2 else " " + f2)}
        versionen.nach_schreiben(ctx.root, slug, "wiederhergestellt", f"Fassung vom {zeile['zeit'].replace('T', ' ')[:16]}")
        nachher = None
        try:
            nachher = schnappschuss(ctx.bewerte(slug)[1])
        except Exception:
            pass
        z = {"id": uuid.uuid4().hex[:12], "slug": slug, "status": "wiederhergestellt", "gestartet": _jetzt(),
             "uebernommen_am": _jetzt(), "schritte": [], "vorher": vorher, "nachher": nachher, "backup": str(backup),
             "wiederhergestellt": {"vid": vid, "zeit": zeile["zeit"], "label": zeile["label"]}}
        if vorher:
            _sichern(ctx, slug, z)
        return {"ok": True, "meldung": f"Fassung vom {zeile['zeit'].replace('T', ' ')[:16]} wiederhergestellt, gebaut und neu bewertet."}
    finally:
        sperre_freigeben(slug)
