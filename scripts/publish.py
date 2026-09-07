#!/usr/bin/env python3
"""Baut, committet, pusht und verteilt einen Artikel.

Nutzung:
    .venv/bin/python scripts/publish.py <slug> [--dry-run] [--channels mastodon,bluesky] [--yes]

--dry-run   führt alles ausser tatsächlichem Posten und Pushen aus.
--yes       überspringt interaktive Bestätigungen (für die Verwaltungsseite/Cron).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import ROOT, load_config, parse_article  # noqa: E402
from envutil import load_dotenv  # noqa: E402
from social import bluesky, linkedin, mastodon  # noqa: E402
from summarize import summarize_all  # noqa: E402

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, text=True, **kwargs)


def confirm(prompt: str, auto_yes: bool) -> bool:
    if auto_yes:
        print(f"{prompt} [auto-ja]")
        return True
    answer = input(f"{prompt} [j/N] ").strip().lower()
    return answer == "j"


def check_diff_for_secrets(cfg: dict) -> list[str]:
    diff = run(["git", "diff", "--cached"], capture_output=True).stdout
    problems = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(diff):
            problems.append(f"Verdächtiges Muster im Diff: {pattern.pattern}")
    for term in cfg.get("forbidden_terms", []):
        if term and term.lower() in diff.lower():
            problems.append(f"Verbotener Begriff im Diff: {term!r}")
    return problems


def wait_for_pages_deploy(commit_sha: str) -> bool:
    result = run(
        ["gh", "run", "list", "--branch", "master", "--limit", "1", "--json", "databaseId,headSha"],
        capture_output=True,
    )
    if result.returncode != 0:
        print("WARNUNG: konnte Actions-Run nicht ermitteln, überspringe Wartezeit.", file=sys.stderr)
        return False
    runs = json.loads(result.stdout or "[]")
    if not runs or runs[0]["headSha"] != commit_sha:
        print("WARNUNG: kein passender Actions-Run gefunden.", file=sys.stderr)
        return False
    run_id = str(runs[0]["databaseId"])
    watch = run(["gh", "run", "watch", run_id, "--exit-status"])
    return watch.returncode == 0


def write_manual_posts(manual_texts: dict[str, str]) -> None:
    path = ROOT / "manual-posts.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"## {timestamp}\n"]
    for channel, text in manual_texts.items():
        lines.append(f"### {channel}\n\n{text}\n")
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Manuelle Posts\n\n"
    path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")


def append_log(entries: list[str]) -> None:
    path = ROOT / "publish-log.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Publish-Log\n\n"
    block = f"## {timestamp}\n\n" + "\n".join(f"- {e}" for e in entries) + "\n\n"
    path.write_text(existing + block, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slug", help="Slug des Artikels")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--channels", help="Kommagetrennt, z.B. mastodon,bluesky,linkedin")
    parser.add_argument("--yes", action="store_true", help="Bestätigungen überspringen")
    args = parser.parse_args()

    cfg = load_config()
    load_dotenv(ROOT / ".env")

    path = ROOT / cfg["paths"]["articles_dir"] / f"{args.slug}.md"
    if not path.exists():
        print(f"FEHLER: {path} nicht gefunden", file=sys.stderr)
        return 1
    meta = parse_article(path)

    requested_channels = set(args.channels.split(",")) if args.channels else None

    print(f"1) Baue Seite für '{meta['title']}' ...")
    build_result = run([sys.executable, str(ROOT / "scripts" / "build.py")])
    if build_result.returncode != 0:
        return 1

    print("2) Zeige Diff ...")
    run(["git", "add", "-A"])
    diff_stat = run(["git", "diff", "--cached", "--stat"], capture_output=True)
    print(diff_stat.stdout)

    problems = check_diff_for_secrets(cfg)
    if problems:
        print("ABBRUCH - verdächtiger Inhalt im Diff:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        run(["git", "reset"])
        return 1

    if not diff_stat.stdout.strip():
        print("Keine Änderungen, nichts zu committen.")
    elif not confirm("3) Committen und pushen?", args.yes):
        print("Abgebrochen.")
        run(["git", "reset"])
        return 1
    elif args.dry_run:
        print("(--dry-run: kein Commit, kein Push)")
        run(["git", "reset"])
    else:
        run(["git", "commit", "-m", f"Artikel: {meta['title']}"])
        push = run(["git", "push"])
        if push.returncode != 0:
            return 1
        sha = run(["git", "rev-parse", "HEAD"], capture_output=True).stdout.strip()
        print("4) Warte auf GitHub-Pages-Deploy ...")
        wait_for_pages_deploy(sha)

    print("5) Erzeuge Zusammenfassungen ...")
    summaries = summarize_all(meta, cfg)

    log_entries = []
    manual_texts = {}
    canonical_url = f"{cfg['site']['base_url']}/artikel/{meta['slug']}/"

    for channel, channel_cfg in cfg["channels"].items():
        if requested_channels is not None and channel not in requested_channels:
            continue
        if channel_cfg.get("manual"):
            text = summaries.get(channel)
            if isinstance(text, dict):
                text = f"# {text['title']}\n\n{text['body']}"
            if text is None:
                text = f"{meta['description']}\n\n{canonical_url}"
            manual_texts[channel] = text
            continue
        if not channel_cfg.get("enabled"):
            continue

        text = summaries.get(channel)
        print(f"\n6) Kanal: {channel}\n---\n{text}\n---")
        if not confirm(f"Auf {channel} posten?", args.yes):
            print(f"  {channel}: übersprungen.")
            continue
        if args.dry_run:
            print("  (--dry-run: nicht wirklich gepostet)")
            continue

        try:
            if channel == "mastodon":
                result = mastodon.post_status(
                    channel_cfg["instance"], os.environ["MASTODON_ACCESS_TOKEN"], text
                )
            elif channel == "bluesky":
                result = bluesky.post(
                    os.environ["BLUESKY_HANDLE"], os.environ["BLUESKY_APP_PASSWORD"], text
                )
            elif channel == "linkedin":
                token = os.environ["LINKEDIN_ACCESS_TOKEN"]
                person_urn = linkedin.get_person_urn(token)
                result = linkedin.post_share(token, person_urn, text)
                linkedin.post_comment(token, person_urn, result["urn"], canonical_url)
            else:
                print(f"  {channel}: kein Posting-Modul vorhanden, übersprungen.")
                continue
        except Exception as exc:
            print(f"  FEHLER bei {channel}: {exc}", file=sys.stderr)
            log_entries.append(f"{channel}: FEHLGESCHLAGEN - {exc}")
            continue

        print(f"  Gepostet: {result.get('url')}")
        log_entries.append(f"{channel}: {result.get('url')}")

    if manual_texts:
        print("\n7) Schreibe manual-posts.md ...")
        if not args.dry_run:
            write_manual_posts(manual_texts)
        for channel in manual_texts:
            log_entries.append(f"{channel}: manuell (siehe manual-posts.md)")

    if log_entries and not args.dry_run:
        append_log([f"{meta['slug']}: {e}" for e in log_entries])

    print("\nFertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
