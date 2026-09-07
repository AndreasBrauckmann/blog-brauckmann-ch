#!/usr/bin/env python3
"""Erzeugt ein Bluesky-App-Passwort per API und trägt es in .env ein.

Nutzt einmalig das echte Account-Passwort (nur zur Anmeldung, wird nirgends
gespeichert) statt des Umwegs über Einstellungen -> App-Passwörter im
Browser - com.atproto.server.createAppPassword ist ein regulärer,
authentifizierter API-Aufruf, kein Scraping.

Nutzung:
    .venv/bin/python scripts/bluesky_bootstrap.py

Interaktiv, weil das Account-Passwort nicht als Argument/Umgebungsvariable
in der Shell-History oder in Prozesslisten auftauchen soll.
"""

import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envutil import load_dotenv  # noqa: E402
from social import bluesky  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def _set_env_var(path: Path, key: str, value: str) -> None:
    """Ersetzt eine Zeile ``KEY=...`` in .env, oder hängt sie an - alle
    anderen Zeilen (Secrets, Kommentare) bleiben unverändert stehen."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    pattern = re.compile(rf"^{re.escape(key)}=.*$")
    for i, line in enumerate(lines):
        if pattern.match(line.rstrip("\n")):
            lines[i] = f"{key}={value}\n"
            break
    else:
        lines.append(f"{key}={value}\n")
    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    load_dotenv(ENV_PATH)
    handle = input("Bluesky-Handle (z.B. brauckmannblog.bsky.social): ").strip()
    password = getpass.getpass("Bluesky-Account-Passwort (wird NICHT gespeichert, nur zur Anmeldung genutzt): ")

    print("Melde an ...")
    try:
        session = bluesky.create_session(handle, password)
    except bluesky.BlueskyError as exc:
        print(f"Anmeldung fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    del password  # aus dem Speicher, sobald die Session steht

    name = input("Name für das App-Passwort [blog-brauckmann-ch]: ").strip() or "blog-brauckmann-ch"
    print("Erzeuge App-Passwort ...")
    try:
        result = bluesky.create_app_password(session["accessJwt"], name)
    except bluesky.BlueskyError as exc:
        print(f"App-Passwort-Erzeugung fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    _set_env_var(ENV_PATH, "BLUESKY_HANDLE", handle)
    _set_env_var(ENV_PATH, "BLUESKY_APP_PASSWORD", result["password"])
    print(f"\nApp-Passwort '{name}' erzeugt und in {ENV_PATH} eingetragen")
    print("(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD). Das Account-Passwort wurde nirgends gespeichert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
