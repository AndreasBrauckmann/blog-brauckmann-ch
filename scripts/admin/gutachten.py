"""„Claude hinzuziehen“: Gutachten zu Satz und Format eines Artikels durch einen headless Claude-Code-Lauf.

Der Lauf darf NUR lesen (Tools Read, Grep, Glob; kein Bash, kein Edit/Write, kein Netz) und schreibt nie in Artikel oder
CSS. Er laeuft ueber die Auftrags-Warteschlange (einer zur Zeit) mit Sperre je Artikel, Timeout 10 Minuten und
Abbrechen-Knopf. Das Ergebnis liegt unter data/ranking/gutachten/<slug>.json. Vorschlaege setzt der Mensch ueber die
bestehenden Wege um (Durchlauf, Uebernehmen mit Diff).

Die Anmeldung der CLI ist die des Dienstbenutzers (HOME, ~/.claude): die Verwaltung braucht keine zusaetzlichen Rechte
und gibt keine Zugangsdaten weiter - dem Kindprozess wird eine minimale Umgebung ohne die Schluessel aus der .env mitgegeben,
und das Lesen von .env, .secrets und ~/.claude ist ausdruecklich verboten.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import in_ordnung as io
import llm
import satzmessung

TIMEOUT = 600
MAX_TURNS = 12
MODELL = "opus"

SCHEMA = """{
  "zusammenfassung": "2-3 Sätze: Gesamteindruck von Satz und Format dieses Artikels",
  "befunde": [
    {"kriterium": "Lesefluss | Absatz- und Satzrhythmus | Überschriftenfolge | Listen, Tabellen, Boxen | Bilder im Textfluss | Typografie (CSS)",
     "schwere": "hoch | mittel | niedrig",
     "fundstelle": "Abschnitt „<Überschrift>“, Absatz N  (leer, wenn der Befund den ganzen Artikel oder die CSS betrifft)",
     "vorschlag": "konkrete Änderung: bei Text der neue Wortlaut oder die Umbauanweisung, bei CSS die Regel mit Selektor und Wert"}
  ]
}"""


def pruefe_cli() -> tuple[bool, str]:
    """Ist die claude-CLI vorhanden? (Anmeldung zeigt sich beim Lauf; dann gibt es eine klare Meldung.)"""
    pfad = shutil.which("claude") or str(Path.home() / ".npm-global" / "bin" / "claude")
    if not Path(pfad).exists():
        return False, "Die claude-CLI wurde nicht gefunden (PATH des Dienstes). Installation und Anmeldung (`claude auth login`) prüfen."
    return True, pfad


def prompt(root: Path, slug: str, satz_text: str, bilder: list[Path]) -> str:
    bilderliste = "\n".join(f"- {b.relative_to(root)}" for b in bilder)
    return f"""Du bist Lektor und Typografie-Gutachter für den Blog in diesem Repository. Erstelle ein Gutachten zu SATZ UND FORMAT des Artikels „{slug}“.

Lies zuerst (nur lesen!):
- die Quelle: articles/{slug}.md
- die gebaute Seite: dist/artikel/{slug}/index.html
- die gemeinsame CSS: static/style.css
- die Regeln des Projekts: CLAUDE.md (u. a. „Titel und Beschreibung in einem Guss“, Pflicht-Meta-Tags)
- die Bildschirmfotos (Kopf und Textstelle; hell/dunkel, Desktop 1280 px / Handy 393 px):
{bilderliste}

Gemessene Werte (deterministisch, ohne KI; „Satz & Layout“):
{satz_text}

Beurteile aus Sicht einer Leserin am Handy und am Desktop: Lesefluss, Absatz- und Satzrhythmus, Überschriftenfolge, Listen/Tabellen/Boxen, Bilder im Textfluss, Typografie. Belege jeden Befund mit einer Fundstelle (Abschnitt „…“, Absatz N) und mache einen konkreten Vorschlag (neuer Wortlaut bzw. CSS-Regel mit Selektor und Wert). Nenne nur Befunde, die du am Material belegen kannst; erfinde nichts. Höchstens 12 Befunde, wichtigste zuerst.

Verbindlich: Du darfst NICHTS ändern, nur lesen (Read, Grep, Glob). Lies niemals .env, .secrets oder ~/.claude. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt nach diesem Schema, auf Deutsch, ohne Text davor oder danach:
{SCHEMA}"""


def satz_text(root: Path, slug: str) -> str:
    import bewertung as bw
    roh = satzmessung.gespeichert(root, slug)
    if not roh:
        return "(noch nicht gemessen)"
    return "\n".join(f"- {k.name}: {k.messwert} (Soll {k.soll}; Status {k.status})" for k in bw.bewerte_satz(roh) if k.status != "na")


def minimale_umgebung() -> dict:
    erlaubt = ("PATH", "HOME", "LANG", "LC_ALL", "USER", "LOGNAME", "TERM", "SHELL", "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")
    return {k: v for k, v in os.environ.items() if k in erlaubt}


def befehl(cli: str, text: str) -> list[str]:
    return [cli, "-p", text, "--model", MODELL, "--output-format", "json", "--max-turns", str(MAX_TURNS),
            "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob",
            "--disallowedTools", "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Read(./.env),Read(./.env.*),Read(./.secrets/**),Read(~/.claude/**),Read(~/.ssh/**)",
            "--permission-mode", "dontAsk", "--no-session-persistence"]


def auswerten(roh_stdout: str) -> dict:
    """Ergebnisobjekt aus der JSON-Ausgabe der CLI. Wirft llm.LLMFehler mit lesbarem Text."""
    try:
        außen = json.loads(roh_stdout)
    except json.JSONDecodeError:
        raise llm.LLMFehler("Die claude-CLI lieferte keine auswertbare Ausgabe.") from None
    if außen.get("is_error"):
        text = str(außen.get("result") or "")
        if any(w in text.lower() for w in ("login", "authenticate", "oauth", "credit", "api key")):
            raise llm.LLMFehler("Die claude-CLI ist für den Dienstbenutzer nicht angemeldet (`claude auth login` als dieser Benutzer ausführen).")
        raise llm.LLMFehler("Die claude-CLI meldet einen Fehler: " + text[:200])
    inhalt = llm.json_aus_text(str(außen.get("result") or ""))
    befunde = []
    for b in (inhalt.get("befunde") or [])[:12]:
        if isinstance(b, dict):
            befunde.append({"kriterium": str(b.get("kriterium") or "")[:80], "schwere": str(b.get("schwere") or "mittel").lower()[:10],
                            "fundstelle": str(b.get("fundstelle") or "")[:200], "vorschlag": str(b.get("vorschlag") or "")[:1500]})
    modelle = list((außen.get("modelUsage") or {}).keys())
    return {"zusammenfassung": str(inhalt.get("zusammenfassung") or "")[:800], "befunde": befunde,
            "modell": ", ".join(modelle) or MODELL, "turns": außen.get("num_turns"), "dauer_ms": außen.get("duration_ms"),
            "kosten_usd": außen.get("total_cost_usd")}


def lauf(ctx, slug: str, z: dict, frist_ende: float, popen=subprocess.Popen) -> None:
    """Der eigentliche Lauf (im Queue-Thread). `popen` ist austauschbar (Tests)."""
    root = ctx.root
    ok, cli = pruefe_cli()
    if not ok:
        raise llm.LLMFehler(cli)
    z["schritt"] = "Bildschirmfotos erzeugen"
    _sichern(ctx, slug, z)
    bilder = satzmessung.bilder_fuer_gutachten(root, slug)
    io._pruefe_abbruch(slug, frist_ende)
    z["schritt"] = "Claude liest und begutachtet"
    _sichern(ctx, slug, z)
    start = time.time()
    proc = popen(befehl(cli, prompt(root, slug, satz_text(root, slug), bilder)), cwd=str(root), env=minimale_umgebung(),
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while True:
        try:
            aus, fehl = proc.communicate(timeout=1)
            break
        except subprocess.TimeoutExpired:
            if io.abbruch_angefordert(slug) or time.time() - start > TIMEOUT:
                proc.kill()
                proc.communicate()
                if io.abbruch_angefordert(slug):
                    raise io.AuftragFehler("Vom Nutzer abgebrochen.")
                raise llm.LLMFehler(f"Zeitüberschreitung: der Lauf wurde nach {TIMEOUT // 60} Minuten beendet.")
    if proc.returncode not in (0, None) and not aus.strip():
        text = (fehl or "").strip()[-200:]
        if any(w in text.lower() for w in ("login", "authenticate", "credential")):
            raise llm.LLMFehler("Die claude-CLI ist für den Dienstbenutzer nicht angemeldet (`claude auth login` als dieser Benutzer ausführen).")
        raise llm.LLMFehler("Die claude-CLI wurde mit Fehler beendet: " + text)
    erg = auswerten(aus)
    erg["dauer_s"] = round(time.time() - start, 1)
    erg["zeitpunkt"] = datetime.now().isoformat(timespec="seconds")
    z["ergebnis"] = erg
    z["status"] = "fertig"
    z["schritt"] = "fertig"
    ctx.speicher.schreiben(erg, "gutachten", f"{slug}.json")


def _sichern(ctx, slug: str, z: dict) -> None:
    ctx.speicher.schreiben(z, "gutachten", f"{slug}_lauf.json")


def starte(ctx, slug: str) -> tuple[bool, str]:
    """Reiht ein Gutachten in die Warteschlange (einer zur Zeit, Sperre je Artikel)."""
    ok, info = pruefe_cli()
    if not ok:
        return False, info
    if not ctx.artikel_pfad(slug).exists():
        return False, "Nur Markdown-Artikel werden unterstützt."
    if not satzmessung.seite(ctx.root, slug).exists():
        return False, "Die gebaute Seite fehlt (dist/) – bitte zuerst bauen."
    if not io.sperre_nehmen(slug):
        return False, "Für diesen Artikel läuft bereits ein Auftrag."
    z = {"slug": slug, "status": "wartet", "gestartet": io._jetzt(), "schritt": "wartet in der Warteschlange"}
    _sichern(ctx, slug, z)
    io._einreihen(ctx, slug, z, runner=_lauf_gutachten)
    return True, "eingereiht"


def _lauf_gutachten(ctx, slug: str, z: dict) -> None:
    frist_ende = time.time() + TIMEOUT + 120
    z["status"] = "laeuft"
    _sichern(ctx, slug, z)
    try:
        lauf(ctx, slug, z, frist_ende)
    except io.AuftragFehler as exc:
        z["status"], z["meldung"] = "abgebrochen", str(exc)
    except llm.LLMFehler as exc:
        z["status"], z["meldung"] = "fehler", str(exc)
    except Exception as exc:
        z["status"], z["meldung"] = "fehler", f"Unerwarteter Fehler: {type(exc).__name__}: {str(exc)[:200]}"
    finally:
        z["beendet"] = io._jetzt()
        try:
            _sichern(ctx, slug, z)
        finally:
            io.sperre_freigeben(slug)


def zustand(ctx, slug: str) -> dict | None:
    z = ctx.speicher.lesen("gutachten", f"{slug}_lauf.json")
    if z and z.get("status") in ("laeuft", "wartet") and not io.ist_gesperrt(slug):
        z["status"], z["meldung"] = "abgebrochen", "Der Lauf wurde unterbrochen (Neustart der Verwaltung)."
        _sichern(ctx, slug, z)
    return z
