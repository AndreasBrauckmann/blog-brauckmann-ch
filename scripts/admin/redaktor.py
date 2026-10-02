"""Quick-Redaktor: LinkedIn-Beitragstexte messen und (optional) behutsam verbessern.

Reine Logik ohne Flask (Seite: redaktor_views.py). Wiederverwendet werden die Bausteine der Verwaltung:

- ki_muster.messe / erfuellung   (Gedankenstriche, „nicht X, sondern Y“, Floskeln, Verstärker, Rhythmus)
- bewertung.amstad / saetze / woerter / linear / haken_in   (Lesbarkeit, Satzlänge)
- plattformen.linkedin_kachel und die LinkedIn-Konstanten (140/210 sichtbar, 300 Karte, 3000 hart)
- in_ordnung._zahlen / _urls / _FACH / klartext   (Schutzprüfung: Zahlen, Links, Fachbegriffe)
- llm.chat + Modellwahl (Aufgabe „text_umschreiben“ = starke Stufe, einmalige Eskalation)

Datenschutz: Eingegebene Texte werden NIE gespeichert oder protokolliert. Die einzige Datei, die dieses
Modul schreibt, ist der anonymisierte Zähler data/redaktor/zaehler.json (Datum, Länge, Modus, Dauer,
Modell, Punktzahlen; keine Texte, keine IP-Adressen). Auch die Fehlerablage von llm.json_aus_text
(data/ranking/llm_fehler/) wird hier bewusst NICHT benutzt, weil die Rohantwort den Text enthielte.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import threading
import time
from collections import Counter, deque
from datetime import date, datetime
from pathlib import Path

import bewertung as bw
import ki_muster
import llm
import plattformen as pf

ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------
# Einstellungen (alle aus der .env, mit sicheren Vorgaben)
# --------------------------------------------------------------------------


def _int_env(name: str, vorgabe: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "").strip() or vorgabe))
    except ValueError:
        return vorgabe


def einstellungen() -> dict:
    return {
        "code": os.environ.get("REDAKTOR_CODE", "").strip(),
        # Nur der ausdrueckliche Wert „abo“ schaltet das LLM ein; alles andere (auch leer) = aus.
        "llm_modus": "abo" if os.environ.get("REDAKTOR_LLM_MODUS", "").strip().lower() == "abo" else "aus",
        "limit_stunde_ip": _int_env("REDAKTOR_LIMIT_STUNDE_IP", 20),
        "limit_tag": _int_env("REDAKTOR_LIMIT_TAG", 150),
        "max_zeichen": _int_env("REDAKTOR_MAX_ZEICHEN", 3500),
        "llm_timeout": _int_env("REDAKTOR_LLM_TIMEOUT", 150),
        "fehlversuche_stunde": _int_env("REDAKTOR_FEHLVERSUCHE_STUNDE", 10),
    }


def llm_verfuegbar() -> tuple[bool, str]:
    e = einstellungen()
    if e["llm_modus"] != "abo":
        return False, "Die Verbesserung per KI ist ausgeschaltet. Verfügbar ist nur „Nur prüfen“."
    if not llm.llm_status()["aktiv"]:
        return False, "Die KI ist nicht eingerichtet. Verfügbar ist nur „Nur prüfen“."
    return True, ""


MODI = {
    "behutsam": "Behutsam",
    "straffen": "Straffen",
    "pruefen": "Nur prüfen",
}
ZIELE = (300, 600, 1300)
WARTEZEITEN = (5, 15)  # Wiederholung bei Verbindungsfehlern; kuerzer als in der Verwaltung, weil jemand vor der Seite wartet

# --------------------------------------------------------------------------
# Zerlegen
# --------------------------------------------------------------------------

HASHTAG = re.compile(r"(?<![\w&/#])#([A-Za-zÄÖÜäöüß0-9_][\wÄÖÜäöüß]*)")
ERWAEHNUNG = re.compile(r"(?<![\w@])@[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß.\-]*[\wÄÖÜäöüß]")
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+[^\s<>\"')\].,;:!?]")
ZITAT = re.compile(r"„[^“\n]{1,400}“|\"[^\"\n]{1,400}\"|»[^«\n]{1,400}«")
UNICODE_FETT = re.compile(r"[\U0001D400-\U0001D7FF]")
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")
MARKDOWN = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__|^#{1,6}\s+\S|\[[^\]\n]+\]\([^)\s]+\)|(?<![\w*])\*[^*\s][^*\n]*\*(?![\w*])", re.M)
NUR_HASHTAGS = re.compile(r"^\s*(?:#[\wÄÖÜäöüß]+[\s,]*)+$")
NUR_URL = re.compile(r"^\s*(?:" + URL.pattern + r")\s*$")


def normalisiere(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def teile_fuss(text: str) -> tuple[str, str]:
    """(Rumpf, Fuss). Fuss = die letzten Zeilen, die nur aus Hashtags, einer URL oder Leerraum bestehen.
    Nach der Hausregel steht die Adresse im Textabsatz, also im Rumpf; im Fuss bleiben die Hashtags."""
    zeilen = text.rstrip().split("\n")
    i = len(zeilen)
    while i > 0 and (not zeilen[i - 1].strip() or NUR_HASHTAGS.match(zeilen[i - 1]) or NUR_URL.match(zeilen[i - 1])):
        i -= 1
    return "\n".join(zeilen[:i]).rstrip(), "\n".join(zeilen[i:]).strip()


TAG_KETTE_ENDE = re.compile(r"(?:[ \t]+#[A-Za-zÄÖÜäöüß0-9_][\wÄÖÜäöüß]*)+[ \t]*$")


def _tag_kette_am_ende(zeile_oder_text: str) -> str:
    """Hashtag-Kette am Ende der (letzten) Zeile, z. B. „… arbeitet. #Cloud #KI“ -> „ #Cloud #KI“."""
    letzte = zeile_oder_text.rstrip().split("\n")[-1] if zeile_oder_text.strip() else ""
    m = TAG_KETTE_ENDE.search(letzte)
    return m.group(0) if m and letzte[:m.start()].strip() else ""


def absaetze(text: str) -> list[str]:
    return [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]


def prosa_bloecke(text: str) -> list[str]:
    """Zeilen mit Fliesstext (ohne Hashtag-/URL-Zeilen), URLs und Hashtag-Zeichen entfernt - fuer die Sprachmessung.
    Jede Zeile ist ein eigener Block: LinkedIn-Texte setzen oft einen Satz je Zeile ohne Punkt."""
    erg = []
    for z in text.split("\n"):
        if not z.strip() or NUR_HASHTAGS.match(z) or NUR_URL.match(z):
            continue
        z = URL.sub(" ", z)
        z = HASHTAG.sub(lambda m: m.group(1), z)
        z = re.sub(r"\s+", " ", z).strip()
        if bw.woerter(z):
            erg.append(z)
    return erg


def _url_zeilen(text: str) -> list[int]:
    return [i for i, z in enumerate(text.split("\n")) if URL.search(z)]


# --------------------------------------------------------------------------
# Messen: Prüfliste mit Messwert, Soll, Stufe und Punktzahl 0-100
# --------------------------------------------------------------------------


def _p(pid, name, erfuellung, messwert, soll, gewicht, etikett, handgriff="", stufe=None, info=False) -> dict:
    e = max(0.0, min(100.0, float(erfuellung)))
    if stufe is None:
        stufe = "ok" if e >= 85 else ("warn" if e >= 50 else "fehler")
    return {"id": pid, "name": name, "erfuellung": round(e, 1), "messwert": messwert, "soll": soll, "gewicht": gewicht,
            "etikett": etikett, "handgriff": handgriff if stufe != "ok" else "", "stufe": stufe, "info": info}


def _zahl(x: float, n: int = 1) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def aufbau_befund(t: str) -> dict:
    """Hausregel (1.10.2026): Die Adresse steht DIREKT hinter dem Text im selben Absatz (nach einem Leerzeichen), danach eine
    Leerzeile, dann die Hashtags gesammelt in der letzten Zeile. Gründe: Die Adresse steht dort, wo das Auge nach dem Lesen
    hinfällt; Hashtags sind das Unwichtigste; die Leerzeile verhindert am Handy, dass man ein Hashtag statt der Adresse antippt."""
    abs_ = absaetze(t)
    urls = URL.findall(t)
    hat_tags = bool(HASHTAG.findall(t))
    tags_zuletzt = (not hat_tags) or bool(abs_ and NUR_HASHTAGS.match(abs_[-1]))
    text_abs = abs_[:-1] if hat_tags and tags_zuletzt else abs_
    ziel = text_abs[-1] if text_abs else ""
    am_ende = len(urls) == 1 and bool(re.search(r"\S[ \t]+(?:" + URL.pattern + r")\s*$", ziel))
    allein = len(urls) == 1 and bool(NUR_URL.match(ziel))
    if not tags_zuletzt:
        return {"erfuellung": 30, "messwert": "Hashtags nicht gesammelt in der letzten Zeile",
                "handgriff": "Hashtags gesammelt in die letzte Zeile setzen, mit einer Leerzeile davor; die Adresse steht direkt hinter dem Text."}
    if am_ende:
        return {"erfuellung": 100, "messwert": "Adresse am Ende des Textes" + (", Hashtags zuletzt" if hat_tags else ""), "handgriff": ""}
    if allein:
        return {"erfuellung": 60, "messwert": "Adresse allein in eigener Zeile",
                "handgriff": "Die Adresse direkt hinter den letzten Satz setzen (ein Leerzeichen davor), nicht in eine eigene Zeile."}
    return {"erfuellung": 30, "messwert": f"{len(urls)} Adresse(n), nicht am Ende des Textes",
            "handgriff": "Die Adresse aus dem Satz nehmen und direkt hinter den letzten Satz setzen; im Satz genügt „(Link am Ende)“."}


def messen(text: str) -> dict:
    """Alle Prüfungen eines Beitragstexts. Deterministisch, ohne KI. Ergebnis: {pruefungen, punkte, kennzahlen, kachel}."""
    text = normalisiere(text)
    t = text.strip()
    n = len(t)
    rumpf, fuss = teile_fuss(t)
    tags = HASHTAG.findall(t)
    tags_fuss = HASHTAG.findall(fuss) + HASHTAG.findall(_tag_kette_am_ende(rumpf))
    urls = URL.findall(t)
    zeilen = t.split("\n")
    url_zeilen = _url_zeilen(t)
    letzte_zeile = len(zeilen) - 1
    prosa = prosa_bloecke(rumpf)
    lb = bw.amstad(prosa)
    alle_s = [s for b in prosa for s in bw.saetze(b)]
    lang = [s for s in alle_s if len(bw.woerter(s)) > 25]
    anteil_lang = 100 * len(lang) / len(alle_s) if alle_s else 0.0
    abs_woerter = [len(bw.woerter(URL.sub(" ", a))) for a in absaetze(rumpf)]
    km = ki_muster.messe(prosa) if prosa else None
    p: list[dict] = []

    # 1. Zeichenlimit (belegt)
    p.append(_p("limit", "Zeichenlimit", 100 if n <= pf.LINKEDIN_HART else 0, f"{n} Zeichen", f"höchstens {pf.LINKEDIN_HART:,}".replace(",", "."),
                12, "belegt", f"Um mindestens {n - pf.LINKEDIN_HART} Zeichen kürzen, sonst nimmt LinkedIn den Beitrag nicht an.",
                stufe="ok" if n <= pf.LINKEDIN_HART else "fehler"))

    # 2. Haken in den ersten 140 Zeichen (Praxis)
    vorn = t[:pf.LINKEDIN_SICHTBAR_MOBIL]
    erster = (bw.saetze(prosa[0])[0] if prosa and bw.saetze(prosa[0]) else (prosa[0] if prosa else ""))
    ende_erster = t.find(erster[-20:]) + len(erster[-20:]) if erster else 0
    signal, grund = bw.haken_in(vorn)
    satz_ok = 0 < ende_erster <= pf.LINKEDIN_SICHTBAR_MOBIL
    e = (60 if signal else 15) + (40 if satz_ok else 0)
    p.append(_p("haken", "Haken vor „…mehr“ (erste 140 Zeichen)", e,
                f"erster Satz endet bei Zeichen {ende_erster}; {grund}", "erster Satz endet vor Zeichen 140 und nennt Zahl, Problem oder Nutzen",
                12, "praxis", "Den wichtigsten Gedanken (Zahl, Problem, Ergebnis) in einen ersten Satz unter 140 Zeichen ziehen; Begrüßung und Anlauf streichen."))

    # 3. Hashtags: höchstens 3 (Hausregel, nicht geprüft)
    nt = len(tags)
    p.append(_p("hashtags", "Hashtags höchstens 3", bw.linear(nt, 3, 8), f"{nt} Hashtags", "höchstens 3", 6, "ungeprueft",
                f"Auf die 3 treffendsten kürzen ({', '.join('#' + x for x in tags[:3])}), den Rest streichen." if nt > 3 else ""))

    # 4. Hashtags am Ende
    mitten = nt - len(tags_fuss)
    p.append(_p("hashtags_ende", "Hashtags am Ende", 100 if mitten == 0 else 30, "alle am Ende" if mitten == 0 else f"{mitten} im Text verstreut",
                "Hashtags gesammelt in der letzten Zeile", 4, "ungeprueft",
                "Hashtags aus den Sätzen nehmen (das Wort bleibt stehen) und gesammelt ans Ende setzen."))

    # 5. Aufbau: Adresse direkt hinter dem Text (selber Absatz), Leerzeile, Hashtags zuletzt (Hausregel ab 1.10.2026)
    if not urls:
        p.append(_p("link", "Adresse im Textabsatz, Hashtags zuletzt", 100, "keine Adresse",
                    "Adresse, falls nötig, direkt hinter dem Text; Leerzeile; Hashtags in der letzten Zeile", 6, "ungeprueft"))
    else:
        befund = aufbau_befund(t)
        p.append(_p("link", "Adresse im Textabsatz, Hashtags zuletzt", befund["erfuellung"], befund["messwert"],
                    "Adresse direkt hinter dem Text im selben Absatz; Leerzeile; Hashtags gesammelt in der letzten Zeile", 6, "ungeprueft",
                    befund["handgriff"]))
        karte_ok = n <= pf.LINKEDIN_KARTE_MAX
        p.append(_p("karte", "Link-Karte in der Profil-Übersicht", 100 if karte_ok else 55, f"{n} Zeichen mit Adresse",
                    f"höchstens {pf.LINKEDIN_KARTE_MAX} Zeichen, damit die Karte erscheint", 3, "praxis",
                    "Die Link-Karte erschien in der Profil-Übersicht nur bei kurzem Text (Praxisbefund). Ob die Stelle der Adresse dafür eine "
                    "Rolle spielt, ist nicht belegt (Annahme: LinkedIn nimmt die erste Adresse). Für Klicks: kurz fassen."))

    # 6. Kurze Absätze (Hausregel)
    am = max(abs_woerter) if abs_woerter else 0
    p.append(_p("absaetze", "Kurze Absätze", bw.linear(am, 50, 120), f"längster Absatz {am} Wörter ({len(abs_woerter)} Absätze)",
                "höchstens 50 Wörter je Absatz, Leerzeile dazwischen", 8, "ungeprueft",
                "Die Textwand an jedem Gedankenwechsel mit einer Leerzeile teilen; ein Absatz = ein Gedanke."))

    # 7. Kein Markdown
    md = MARKDOWN.findall(t)
    p.append(_p("markdown", "Kein Markdown", 100 if not md else 20, f"{len(md)} Markdown-Auszeichnung(en)" if md else "keins",
                "keine **Sterne**, # Rauten am Zeilenanfang oder [Text](Link)", 5, "ungeprueft",
                "LinkedIn zeigt **fett** als Sterne an: Sterne entfernen, Betonung über Satzstellung erreichen."))

    # 8. Unicode-„Fett“
    uf = len(UNICODE_FETT.findall(t))
    p.append(_p("unicode_fett", "Kein Unicode-„Fett“", 100 if not uf else 30, f"{uf} Sonderzeichen" if uf else "keins",
                "normale Buchstaben", 3, "ungeprueft",
                "Unicode-„Fett“ (𝐁𝐞𝐢𝐬𝐩𝐢𝐞𝐥) durch normale Buchstaben ersetzen: Screenreader lesen es oft Zeichen für Zeichen oder gar nicht vor, und die Suche findet die Wörter nicht."))

    # 9. Doppelte Leerzeilen
    dl = len(re.findall(r"\n[ \t]*\n[ \t]*\n", t))
    p.append(_p("leerzeilen", "Keine doppelten Leerzeilen", 100 if not dl else 50, f"{dl} Stelle(n)" if dl else "keine", "eine Leerzeile zwischen Absätzen", 2,
                "ungeprueft", "Mehrere Leerzeilen hintereinander auf eine reduzieren."))

    # 10. Klingt menschlich (KI-Muster)
    if km:
        erf, mw, tipp = ki_muster.erfuellung(km)
        absolut = ", ".join(f"{r['name']} {km[r['id']]['anzahl']}" for r in ki_muster.REGELN if r["gewicht"] and km[r["id"]]["anzahl"])
        p.append(_p("ki_muster", "Klingt menschlich (KI-Muster)", erf, (absolut or "keine Treffer") + f" bei {km['woerter']} Wörtern",
                    "Gedankenstriche ≤ 4, Floskeln ≤ 2, Verstärker ≤ 6 je 1.000 Wörter; „nicht X, sondern Y“ ≤ 1", 15, "ungeprueft", tipp))

    # 11.-13. Lesbarkeit (Projektregeln)
    if lb["woerter"]:
        p.append(_p("amstad", "Lesbarkeit (Amstad)", bw.linear(lb["index"], 50, 20), _zahl(lb["index"]), "mindestens 50", 10, "ungeprueft",
                    "Kürzere Wörter und Sätze: zusammengesetzte Wörter auflösen, Fachwörter erklären."))
        p.append(_p("satzlaenge", "Mittlere Satzlänge", bw.linear(lb["asl"], 17, 28), f"{_zahl(lb['asl'])} Wörter", "höchstens 17 Wörter", 8, "ungeprueft",
                    "Lange Sätze am Komma teilen; je Satz ein Gedanke."))
        bsp = f" Längster: „{max(lang, key=lambda s: len(bw.woerter(s)))[:90]}…“" if lang else ""
        p.append(_p("lange_saetze", "Sehr lange Sätze (> 25 Wörter)", bw.linear(anteil_lang, 10, 35), f"{len(lang)} von {len(alle_s)}",
                    "höchstens 10 %", 5, "ungeprueft", "Sätze über 25 Wörter teilen." + bsp))

    # Nur Hinweise (keine Punkte)
    em = len(EMOJI.findall(t))
    p.append(_p("emojis", "Emojis", 100, f"{em}", "keine Regel", 0, "ungeprueft",
                "Emojis sind Geschmackssache. Screenreader lesen jedes Emoji mit seinem Namen vor; als Aufzählungszeichen stören sie beim Vorlesen.",
                stufe="info" if em else "ok", info=True))
    art = "Link-Beitrag (mit Karte, falls kurz)" if urls else "Text-Beitrag (ohne Link)"
    p.append(_p("art", "Beitragsart", 100, art, "bewusst wählen", 0, "praxis",
                "Text-Beitrag: lebt vom Text im Feed. Link-Beitrag: lebt von der Karte; die erschien in der Profil-Übersicht nur bei kurzem Text (Praxisbefund).",
                stufe="info", info=True))

    gewicht = sum(x["gewicht"] for x in p if not x["info"]) or 1
    punkte = round(sum(x["gewicht"] * x["erfuellung"] for x in p if not x["info"]) / gewicht)
    if n > pf.LINKEDIN_HART:
        punkte = min(punkte, 49)  # ueber dem harten Limit nie „gut“
    kachel = pf.linkedin_kachel(t, bool(urls))
    return {"pruefungen": p, "punkte": punkte, "zeichen": n, "woerter": lb["woerter"], "kachel": kachel,
            "domain": _domain(urls[0]) if urls else "", "hashtags": tags, "urls": urls}


def _domain(url: str) -> str:
    u = re.sub(r"^https?://", "", url)
    return u.split("/")[0].removeprefix("www.")


# --------------------------------------------------------------------------
# Feste (regelbasierte) Korrekturen, ohne KI
# --------------------------------------------------------------------------


def feste_korrekturen(text: str, aufbau_erlaubt: bool) -> tuple[str, list[dict]]:
    """Markdown-Sterne entfernen, Mehrfach-Leerzeilen zusammenziehen; mit Erlaubnis zusätzlich Links und Hashtags ans Ende,
    Hashtags auf 3. Liefert (Text, Änderungen [{was, grund, quelle}])."""
    t = normalisiere(text).strip()
    aend: list[dict] = []
    neu = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", t)
    neu = re.sub(r"__([^_\n]+)__", r"\1", neu)
    neu = re.sub(r"^#{1,6}\s+(?=\S)", "", neu, flags=re.M)
    if neu != t:
        aend.append({"was": "Markdown-Sterne und -Rauten entfernt", "grund": "LinkedIn zeigt **fett** als Sterne an.", "quelle": "Regel"})
        t = neu
    if UNICODE_FETT.search(t):
        import unicodedata
        neu = UNICODE_FETT.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), t)
        aend.append({"was": "Unicode-„Fett“ in normale Buchstaben zurückverwandelt",
                     "grund": "Screenreader lesen solche Sonderzeichen oft nicht als Wort vor, und die Suche findet sie nicht.", "quelle": "Regel"})
        t = neu
    neu = re.sub(r"[ \t]+\n", "\n", t)
    neu = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", neu)
    if neu != t:
        aend.append({"was": "Mehrfache Leerzeilen auf eine reduziert", "grund": "Große Lücken wirken im Feed wie ein Fehler.", "quelle": "Regel"})
        t = neu
    if not aufbau_erlaubt:
        return t, aend

    rumpf, fuss = teile_fuss(t)
    # Links aus dem Fliesstext ans Ende
    urls_rumpf = URL.findall(rumpf)
    fuss_urls = URL.findall(fuss)
    am_ende = re.search(r"\S[ \t]+(" + URL.pattern + r")\s*$", rumpf)
    if urls_rumpf and not (len(urls_rumpf) == 1 and am_ende):
        rumpf = URL.sub("(Link am Ende)", rumpf)
        rumpf = re.sub(r"\(Link am Ende\)\s*([.,;:!?])", r"(Link am Ende)\1", rumpf)
        aend.append({"was": f"{len(urls_rumpf)} Adresse(n) aus dem Satz ans Ende des Textes verschoben, im Satz steht „(Link am Ende)“",
                     "grund": "Eine Adresse mitten im Satz unterbricht das Lesen; direkt hinter dem Text fällt das Auge nach dem Lesen auf sie.", "quelle": "Regel"})
    elif urls_rumpf:
        rumpf = rumpf[:am_ende.start(1)].rstrip()  # steht schon richtig; wird unten unverändert wieder angehängt
    if fuss_urls:
        aend.append({"was": "Adresse aus der eigenen Zeile direkt hinter den Text gesetzt",
                     "grund": "Die Adresse gehört in den Textabsatz; die Hashtags kommen nach einer Leerzeile zuletzt.", "quelle": "Regel"})
    alle_urls = list(dict.fromkeys(urls_rumpf + fuss_urls))
    # Hashtags: aus Sätzen lösen, sammeln, auf 3 kürzen
    tags_rumpf = HASHTAG.findall(rumpf)
    tags_fuss = HASHTAG.findall(fuss)
    if tags_rumpf:
        rumpf_zeilen, verschoben, geloest = [], 0, 0
        for z in rumpf.split("\n"):
            if NUR_HASHTAGS.match(z):
                verschoben += len(HASHTAG.findall(z))
                continue
            kette = TAG_KETTE_ENDE.search(z)
            if kette and z[:kette.start()].strip():
                verschoben += len(HASHTAG.findall(kette.group(0)))
                z = z[:kette.start()].rstrip()
            geloest += len(HASHTAG.findall(z))
            rumpf_zeilen.append(HASHTAG.sub(lambda m: m.group(1), z))
        rumpf = re.sub(r"\n\s*\n(?:\s*\n)+", "\n\n", "\n".join(rumpf_zeilen)).strip()
        if verschoben:
            aend.append({"was": f"{verschoben} Hashtag(s) gesammelt ans Ende gesetzt",
                         "grund": "Hashtags gehören gesammelt in die letzte Zeile, nicht an den Satz.", "quelle": "Regel"})
        if geloest:
            aend.append({"was": f"{geloest} Hashtag(s) mitten im Satz aufgelöst (das Wort bleibt stehen, der Hashtag steht am Ende)",
                         "grund": "Rauten mitten im Satz stören den Lesefluss.", "quelle": "Regel"})
    alle_tags = list(dict.fromkeys(tags_rumpf + tags_fuss))
    behalten = alle_tags[:3]
    if len(alle_tags) > 3:
        aend.append({"was": f"Hashtags von {len(alle_tags)} auf 3 gekürzt (behalten: {', '.join('#' + x for x in behalten)}; "
                            f"gestrichen: {', '.join('#' + x for x in alle_tags[3:])})",
                     "grund": "Mehr als 3 Hashtags wirken wie Werbung. Behalten wurden die ersten drei; bitte prüfen, ob es die treffendsten sind.",
                     "quelle": "Regel"})
    text = rumpf.strip()
    if alle_urls:
        text = (text + " " + " ".join(alle_urls)).strip()
    teile = [text]
    if behalten:
        teile.append(" ".join("#" + x for x in behalten))
    return "\n\n".join(x for x in teile if x), aend


# --------------------------------------------------------------------------
# Schutzprüfung (Ideen aus in_ordnung.schutzpruefung_stelle, für Beitragstexte)
# --------------------------------------------------------------------------


def _io():
    import in_ordnung  # spaet: zieht versionen/metas_auswahl nach
    return in_ordnung


def _liste(c) -> str:
    items = sorted(c.elements()) if hasattr(c, "elements") else sorted(c)
    return ", ".join(f"„{x}“" for x in items[:4]) + (" …" if len(items) > 4 else "")


def schutzpruefung(alt: str, neu: str, *, weglassen_erlaubt: bool = False, min_anteil: float = 0.6) -> list[str]:
    """Gründe in einfacher Sprache, warum eine Änderung verworfen wird. Leer = in Ordnung.
    Geschützt: Zahlen, Links, @-Erwähnungen, Hashtags, Fachbegriffe/Namen mit Großbuchstaben im Wort oder Ziffern,
    wörtliche Zitate. weglassen_erlaubt (Modus „Straffen“): Weglassen ist erlaubt, Erfinden und Ändern nie."""
    io = _io()
    v: list[str] = []
    if not neu.strip():
        return ["Die KI hat keinen Text geliefert."]

    def vergleich(name: str, a: Counter, b: Counter, regel: str) -> None:
        neu_dazu, fehlt = b - a, (a - b if not weglassen_erlaubt else Counter())
        teile = ([f"neu: {_liste(neu_dazu)}"] if neu_dazu else []) + ([f"fehlt: {_liste(fehlt)}"] if fehlt else [])
        if teile:
            v.append(f"{name} verändert ({'; '.join(teile)}). {regel}")

    vergleich("Zahlen", io._zahlen(alt), io._zahlen(neu), "Zahlen dürfen nicht verändert, ergänzt oder weggelassen werden.")
    vergleich("Links", Counter(URL.findall(alt)), Counter(URL.findall(neu)), "Links bleiben, wie sie sind.")
    vergleich("Erwähnungen", Counter(ERWAEHNUNG.findall(alt)), Counter(ERWAEHNUNG.findall(neu)), "@-Erwähnungen bleiben, wie sie sind.")
    vergleich("Hashtags", Counter(HASHTAG.findall(alt)), Counter(HASHTAG.findall(neu)), "Hashtags bleiben, wie sie sind.")
    vergleich("Namen/Fachbegriffe", Counter(set(io._FACH.findall(io.klartext(alt)))), Counter(set(io._FACH.findall(io.klartext(neu)))),
              "Namen und Fachbegriffe bleiben wie im Original.")
    vergleich("Zitate", Counter(ZITAT.findall(alt)), Counter(ZITAT.findall(neu)), "Wörtliche Zitate bleiben unverändert.")
    if not weglassen_erlaubt:
        wa, wn = len(bw.woerter(alt)), len(bw.woerter(neu))
        if wn > 1.3 * wa + 6:
            v.append(f"Die Stelle ist deutlich länger geworden ({wa} → {wn} Wörter); die KI könnte etwas hinzugedichtet haben.")
        if wn < min_anteil * wa - 2:
            v.append(f"Die Stelle ist deutlich kürzer geworden ({wa} → {wn} Wörter); es könnte Inhalt verloren gegangen sein.")
    return v


# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------

SYSTEM = """Du bist eine erfahrene Lektorin für deutschsprachige LinkedIn-Beiträge von Fachleuten.
Du verbesserst fremde Texte behutsam: Die Stimme, die Aussage und die Wortwahl des Autors bleiben erhalten.
Du erfindest nie Fakten, Zahlen, Namen oder Zitate und änderst keine. Du machst keine Aussagen über Reichweite, Algorithmus oder Sichtbarkeit bei LinkedIn. Links, @-Erwähnungen, Hashtags und Zitate in Anführungszeichen fasst du nicht an.
""" + llm.KI_MUSTER_REGELN + """
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. In den Werten verwendest du für Anführungszeichen nur „…“ oder ‚…‘, nie gerade Anführungszeichen."""


def prompt_behutsam(rumpf: str, offene: list[str]) -> str:
    return f"""Verbessere diesen LinkedIn-Beitrag behutsam. Behebe nur:
- Rechtschreib-, Grammatik- und Zeichensetzungsfehler,
- KI-Muster nach den Regeln oben (Gedankenstriche, „nicht X, sondern Y“, Floskeln, Verstärker, gleich lange Satzfolgen),
- schwere Lesbarkeit: Sätze über 20 Wörter teilen, Textwände mit Leerzeilen in kurze Absätze gliedern,
- einen schwachen Anfang: der erste Satz soll den Kern (Zahl, Problem, Ergebnis) in höchstens 140 Zeichen tragen, falls der Text das hergibt.
Die Gesamtlänge bleibt innerhalb von ±15 %. Lieber wenige gute Änderungen als viele.

Gemessene Schwächen: {'; '.join(offene) or 'keine'}
„(Link am Ende)“ verweist auf die Adresse am Ende des Textes. Diese Adresse bleibt wörtlich und an ihrer Stelle; die Hashtags am Ende bekommst du nicht zu sehen.

Liefere jede Änderung einzeln:
- "alt": ein WÖRTLICHER Ausschnitt aus dem Text (Zeichen für Zeichen kopiert, eindeutig, höchstens 2 Sätze),
- "neu": der Ersatz; um einen Absatz zu teilen, setze eine Leerzeile (\\n\\n). Nichts ersatzlos streichen,
- "grund": ein kurzer Satz in einfacher Sprache, warum,
- "art": "fehler" | "ki_muster" | "lesbarkeit" | "absatz" | "anfang".
Unter "offen" nennst du höchstens 3 Schwächen, die du NICHT beheben darfst (z. B. fehlende Belege, unklare Aussage), je mit einem konkreten Handgriff für den Autor.

Text:
<<<
{rumpf}
>>>

Antworte nur mit diesem JSON:
{{"aenderungen": [{{"alt": "...", "neu": "...", "grund": "...", "art": "..."}}], "offen": [{{"problem": "...", "handgriff": "..."}}]}}"""


def prompt_straffen(rumpf: str, ziel: int, rueckmeldung: str = "") -> str:
    return f"""Kürze diesen LinkedIn-Beitrag auf höchstens {ziel} Zeichen (zähle sorgfältig, lieber kürzer).
- Die Stimme und Wortwahl des Autors bleiben erhalten; der Kern kommt in den ersten Satz (höchstens 140 Zeichen).
- Du darfst Nebensächliches weglassen, aber nichts hinzufügen: keine neuen Fakten, Zahlen, Namen, Zitate.
- Links, @-Erwähnungen, Hashtags und Zitate in Anführungszeichen bleiben wörtlich stehen, wenn du sie behältst.
- Kurze Absätze mit Leerzeilen, kein Markdown, keine Emojis hinzufügen.
- „(Link am Ende)“ verweist auf die Adresse am Ende des Textes. Diese Adresse bleibt wörtlich und an ihrer Stelle; die Hashtags am Ende bekommst du nicht zu sehen.
{rueckmeldung}
Text:
<<<
{rumpf}
>>>

Antworte nur mit diesem JSON:
{{"text": "der gekürzte Beitrag", "aenderungen": [{{"was": "was du gekürzt oder umgestellt hast", "grund": "kurzer Satz"}}], "offen": [{{"problem": "...", "handgriff": "..."}}]}}"""


def json_ohne_ablage(antwort: str) -> dict:
    """Wie llm.json_aus_text, aber OHNE die Rohantwort unter data/ abzulegen (sie enthielte den Beitragstext)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", antwort, re.S)
    roh = m.group(1) if m else antwort[antwort.find("{"): antwort.rfind("}") + 1]
    # Deutsche Anführungszeichen mit geradem Schlusszeichen („Kurz vorweg", …) reparieren: das gerade Zeichen
    # beendet sonst die JSON-Zeichenkette, besonders wenn ein Komma folgt.
    deutsch = re.sub(r"„([^\"„“\n]{1,120})\"", r"„\1“", roh)
    for kandidat in (roh, llm._json_bereinigen(roh), llm._json_bereinigen(llm._json_innere_anfuehrungszeichen(roh)),
                     llm._json_bereinigen(deutsch), llm._json_bereinigen(llm._json_innere_anfuehrungszeichen(deutsch))):
        try:
            d = json.loads(kandidat, strict=False)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            pass
    raise llm.LLMFehler("Die KI-Antwort war kein gültiges JSON.")


NACHFRAGE = ("\n\nDeine letzte Antwort war kein gültiges JSON. Antworte erneut NUR mit dem vollständigen JSON-Objekt, ohne Text davor "
             "oder danach. Verwende in den Werten für Anführungszeichen nur „…“ oder ‚…‘, nie gerade Anführungszeichen.")


def _chat(system: str, prompt: str, modell: str, timeout: int, zaehler: dict) -> dict:
    """Ein KI-Aufruf mit JSON-Auswertung; bei ungültigem JSON genau eine Nachfrage mit demselben Modell
    (zusammen „zweimal nicht bestanden“ -> der Aufrufer eskaliert eine Stufe höher)."""
    for versuch in range(2):
        zaehler["aufrufe"] += 1
        antwort = llm.chat(system, prompt + (NACHFRAGE if versuch else ""), timeout=timeout, max_tokens=4000, modell=modell,
                           wartezeiten=WARTEZEITEN)
        zaehler["modell"] = getattr(antwort, "modell", modell) or modell
        try:
            return json_ohne_ablage(antwort)
        except llm.LLMFehler:
            if versuch:
                raise
    raise llm.LLMFehler("Die KI-Antwort war kein gültiges JSON.")


def _finde(text: str, alt: str) -> tuple[int, int] | None:
    """Position von `alt` in `text`: wörtlich und eindeutig, sonst mit flexiblem Leerraum."""
    if not alt.strip():
        return None
    if text.count(alt) == 1:
        i = text.find(alt)
        return i, i + len(alt)
    muster = r"\s+".join(re.escape(w) for w in alt.split())
    treffer = list(re.finditer(muster, text))
    if len(treffer) == 1:
        return treffer[0].start(), treffer[0].end()
    return None


def wende_aenderungen_an(rumpf: str, aenderungen: list) -> tuple[str, list[dict], list[dict]]:
    """Wendet LLM-Änderungen einzeln an. Jede besteht die Schutzprüfung oder wird verworfen (mit Grund)."""
    angenommen, verworfen = [], []
    t = rumpf
    for a in aenderungen if isinstance(aenderungen, list) else []:
        if not isinstance(a, dict):
            continue
        alt, neu = str(a.get("alt", "")), str(a.get("neu", ""))
        grund = str(a.get("grund", "")).strip() or "ohne Begründung"
        if alt == neu:
            continue
        pos = _finde(t, alt)
        if pos is None:
            verworfen.append({"alt": alt, "neu": neu, "grund": grund,
                              "warum": "Die Stelle stand so nicht (oder mehrfach) im Text; die Änderung wurde nicht übernommen."})
            continue
        if not neu.strip():
            verworfen.append({"alt": alt, "neu": "", "grund": grund,
                              "warum": "Die KI wollte die Stelle ganz streichen. Im Modus „Behutsam“ bleibt jeder Gedanke stehen; zum Kürzen „Straffen“ wählen."})
            continue
        gruende = schutzpruefung(alt, neu, min_anteil=0.45)  # Floskelsätze dürfen um gut die Hälfte schrumpfen
        if gruende:
            verworfen.append({"alt": alt, "neu": neu, "grund": grund, "warum": " ".join(gruende)})
            continue
        t = t[:pos[0]] + neu + t[pos[1]:]
        angenommen.append({"alt": alt, "neu": neu, "was": f"„{_kurz(alt)}“ → „{_kurz(neu)}“", "grund": grund,
                           "art": str(a.get("art", "")), "quelle": "KI"})
    return t, angenommen, verworfen


def _kurz(s: str, n: int = 90) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + " …"


def _offen_aus(d: dict) -> list[dict]:
    erg = []
    for o in (d.get("offen") or [])[:3]:
        if isinstance(o, dict) and o.get("problem"):
            erg.append({"problem": str(o["problem"]), "handgriff": str(o.get("handgriff", "")), "quelle": "KI"})
    return erg


# --------------------------------------------------------------------------
# Wortdiff
# --------------------------------------------------------------------------

_TOKEN = re.compile(r"\n|[ \t]+|[\wÄÖÜäöüß]+|[^\w\s]", re.U)


def wortdiff(alt: str, neu: str) -> list[tuple[str, str]]:
    """[(art, text)] mit art in gleich|weg|neu - fuer die rot/gruene Darstellung (Vorlage escaped)."""
    a, b = _TOKEN.findall(alt), _TOKEN.findall(neu)
    erg: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            erg.append(("gleich", "".join(a[i1:i2])))
        else:
            if i2 > i1:
                erg.append(("weg", "".join(a[i1:i2])))
            if j2 > j1:
                erg.append(("neu", "".join(b[j1:j2])))
    return erg


# --------------------------------------------------------------------------
# Durchlauf
# --------------------------------------------------------------------------

_llm_sperre = threading.Semaphore(1)  # schont den Wrapper: immer nur ein KI-Lauf des Redaktors zugleich


class Belegt(RuntimeError):
    pass


def verarbeite(text: str, modus: str, *, ziel: int = 600, aufbau_erlaubt: bool = False) -> dict:
    """Ein Durchlauf. Ergebnis enthält Original und Vorschlag nur für die Antwortseite; nichts davon wird gespeichert."""
    start = time.monotonic()
    text = normalisiere(text).strip()
    modus = modus if modus in MODI else "pruefen"
    ziel = ziel if ziel in ZIELE else 600
    vorher = messen(text)
    erg = {"modus": modus, "modus_name": MODI[modus], "ziel": ziel, "original": text, "vorher": vorher, "vorschlag": None,
           "nachher": None, "aenderungen": [], "verworfen": [], "offen": [], "meldung": "", "modell": "", "aufrufe": 0}
    zaehler = {"aufrufe": 0, "modell": ""}

    if modus != "pruefen":
        ok, warum = llm_verfuegbar()
        if not ok:
            erg["meldung"] = warum
            modus = erg["modus"] = "pruefen"
            erg["modus_name"] = MODI["pruefen"]

    if modus != "pruefen":
        if not _llm_sperre.acquire(blocking=False):
            raise Belegt("Gerade läuft schon eine Überarbeitung. Bitte in einer Minute erneut versuchen.")
        try:
            _ki_lauf(erg, text, modus, ziel, aufbau_erlaubt, zaehler)
        finally:
            _llm_sperre.release()

    # „Was noch nicht gut ist“: Messung am Ergebnis (bzw. am Original bei „Nur prüfen“)
    basis = erg["nachher"] or vorher
    for x in basis["pruefungen"]:
        if x["stufe"] in ("warn", "fehler") and x["handgriff"]:
            erg["offen"].append({"problem": f"{x['name']}: {x['messwert']} (Soll: {x['soll']})", "handgriff": x["handgriff"], "quelle": "Messung"})
    erg["aufrufe"] = zaehler["aufrufe"]
    erg["modell"] = zaehler["modell"]
    erg["dauer_s"] = round(time.monotonic() - start, 1)
    return erg


def _ki_lauf(erg: dict, text: str, modus: str, ziel: int, aufbau_erlaubt: bool, zaehler: dict) -> None:
    timeout = einstellungen()["llm_timeout"]
    fest, fest_aend = feste_korrekturen(text, aufbau_erlaubt)
    rumpf, fuss = teile_fuss(fest)
    offene = [f"{x['name']}: {x['messwert']}" for x in messen(fest)["pruefungen"] if x["stufe"] in ("warn", "fehler") and not x["info"]]
    modell = llm.modell_fuer("text_umschreiben")
    hoeher = llm.eskalations_modell("text_umschreiben")
    neu_rumpf, angenommen, verworfen, offen_ki = rumpf, [], [], []
    try:
        if modus == "behutsam":
            bestes = None
            for versuch, m in enumerate([modell] + ([hoeher[0]] if hoeher else [])):
                try:
                    d = _chat(SYSTEM, prompt_behutsam(rumpf, offene), m, timeout, zaehler)
                except llm.LLMVerbindung:
                    if bestes:
                        break
                    raise
                except llm.LLMFehler:
                    if versuch == 0 and hoeher:
                        continue  # zweimal kein gültiges JSON -> einmal eine Stufe höher (Eskalation)
                    if bestes:
                        break
                    raise
                lauf = wende_aenderungen_an(rumpf, d.get("aenderungen")) + (_offen_aus(d),)
                if bestes is None or len(lauf[1]) > len(bestes[1]):
                    bestes = lauf
                if lauf[2] and len(lauf[2]) > len(lauf[1]) and versuch == 0 and hoeher:
                    continue  # mehr verworfen als angenommen -> einmal mit der nächsthöheren Stufe
                break
            if bestes:
                neu_rumpf, angenommen, verworfen, offen_ki = bestes
            wa, wn = len(rumpf), len(neu_rumpf)
            if wa and abs(wn - wa) / wa > 0.15:
                offen_ki.append({"problem": f"Die Länge hat sich um {round(100 * (wn - wa) / wa)} % verändert (Ziel: ±15 %).",
                                 "handgriff": "Vorschlag gegenlesen: Ist noch alles drin, was dir wichtig ist?", "quelle": "Messung"})
        else:  # straffen
            ziel_rumpf = max(80, ziel - (len(fuss) + 2 if fuss else 0))
            rueck = ""
            for versuch in range(2):
                d = _chat(SYSTEM, prompt_straffen(rumpf, ziel_rumpf, rueck), modell if versuch == 0 or not hoeher else hoeher[0], timeout, zaehler)
                kandidat = str(d.get("text", "")).strip()
                gruende = schutzpruefung(rumpf, kandidat, weglassen_erlaubt=True)
                if gruende:
                    verworfen = [{"alt": "ganzer Text", "neu": kandidat, "grund": "Kürzung", "warum": " ".join(gruende)}]
                    rueck = "Deine letzte Fassung wurde abgelehnt: " + " ".join(gruende) + " Halte dich streng an die Regeln."
                    continue
                verworfen = []
                neu_rumpf = kandidat
                for a in d.get("aenderungen") or []:
                    if isinstance(a, dict) and a.get("was"):
                        angenommen.append({"was": str(a["was"]), "grund": str(a.get("grund", "")), "quelle": "KI"})
                offen_ki = _offen_aus(d)
                break
            if verworfen:
                erg["meldung"] = "Die Kürzung wurde verworfen, weil sie die Schutzprüfung zweimal nicht bestanden hat. Unten siehst du nur die festen Korrekturen."
    except llm.LLMVerbindung:
        erg["meldung"] = "Die KI war nicht erreichbar. Unten siehst du nur die festen Korrekturen und die Messung."
    except llm.LLMFehler as exc:
        erg["meldung"] = f"Die KI-Antwort war nicht verwertbar ({exc}). Unten siehst du nur die festen Korrekturen und die Messung."
    if verworfen and modus == "straffen":
        # Begründung bleibt sichtbar; der verworfene Text selbst wird nicht angezeigt
        for x in verworfen:
            x["neu"] = ""
    neu_rumpf = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", re.sub(r"[ \t]+\n", "\n", neu_rumpf)).strip()
    vorschlag = neu_rumpf + ("\n\n" + fuss if fuss else "")
    erg["vorschlag"] = vorschlag
    erg["nachher"] = messen(vorschlag)
    erg["aenderungen"] = fest_aend + angenommen
    erg["verworfen"] = verworfen
    erg["offen"] = offen_ki
    erg["diff"] = wortdiff(text, vorschlag)


# --------------------------------------------------------------------------
# Ratenbegrenzung (im Speicher, IP wird nie gespeichert) und anonymisierter Zähler (Datei)
# --------------------------------------------------------------------------


class Ratenbegrenzer:
    def __init__(self, fenster_s: int = 3600):
        self.fenster = fenster_s
        self._je_ip: dict[str, deque] = {}
        self._sperre = threading.Lock()

    def zulassen(self, ip: str, limit: int, jetzt: float | None = None) -> bool:
        jetzt = time.time() if jetzt is None else jetzt
        with self._sperre:
            q = self._je_ip.setdefault(ip, deque())
            while q and jetzt - q[0] >= self.fenster:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(jetzt)
            # alte, leere Einträge aufräumen (Speicher begrenzen)
            if len(self._je_ip) > 5000:
                for k in [k for k, v in self._je_ip.items() if not v or jetzt - v[-1] >= self.fenster]:
                    del self._je_ip[k]
            return True

    def anzahl(self, ip: str, jetzt: float | None = None) -> int:
        jetzt = time.time() if jetzt is None else jetzt
        with self._sperre:
            return sum(1 for t in self._je_ip.get(ip, ()) if jetzt - t < self.fenster)

    def leeren(self) -> None:
        with self._sperre:
            self._je_ip.clear()


class Zaehler:
    """data/redaktor/zaehler.json: je Tag Summen, dazu die letzten 200 Läufe ohne Text und ohne IP."""

    def __init__(self, pfad: Path | None = None):
        self.pfad = pfad or ROOT / "data" / "redaktor" / "zaehler.json"
        self._sperre = threading.Lock()

    def _laden(self) -> dict:
        try:
            return json.loads(self.pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"tage": {}, "laeufe": []}

    def heute(self) -> int:
        with self._sperre:
            return int(self._laden().get("tage", {}).get(date.today().isoformat(), {}).get("aufrufe", 0))

    def buchen(self, eintrag: dict) -> None:
        erlaubt = {"laenge", "modus", "dauer_s", "modell", "punkte_vorher", "punkte_nachher", "aufrufe_llm", "ergebnis"}
        e = {k: v for k, v in eintrag.items() if k in erlaubt}
        e["zeit"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self._sperre:
            d = self._laden()
            tag = d.setdefault("tage", {}).setdefault(date.today().isoformat(), {"aufrufe": 0, "llm_aufrufe": 0, "dauer_s": 0.0, "modi": {}})
            tag["aufrufe"] += 1
            tag["llm_aufrufe"] += int(e.get("aufrufe_llm", 0) or 0)
            tag["dauer_s"] = round(tag["dauer_s"] + float(e.get("dauer_s", 0) or 0), 1)
            tag["modi"][e.get("modus", "?")] = tag["modi"].get(e.get("modus", "?"), 0) + 1
            d["laeufe"] = (d.get("laeufe", []) + [e])[-200:]
            d["tage"] = dict(sorted(d["tage"].items())[-120:])
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.pfad.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.pfad)
