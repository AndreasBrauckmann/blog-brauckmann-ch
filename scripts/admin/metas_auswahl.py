"""Metas (Titel, Beschreibung, og:image:alt, Vorschaubild): Vorschlaege, verbindliche
Grenzpruefung und Aufbereitung fuer die gemeinsame Auswahl-Seite.

Fachlich frei von Flask. Genutzt von ranking_views.py (Abschnitt „Metas
optimieren“) und in_ordnung.py (Metas-Schritt von „Alles in Ordnung
bringen“) - beide zeigen dieselbe Auswahl (Vorlage _metas_auswahl.html).

Grenzen (verbindlich, programmatisch nachgemessen - dem Modell wird nicht
geglaubt): Titel 40-70, Beschreibung 120-160 (Haken in den ersten 90
Zeichen), og:image:alt 60-160 Zeichen. Ein Vorschlag ausserhalb der Grenzen
wird nie empfohlen oder vorausgewaehlt; verfehlt ein Feld alle Grenzen, wird
einmal mit konkreter Rueckmeldung neu angefragt (zu lang um N Zeichen ...).
"""

from __future__ import annotations

import re
from pathlib import Path

import sys

import bewertung as bw
import llm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import titel_beschreibung as tb  # noqa: E402  (gemeinsame Logik mit scripts/build.py)

# Zielwerte beim Nachfragen: knapp unter der Obergrenze, damit Zaehlfehler des Modells nicht ueber das Soll fuehren
ZIEL_MAX = {"title": 65, "description": 150, "og_image_alt": 150}

# Zeilen der H1 (Titel) im gebauten Artikel. Kalibriert mit Playwright an den gebauten Seiten (1.10.2026):
# H1 = 1.9rem = 30,4 px fett (System-Schrift), Handy 393 px minus 2 x 1rem Rand = 361 px, Desktop: main max 70ch = 623 px.
# Greedy-Umbruch mit mittlerer Zeichenbreite 0,55 em und Leerzeichen 0,28 em; an den fuenf Artikeln trifft das 9 von 10 Werten.
H1_PX = 30.4
H1_BREITE_HANDY = 361
H1_BREITE_DESKTOP = 623
H1_ZEICHENBREITE = 0.55
H1_LEERZEICHEN = 0.28


def titel_zeilen(text: str) -> dict:
    """Geschaetzte Zeilen der H1 am Handy und am Desktop; Ampel am Handy: 1-3 gruen, 4 gelb, ab 5 rot."""
    def umbruch(breite: float) -> int:
        zeilen, x = 1, 0.0
        for wort in (text or "").split():
            b = len(wort) * H1_ZEICHENBREITE * H1_PX
            if x == 0:
                x = b
            elif x + H1_LEERZEICHEN * H1_PX + b <= breite:
                x += H1_LEERZEICHEN * H1_PX + b
            else:
                zeilen, x = zeilen + 1, b
        return zeilen
    handy = umbruch(H1_BREITE_HANDY)
    return {"handy": handy, "desktop": umbruch(H1_BREITE_DESKTOP), "ampel": "gruen" if handy <= 3 else ("gelb" if handy == 4 else "rot")}


META_GRENZEN = {
    "title": (40, 70),
    "description": (120, 160),
    "og_image_alt": (60, 160),
}
FELD_NAMEN = {"title": "Titel", "description": "Beschreibung", "og_image_alt": "Bild-Alternativtext (og:image:alt)"}
LLM_KEY = {"title": "titel", "description": "beschreibung", "og_image_alt": "og_image_alt"}
HAKEN_ZEICHEN = 90
GOOGLE_TITEL = 60
GOOGLE_BESCHREIBUNG = 155
MAX_KARTEN = 3
LLM_TIMEOUT = 200

_URL = re.compile(r"https?://", re.I)


def grenze_ampel(feld: str, n: int) -> str:
    """gruen = im Soll, gelb = knapp daneben (bis 10 Zeichen), rot = ausserhalb."""
    lo, hi = META_GRENZEN[feld]
    if lo <= n <= hi:
        return "gruen"
    if lo - 10 <= n <= hi + 10:
        return "gelb"
    return "rot"


def normalisiere_beschreibung(text: str) -> str:
    """Vorschlag bereinigen: fuehrende Auslassungspunkte entfernen, normaler Satzanfang (Grossbuchstabe)."""
    return tb.bereinige(text)


def pruefe_meta(feld: str, text: str, aktuell: str = "", gegenueber: str | None = None) -> str | None:
    """Strenge Pruefung eines VORSCHLAGS. None = alle Grenzen eingehalten, sonst der konkrete Grund.
    Zeichenzahl = gespeicherter Text. `gegenueber` = der andere Teil der
    Kombination (Titel bzw. Beschreibung) fuer die Regel „in einem Guss“; None = nicht pruefen."""
    t = (text or "").strip()
    lo, hi = META_GRENZEN[feld]
    if not t:
        return "leer"
    if "\n" in t or "<" in t or ">" in t:
        return "Zeilenumbruch oder HTML"
    if _URL.search(t):
        return "enthält eine URL"
    if feld in ("title", "description") and re.search(r"(?<=\S)\s(?:—|--|–)\s(?=\S)", t):
        return "enthält einen Gedankenstrich (Regel „Schreibregeln gegen KI-Muster“: Punkt, Komma oder Doppelpunkt)"
    n = len(t)
    if n > hi:
        return f"zu lang um {n - hi} Zeichen ({n}, Soll {lo}–{hi})"
    if n < lo:
        return f"zu kurz um {lo - n} Zeichen ({n}, Soll {lo}–{hi})"
    if t == (aktuell or "").strip():
        return "unverändert"
    if feld == "description":
        ok, _g = bw.haken_in(t[:HAKEN_ZEICHEN])
        if not ok:
            return f"kein Haken in den ersten {HAKEN_ZEICHEN} Zeichen"
        if gegenueber:
            u = tb.ueberschneidung(gegenueber, t)
            if not u["ok"]:
                return "wiederholt den Titel: " + u["hinweis"]
    if feld == "title" and gegenueber:
        u = tb.ueberschneidung(t, gegenueber)
        if not u["ok"]:
            return "wiederholt sich mit der Beschreibung: " + u["hinweis"]
    return None


def pruefe_wert_hart(feld: str, wert: str) -> str | None:
    """Nur harte Ausschluesse fuer einen vom Nutzer gewaehlten/angepassten Wert (Laengen nur als Warnung)."""
    t = (wert or "").strip()
    if not t:
        return "leer"
    if "\n" in t or "<" in t or ">" in t:
        return "Zeilenumbruch oder HTML"
    if len(t) > 400:
        return "länger als 400 Zeichen"
    if feld != "og_image_alt" and _URL.search(t):
        return "enthält eine URL"
    return None


def _tags_in(text: str, tags: list[str]) -> int:
    t = text.lower()
    return sum(1 for g in tags if g.lower() in t)


def begruendung(feld: str, text: str, tags: list[str]) -> str:
    n = len(text)
    teile = []
    if feld == "title":
        z = titel_zeilen(text)
        teile.append(f"≈ {z['handy']} Zeilen am Handy, {z['desktop']} am Desktop")
        if tags:
            teile.append(f"{_tags_in(text, tags)} von {len(tags)} Schlüsselbegriffen")
    elif feld == "description":
        ok, g = bw.haken_in(text[:HAKEN_ZEICHEN])
        teile.append(f"Haken in den ersten {HAKEN_ZEICHEN} Zeichen" if ok else "kein klarer Haken vorn")
        teile.append("wird nicht gekürzt" if n <= GOOGLE_BESCHREIBUNG else f"Google kürzt ab {GOOGLE_BESCHREIBUNG}")
        if tags:
            teile.append(f"{_tags_in(text, tags)} von {len(tags)} Schlüsselbegriffen")
    else:
        teile.append("sachlich, beschreibt das Bild" if 60 <= n <= 160 else "Länge ungünstig")
    return ", ".join(teile)


def karte(feld: str, text: str, tags: list[str], aktuell: str = "", gegenueber: str | None = None) -> dict:
    t = (text or "").strip()
    grund = pruefe_meta(feld, t, aktuell, gegenueber)
    k = {"text": t, "laenge": len(t), "ampel": grenze_ampel(feld, len(t)), "ok": grund is None,
         "grund": grund or "", "begruendung": begruendung(feld, t, tags)}
    if feld == "description" and gegenueber is not None:
        k["guss"] = tb.ueberschneidung(gegenueber, t)
    if feld == "title":
        k["zeilen"] = titel_zeilen(t)
    return k


# --------------------------------------------------------------------------
# LLM: Vorschlaege holen, nachmessen, einmal nachfragen
# --------------------------------------------------------------------------


def _rueckmeldung(feld: str, texte: list[str], aktuell: str, gegenueber: str | None) -> str:
    zeilen = []
    for i, t in enumerate(texte, 1):
        g = pruefe_meta(feld, t, aktuell, gegenueber)
        if not g:
            continue
        n = len(t.strip())
        if n > META_GRENZEN[feld][1]:
            hinweis = f"{n - ZIEL_MAX[feld]} Zeichen zu lang, auf höchstens {ZIEL_MAX[feld]} kürzen, Sinn behalten."
        elif "Titel" in g or "Beschreibung" in g:
            hinweis = "Anders formulieren: die Beschreibung nennt die NÄCHSTE Information (Wie? Was genau? Wozu?) und wiederholt nichts aus dem Titel."
        else:
            hinweis = "Neu formulieren, Sinn behalten."
        zeilen.append(f"- {FELD_NAMEN[feld]}, Variante {i} ({n} Zeichen): {g}. {hinweis}")
    return "\n".join(zeilen)


def anfordern(chat, meta: dict, lesetext: str, felder: set[str], extra: str = "", modell: str | None = None) -> dict:
    """Holt Vorschlaege fuer `felder`, misst nach, fragt bei Verfehlung genau einmal mit konkreter
    Rueckmeldung nach. Gemessen wird die Kombination: die Beschreibung gegen den (ersten gueltigen) Titel
    (Regel „in einem Guss“), ein einzeln erzeugter Titel gegen die vorhandene Beschreibung. Ergebnis:
      {"felder": {feld: {"texte": [..] (gueltige zuerst), "gueltig": n}},
       "abgewiesen": [{feld, text, grund, runde}], "nachgefragt": bool}"""
    aktuell = {f: str(meta.get(f) or "") for f in META_GRENZEN}
    prompt = llm.metas_prompt(meta, lesetext, aktuell["og_image_alt"]) + extra
    roh: dict[str, list[tuple[str, int]]] = {f: [] for f in felder}

    def sammle(antwort_text: str, runde: int) -> None:
        kand = llm.json_aus_text(antwort_text)
        for f in felder:
            liste = kand.get(LLM_KEY[f]) or []
            if isinstance(liste, str):
                liste = [liste]
            for t in [str(x).strip() for x in liste][:MAX_KARTEN]:
                if f == "description":
                    t = normalisiere_beschreibung(t)
                if t and t not in [x for x, _r in roh[f]]:
                    roh[f].append((t, runde))

    def bewerte() -> tuple[dict, dict, list, str]:
        gueltig = {f: [] for f in felder}
        ungueltig = {f: [] for f in felder}
        abgew: list[dict] = []
        beschr_gegenueber = None if "description" in felder else aktuell["description"]
        if "title" in felder:
            for t, r in roh["title"]:
                g = pruefe_meta("title", t, aktuell["title"], beschr_gegenueber)
                (gueltig if g is None else ungueltig)["title"].append(t)
                if g:
                    abgew.append({"feld": "title", "text": t, "laenge": len(t), "grund": g, "runde": r})
        titel_fest = gueltig["title"][0] if "title" in felder and gueltig["title"] else aktuell["title"]
        for f in felder - {"title"}:
            for t, r in roh[f]:
                g = pruefe_meta(f, t, aktuell[f], titel_fest if f == "description" else None)
                (gueltig if g is None else ungueltig)[f].append(t)
                if g:
                    abgew.append({"feld": f, "text": t, "laenge": len(t), "grund": g, "runde": r})
        return gueltig, ungueltig, abgew, titel_fest

    sammle(chat(llm.METAS_SYSTEM, prompt, timeout=LLM_TIMEOUT, max_tokens=1500, aufgabe="metas", **({"modell": modell} if modell else {})), 1)
    gueltig, ungueltig, abgewiesen, titel_fest = bewerte()
    nachgefragt = False
    for runde in (2, 3):  # bei Verfehlung bis zu zweimal mit der gemessenen Abweichung nachfragen
        fehlt = [f for f in felder if not gueltig[f]]
        if not fehlt:
            break
        nachgefragt = True
        gegen = {"description": titel_fest, "title": aktuell["description"] if "description" not in felder else None}
        feedback = "\n".join(_rueckmeldung(f, [t for t, _r in roh[f]][-MAX_KARTEN:], aktuell[f], gegen.get(f)) for f in fehlt if roh[f])
        grenzen = "; ".join(f"{FELD_NAMEN[f]} {META_GRENZEN[f][0]}–{META_GRENZEN[f][1]} Zeichen (anstreben: höchstens {ZIEL_MAX[f]})" for f in fehlt)
        nachfrage = (prompt + "\n\nKORREKTUR: Deine Vorschläge für " + ", ".join(FELD_NAMEN[f] for f in fehlt)
                     + " erfüllten die Regeln nicht. Gemessen:\n" + feedback + f"\nGrenzen: {grenzen}. "
                     + ("Der Titel steht fest: „" + titel_fest + "“ – die Beschreibung setzt ihn inhaltlich fort, beginnt normal mit einem Großbuchstaben ohne Auslassungspunkte und wiederholt keine Zahl, kein Schlüsselwort, keine Wortfolge daraus. " if "description" in fehlt else "")
                     + "Liefere diese Felder neu, genau 3 Varianten je Feld; zähle die Zeichen und bleibe lieber knapp unter der Obergrenze. "
                     + f"Beschreibung: Problem oder Nutzen in den ersten {HAKEN_ZEICHEN} Zeichen. Die übrigen Felder als leere Liste.")
        try:
            sammle(chat(llm.METAS_SYSTEM, nachfrage, timeout=LLM_TIMEOUT, max_tokens=1500, aufgabe="metas", **({"modell": modell} if modell else {})), runde)
        except llm.LLMFehler:
            break  # die bisherigen Runden bleiben maßgeblich
        gueltig, ungueltig, abgewiesen, titel_fest = bewerte()
    erg = {}
    for f in felder:
        # gueltige zuerst; nur wenn es keinen gueltigen gibt, die ungueltigen (gekennzeichnet) zeigen
        texte = gueltig[f][:MAX_KARTEN] if gueltig[f] else ungueltig[f][-2:]
        erg[f] = {"texte": texte, "gueltig": len(gueltig[f][:MAX_KARTEN])}
    return {"felder": erg, "abgewiesen": abgewiesen, "nachgefragt": nachgefragt, "modell": modell or llm.modell_fuer("metas")}


# --------------------------------------------------------------------------
# Aufbereitung fuer die Auswahl-Seite
# --------------------------------------------------------------------------


def bilder_optionen(root: Path, meta: dict, body: str = "") -> list[dict]:
    """Bilder, die der Artikel schon verwendet (plus das aktuelle Vorschaubild); die KI erzeugt keine Bilder."""
    aktuell = meta.get("og_image") or meta.get("image") or meta.get("thumb") or ""
    pfade = []
    for p in [aktuell, meta.get("og_image"), meta.get("image"), meta.get("thumb")]:
        if p and p not in pfade:
            pfade.append(p)
    for m in re.finditer(r"(?:src\s*=\s*[\"']|!\[[^\]]*\]\()(/static/img/[^\s\"')]+)", body or meta.get("body_md", "")):
        if m.group(1) not in pfade:
            pfade.append(m.group(1))
    erg = []
    for p in pfade:
        if not p.startswith("/static/img/"):
            continue
        datei = root / p.lstrip("/")
        if not datei.is_file() or datei.suffix.lower() == ".svg":
            continue
        masse = bw.bildmasse(datei)
        gut = bool(masse and masse[0] >= 1200 and abs(masse[0] / masse[1] - 1.91) <= 0.08)
        erg.append({"pfad": p, "rel": p.split("/static/img/", 1)[-1], "masse": masse,
                    "ampel": "gruen" if gut else ("gelb" if masse and masse[0] >= 600 else "rot"),
                    "hinweis": "geeignet (≥ 1200 px, ≈ 1,91:1)" if gut else "nicht ideal für die Link-Vorschau",
                    "aktuell": p == aktuell})
    return erg


def auswahl(root: Path, meta: dict, vorschlaege: dict | None, benoetigt: set[str] | None = None) -> dict:
    """Modell fuer _metas_auswahl.html. `vorschlaege` = Ergebnis von anfordern() (oder None).
    Die Beschreibung wird gegen den empfohlenen Titel geprueft (Regel „in einem Guss“)."""
    tags = [str(t) for t in meta.get("tags") or []]
    aktuell = {f: str(meta.get(f) or "") for f in META_GRENZEN}
    felder = {}
    titel_fest = aktuell["title"]
    beschr_gegen = None
    for f, (lo, hi) in META_GRENZEN.items():
        akt = aktuell[f]
        kart = []
        roh = ((vorschlaege or {}).get("felder", {}).get(f) or {}).get("texte", [])
        braucht = benoetigt is None or f in benoetigt
        if f == "title":
            beschr_gegen = None if (benoetigt is None or "description" in benoetigt) else aktuell["description"]
        for t in roh:
            if f == "description":
                t = normalisiere_beschreibung(t)
            gegen = beschr_gegen if f == "title" else (titel_fest if f == "description" else None)
            k = karte(f, t, tags, akt, gegen)
            if k["grund"] == "unverändert":
                continue
            kart.append(k)
        empfohlen = next((i for i, k in enumerate(kart) if k["ok"]), None)
        if f == "title" and empfohlen is not None:  # mehrere gueltige Titel: der mit den wenigsten Handyzeilen (bei Gleichstand der erste)
            empfohlen = min((i for i, k in enumerate(kart) if k["ok"]), key=lambda i: (kart[i]["zeilen"]["handy"], i))
        if f == "title" and empfohlen is not None:
            titel_fest = kart[empfohlen]["text"]
        aktuell_info = {"text": akt, "laenge": len(akt), "ampel": grenze_ampel(f, len(akt)), "ausserhalb": grenze_ampel(f, len(akt)) != "gruen"}
        if f == "title":
            aktuell_info["zeilen"] = titel_zeilen(akt)
        felder[f] = {
            "name": FELD_NAMEN[f], "lo": lo, "hi": hi, "aktuell": aktuell_info,
            "karten": kart, "empfohlen": empfohlen,
            "gewaehlt": "" if empfohlen is None else str(empfohlen),
            "benoetigt": braucht, "hat_vorschlaege": bool(kart),
        }
    felder["description"]["aktuell"]["guss"] = tb.ueberschneidung(aktuell["title"], aktuell["description"])
    start_t = felder["title"]["karten"][felder["title"]["empfohlen"]]["text"] if felder["title"]["empfohlen"] is not None else aktuell["title"]
    start_b = (felder["description"]["karten"][felder["description"]["empfohlen"]]["text"]
               if felder["description"]["empfohlen"] is not None else aktuell["description"])
    return {"felder": felder, "bilder": bilder_optionen(root, meta),
            "abgewiesen": (vorschlaege or {}).get("abgewiesen", []), "nachgefragt": (vorschlaege or {}).get("nachgefragt", False),
            "tags": tags, "guss": tb.ueberschneidung(start_t, start_b)}


def standard_werte(a: dict) -> dict[str, str]:
    """Die vorausgewaehlte Kombination: je Feld die empfohlene Variante (nur gueltige)."""
    erg = {}
    for f, g in a["felder"].items():
        if g["empfohlen"] is not None and g["benoetigt"]:
            erg[f] = g["karten"][g["empfohlen"]]["text"]
    return erg
