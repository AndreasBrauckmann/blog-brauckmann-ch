"""Titel und Beschreibung lesen sich in einem Guss (verbindliche Projektregel, siehe CLAUDE.md).

Die Beschreibung setzt den Titel fort und wiederholt keine Zahl, kein Schluesselwort und
keine Wortfolge aus dem Titel. Dieses Modul misst die Ueberschneidung. Es hat keine
Abhaengigkeiten (kein Flask) und wird von scripts/build.py (Warnung beim Bauen), der
Verwaltung (Metas-Auswahl, Ranking) und den Tests genutzt - die Logik steht nur hier.

Regel (Schwellen):
  * eine gemeinsame Zahl (mit mindestens zwei Ziffern, z. B. 84.000, 2010) ODER
  * mindestens SCHWELLE_WOERTER (2) gemeinsame bedeutungstragende Woerter ODER
  * eine gemeinsame Wortfolge ab zwei Woertern, die ein bedeutungstragendes Wort enthaelt
    ("ohne Login")
=> Beschreibung "wiederholt den Titel".
Bedeutungstragend: kein Stoppwort, mindestens vier Buchstaben. Woerter werden grob auf ihren
Stamm gekuerzt (kostenlos/kostenlose, Dashboard/Dashboards). Fuehrende Auslassungspunkte der Beschreibung werden vor dem Messen entfernt.
"""

from __future__ import annotations

import re

SCHWELLE_WOERTER = 2

_WORT = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+(?:['’.,][A-Za-zÄÖÜäöüß0-9]+)*")
_ZAHL = re.compile(r"\d[\d.,]*\d|\d")

STOPPWOERTER = set("""
aber alle allem allen aller alles also auch auf aus bei bin bis bist dabei dadurch dafür dagegen daher damit danach dann
dass dazu dein deine dem den denn der des die dies diese diesem diesen dieser dieses doch dort durch ein eine einem einen
einer eines einfach er es etwa euch euer für gegen gibt hat hatte hier ihm ihn ihr ihre ihrem ihren ihrer im in ins ist
jede jedem jeden jeder jedes jetzt kann kein keine keinem keinen keiner können machen man mehr mein meine mit muss nach
nicht noch nun nur oder ohne per sich sie sind so soll sollen sondern statt über um und uns unser unsere unter viel vom von
vor was weil wenn wer werden wie wieder wir wird wo wurde wurden zu zum zur zwischen
mal schon seit sehr bereits immer wieso warum wozu welche welcher welches
""".split())


def _normal(w: str) -> str:
    w = w.lower().replace("ß", "ss")
    if len(w) >= 6:
        for suf in ("en", "er", "es", "em", "e", "n", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 5:
                if suf == "s" and w[-2] in "aeiouls":  # kostenlos, Status: kein Plural-s
                    continue
                return w[: -len(suf)]
    return w


def _bedeutend(w: str) -> bool:
    return len(w) >= 4 and w.lower() not in STOPPWOERTER and not w.isdigit()


def _woerter(text: str) -> list[str]:
    """Woerter ohne reine Zahlen (Zahlen werden getrennt gemessen)."""
    return [w.strip(".,") for w in _WORT.findall(text) if w.strip(".,") and not re.fullmatch(r"[\d.,]+", w.strip(".,"))]


def _zahlen(text: str) -> list[str]:
    erg = []
    for z in _ZAHL.findall(text):
        z = z.strip(".,")
        if sum(c.isdigit() for c in z) >= 2:
            erg.append(re.sub(r"[.,]", "", z))
    return erg


def bereinige(beschreibung: str) -> str:
    """Entfernt fuehrende Auslassungspunkte („…“, „...“) und beginnt mit einem Grossbuchstaben.
    Beschreibungen beginnen normal; Auslassungspunkte am Anfang sind nicht gewuenscht."""
    t = re.sub(r"^\s*(?:…|\.{2,})\s*", "", beschreibung or "").strip()
    return t[:1].upper() + t[1:] if t else t


def ueberschneidung(titel: str, beschreibung: str) -> dict:
    """{wiederholt: [angezeigte Teile], ok: bool, hinweis: str}. ok = liest sich in einem Guss."""
    beschr = bereinige(beschreibung)
    tw, bwords = _woerter(titel or ""), _woerter(beschr)
    wiederholt: list[str] = []
    # Zahlen
    tz = set(_zahlen(titel or ""))
    zahlen = []
    for z in _WORT.findall(beschr):
        roh = z.strip(".,")
        key = re.sub(r"[.,]", "", roh)
        if sum(c.isdigit() for c in roh) >= 2 and key in tz and roh not in zahlen:
            zahlen.append(roh)
    # Wortfolgen ab zwei Woertern (mit mindestens einem bedeutungstragenden Wort)
    tn = [_normal(w) for w in tw]
    bn = [_normal(w) for w in bwords]
    folgen, belegt = [], set()
    i = 0
    while i < len(bn) - 1:
        best = 0
        for j in range(len(tn) - 1):
            k = 0
            while i + k < len(bn) and j + k < len(tn) and bn[i + k] == tn[j + k]:
                k += 1
            best = max(best, k)
        if best >= 2 and any(_bedeutend(w) for w in bwords[i:i + best]) and not all(w.isdigit() for w in bwords[i:i + best]):
            folgen.append(" ".join(bwords[i:i + best]))
            belegt.update(range(i, i + best))
            i += best
        else:
            i += 1
    # einzelne bedeutungstragende Woerter (nicht schon in einer Folge oder Zahl)
    titel_stamm = {_normal(w) for w in tw if _bedeutend(w)}
    einzel = []
    for idx, w in enumerate(bwords):
        if idx in belegt or not _bedeutend(w):
            continue
        if _normal(w) in titel_stamm and _normal(w) not in {_normal(e) for e in einzel}:
            einzel.append(w)
    wiederholt = zahlen + folgen + einzel
    in_folgen = {_normal(w) for f in folgen for w in f.split() if _bedeutend(w)}
    zaehler_woerter = len(set(_normal(w) for w in einzel) | in_folgen)
    wiederholt_flag = bool(zahlen) or bool(folgen) or zaehler_woerter >= SCHWELLE_WOERTER
    if not wiederholt_flag:
        return {"wiederholt": [], "ok": True, "hinweis": "Liest sich in einem Guss."}
    zeigen = [f"‚{x}‘" for x in wiederholt[:4]]
    teile = zeigen[0] if len(zeigen) == 1 else ", ".join(zeigen[:-1]) + " und " + zeigen[-1]
    return {"wiederholt": wiederholt, "ok": False,
            "hinweis": f"{teile} {'steht' if len(zeigen) == 1 else 'stehen'} schon im Titel."}
