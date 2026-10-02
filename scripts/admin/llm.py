"""Optionales LLM fuer Lektorat und Meta-Vorschlaege.

Zugang ausschliesslich ueber die Blog-eigene .env (envutil.load_dotenv):

    BLOG_LLM_API_KEY=...        # Pflicht, sonst bleibt alles LLM-Seitige aus
    BLOG_LLM_BASE_URL=http://127.0.0.1:8001/v1   # OpenAI-kompatibel (claude-wrapper, Host-Port 8001)
    BLOG_LLM_MODEL=claude-sonnet-4-6

Der Schluessel wird nie ausgegeben, geloggt oder in Fehlermeldungen
uebernommen. Kein Schluessel -> llm_status() meldet "nicht konfiguriert",
die Verwaltung zeigt einen Hinweis, alle regelbasierten Teile laufen weiter.
Keine zusaetzliche Abhaengigkeit: reines urllib.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

STANDARD_BASIS = "http://127.0.0.1:8001/v1"
WARTEZEITEN = (5, 15, 30, 60, 120)  # Sekunden vor jeder Wiederholung bei Verbindungsfehlern, Timeouts, 502/503/504, „API Error: 5xx“
_WRAPPER_5XX = re.compile(r"^\s*API Error:\s*5\d\d")


def _schlafen(sekunden: float) -> None:
    import time
    time.sleep(sekunden)


def _wrapper_5xx(exc) -> bool:
    try:
        return bool(re.search(r"API Error:\s*5\d\d", exc.read(600).decode("utf-8", "replace")))
    except Exception:
        return False


def dienst_erreichbar(timeout: int = 10) -> bool:
    """Kurzer Gesundheitstest (GET <basis>/models). Jede HTTP-Antwort unter 500 zaehlt als erreichbar."""
    st = llm_status()
    if not st["aktiv"]:
        return False
    req = urllib.request.Request(st["basis"] + "/models", headers={"Authorization": "Bearer " + os.environ.get("BLOG_LLM_API_KEY", "").strip()})
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
STANDARD_MODELL = "claude-sonnet-4-6"


class LLMFehler(RuntimeError):
    pass


class LLMVerbindung(LLMFehler):
    """Der Dienst war auch nach allen Wiederholungen nicht erreichbar (Verbindung, Timeout, 5xx) - KEIN Fehler des Inhalts."""


class LLMAbgeschnitten(LLMFehler):
    """Die Antwort wurde vom Antwortlimit abgeschnitten - die Aufgabe sollte geteilt werden."""


class Antwort(str):
    """Antworttext (str) mit Zusatzangaben: .modell (verwendetes Modell), .abgeschnitten (Antwortlimit erreicht)."""
    modell: str = ""
    abgeschnitten: bool = False


# Modellwahl nach Aufgabe (CLAUDE.md, „Modellwahl nach Aufgabe"): Stufen stehen in der .env.
STUFE_STARK_VORGABE = "claude-opus-4-6"
AUFGABEN_STUFE = {"metas": 0, "links": 0, "plattform": 0, "lektorat": 1, "text_umschreiben": 1, "gegenlesen": 1, "tiefenanalyse": 2}
STUFEN_NAMEN = ("Standard", "stark", "max")


def modell_stufen() -> list[str]:
    """[Standard, stark, max] - eine fehlende Stufe uebernimmt die naechstniedrigere."""
    standard = os.environ.get("BLOG_LLM_MODEL", "").strip() or STANDARD_MODELL
    stark = os.environ.get("BLOG_LLM_MODEL_STARK", "").strip() or STUFE_STARK_VORGABE
    hoechst = os.environ.get("BLOG_LLM_MODEL_MAX", "").strip() or stark
    return [standard, stark, hoechst]


def modell_fuer(aufgabe: str | None, stufen_hoeher: int = 0) -> str:
    """Modell fuer eine Aufgabenart; unbekannte oder fehlende Aufgabe = Standard (Altaufrufe bleiben unveraendert)."""
    stufen = modell_stufen()
    i = min(AUFGABEN_STUFE.get(aufgabe or "", 0) + stufen_hoeher, 2)
    return stufen[i]


def eskalations_modell(aufgabe: str | None) -> tuple[str, str] | None:
    """(Modell, Stufenname) der naechsthoeheren Stufe - None, wenn es keine andere gibt (nie nach unten)."""
    aktuell = modell_fuer(aufgabe)
    stufen = modell_stufen()
    i = AUFGABEN_STUFE.get(aufgabe or "", 0)
    for j in range(i + 1, 3):
        if stufen[j] != aktuell:
            return stufen[j], STUFEN_NAMEN[j]
    return None


def llm_status() -> dict:
    key = os.environ.get("BLOG_LLM_API_KEY", "").strip()
    return {
        "aktiv": bool(key),
        "basis": os.environ.get("BLOG_LLM_BASE_URL", STANDARD_BASIS).rstrip("/"),
        "modell": os.environ.get("BLOG_LLM_MODEL", STANDARD_MODELL),
        "hinweis": "" if key else (
            "LLM nicht konfiguriert: BLOG_LLM_API_KEY fehlt in der .env des Blogs "
            "(siehe .env.example). Lektorat und Meta-Vorschläge sind deaktiviert; "
            "die regelbasierte Bewertung läuft vollständig."
        ),
    }


def chat(system: str, nutzer: str, *, timeout: int = 240, max_tokens: int = 3000, aufgabe: str | None = None, modell: str | None = None,
         wartezeiten: tuple | None = None) -> str:
    """wartezeiten: eigene Wiederholungsabstaende (Sekunden); None = WARTEZEITEN (Verwaltung). Der Quick-Redaktor nutzt kuerzere."""
    st = llm_status()
    gewaehlt = modell or modell_fuer(aufgabe)
    if not st["aktiv"]:
        raise LLMFehler(st["hinweis"])
    key = os.environ["BLOG_LLM_API_KEY"].strip()
    nutzlast = {
        "model": gewaehlt,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": nutzer}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        st["basis"] + "/chat/completions",
        data=json.dumps(nutzlast).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    daten = None
    letzter = "keine Antwort"
    for versuch, wartezeit in enumerate((0,) + (WARTEZEITEN if wartezeiten is None else tuple(wartezeiten))):
        if wartezeit:
            _schlafen(wartezeit)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                daten = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Antworttext kuerzen; enthaelt nie den Schluessel (der steht nur im Request-Header)
            if exc.code in (502, 503, 504) or (exc.code == 500 and _wrapper_5xx(exc)):
                letzter = f"HTTP {exc.code}"
                continue
            # 4xx und uebrige Fehler sind Konfigurationsfehler (z. B. 404 Modell unbekannt): sofort melden, nie wiederholen
            raise LLMFehler(f"LLM-Dienst antwortet mit HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            letzter = type(exc.reason).__name__ if isinstance(exc, urllib.error.URLError) and exc.reason is not None else type(exc).__name__
            continue
        except json.JSONDecodeError:
            raise LLMFehler("LLM-Antwort ist kein JSON") from None
        try:
            inhalt = daten["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMFehler("LLM-Antwort ohne Inhalt") from None
        if isinstance(inhalt, str) and _WRAPPER_5XX.match(inhalt):  # Wrapper meldet „API Error: 5xx“ als Antworttext
            letzter, daten = "Wrapper meldet " + inhalt.strip()[:40], None
            continue
        break
    if daten is None:
        raise LLMVerbindung(f"LLM-Dienst nicht erreichbar ({letzter})")
    try:
        a = Antwort(daten["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise LLMFehler("LLM-Antwort ohne Inhalt") from None
    a.modell = gewaehlt
    try:
        a.abgeschnitten = daten["choices"][0].get("finish_reason") == "length"
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return a


def _json_bereinigen(roh: str) -> str:
    """Entfernt, was Modelle gern in JSON mischen: //-Kommentare und Kommas vor } oder ]
    (nur ausserhalb von Zeichenketten)."""
    aus, in_str, esc, i = [], False, False, 0
    while i < len(roh):
        c = roh[i]
        if in_str:
            aus.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            aus.append(c)
        elif c == "/" and roh[i + 1:i + 2] == "/":
            while i < len(roh) and roh[i] != "\n":
                i += 1
            continue
        else:
            aus.append(c)
        i += 1
    return re.sub(r",\s*([}\]])", r"\1", "".join(aus))


def _json_innere_anfuehrungszeichen(roh: str) -> str:
    """Maskiert gerade Anfuehrungszeichen MITTEN in Zeichenketten (Modelle uebernehmen sie
    unmaskiert aus dem Artikeltext, z. B. „Kontor" oder \"Premium\"-Stufe). Ein Zeichen schliesst
    eine Zeichenkette nur, wenn danach (nach Leerraum) , } ] : oder das Ende folgt."""
    aus, in_str, esc = [], False, False
    n = len(roh)
    for i, c in enumerate(roh):
        if not in_str:
            aus.append(c)
            if c == '"':
                in_str = True
            continue
        if esc:
            aus.append(c)
            esc = False
        elif c == "\\":
            aus.append(c)
            esc = True
        elif c == '"':
            j = i + 1
            while j < n and roh[j] in " \t\r\n":
                j += 1
            if j >= n or roh[j] in ",}]:":
                aus.append(c)
                in_str = False
            else:
                aus.append('\\"')
        else:
            aus.append(c)
    return "".join(aus)


def _fehlerdatei(text: str, grund: str) -> None:
    """Rohantwort bei Parse-Fehlern zur Diagnose ablegen (data/, nie im Repo)."""
    try:
        from pathlib import Path as _P
        from datetime import datetime as _D
        ziel = _P(__file__).resolve().parents[2] / "data" / "ranking" / "llm_fehler"
        ziel.mkdir(parents=True, exist_ok=True)
        (ziel / f"{_D.now():%Y%m%d-%H%M%S}.txt").write_text(f"{grund}\n---\n{text}", encoding="utf-8")
        for alt in sorted(ziel.glob("*.txt"))[:-20]:
            alt.unlink()
    except OSError:
        pass


def json_aus_text(text: str) -> dict:
    """Holt das erste JSON-Objekt aus einer Modellantwort (auch in ```json-Zaeunen).
    Toleriert //-Kommentare, Kommas vor Klammern und Zeilenumbrueche in Zeichenketten.
    Bei Fehlern wird die Rohantwort unter data/ranking/llm_fehler/ abgelegt."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    roh = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    letzter = None
    for kandidat in (roh, _json_bereinigen(roh), _json_bereinigen(_json_innere_anfuehrungszeichen(roh))):
        try:
            return json.loads(kandidat, strict=False)
        except json.JSONDecodeError as exc:
            letzter = exc
    abgeschnitten = text.count("{") > text.count("}")
    grund = (f"abgeschnitten (mehr offene als geschlossene Klammern, {len(text)} Zeichen)" if abgeschnitten
             else f"{letzter.msg} in Zeile {letzter.lineno}, Spalte {letzter.colno}")
    _fehlerdatei(text, grund)
    if abgeschnitten or getattr(text, "abgeschnitten", False):
        raise LLMAbgeschnitten(f"LLM-Antwort enthielt kein gültiges JSON ({grund})") from None
    raise LLMFehler(f"LLM-Antwort enthielt kein gültiges JSON ({grund})") from None


def chat_json(system: str, nutzer: str, *, timeout: int = 240, max_tokens: int = 3000, aufgabe: str | None = None, modell: str | None = None) -> dict:
    """Wie chat() + json_aus_text(), mit EINER automatischen Nachfrage, wenn die Antwort kein gueltiges JSON war.
    Eine abgeschnittene Antwort (Antwortlimit) wird NICHT erneut angefragt, sondern als LLMAbgeschnitten gemeldet:
    der Aufrufer teilt die Aufgabe in kleinere Stuecke."""
    antwort = chat(system, nutzer, timeout=timeout, max_tokens=max_tokens, aufgabe=aufgabe, modell=modell)
    try:
        return json_aus_text(antwort)
    except LLMAbgeschnitten:
        raise
    except LLMFehler as erster:
        nachfrage = (nutzer + "\n\nDeine letzte Antwort war kein gültiges JSON (" + str(erster).split("(", 1)[-1].rstrip(")")
                     + "). Antworte erneut NUR mit dem vollständigen JSON-Objekt, ohne Kommentare, ohne Text davor oder danach, "
                     "alle Anführungszeichen im Text mit \\\" maskiert, und halte dich kürzer.")
        return json_aus_text(chat(system, nachfrage, timeout=timeout, max_tokens=max_tokens, aufgabe=aufgabe, modell=modell))


LEKTORAT_SYSTEM = """Du bist ein erfahrenes Redaktionsteam für einen deutschsprachigen IT-Fachblog
(Zielgruppe: IT-Fachleute, Entscheider in KMU). Ihr vereint vier Rollen:
Lektorin (Lesbarkeit, Struktur, Stil, Markterfolg), Redakteur (kürzen, Logik schärfen,
Zielgruppe), Content Strategist (Lesbarkeit, Klickchancen, SEO, Erfolgsaussichten) und
Copy Editor (Rohtext verfeinern, Wirkung, Verständlichkeit).
Bewerte ehrlich und konkret, ohne Lobhudelei. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."""

LEKTORAT_KRITERIEN = {
    "lesbarkeit": "Lesbarkeit (Satzbau, Wortwahl, Verständlichkeit)",
    "fluss": "Flüssig und zusammenhängend (roter Faden, Übergänge)",
    "struktur": "Struktur und Logik (Aufbau, Gliederung, Kürze)",
    "stil": "Stil und Wirkung (Ton, Prägnanz, Bilder)",
    "zielgruppe": "Zielgruppe (Nutzen für IT-Fachpublikum klar?)",
    "grafiken": "Grafiken lockern den Artikel auf (Platzierung, Nutzen)",
    "vorschau": "Artikelvorschau (Titel, Beschreibung) hält hohen Ansprüchen stand",
    "markterfolg": "Klick- und Erfolgschancen (Relevanz, Neuigkeitswert, Teilbarkeit)",
    "klingt_menschlich": "Klingt menschlich (keine KI-Muster: Rhythmus, Stimme, Sprüche, Dramaturgie-Floskeln)",
}

# Schreibregeln gegen KI-Muster (CLAUDE.md, „Schreibregeln gegen KI-Muster"; Ideen aus stop-slop, deutsch angepasst)
KI_MUSTER_REGELN = """Schreibregeln gegen KI-Muster:
- Keine Gedankenstriche (—, –, --) als Stilmittel; Punkt, Komma, Doppelpunkt oder Klammer. Zahlenbereiche (2010–2026) und Bindestriche in Wörtern sind erlaubt.
- Kein „nicht X, sondern Y“ als Dauerfigur; direkt sagen, was es ist.
- Keine Einleiter und Floskeln („Kurz vorweg“, „Der Punkt ist“, „Das ist der eigentliche …“, „Und genau das“, „im Grunde“, „sozusagen“).
- Keine Verstärker und Füllwörter auf Vorrat (genau, ganz, wirklich, echt, durchaus, schlicht, einfach, eigentlich).
- Aktiv, mit einem Menschen oder einer klaren Sache als Subjekt; konkret statt vage (Zahl, Name, Beispiel).
- Satzrhythmus mischen: nie drei gleich lange Sätze hintereinander.
- Keine rhetorischen Frage-Antwort-Muster und keine „zitierfähig“ klingenden Sprüche."""


def lektorat_prompt(meta: dict, lesetext: str, kennzahlen: str) -> str:
    krit = "\n".join(f'    "{k}": {{"note": 1-5, "begruendung": "höchstens 2 Sätze"}},  // {v}'
                     for k, v in LEKTORAT_KRITERIEN.items())
    return f"""Beurteile diesen Artikel. Noten: 5 = sehr gut, 1 = mangelhaft.

Titel: {meta.get('title')}
Beschreibung (Vorschautext): {meta.get('description')}
Zusammenfassung oben: {meta.get('summary', '')}
Tags: {', '.join(meta.get('tags', []) or [])}
Regelbasierte Messwerte: {kennzahlen}

{KI_MUSTER_REGELN}
Für „klingt_menschlich“ beurteilst du, was Zählregeln nicht sehen (Rhythmus, Stimme, Sprüche, Dramaturgie-Floskeln), und nennst in der Begründung 2 bis 3 Fundstellen im Wortlaut.

Artikeltext (## = Überschrift, [Bild: …] = visuelles Element an dieser Stelle):
<<<
{lesetext}
>>>

Antworte nur mit diesem JSON:
{{
  "kriterien": {{
{krit}
  }},
  "vorschau_haelt_stand": {{"urteil": "ja" | "eingeschraenkt" | "nein", "begruendung": "1-2 Sätze"}},
  "verbesserungen": ["genau drei konkrete, umsetzbare Verbesserungen, je mit Fundstelle oder Formulierungsvorschlag"]
}}"""


METAS_REGEL_GUSS = """REGEL „Titel und Beschreibung in einem Guss“ (verbindlich): Die Beschreibung SETZT DEN TITEL FORT, als würde der Satz
hinter dem Titel weitergehen. Sie beginnt normal mit einem Großbuchstaben, OHNE Auslassungspunkte („…“ oder „...“) am Anfang, und wiederholt weder Zahlen noch Schlüsselbegriffe noch Wortfolgen aus dem
Titel, sondern nennt die nächste Information (Wie? Was genau? Wozu?). Titel und Beschreibung hintereinander gelesen ergeben einen Satz.
Schlecht: Titel „Wirtschaftskalender: 84.000 Termine, kostenlos, ohne Login“ + Beschreibung „Über 84.000 Konjunkturtermine seit 2010, ohne Login, kostenlose API“
(Zahl und „ohne Login“ doppelt). Gut: dieselbe Überschrift + Beschreibung „Seit 2010 mit kostenloser API, sechs Download-Formaten und
KI-Recherche per Klick; jeder Termin verlinkt zur Originalquelle.“"""

METAS_SYSTEM = """Du bist Content Strategist und Copy Editor für einen deutschsprachigen IT-Fachblog.
Du schreibst Titel und Beschreibungen für Link-Vorschauen (LinkedIn, Google): ehrlich, konkret,
ohne übertriebene Versprechen, ohne Clickbait, ohne Emojis, ohne Hashtags. Keine Gedankenstriche (—, –, --) und keine Floskeln
(„Kurz vorweg“, „Der Punkt ist“, „im Grunde“, „sozusagen“, „Und genau das“) in Titeln und Beschreibungen.
""" + METAS_REGEL_GUSS + """
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."""


def metas_prompt(meta: dict, lesetext: str, bild_alt: str) -> str:
    laenge = "je 120-160 Zeichen; strebe höchstens 150 Zeichen an (zähle nach, lieber kürzer als zu lang)"
    return f"""Schlage für diesen Artikel neue Vorschautexte vor.

Aktueller Titel ({len(str(meta.get('title', '')))} Zeichen): {meta.get('title')}
Aktuelle Beschreibung ({len(str(meta.get('description', '')))} Zeichen): {meta.get('description')}
Aktueller Bild-Alternativtext: {bild_alt or '(keiner)'}
Tags: {', '.join(meta.get('tags', []) or [])}

Regeln:
- titel: genau 3 Varianten, je 40-70 Zeichen (anstreben: höchstens 65), Kernaussage und wichtigster Begriff vorn.
- beschreibung: genau 3 Varianten, {laenge}. Sie SETZT DEN TITEL FORT (Regel unten), beginnt normal mit einem Großbuchstaben ohne Auslassungspunkte und nicht mit einer Floskel wie
  "In diesem Artikel". In den ersten 90 Zeichen steht der Haken (konkrete Information, Nutzen oder Problem). Ehrlich, nur was der Artikel hält.
  Sie darf KEINE Zahl, kein Schlüsselwort und keine Wortfolge enthalten, die in einer deiner Titel-Varianten steht.
- og_image_alt: ein sachlicher Alternativtext (60-160 Zeichen) für das Vorschaubild. Du siehst das Bild
  nicht: stütze dich auf den vorhandenen Alternativtext und den Artikel, erfinde keine Bilddetails.
- Zähle die Zeichen sorgfältig.

{METAS_REGEL_GUSS}

Artikeltext (Auszug):
<<<
{lesetext[:12000]}
>>>

Antworte nur mit diesem JSON:
{{"titel": ["...", "...", "..."], "beschreibung": ["...", "...", "..."], "og_image_alt": "..."}}"""


# --------------------------------------------------------------------------
# Plattform-Auto-Analyse (plattform_views.py): Beitragstext + Eignung je Plattform
# --------------------------------------------------------------------------

PLATTFORM_ANALYSE_SYSTEM = """Du bist Social-Media-Redakteur für einen deutschsprachigen IT-Fachblog
(Zielgruppe: IT-Fachleute, Entscheider in KMU). Du schreibst einen Beitragstext für genau EINE Plattform,
hältst deren Limits und Regeln ein, bleibst ehrlich (nur was der Artikel hält), ohne Clickbait und ohne Emojis,
und bewertest ehrlich, wie gut sich der Artikel für diese Plattform eignet.
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."""


def plattform_analyse_prompt(plattform_name: str, regeln: str, limit: str, meta: dict, lesetext: str, url: str,
                             titel_noetig: bool = False, link_erlaubt: bool = True) -> str:
    titel_zeile = '  "titel": "Titel (Reddit: höchstens 300 Zeichen, keine Werbesprache)",\n' if titel_noetig else ""
    link_regel = (f"- Der Text endet mit dieser Artikel-URL in einer eigenen Zeile: {url}" if link_erlaubt
                  else "- KEIN Link auf den eigenen Blog im Text (die Plattform lehnt solche Links ab); stattdessen eine Diskussionsfrage mit Mehrwert.")
    return f"""Plattform: {plattform_name}
Limits: {limit}
Regeln der Plattform:
{regeln}

Aufgabe:
- Schreibe einen passenden Beitragstext für genau diese Plattform. Der erste Satz muss tragen.
{link_regel}
- Halte das Zeichenlimit sicher ein (zähle sorgfältig).
- Bewerte die Eignung dieses Artikels für diese Plattform von 0 bis 100 (0 = ungeeignet) mit kurzer Begründung
  und nenne konkrete Risiken (z. B. Regelverstöße, fehlende Passung).

Artikel:
Titel: {meta.get('title')}
Beschreibung: {meta.get('description')}
Slogan: {meta.get('slogan', '')}
Tags: {', '.join(meta.get('tags', []) or [])}

Artikeltext (Auszug):
<<<
{lesetext[:9000]}
>>>

Antworte nur mit diesem JSON:
{{
{titel_zeile}  "text": "der Beitragstext",
  "eignung": 0-100,
  "begruendung": "höchstens 3 Sätze",
  "risiken": ["Risiko 1", "Risiko 2"]
}}"""
