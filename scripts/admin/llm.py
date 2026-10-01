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
STANDARD_MODELL = "claude-sonnet-4-6"


class LLMFehler(RuntimeError):
    pass


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


def chat(system: str, nutzer: str, *, timeout: int = 240, max_tokens: int = 3000) -> str:
    st = llm_status()
    if not st["aktiv"]:
        raise LLMFehler(st["hinweis"])
    key = os.environ["BLOG_LLM_API_KEY"].strip()
    nutzlast = {
        "model": st["modell"],
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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            daten = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Antworttext kuerzen; enthaelt nie den Schluessel (der steht nur im Request-Header)
        raise LLMFehler(f"LLM-Dienst antwortet mit HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMFehler(f"LLM-Dienst nicht erreichbar ({type(exc).__name__})") from None
    except json.JSONDecodeError:
        raise LLMFehler("LLM-Antwort ist kein JSON") from None
    try:
        return daten["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMFehler("LLM-Antwort ohne Inhalt") from None


def json_aus_text(text: str) -> dict:
    """Holt das erste JSON-Objekt aus einer Modellantwort (auch in ```json-Zaeunen)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    roh = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(roh)
    except json.JSONDecodeError:
        raise LLMFehler("LLM-Antwort enthielt kein gültiges JSON") from None


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
}


def lektorat_prompt(meta: dict, lesetext: str, kennzahlen: str) -> str:
    krit = "\n".join(f'    "{k}": {{"note": 1-5, "begruendung": "höchstens 2 Sätze"}},  // {v}'
                     for k, v in LEKTORAT_KRITERIEN.items())
    return f"""Beurteile diesen Artikel. Noten: 5 = sehr gut, 1 = mangelhaft.

Titel: {meta.get('title')}
Beschreibung (Vorschautext): {meta.get('description')}
Zusammenfassung oben: {meta.get('summary', '')}
Tags: {', '.join(meta.get('tags', []) or [])}
Regelbasierte Messwerte: {kennzahlen}

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


METAS_SYSTEM = """Du bist Content Strategist und Copy Editor für einen deutschsprachigen IT-Fachblog.
Du schreibst Titel und Beschreibungen für Link-Vorschauen (LinkedIn, Google): ehrlich, konkret,
ohne übertriebene Versprechen, ohne Clickbait, ohne Emojis, ohne Hashtags.
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."""


def metas_prompt(meta: dict, lesetext: str, bild_alt: str) -> str:
    return f"""Schlage für diesen Artikel neue Vorschautexte vor.

Aktueller Titel ({len(str(meta.get('title', '')))} Zeichen): {meta.get('title')}
Aktuelle Beschreibung ({len(str(meta.get('description', '')))} Zeichen): {meta.get('description')}
Aktueller Bild-Alternativtext: {bild_alt or '(keiner)'}
Tags: {', '.join(meta.get('tags', []) or [])}

Regeln:
- titel: genau 3 Varianten, je 40-70 Zeichen, Kernaussage und wichtigster Begriff vorn.
- beschreibung: genau 3 Varianten, je 120-160 Zeichen. In den ersten 100 Zeichen steht das Problem
  oder der konkrete Nutzen (Haken), keine Floskel wie "In diesem Artikel". Ehrlich, nur was der Artikel hält.
- og_image_alt: ein sachlicher Alternativtext (60-160 Zeichen) für das Vorschaubild. Du siehst das Bild
  nicht: stütze dich auf den vorhandenen Alternativtext und den Artikel, erfinde keine Bilddetails.
- Zähle die Zeichen sorgfältig.

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
