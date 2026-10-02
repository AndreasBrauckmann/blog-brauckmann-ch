"""Versionsverlauf je Artikel (Vorbild: OneDrive-Versionsverlauf).

Quellen:
  1. Eigene Schnappschuesse: data/versions/<slug>/<zeitstempel>__<grund>.md plus
     index.json. Vor und nach JEDEM Schreibvorgang der Verwaltung wird gesichert.
     Bestehende Backups unter data/backups/artikel/ werden einmalig einsortiert.
  2. Aenderungen ausserhalb der Verwaltung: abgleich() vergleicht den Hash der
     Datei mit dem letzten Schnappschuss und legt bei Abweichung einen neuen an.
  3. Git-Verlauf (nur lesend: git log --follow, git show): committete Fassungen.
     Gleicher Inhalt wie ein Schnappschuss -> eine gemeinsame Zeile.

Aufbewahrung: die letzten 200 Schnappschuesse je Artikel; aeltere werden
geloescht, nie aber die zuletzt veroeffentlichte (committete) Fassung.
Bilddateien werden nicht versioniert (siehe Git). Alles liegt unter data/
(in .gitignore). Funktionen nehmen die Repo-Wurzel als Parameter (Tests:
Wegwerf-Verzeichnisse).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import yaml

MAX_SCHNAPPSCHUESSE = 200
MAX_COMMITS = 60

GRUENDE = {
    "start": "Erste Erfassung",
    "extern": "Änderung außerhalb der Verwaltung",
    "metas": "Metas übernommen",
    "ordnung": "Alles in Ordnung bringen",
    "rueckgaengig": "Rückgängig",
    "wiederhergestellt": "Version wiederhergestellt",
    "backup": "Backup (importiert)",
}
_VID_S = re.compile(r"^s-(\d{8}-\d{6}(?:-\d+)?__[a-z]+)$")
_VID_G = re.compile(r"^g-([0-9a-f]{40})$")

_lock = threading.RLock()
# wird von in_ordnung gesetzt: (slug) -> bool; waehrend eines Schreibvorgangs kein Abgleich
gesperrt_fn = lambda slug: False  # noqa: E731


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dir(root: Path, slug: str) -> Path:
    return root / "data" / "versions" / slug


def _index_pfad(root: Path, slug: str) -> Path:
    return _dir(root, slug) / "index.json"


def _lade(root: Path, slug: str) -> dict:
    p = _index_pfad(root, slug)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    d.setdefault("eintraege", [])
    d.setdefault("importiert", [])
    d.setdefault("git", {})
    return d


def _speichere(root: Path, slug: str, d: dict) -> None:
    p = _index_pfad(root, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def kennzahlen(text: str) -> dict:
    """Wörter (Fliesstext ohne Frontmatter, grob), Titel, Beschreibung."""
    titel = beschr = ""
    body = text
    if text.startswith("---"):
        ende = text.find("\n---", 3)
        if ende > 0:
            try:
                fm = yaml.safe_load(text[3:ende]) or {}
                titel, beschr = str(fm.get("title") or ""), str(fm.get("description") or "")
            except yaml.YAMLError:
                pass
            body = text[ende + 4:]
    body = re.sub(r"<(style|script|svg)\b.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return {"woerter": len(re.findall(r"\w+", body)), "titel": titel, "beschr": beschr}


def _zeit(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def sichere(root: Path, slug: str, text: str, grund: str, zeit: datetime | None = None, hinweis: str = "") -> dict | None:
    """Legt einen Schnappschuss an. Gleicher Inhalt wie der juengste Schnappschuss -> kein neuer (None)."""
    with _lock:
        d = _lade(root, slug)
        h = hash_text(text)
        if d["eintraege"] and d["eintraege"][-1]["hash"] == h:
            return None
        zeit = zeit or datetime.now()
        stempel = zeit.strftime("%Y%m%d-%H%M%S")
        name = f"{stempel}__{grund}"
        n = 1
        while (_dir(root, slug) / f"{name}.md").exists():
            name = f"{stempel}-{n}__{grund}"
            n += 1
        _dir(root, slug).mkdir(parents=True, exist_ok=True)
        (_dir(root, slug) / f"{name}.md").write_text(text, encoding="utf-8")
        k = kennzahlen(text)
        e = {"id": name, "zeit": _zeit(zeit), "grund": grund, "hash": h, "bytes": len(text.encode("utf-8")),
             "woerter": k["woerter"], "titel": k["titel"], "beschr": k["beschr"], "hinweis": hinweis}
        d["eintraege"].append(e)
        d["eintraege"].sort(key=lambda x: x["zeit"])
        _speichere(root, slug, d)
        _aufraeumen(root, slug, d)
        return e


def _backups_einsortieren(root: Path, slug: str, d: dict) -> bool:
    geaendert = False
    bdir = root / "data" / "backups" / "artikel"
    if not bdir.exists():
        return False
    muster = re.compile(rf"^{re.escape(slug)}\.(\d{{8}}-\d{{6}})(?:-(\d+))?\.md$")
    for p in sorted(bdir.glob(f"{slug}.*.md")):
        m = muster.match(p.name)
        if not m or p.name in d["importiert"]:
            continue
        d["importiert"].append(p.name)
        geaendert = True
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        h = hash_text(text)
        if any(e["hash"] == h for e in d["eintraege"]):
            continue  # Inhalt schon vorhanden: nicht doppelt anlegen
        zeit = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
        name = f"{m.group(1)}-b{m.group(2) or 0}__backup"
        (_dir(root, slug)).mkdir(parents=True, exist_ok=True)
        (_dir(root, slug) / f"{name}.md").write_text(text, encoding="utf-8")
        k = kennzahlen(text)
        d["eintraege"].append({"id": name, "zeit": _zeit(zeit), "grund": "backup", "hash": h, "bytes": len(text.encode("utf-8")),
                               "woerter": k["woerter"], "titel": k["titel"], "beschr": k["beschr"], "hinweis": p.name})
    if geaendert:
        d["eintraege"].sort(key=lambda x: x["zeit"])
    return geaendert


def abgleich(root: Path, slug: str) -> dict | None:
    """Erkennt Aenderungen ausserhalb der Verwaltung; importiert alte Backups. Gibt den neuen Eintrag zurueck oder None."""
    pfad = root / "articles" / f"{slug}.md"
    if not pfad.exists() or gesperrt_fn(slug):
        return None
    with _lock:
        d = _lade(root, slug)
        if _backups_einsortieren(root, slug, d):
            _speichere(root, slug, d)
        text = pfad.read_text(encoding="utf-8")
        h = hash_text(text)
        letzter = d["eintraege"][-1] if d["eintraege"] else None
        if letzter and letzter["hash"] == h:
            return None
        zeit = datetime.fromtimestamp(pfad.stat().st_mtime)
        if letzter and zeit < datetime.fromisoformat(letzter["zeit"]):
            zeit = datetime.now()  # Dateizeit vor dem letzten Eintrag: Reihenfolge wahren
        # Inhalt war schon einmal da (z. B. Datei von Hand zurueckgesetzt): trotzdem als neue Zeile, damit der Verlauf stimmt
        return sichere(root, slug, text, "start" if not letzter else "extern", zeit)


def abgleich_alle(root: Path, slugs) -> None:
    for s in slugs:
        try:
            abgleich(root, s)
        except OSError:
            pass


def vor_schreiben(root: Path, slug: str) -> None:
    """Sichert die aktuelle Fassung, bevor die Verwaltung schreibt (inkl. Erkennung externer Aenderungen)."""
    pfad = root / "articles" / f"{slug}.md"
    with _lock:
        d = _lade(root, slug)
        if _backups_einsortieren(root, slug, d):
            _speichere(root, slug, d)
        text = pfad.read_text(encoding="utf-8")
        letzter = d["eintraege"][-1] if d["eintraege"] else None
        if not letzter or letzter["hash"] != hash_text(text):
            sichere(root, slug, text, "start" if not letzter else "extern", datetime.fromtimestamp(pfad.stat().st_mtime) if letzter is None else datetime.now())


def nach_schreiben(root: Path, slug: str, grund: str, hinweis: str = "") -> dict | None:
    """Traegt die Fassung nach einem Schreibvorgang der Verwaltung als Version ein."""
    text = (root / "articles" / f"{slug}.md").read_text(encoding="utf-8")
    e = sichere(root, slug, text, grund, hinweis=hinweis)
    if e is None:  # gleicher Inhalt wie der juengste Schnappschuss: Grund nachtragen
        with _lock:
            d = _lade(root, slug)
            if d["eintraege"] and d["eintraege"][-1]["grund"] in ("start", "extern"):
                d["eintraege"][-1]["grund"] = grund
                d["eintraege"][-1]["hinweis"] = hinweis
                _speichere(root, slug, d)
    return e


# --------------------------------------------------------------------------
# Git (nur lesen)
# --------------------------------------------------------------------------


def _git(root: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)


def git_commits(root: Path, slug: str) -> list[dict]:
    """[{sha, zeit, meldung}] neueste zuerst; leer ohne Git."""
    try:
        r = _git(root, "log", "--follow", f"--max-count={MAX_COMMITS}", "--format=%H%x1f%cI%x1f%s", "--", f"articles/{slug}.md")
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    erg = []
    for zeile in r.stdout.splitlines():
        teile = zeile.split("\x1f")
        if len(teile) == 3:
            try:
                z = datetime.fromisoformat(teile[1]).astimezone().replace(tzinfo=None)
            except ValueError:
                continue
            erg.append({"sha": teile[0], "zeit": _zeit(z), "meldung": teile[2]})
    return erg


def git_text(root: Path, slug: str, sha: str) -> str | None:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None
    try:
        r = _git(root, "show", f"{sha}:articles/{slug}.md")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


# --------------------------------------------------------------------------
# Gesamtliste
# --------------------------------------------------------------------------


def alle(root: Path, slug: str) -> list[dict]:
    """Zeilen fuer die Box, neueste zuerst. Jede: id, zeit, grund, label, hash, woerter, d_woerter,
    titel_geaendert, beschr_geaendert, aktuell, commit {sha, meldung} | None, hinweis."""
    pfad = root / "articles" / f"{slug}.md"
    aktuell_hash = hash_text(pfad.read_text(encoding="utf-8")) if pfad.exists() else ""
    with _lock:
        d = _lade(root, slug)
        zeilen = [dict(e, quelle="snapshot", commit=None, label=GRUENDE.get(e["grund"], e["grund"]), vid="s-" + e["id"]) for e in d["eintraege"]]
        commits = git_commits(root, slug)
        cache = d["git"]
        neu = False
        for c in commits:
            if c["sha"] not in cache:
                t = git_text(root, slug, c["sha"])
                if t is None:
                    cache[c["sha"]] = None
                else:
                    k = kennzahlen(t)
                    cache[c["sha"]] = {"hash": hash_text(t), "woerter": k["woerter"], "titel": k["titel"], "beschr": k["beschr"]}
                neu = True
        if neu:
            _speichere(root, slug, d)
        for pos, c in enumerate(commits):
            k = cache.get(c["sha"])
            if not k:
                continue
            # gleicher Inhalt wie ein (noch nicht zugeordneter) Schnappschuss: gemeinsame Zeile
            kandidaten = [z for z in zeilen if z["quelle"] == "snapshot" and z["hash"] == k["hash"] and not z["commit"]]
            if kandidaten:
                ct = datetime.fromisoformat(c["zeit"])
                z = min(kandidaten, key=lambda x: abs((datetime.fromisoformat(x["zeit"]) - ct).total_seconds()))
                z["commit"] = {"sha": c["sha"], "meldung": c["meldung"], "zeit": c["zeit"]}
            else:
                zeilen.append({"id": c["sha"], "vid": "g-" + c["sha"], "zeit": c["zeit"], "grund": "commit", "label": "Commit",
                               "hash": k["hash"], "woerter": k["woerter"], "titel": k["titel"], "beschr": k["beschr"], "quelle": "git",
                               "commit": {"sha": c["sha"], "meldung": c["meldung"], "zeit": c["zeit"]}, "hinweis": "", "_ord": len(commits) - pos})
    zeilen.sort(key=lambda z: (z["zeit"], z.get("_ord", 0)))
    for i, z in enumerate(zeilen):
        vor = zeilen[i - 1] if i else None
        z["d_woerter"] = (z["woerter"] - vor["woerter"]) if vor else None
        z["titel_geaendert"] = bool(vor and vor["titel"] != z["titel"])
        z["beschr_geaendert"] = bool(vor and vor["beschr"] != z["beschr"])
        z["aktuell"] = False
    zeilen.reverse()
    for z in zeilen:
        if z["hash"] == aktuell_hash:
            z["aktuell"] = True
            break
    return zeilen


def text_von(root: Path, slug: str, vid: str) -> str | None:
    m = _VID_S.match(vid)
    if m:
        p = _dir(root, slug) / f"{m.group(1)}.md"
        return p.read_text(encoding="utf-8") if p.is_file() else None
    m = _VID_G.match(vid)
    if m:
        return git_text(root, slug, m.group(1))
    return None


def zeile(root: Path, slug: str, vid: str) -> dict | None:
    return next((z for z in alle(root, slug) if z["vid"] == vid), None)


def diff_zeilen(alt: str, neu: str, alt_name: str, neu_name: str) -> list[str]:
    return list(difflib.unified_diff(alt.splitlines(), neu.splitlines(), alt_name, neu_name, lineterm="", n=2))


def frontmatter_gueltig(text: str, slug: str) -> str | None:
    """Fehlertext oder None. Eine wiederhergestellte Fassung muss ein lesbares Frontmatter mit gleichem Slug haben."""
    if not text.startswith("---"):
        return "Fassung beginnt nicht mit Frontmatter"
    ende = text.find("\n---", 3)
    if ende < 0:
        return "Ende des Frontmatters nicht gefunden"
    try:
        fm = yaml.safe_load(text[3:ende]) or {}
    except yaml.YAMLError:
        return "Frontmatter nicht lesbar"
    fehlt = [k for k in ("title", "slug", "date", "description") if k not in fm]
    if fehlt:
        return "Frontmatter fehlt: " + ", ".join(fehlt)
    if str(fm.get("slug")) != slug:
        return f"Slug der Fassung ({fm.get('slug')}) passt nicht zu {slug}"
    return None


# --------------------------------------------------------------------------
# Aufbewahrung
# --------------------------------------------------------------------------


def _aufraeumen(root: Path, slug: str, d: dict) -> None:
    """Letzte MAX_SCHNAPPSCHUESSE behalten; die zuletzt committete Fassung nie loeschen."""
    ein = d["eintraege"]
    if len(ein) <= MAX_SCHNAPPSCHUESSE:
        return
    geschuetzt: set[str] = set()
    for c in git_commits(root, slug)[:1]:
        k = d["git"].get(c["sha"])
        if k is None:
            t = git_text(root, slug, c["sha"])
            k = {"hash": hash_text(t)} if t else None
        if k:
            geschuetzt.add(k["hash"])
    ueberzaehlig = len(ein) - MAX_SCHNAPPSCHUESSE
    behalten, entfernt = [], 0
    for e in ein:  # aelteste zuerst
        if entfernt < ueberzaehlig and e["hash"] not in geschuetzt:
            try:
                (_dir(root, slug) / f"{e['id']}.md").unlink()
            except OSError:
                pass
            entfernt += 1
        else:
            behalten.append(e)
    d["eintraege"] = behalten
    _speichere(root, slug, d)
