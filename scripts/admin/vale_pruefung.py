"""Fundstellen per Vale (https://vale.sh, Markdown-bewusster Prosa-Linter).

Vale ergaenzt die regelbasierte Bewertung um konkrete Fundstellen mit
Zeilennummer (sehr lange Saetze, Fuellwoerter, Floskeln, Passiv,
Nominalstil). Die Regeln liegen als YAML in scripts/admin/vale/styles/BlogDE,
das Binary (Go, arm64, keine Abhaengigkeiten) unter data/werkzeuge/vale -
nicht im Repo. Fehlt es, bleibt dieser Teil einfach leer. Fliesst NICHT in
die Punktzahl ein.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HIER = Path(__file__).resolve().parent
KONFIG = HIER / "vale" / ".vale.ini"
_cache: dict[str, tuple[float, dict]] = {}


def binary(root: Path) -> Path | None:
    p = root / "data" / "werkzeuge" / "vale"
    return p if p.exists() else None


def pruefe(root: Path, datei: Path) -> dict:
    """{"verfuegbar": bool, "befunde": [{zeile, regel, stufe, text, auszug}], "fehler": str|None}"""
    vb = binary(root)
    if vb is None:
        return {"verfuegbar": False, "befunde": [], "fehler": None}
    if datei.suffix != ".md" or not datei.exists():
        return {"verfuegbar": True, "befunde": [], "fehler": "nur Markdown-Artikel"}
    schluessel = str(datei)
    mtime = datei.stat().st_mtime
    if schluessel in _cache and _cache[schluessel][0] == mtime:
        return _cache[schluessel][1]
    try:
        r = subprocess.run([str(vb), "--config", str(KONFIG), "--output", "JSON", "--no-exit", str(datei)],
                           capture_output=True, text=True, timeout=60, cwd=root)
        roh = json.loads(r.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"verfuegbar": True, "befunde": [], "fehler": f"Vale-Lauf fehlgeschlagen ({type(exc).__name__})"}
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    befunde = []
    for alerts in roh.values():
        for a in alerts:
            nr = int(a.get("Line") or 0)
            text = zeilen[nr - 1] if 0 < nr <= len(zeilen) else ""
            span = a.get("Span") or [1, 1]
            start = max(0, int(span[0]) - 1)
            auszug = text[start:start + 140] + ("…" if len(text) > start + 140 else "")
            befunde.append({"zeile": nr, "regel": str(a.get("Check", "")).split(".")[-1], "stufe": a.get("Severity", ""),
                            "text": a.get("Message", ""), "auszug": auszug})
    erg = {"verfuegbar": True, "befunde": befunde, "fehler": None}
    _cache[schluessel] = (mtime, erg)
    return erg
