"""Messung „F · Satz & Layout“: Playwright gegen die gebaute Seite, Ergebnis je Build zwischengespeichert.

Die Messung selbst macht satz_messlauf.py in einem Unterprozess mit dem Python, das Playwright hat
(BLOG_PLAYWRIGHT_PYTHON, Vorgabe ~/TradingAgents/.venv/bin/python). Ergebnisse liegen unter
data/ranking/satz/<slug>.json (Hash der dist-Seite); ein neuer Build mit anderem Inhalt oder anderem CSS
macht den Eintrag ungueltig. Gemessen wird im Hintergrund, immer nur eine Messung gleichzeitig.
Bildschirmfotos fuer Vergleich und Gutachten: data/ranking/satz/bilder/<slug>/.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
MESSLAUF = HIER / "satz_messlauf.py"
TIMEOUT = 240
_lock = threading.Lock()
_messend: set[str] = set()


def playwright_python() -> str:
    return os.environ.get("BLOG_PLAYWRIGHT_PYTHON") or str(Path.home() / "TradingAgents" / ".venv" / "bin" / "python")


def verzeichnis(root: Path) -> Path:
    p = root / "data" / "ranking" / "satz"
    p.mkdir(parents=True, exist_ok=True)
    return p


def seite(root: Path, slug: str) -> Path:
    return root / "dist" / "artikel" / slug / "index.html"


def seiten_hash(root: Path, slug: str, css_text: str = "") -> str:
    s = seite(root, slug)
    if not s.exists():
        return ""
    return hashlib.sha256(s.read_bytes() + css_text.encode()).hexdigest()[:20]


def _datei(root: Path, name: str) -> Path:
    return verzeichnis(root) / f"{name}.json"


def lesen(root: Path, name: str, hash_: str) -> dict | None:
    try:
        d = json.loads(_datei(root, name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return d.get("roh") if d.get("hash") == hash_ and hash_ else None


def gespeichert(root: Path, slug: str) -> dict | None:
    """Rohmesswerte fuer den aktuellen Build des Artikels - oder None (noch nicht gemessen / veraltet)."""
    return lesen(root, slug, seiten_hash(root, slug))


def wird_gemessen(slug: str) -> bool:
    with _lock:
        return slug in _messend


def _speichern(root: Path, name: str, hash_: str, roh: dict) -> None:
    p = _datei(root, name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"hash": hash_, "zeitpunkt": datetime.now().isoformat(timespec="seconds"), "roh": roh}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def messlauf(root: Path, slug: str, css: Path | None = None, bilder: Path | None = None, praefix: str = "satz") -> dict:
    """Fuehrt die Messung aus (blockierend). Wirft RuntimeError mit lesbarem Text bei Fehlern."""
    s = seite(root, slug)
    if not s.exists():
        raise RuntimeError("Die gebaute Seite fehlt (dist/) - bitte zuerst bauen.")
    cmd = [playwright_python(), str(MESSLAUF), str(s)]
    if css:
        cmd += ["--css", str(css)]
    if bilder:
        cmd += ["--bilder", str(bilder), "--praefix", praefix]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=root)
    except FileNotFoundError:
        raise RuntimeError("Python mit Playwright nicht gefunden (BLOG_PLAYWRIGHT_PYTHON).") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Messung nach {TIMEOUT} Sekunden abgebrochen.") from None
    if r.returncode != 0:
        raise RuntimeError("Messung fehlgeschlagen: " + (r.stderr or r.stdout).strip()[-300:])
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("Messung lieferte kein JSON.") from None


def messen(root: Path, slug: str) -> dict:
    """Misst und speichert fuer den aktuellen Build."""
    h = seiten_hash(root, slug)
    roh = messlauf(root, slug)
    _speichern(root, slug, h, roh)
    return roh


def im_hintergrund(root: Path, slugs: list[str], nur_veraltete: bool = True) -> int:
    """Startet (eine) Hintergrundmessung fuer die Artikel; gibt die Zahl der eingeplanten Artikel zurueck."""
    offen = [s for s in slugs if seite(root, s).exists() and not (nur_veraltete and gespeichert(root, s))]
    with _lock:
        neu = [s for s in offen if s not in _messend]
        _messend.update(neu)
    if not neu:
        return 0

    def arbeit():
        for s in neu:
            try:
                messen(root, s)
            except Exception:
                pass  # Fehler zeigt sich als „noch nicht gemessen“; erneutes Anstossen moeglich
            finally:
                with _lock:
                    _messend.discard(s)
    threading.Thread(target=arbeit, daemon=True, name="satzmessung").start()
    return len(neu)


# --- Entwurfs-CSS (Vorher/Nachher ohne die echte CSS zu aendern) -----------------------------------------------


def entwurf_css(root: Path) -> Path:
    return verzeichnis(root) / "entwurf.css"


def entwurf_messen(root: Path, slug: str) -> dict:
    """Misst den Artikel mit dem Entwurfs-CSS (zusaetzlich zur echten CSS) und erzeugt Vorher/Nachher-Bilder."""
    css = entwurf_css(root)
    if not css.exists():
        raise RuntimeError("Kein Entwurfs-CSS vorhanden (data/ranking/satz/entwurf.css).")
    bilder = verzeichnis(root) / "bilder" / slug
    h = seiten_hash(root, slug, css.read_text(encoding="utf-8"))
    roh = messlauf(root, slug, css=css, bilder=bilder, praefix="nachher")
    messlauf(root, slug, css=None, bilder=bilder, praefix="vorher")
    _speichern(root, f"{slug}-entwurf", h, roh)
    return roh


def entwurf_gespeichert(root: Path, slug: str) -> dict | None:
    css = entwurf_css(root)
    if not css.exists():
        return None
    return lesen(root, f"{slug}-entwurf", seiten_hash(root, slug, css.read_text(encoding="utf-8")))


def bilder_fuer_gutachten(root: Path, slug: str) -> list[Path]:
    """Bildschirmfotos (hell/dunkel, Desktop/Handy) fuer das Gutachten; neu erzeugt, wenn die Seite sich geaendert hat."""
    ordner = verzeichnis(root) / "bilder" / slug
    messlauf(root, slug, bilder=ordner, praefix="gutachten")
    return sorted(ordner.glob("gutachten-*.png"))


def uebersicht(root: Path, slugs: list[str], entwurf: bool = False) -> dict:
    """{kriterium_id: {"name","soll","artikel": {slug: {"status","messwert","vorschlag"} | None}, "betroffen": N, "gemessen": M}}.
    Zeigt, ob ein Mangel nur einen Artikel betrifft oder - wie meist - die gemeinsame static/style.css."""
    import bewertung as bw
    erg: dict = {}
    for slug in slugs:
        roh = entwurf_gespeichert(root, slug) if entwurf else gespeichert(root, slug)
        kr = {k.id: k for k in bw.bewerte_satz(roh)} if roh else {}
        for kid, (kat, name, punkte, soll) in bw.KRITERIEN.items():
            if kat != "F":
                continue
            e = erg.setdefault(kid, {"name": name, "soll": soll, "artikel": {}, "betroffen": 0, "gemessen": 0})
            k = kr.get(kid)
            e["artikel"][slug] = {"status": k.status, "messwert": k.messwert, "vorschlag": k.vorschlag} if k else None
            if k and k.status != "na":
                e["gemessen"] += 1
                if k.status in ("teils", "nein"):
                    e["betroffen"] += 1
    return erg
