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


def strip_markdown(body_md: str) -> list[str]:
    """Zerlegt den Artikel-Body in reine Text-Absätze (keine Überschriften,
    Codeblöcke, Trennlinien)."""
    paragraphs = []
    in_code_block = False
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


def summarize_short(meta: dict, max_chars: int, with_hashtags: bool = False) -> str:
    text = meta["description"]
    if with_hashtags:
        tags = hashtags(meta.get("tags", []))
        if tags:
            budget = max_chars - len(tags) - 1
            return f"{truncate(text, budget)} {tags}"
    return truncate(text, max_chars)


def summarize_linkedin(meta: dict, min_chars: int, max_chars: int) -> str:
    paragraphs = strip_markdown(meta["body_md"])
    hook = f"{meta['title']}\n\n{meta['description']}"
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


def summarize_reddit(meta: dict, canonical_url: str) -> dict:
    paragraphs = strip_markdown(meta["body_md"])[:4]
    body = "\n\n".join(paragraphs)
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
        text = summarize_short(meta, channels["bluesky"]["max_chars"] - len(canonical_url) - 1)
        result["bluesky"] = f"{text}\n{canonical_url}"
    if "x" in channels:
        result["x"] = summarize_short(meta, channels["x"]["max_chars"])
    if "linkedin" in channels:
        result["linkedin"] = summarize_linkedin(
            meta, channels["linkedin"].get("min_chars", 1200), channels["linkedin"]["max_chars"]
        )
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
