"""Deploy-Ablauf der Verwaltung: Pruefen -> Bauen -> Diff -> Veroeffentlichen -> Live pruefen.

Grundsaetze (siehe CLAUDE.md, Abschnitt Verwaltung):
- Nichts wird ohne Klick + Bestaetigung committet oder gepusht.
- Committet wird nur, was der Nutzer ausgewaehlt hat, und nur aus einer
  festen Whitelist (articles/, dist/, static/img/, templates/, config.yaml,
  CLAUDE.md, publish-log.md; scripts/ und alles Uebrige nur mit
  ausdruecklicher Auswahl). NIE: manual-posts.md, data/, .env*, .secrets/.
  Geloeschte Dateien nur mit ausdruecklicher Auswahl.
- Der Stand, den der Nutzer geprueft hat, wird als Fingerabdruck (HEAD +
  Inhalt jeder ausgewaehlten Datei) mitgeschickt; hat sich seither etwas
  geaendert, bricht das Veroeffentlichen ab.
- Commit nur der ausgewaehlten Pfade (git commit --only), damit nichts
  mitrutscht, was jemand anders schon in den Index gelegt hat.

Alle Funktionen nehmen das Repo-Wurzelverzeichnis als Parameter, damit die
Tests gegen ein Wegwerf-Repo mit eigenem Bare-Remote laufen.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

NIE = ("manual-posts.md", "data/*", "data", ".env", ".env.*", ".secrets/*", "*.pem", "*.key", "id_rsa*",
       "id_ed25519*", "*.sqlite", "*.db", "logs/*", "seo-log/*")
ERLAUBT_MIT_AUSWAHL_TROTZ_NIE = (".env.example",)
STANDARD_JA = ("articles/*", "dist/*", "templates/*", "config.yaml", "CLAUDE.md", "publish-log.md")

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|access[_-]?token|password|app[_-]?password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{30,}"),
]


class DeployFehler(RuntimeError):
    pass


def git(root: Path, *args: str, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise DeployFehler(f"git {' '.join(args[:2])} fehlgeschlagen: {(r.stderr or r.stdout).strip()[:400]}")
    return r


# --------------------------------------------------------------------------
# Status und Klassifizierung
# --------------------------------------------------------------------------


@dataclass
class Aenderung:
    pfad: str
    code: str  # zwei Zeichen aus git status --porcelain (XY), "??" = neu
    alt_pfad: str | None = None
    art: str = ""  # neu | geaendert | geloescht | umbenannt
    bereich: str = ""
    erlaubt: bool = True
    standard: bool = False
    grund: str = ""
    referenziert_von: list[str] = field(default_factory=list)


def status(root: Path) -> list[Aenderung]:
    r = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", check=True)
    teile = r.stdout.split("\0")
    erg: list[Aenderung] = []
    i = 0
    while i < len(teile):
        eintrag = teile[i]
        i += 1
        if len(eintrag) < 4:
            continue
        code, pfad = eintrag[:2], eintrag[3:]
        alt = None
        if "R" in code or "C" in code:
            alt = teile[i]
            i += 1
        a = Aenderung(pfad=pfad, code=code, alt_pfad=alt)
        if code == "??" or "A" in code:
            a.art = "neu"
        elif "D" in code:
            a.art = "geloescht"
        elif "R" in code:
            a.art = "umbenannt"
        else:
            a.art = "geaendert"
        erg.append(a)
    return erg


def _passt(pfad: str, muster: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(pfad, m) or pfad == m.rstrip("/*") for m in muster)


def bilder_der_artikel(root: Path, artikel_pfade: list[str]) -> dict[str, list[str]]:
    """static/img/...-Pfad -> Liste der Artikel, die ihn referenzieren (Frontmatter + Text)."""
    ref: dict[str, list[str]] = {}
    for ap in artikel_pfade:
        p = root / ap
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"/static/(img/[^\s\"')<>]+)", text):
            ref.setdefault("static/" + m.group(1).rstrip(".,;"), []).append(Path(ap).stem)
    return ref


def klassifiziere(root: Path, aenderungen: list[Aenderung]) -> list[Aenderung]:
    artikel = [a.pfad for a in aenderungen if a.pfad.startswith("articles/") and a.art != "geloescht"]
    ref = bilder_der_artikel(root, artikel)
    for a in aenderungen:
        p = a.pfad
        a.bereich = p.split("/", 1)[0] if "/" in p else p
        if _passt(p, NIE) and not _passt(p, ERLAUBT_MIT_AUSWAHL_TROTZ_NIE):
            a.erlaubt, a.standard, a.grund = False, False, "nie committen (Laufzeitdaten/Geheimnisse/manuelle Notizen)"
            continue
        if a.art == "geloescht":
            a.standard, a.grund = False, "gelöscht – nur mit ausdrücklicher Auswahl"
            continue
        if p.startswith("static/img/"):
            a.referenziert_von = sorted(set(ref.get(p, [])))
            if a.referenziert_von:
                a.standard, a.grund = True, "Bild eines geänderten Artikels: " + ", ".join(a.referenziert_von)
            else:
                a.standard, a.grund = False, "Bild wird von keinem geänderten Artikel referenziert – nur mit ausdrücklicher Auswahl"
            continue
        if _passt(p, STANDARD_JA):
            a.standard, a.grund = True, "Whitelist"
            continue
        if p.startswith("scripts/"):
            a.standard, a.grund = False, "Skript – nur mit ausdrücklicher Auswahl"
            continue
        a.standard, a.grund = False, "außerhalb der Whitelist – nur mit ausdrücklicher Auswahl"
    return aenderungen


def geaenderte_slugs(aenderungen: list[Aenderung]) -> list[str]:
    slugs: list[str] = []
    for a in aenderungen:
        m = re.match(r"articles/([^/]+)\.(md|html)$", a.pfad) or re.match(r"dist/artikel/([^/]+)/index\.html$", a.pfad)
        if m and m.group(1) not in slugs:
            slugs.append(m.group(1))
    return slugs


# --------------------------------------------------------------------------
# Fingerabdruck des geprueften Stands
# --------------------------------------------------------------------------


def fingerabdruck(root: Path, pfade: list[str]) -> str:
    h = hashlib.sha256()
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    h.update(head.encode())
    for p in sorted(set(pfade)):
        h.update(b"\0" + p.encode())
        datei = root / p
        if datei.is_file():
            h.update(hashlib.sha256(datei.read_bytes()).digest())
        else:
            h.update(b"<fehlt>")
    return h.hexdigest()[:32]


def stand_fingerabdruck(root: Path) -> str:
    """Fingerabdruck ueber ALLE committbaren Aenderungen (nicht nur die
    Auswahl): aendert sich irgendeine davon nach der Pruefung, muss neu
    geprueft werden - auch wenn der Nutzer nur Haekchen umsetzt."""
    return fingerabdruck(root, [a.pfad for a in klassifiziere(root, status(root)) if a.erlaubt])


# --------------------------------------------------------------------------
# Pruefungen vor dem Commit
# --------------------------------------------------------------------------


def geheimnis_pruefung(root: Path, pfade: list[str], verbotene_begriffe: list[str]) -> list[str]:
    """Durchsucht den Diff der ausgewaehlten Pfade (inkl. neuer Dateien)."""
    probleme: list[str] = []
    texte: list[str] = []
    for p in pfade:
        datei = root / p
        if not datei.is_file() or datei.stat().st_size > 3 * 1024 * 1024:
            continue
        roh = datei.read_bytes()
        if b"\0" in roh[:8000]:
            continue  # Binaerdatei
        texte.append(git(root, "diff", "HEAD", "--", p).stdout if git(root, "ls-files", "--error-unmatch", p).returncode == 0
                     else roh.decode("utf-8", "replace"))
    gesamt = "\n".join(texte)
    hinzu = "\n".join(z for z in gesamt.splitlines() if not z.startswith("-"))
    for muster in SECRET_PATTERNS:
        if muster.search(hinzu):
            probleme.append(f"Verdächtiges Muster (möglicher Schlüssel): {muster.pattern[:40]}…")
    for begriff in verbotene_begriffe or []:
        if begriff and begriff.lower() in hinzu.lower():
            probleme.append(f"Verbotener Begriff aus config.yaml: {begriff!r}")
    return probleme


def remote_stand(root: Path, branch: str = "master") -> dict:
    """Nur lesend: holt origin/<branch> und vergleicht mit HEAD."""
    erg = {"branch": git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "ok": True, "hinweise": []}
    f = git(root, "fetch", "--quiet", "origin", branch, timeout=60)
    if f.returncode != 0:
        erg["ok"] = False
        erg["hinweise"].append("git fetch fehlgeschlagen: " + (f.stderr.strip()[:200] or "?"))
        return erg
    hinter = git(root, "rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip()
    vor = git(root, "rev-list", "--count", f"origin/{branch}..HEAD").stdout.strip()
    erg["hinter"], erg["vor"] = int(hinter or 0), int(vor or 0)
    if erg["branch"] != branch:
        erg["ok"] = False
        erg["hinweise"].append(f"Aktueller Branch ist {erg['branch']}, veröffentlicht wird nur von {branch}.")
    if erg["hinter"]:
        erg["ok"] = False
        erg["hinweise"].append(f"Lokaler Stand liegt {erg['hinter']} Commit(s) hinter origin/{branch} – erst abgleichen (git pull --rebase).")
    if erg["vor"]:
        erg["hinweise"].append(f"{erg['vor']} lokale(r) Commit(s) noch nicht gepusht – sie werden mit veröffentlicht.")
    return erg


def verbindung_pruefen(root: Path) -> dict:
    """Nur lesend: git ls-remote (SSH-Zugang) und gh auth status."""
    ls = git(root, "ls-remote", "origin", "HEAD", timeout=30)
    try:
        gh = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=30, cwd=root)
        gh_ok, gh_text = gh.returncode == 0, (gh.stdout + gh.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        gh_ok, gh_text = False, type(exc).__name__
    konto = re.search(r"account (\S+)", gh_text)
    return {"git_ok": ls.returncode == 0, "git_text": (ls.stdout.split("\t")[0][:12] if ls.returncode == 0 else ls.stderr.strip()[:200]),
            "gh_ok": gh_ok, "gh_text": f"angemeldet als {konto.group(1)}" if gh_ok and konto else ("nicht angemeldet" if not gh_ok else "angemeldet"),
            "identitaet": git(root, "config", "user.name").stdout.strip()}


# --------------------------------------------------------------------------
# Bauen, Veroeffentlichen, Pages-Lauf
# --------------------------------------------------------------------------


def bauen(root: Path, timeout: int = 600) -> dict:
    start = datetime.now()
    try:
        r = subprocess.run([sys.executable, str(root / "scripts" / "build.py")], cwd=root, capture_output=True,
                           text=True, timeout=timeout)
        code, ausgabe = r.returncode, (r.stdout + ("\n" + r.stderr if r.stderr else ""))
    except subprocess.TimeoutExpired:
        code, ausgabe = -1, f"Abbruch nach {timeout} s"
    return {"ok": code == 0, "code": code, "ausgabe": ausgabe[-20000:], "dauer": round((datetime.now() - start).total_seconds(), 1),
            "zeitpunkt": start.isoformat(timespec="seconds")}


def log_eintrag(root: Path, zeilen: list[str]) -> None:
    """publish-log.md wie publish.py: ## <UTC-Zeit> + Spiegelstriche. Keine Kennzahlen."""
    path = root / "publish-log.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bisher = path.read_text(encoding="utf-8") if path.exists() else "# Publish-Log\n\n"
    if not bisher.endswith("\n\n"):
        bisher = bisher.rstrip("\n") + "\n\n"
    path.write_text(bisher + f"## {timestamp}\n\n" + "\n".join(f"- {z}" for z in zeilen) + "\n\n", encoding="utf-8")


def veroeffentlichen(root: Path, pfade: list[str], nachricht: str, *, erwarteter_fingerabdruck: str,
                     verbotene_begriffe: list[str], branch: str = "master", push: bool = True,
                     log_zeilen: list[str] | None = None) -> dict:
    """Commit (nur die ausgewaehlten Pfade + publish-log.md) und Push. Wirft DeployFehler."""
    nachricht = nachricht.strip()
    if not nachricht:
        raise DeployFehler("Commit-Meldung ist leer.")
    if not pfade:
        raise DeployFehler("Keine Dateien ausgewählt.")
    aktuell = {a.pfad: a for a in klassifiziere(root, status(root))}
    for p in pfade:
        if p not in aktuell:
            raise DeployFehler(f"{p} ist nicht (mehr) geändert – bitte neu prüfen.")
        if not aktuell[p].erlaubt:
            raise DeployFehler(f"{p} darf nie committet werden ({aktuell[p].grund}).")
    if stand_fingerabdruck(root) != erwarteter_fingerabdruck:
        raise DeployFehler("Seit der Prüfung hat sich der Stand geändert (Dateien oder HEAD) – bitte Diff neu laden und erneut bestätigen.")
    probleme = geheimnis_pruefung(root, pfade, verbotene_begriffe)
    if probleme:
        raise DeployFehler("Abbruch, verdächtiger Inhalt: " + "; ".join(probleme))
    if push:
        rs = remote_stand(root, branch)
        if not rs["ok"]:
            raise DeployFehler(" ".join(rs["hinweise"]))
    alle = list(dict.fromkeys(pfade))
    if log_zeilen:
        log_eintrag(root, log_zeilen)
        if "publish-log.md" not in alle:
            alle.append("publish-log.md")
    git(root, "add", "-A", "--", *alle, check=True)
    c = git(root, "commit", "--only", "-m", nachricht, "--", *alle)
    if c.returncode != 0:
        git(root, "reset", "-q", "--", *alle)
        raise DeployFehler("Commit fehlgeschlagen: " + (c.stderr or c.stdout).strip()[:400])
    sha = git(root, "rev-parse", "HEAD").stdout.strip()
    erg = {"sha": sha, "dateien": len(alle), "push_ok": None, "push_text": "", "dist_geaendert": any(p.startswith("dist/") for p in alle)}
    if push:
        p = git(root, "push", "origin", f"HEAD:{branch}", timeout=180)
        erg["push_ok"] = p.returncode == 0
        erg["push_text"] = (p.stderr or p.stdout).strip()[-1500:]
    return erg


def pages_lauf(root: Path, sha: str) -> dict:
    """Nur lesend: GitHub-Actions-Lauf zum Commit (gh run list --commit)."""
    try:
        r = subprocess.run(["gh", "run", "list", "--commit", sha, "--limit", "5", "--json",
                            "databaseId,status,conclusion,url,workflowName,createdAt,updatedAt"],
                           cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"zustand": "unbekannt", "text": f"gh nicht ausführbar ({type(exc).__name__})"}
    if r.returncode != 0:
        return {"zustand": "unbekannt", "text": "gh run list fehlgeschlagen: " + r.stderr.strip()[:200]}
    laeufe = json.loads(r.stdout or "[]")
    if not laeufe:
        return {"zustand": "wartet", "text": "Noch kein Actions-Lauf zu diesem Commit sichtbar."}
    lauf = laeufe[0]
    if lauf.get("status") != "completed":
        return {"zustand": "laeuft", "text": f"{lauf.get('workflowName')}: {lauf.get('status')}", "url": lauf.get("url")}
    ok = lauf.get("conclusion") == "success"
    return {"zustand": "erfolg" if ok else "fehler", "text": f"{lauf.get('workflowName')}: {lauf.get('conclusion')}",
            "url": lauf.get("url"), "fertig": lauf.get("updatedAt")}
