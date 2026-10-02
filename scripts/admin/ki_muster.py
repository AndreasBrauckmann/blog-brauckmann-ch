"""„Klingt menschlich (KI-Muster)“: Kriterium der Kategorie B, ganz ohne KI gemessen.

Quelle der Ideen: stop-slop (github.com/hardikpandya/stop-slop, MIT), deutsch angepasst und eigenstaendig umgesetzt
(nichts davon installiert oder kopiert). Die Regeln stehen als Datenstruktur in REGELN, damit sie sich leicht erweitern
lassen, und werden auf der Detailseite unter „Klingt menschlich“ dokumentiert.

Gezaehlt wird im Fliesstext der Artikel (ohne Code, Ueberschriften, Tabellen, Grafiken). Woertliche Zitate in „…“ werden
nicht gezaehlt, weil sie nie veraendert werden duerfen. Zahlenbereiche wie „2010–2026“ und Bindestriche in Woertern sind
keine Gedankenstriche.
"""

from __future__ import annotations

import re

import bewertung as bw

QUELLE = "Ideen aus stop-slop (MIT), deutsch angepasst"
ZITAT = re.compile(r"„[^“]{1,400}“|\"[^\"]{1,400}\"")

# Muster: typ "regex" zaehlt Treffer; „rhythmus“, „frage“ und „passiv“ sind Spezialmessungen (siehe messe()).
REGELN = [
    {"id": "gedankenstrich", "name": "Gedankenstriche", "typ": "regex", "soll": 4.0, "gewicht": 3,
     "muster": r"(?<=\S)\s(?:—|--|–)\s(?=\S)",
     "beschreibung": "Gedankenstrich ' — ', ' -- ' oder ' – ' (mit Leerzeichen). Bindestriche in Wörtern und Zahlenbereiche wie 2010–2026 zählen nicht.",
     "vorschlag": "Durch Punkt, Komma, Doppelpunkt oder Klammer ersetzen, ohne den Sinn zu ändern."},
    {"id": "kontrast", "name": "„nicht X, sondern Y“", "typ": "regex", "soll": 1.0, "gewicht": 2,
     "muster": r"\b(?:nicht|kein|keine|keinen|keinem|keiner)\b[^.!?;:]{1,90}?,\s*(?:sondern|vielmehr)\b",
     "beschreibung": "Binärer Kontrast „nicht X, sondern Y“.",
     "vorschlag": "Direkt sagen, was Y ist; das Verneinte weglassen."},
    {"id": "floskel", "name": "Einleiter und Floskeln", "typ": "regex", "soll": 2.0, "gewicht": 2,
     "muster": r"\b(?:kurz vorweg|vorab|das ist der eigentliche|die eigentliche|der eigentliche|der punkt ist|hier ist|spoiler|und genau das|kein hexenwerk|in der tat|letztlich|im grunde|gewissermaßen|sozusagen)\b",
     "beschreibung": "Einleiter wie „Kurz vorweg“, „Der Punkt ist“, „Und genau das“ und Füllphrasen wie „im Grunde“, „sozusagen“.",
     "vorschlag": "Streichen; der Satz trägt ohne Einleiter."},
    {"id": "verstaerker", "name": "Verstärker und Füllwörter", "typ": "regex", "soll": 6.0, "gewicht": 2,
     "muster": r"\b(?:genau|ganz|wirklich|echt|durchaus|schlicht|einfach|eigentlich|tatsächlich)\b",
     "beschreibung": "Verstärker wie „genau“, „ganz“, „wirklich“, „echt“, „durchaus“, „schlicht“, „einfach“, „eigentlich“, „tatsächlich“.",
     "vorschlag": "Streichen oder durch eine konkrete Angabe ersetzen."},
    {"id": "rhythmus", "name": "Drei gleich lange Sätze hintereinander", "typ": "rhythmus", "soll": 2.0, "gewicht": 2, "absolut": True,
     "beschreibung": "Drei aufeinanderfolgende Sätze (je mindestens 5 Wörter), deren Länge höchstens 3 Wörter auseinanderliegt.",
     "vorschlag": "Rhythmus variieren: einen Satz kürzen, einen verbinden oder umstellen."},
    {"id": "frage", "name": "Rhetorische Frage mit Gleich-Antwort", "typ": "frage", "soll": 1.0, "gewicht": 1, "absolut": True,
     "beschreibung": "Frage, die im nächsten kurzen Satz (höchstens 8 Wörter) sofort beantwortet wird.",
     "vorschlag": "Als Aussage formulieren."},
    {"id": "passiv", "name": "Passiv (nur Hinweis)", "typ": "passiv", "soll": 15.0, "gewicht": 0, "prozent": True,
     "beschreibung": "Anteil der Sätze mit wird/wurde/werden/wurden + Partizip, grob geschätzt; fließt nicht in die Note ein.",
     "vorschlag": "Aktiv mit menschlichem Subjekt formulieren („Ich habe …“, „Wir …“)."},
]

_PASSIV = re.compile(r"\b(?:wird|wurde|werden|wurden)\b[^.!?]{0,60}?\b(?:ge\w{3,}(?:t|en)|\w{3,}iert)\b", re.I)


def ohne_zitate(text: str) -> str:
    return ZITAT.sub(" ", text)


def _saetze(texte: list[str]) -> list[list[str]]:
    """Saetze je Absatz (Zitate entfernt)."""
    return [bw.saetze(ohne_zitate(t)) for t in texte]


def _rhythmus(saetze: list[str]) -> list[int]:
    """Startindizes von Dreiergruppen gleich langer Saetze (nicht ueberlappend)."""
    laengen = [len(bw.woerter(s)) for s in saetze]
    erg, i = [], 0
    while i + 2 < len(laengen):
        g = laengen[i:i + 3]
        if min(g) >= 5 and max(g) - min(g) <= 3:
            erg.append(i)
            i += 3
        else:
            i += 1
    return erg


def _fragen(saetze: list[str]) -> list[int]:
    erg = []
    for i in range(len(saetze) - 1):
        if saetze[i].rstrip().endswith("?") and 0 < len(bw.woerter(saetze[i + 1])) <= 8 and not saetze[i + 1].rstrip().endswith("?"):
            erg.append(i)
    return erg


def messe(texte: list[str]) -> dict:
    """{regel_id: {"anzahl", "je1000" bzw. "prozent", "soll", "ok"}} plus "woerter". Deterministisch, ohne KI."""
    bereinigt = [ohne_zitate(t) for t in texte]
    woerter = sum(len(bw.woerter(t)) for t in bereinigt) or 1
    s_je_absatz = [bw.saetze(t) for t in bereinigt]
    alle_saetze = sum(len(x) for x in s_je_absatz) or 1
    erg: dict = {"woerter": woerter}
    for r in REGELN:
        if r["typ"] == "regex":
            n = sum(len(re.findall(r["muster"], t, re.I)) for t in bereinigt)
        elif r["typ"] == "rhythmus":
            n = sum(len(_rhythmus(s)) for s in s_je_absatz)
        elif r["typ"] == "frage":
            n = sum(len(_fragen(s)) for s in s_je_absatz)
        else:  # passiv
            n = sum(1 for s in s_je_absatz for satz in s if _PASSIV.search(satz))
        if r.get("prozent"):
            wert = round(100 * n / alle_saetze, 1)
        elif r.get("absolut"):
            wert = float(n)
        else:
            wert = round(1000 * n / woerter, 1)
        erg[r["id"]] = {"anzahl": n, "wert": wert, "soll": r["soll"], "ok": wert <= r["soll"]}
    return erg


def erfuellung(m: dict) -> tuple[float, str, str]:
    """(Erfuellung 0-100, Messwert-Text, Vorschlag). Je Regel 100 % bei ≤ Soll, 0 % bei ≥ 3 × Soll; gewichtetes Mittel."""
    summe = punkte = 0.0
    teile, tipps = [], []
    for r in REGELN:
        if not r["gewicht"]:
            continue
        x = m[r["id"]]
        e = 100.0 if x["ok"] else max(0.0, 100.0 * (3 * r["soll"] - x["wert"]) / (2 * r["soll"]))
        summe += r["gewicht"] * e
        punkte += r["gewicht"]
        if not x["ok"]:
            einheit = "" if r.get("absolut") else " je 1000 Wörter"
            teile.append(f"{r['name']}: {str(x['wert']).replace('.', ',')}{einheit} (Soll ≤ {str(r['soll']).replace('.0', '').replace('.', ',')})")
            tipps.append(f"{r['name']}: {r['vorschlag']}")
    p = m["passiv"]
    hinweis = f" · Passiv {str(p['wert']).replace('.', ',')} % der Sätze" + (" (Hinweis)" if not p["ok"] else "")
    messwert = ("; ".join(teile) if teile else "alle Muster im Soll") + hinweis
    return round(summe / punkte, 1), messwert, " ".join(tipps[:3])


def funde(bloecke: list) -> list[dict]:
    """Fundstellen je Absatz fuer die Detailseite. `bloecke` = in_ordnung.finde_bloecke(...) (nur html/md-Absaetze)."""
    erg = []
    for b in bloecke:
        if b.art not in ("html", "md"):
            continue
        text = ohne_zitate(b.klar)
        treffer = []
        for r in REGELN:
            if r["typ"] == "regex":
                for m in re.finditer(r["muster"], text, re.I):
                    von = max(0, m.start() - 40)
                    treffer.append({"regel": r["name"], "auszug": text[von:m.end() + 40].strip()})
            elif r["typ"] in ("rhythmus", "frage"):
                saetze = bw.saetze(text)
                for i in (_rhythmus(saetze) if r["typ"] == "rhythmus" else _fragen(saetze)):
                    treffer.append({"regel": r["name"], "auszug": " ".join(saetze[i:i + (3 if r["typ"] == "rhythmus" else 2)])[:160]})
        if treffer:
            erg.append({"abschnitt": b.abschnitt, "absatz": b.absatz_nr, "zeile": b.zeile, "treffer": treffer})
    return erg


def treffer_summe(text: str) -> int:
    """Gesamtzahl der KI-Muster-Treffer in EINEM Absatz (ohne Passiv-Hinweis) - fuer die Pruefung „wirklich weniger“."""
    m = messe([text])
    return sum(m[r["id"]]["anzahl"] for r in REGELN if r["gewicht"])
