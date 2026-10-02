#!/usr/bin/env python3
"""Erzeugt plattformspezifische Zusammenfassungen eines Artikels.

Nutzung:
    .venv/bin/python scripts/summarize.py <slug> [--help]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import ROOT, load_config, parse_article  # noqa: E402


_BILD_ZEILE = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")
_LI_INHALT = re.compile(r"<li>(.*?)</li>")
_TAG = re.compile(r"<[^>]+>")


def strip_markdown(body_md: str) -> list[str]:
    """Zerlegt den Artikel-Body in reine Text-Absätze (keine Überschriften,
    Codeblöcke, Trennlinien, Bilder). Roh-HTML-Listen (z.B. die
    "fünf-techniken-liste" fürs Web-Layout) werden zu Markdown-Bullets -
    Reddit rendert das, und ueberall sonst bleibt es lesbarer Klartext als
    rohe <ul>/<li>-Tags in der Zwischenablage."""
    paragraphs = []
    in_code_block = False
    in_html_liste = False
    buffer: list[str] = []

    def flush():
        if buffer:
            text = " ".join(buffer).strip()
            if text:
                paragraphs.append(text)
            buffer.clear()

    for line in body_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            flush()
            continue
        if in_code_block:
            continue
        if stripped.startswith("<ul"):
            flush()
            in_html_liste = True
            continue
        if in_html_liste:
            if stripped.startswith("</ul"):
                in_html_liste = False
                continue
            treffer = _LI_INHALT.search(stripped)
            if treffer:
                paragraphs.append(f"- {_TAG.sub('', treffer.group(1)).strip()}")
            continue
        if _BILD_ZEILE.match(stripped):
            flush()
            continue
        if not stripped or stripped == "---":
            flush()
            continue
        if stripped.startswith("#"):
            flush()
            continue
        buffer.append(stripped)
    flush()

    cleaned = []
    for p in paragraphs:
        p = re.sub(r"\*\*(.+?)\*\*", r"\1", p)
        p = re.sub(r"\*(.+?)\*", r"\1", p)
        p = re.sub(r"\[\^[^\]]+\]", "", p)
        p = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", p)
        p = re.sub(r"`([^`]+)`", r"\1", p)
        cleaned.append(p.strip())
    return cleaned


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",.;: ") + "…"


def hashtags(tags: list[str]) -> str:
    return " ".join("#" + re.sub(r"[^A-Za-z0-9]", "", t) for t in tags)


def headline(meta: dict) -> str:
    """Slogan (falls im Frontmatter gesetzt) plus technischer Titel - der
    Slogan ist die griffige Zusammenfassung und muss ZUERST stehen, der
    genaue/technische Titel erst danach. Ohne slogan-Feld bleibt nur der
    Titel wie zuvor."""
    slogan = meta.get("slogan")
    return f"{slogan}\n\n{meta['title']}" if slogan else meta["title"]


def summarize_short(meta: dict, max_chars: int, with_hashtags: bool = False) -> str:
    """Slogan+Titel zuerst, dann die Beschreibung - wie bei summarize_linkedin,
    nur kompakter (Kopf + Leerzeile + Text statt eigener Absaetze). Reicht
    das Budget nicht fuer beides, faellt nur die Beschreibung der Kuerzung
    zum Opfer; der Kopf bleibt ganz, ausser er sprengt das Budget bereits
    allein (dann wird nur er gekuerzt)."""
    tags = hashtags(meta.get("tags", [])) if with_hashtags else ""
    budget = max_chars - len(tags) - 1 if tags else max_chars
    head = headline(meta)
    sep = "\n\n"
    body_budget = budget - len(head) - len(sep)
    if body_budget >= 20:
        text = f"{head}{sep}{truncate(meta['description'], body_budget)}"
    else:
        text = truncate(head, budget)
    if tags:
        text = f"{text} {tags}"
    return text


_SATZ_GRENZE = re.compile(r"(?<=[.!?…])[\"“”»)]*\s+(?=[„\"«(\[A-ZÄÖÜ0-9])")


def _saetze(text: str) -> list[str]:
    """Einfache Satzzerlegung (Abkuerzungen wie z. B. bleiben zusammen)."""
    geschuetzt = re.sub(r"\b(z|d|u|v|o|i)\. ?(B|h|a|U|ä|d)\.", lambda m: m.group(0).replace(".", "\u2024"), text)
    return [s.replace("\u2024", ".").strip() for s in _SATZ_GRENZE.split(geschuetzt) if s.strip()]


def summarize_linkedin_kurz(meta: dict, canonical_url: str, min_chars: int = 150, max_chars: int = 300,
                            max_hashtags: int = 2) -> str:
    """Kurzform mit Karte (Standard): 2-3 kurze Saetze mit Haken (Slogan
    zuerst, dann die Beschreibung), die Artikel-URL DIREKT dahinter im selben
    Absatz, dann Leerzeile und hoechstens 2-3 Hashtags als letzte Zeile
    (Hausregel seit 1.10.2026: Hashtags zuletzt, damit man am Handy nicht
    versehentlich ein Hashtag statt der Adresse antippt). min_chars/max_chars gelten fuer den
    ganzen Beitrag einschliesslich Hashtags und URL. Hintergrund: LinkedIn zeigt mobil ~140, am Desktop ~210
    Zeichen vor "...mehr" - und bei langen Beitraegen erschien in der
    Profil-Uebersicht keine Link-Karte."""
    kandidaten: list[str] = []
    for quelle in (meta.get("slogan"), meta.get("description")):
        for s in _saetze(str(quelle or "")):
            if s not in kandidaten:
                kandidaten.append(s)
    tags = [t for t in (meta.get("tags") or [])][:max(0, min(max_hashtags, 3))]
    tag_zeile = hashtags(tags) if tags else ""
    budget = max_chars - len(canonical_url) - 2 - (len(tag_zeile) + 2 if tag_zeile else 0)
    min_chars = max(0, min_chars - (max_chars - budget))
    gewaehlt: list[str] = []
    laenge = 0
    for s in kandidaten:
        if len(gewaehlt) >= 3:
            break
        zusatz = len(s) + (1 if gewaehlt else 0)
        if laenge + zusatz > budget:
            if laenge >= min_chars or gewaehlt:
                break
            s = truncate(s, budget - laenge - (1 if gewaehlt else 0))
            zusatz = len(s) + (1 if gewaehlt else 0)
        gewaehlt.append(s)
        laenge += zusatz
        if laenge >= min_chars and len(gewaehlt) >= 2:
            break
    if not gewaehlt:
        gewaehlt = [truncate(meta["title"], budget)]
    text = " ".join(gewaehlt) + f" {canonical_url}"
    if tag_zeile:
        text += f"\n\n{tag_zeile}"
    return text


def summarize_linkedin(meta: dict, min_chars: int, max_chars: int, *, canonical_url: str | None = None,
                       format: str = "lang") -> str:
    """format="kurz": siehe summarize_linkedin_kurz (Standard in config.yaml).
    format="lang": Langform wie bisher (Haken + Absaetze bis min_chars,
    hoechstens max_chars, Hashtags am Ende)."""
    if format == "kurz" and canonical_url:
        return summarize_linkedin_kurz(meta, canonical_url, min_chars, max_chars)
    paragraphs = strip_markdown(meta["body_md"])
    hook = f"{headline(meta)}\n\n{meta['description']}"
    parts = [hook]
    length = len(hook)
    for p in paragraphs:
        if length >= min_chars:
            break
        if length + len(p) + 2 > max_chars:
            break
        parts.append(p)
        length += len(p) + 2
    tags = hashtags(meta.get("tags", []))
    text = "\n\n".join(parts)
    if tags and len(text) + len(tags) + 2 <= max_chars:
        text += f"\n\n{tags}"
    return text[:max_chars]


def linkedin_text(meta: dict, cfg: dict, format: str | None = None) -> str:
    """LinkedIn-Text im gewuenschten Format (None = config.yaml, Standard kurz)."""
    li = cfg["channels"]["linkedin"]
    canonical_url = f"{cfg['site']['base_url']}/artikel/{meta['slug']}/"
    fmt = format or li.get("format", "kurz")
    if fmt == "kurz":
        return summarize_linkedin(meta, li.get("min_chars", 150), li.get("max_chars", 300),
                                  canonical_url=canonical_url, format="kurz")
    return summarize_linkedin(meta, li.get("lang_min_chars", 1200), li.get("lang_max_chars", 1800), format="lang")


def summarize_reddit(meta: dict, canonical_url: str) -> dict:
    # "title" bleibt der reine, technische Titel - Reddits eigenes
    # Titelfeld ist einzeilig, ein Slogan davor waere dort unpassend. Im
    # Body (Fliesstext) gilt dieselbe Regel wie ueberall sonst: Slogan zuerst.
    paragraphs = strip_markdown(meta["body_md"])[:4]
    parts = [meta["slogan"]] if meta.get("slogan") else []
    parts += paragraphs
    body = "\n\n".join(parts)
    body += (
        f"\n\nWas ist eure Erfahrung damit? Vollständiger Artikel mit Details: {canonical_url}"
    )
    return {"title": meta["title"], "body": body}


def summarize_all(meta: dict, cfg: dict) -> dict:
    channels = cfg["channels"]
    canonical_url = f"{cfg['site']['base_url']}/artikel/{meta['slug']}/"
    result = {}
    if "mastodon" in channels:
        text = summarize_short(meta, channels["mastodon"]["max_chars"] - len(canonical_url) - 1, with_hashtags=True)
        result["mastodon"] = f"{text}\n{canonical_url}"
    if "bluesky" in channels:
        # Die Karte (_bluesky_link_card in publish.py) zeigt schon Titel +
        # description + Bild - der Post-Text braucht deshalb einen ANDEREN
        # Satz, sonst steht dieselbe Zeile doppelt auf der Seite
        # (Screenshot-Vergleich, Ticket vom 7.9.). Der Slogan ist genau
        # dafuer da: er steht nirgends sonst im Post, und er ist die Zeile,
        # die zuerst stehen soll. Ohne slogan-Feld faellt es auf den ersten
        # Artikelabsatz zurueck (unterscheidet sich von der description
        # so gut wie immer), zuletzt auf die description selbst.
        paragraphs = strip_markdown(meta["body_md"])
        lead = meta.get("slogan") or (paragraphs[0] if paragraphs else meta["description"])
        result["bluesky"] = truncate(lead, channels["bluesky"]["max_chars"])
    if "x" in channels:
        result["x"] = summarize_short(meta, channels["x"]["max_chars"])
    if "linkedin" in channels:
        result["linkedin"] = linkedin_text(meta, cfg)
    if "reddit" in channels:
        result["reddit"] = summarize_reddit(meta, canonical_url)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="Slug des Artikels (Dateiname ohne .md)")
    args = parser.parse_args()

    cfg = load_config()
    articles_dir = ROOT / cfg["paths"]["articles_dir"]
    path = articles_dir / f"{args.slug}.md"
    if not path.exists():
        print(f"FEHLER: {path} nicht gefunden", file=sys.stderr)
        return 1

    meta = parse_article(path)
    summaries = summarize_all(meta, cfg)
    for channel, text in summaries.items():
        print(f"=== {channel} ===")
        if isinstance(text, dict):
            print(f"Titel: {text['title']}")
            print(text["body"])
        else:
            print(text)
        print(f"({len(text) if isinstance(text, str) else len(text['body'])} Zeichen)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
