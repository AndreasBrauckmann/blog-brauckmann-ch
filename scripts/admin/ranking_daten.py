"""Lokale Laufzeitdaten des Artikel-Rankings - NIE ins oeffentliche Repo.

Alles liegt unter data/ranking/ (data/ steht in .gitignore):

    inspector.json       Post-Inspector-Haekchen je Artikel (Datum + Vorschau-Hash)
    linkedin.json        LinkedIn-Kennzahlen (manuell/Import) je Artikel + Profil-Uebersicht
    lektorat/<slug>.json Ergebnis des LLM-Lektorats
    metas/<slug>.json    zuletzt erzeugte Meta-Vorschlaege
    ../backups/artikel/  Sicherungen vor jeder Frontmatter-Aenderung
    .csrf                Geheimnis fuer die Formular-Tokens

Dateien werden atomar geschrieben (tmp + os.replace) und mit 0600 angelegt.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

import yaml


class Speicher:
    def __init__(self, root: Path):
        self.root = root
        self.basis = root / "data" / "ranking"

    # -- Grundfunktionen
    def _pfad(self, *teile: str) -> Path:
        p = self.basis.joinpath(*teile)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def lesen(self, *teile: str, standard=None):
        p = self.basis.joinpath(*teile)
        if not p.exists():
            return standard
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return standard

    def schreiben(self, daten, *teile: str) -> None:
        p = self._pfad(*teile)
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, p)

    # -- CSRF
    def csrf_geheimnis(self) -> bytes:
        p = self._pfad(".csrf")
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32))
        return p.read_text().strip().encode()

    def csrf_token(self) -> str:
        return hmac.new(self.csrf_geheimnis(), b"blog-verwaltung-ranking", hashlib.sha256).hexdigest()

    def csrf_ok(self, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(token, self.csrf_token())

    # -- Post Inspector
    def inspector(self) -> dict:
        return self.lesen("inspector.json", standard={}) or {}

    def inspector_setzen(self, slug: str, datum: str | None, vorschau_hash: str) -> None:
        d = self.inspector()
        if datum:
            d[slug] = {"datum": datum, "vorschau_hash": vorschau_hash}
        else:
            d.pop(slug, None)
        self.schreiben(d, "inspector.json")

    # -- LinkedIn
    def linkedin(self) -> dict:
        d = self.lesen("linkedin.json", standard=None) or {}
        d.setdefault("beitraege", {})
        d.setdefault("profil", [])
        return d

    def linkedin_speichern(self, d: dict) -> None:
        self.schreiben(d, "linkedin.json")

    # -- Lektorat / Metas
    def lektorat(self, slug: str):
        return self.lesen("lektorat", f"{slug}.json")

    def lektorat_speichern(self, slug: str, daten: dict) -> None:
        self.schreiben(daten, "lektorat", f"{slug}.json")

    def metas(self, slug: str):
        return self.lesen("metas", f"{slug}.json")

    def metas_speichern(self, slug: str, daten: dict) -> None:
        self.schreiben(daten, "metas", f"{slug}.json")

    # -- Backups
    def artikel_sichern(self, quelle: Path) -> Path:
        ziel_dir = self.root / "data" / "backups" / "artikel"
        ziel_dir.mkdir(parents=True, exist_ok=True)
        zeit = datetime.now().strftime('%Y%m%d-%H%M%S')
        ziel = ziel_dir / f"{quelle.stem}.{zeit}{quelle.suffix}"
        n = 1
        while ziel.exists():  # nie ein vorhandenes Backup ueberschreiben (zwei Sicherungen in einer Sekunde)
            ziel = ziel_dir / f"{quelle.stem}.{zeit}-{n}{quelle.suffix}"
            n += 1
        shutil.copy2(quelle, ziel)
        return ziel

    def letzte_sicherung(self, quelle: Path) -> Path | None:
        """Neueste Sicherung dieses Artikels aus data/backups/artikel/ (nach Zeitstempel im Namen)."""
        ziel_dir = self.root / "data" / "backups" / "artikel"
        muster = re.compile(rf"^{re.escape(quelle.stem)}\.(\d{{8}}-\d{{6}})(?:-(\d+))?{re.escape(quelle.suffix)}$")
        treffer = []
        for p in ziel_dir.glob(f"{quelle.stem}.*{quelle.suffix}") if ziel_dir.exists() else []:
            m = muster.match(p.name)
            if m:
                treffer.append((m.group(1), int(m.group(2) or 0), p))
        return max(treffer)[2] if treffer else None


def vorschau_hash(titel: str, beschreibung: str, bild: str) -> str:
    """Fingerabdruck der Link-Vorschau. Aendert sich Titel, Beschreibung oder
    Bild nach dem Post-Inspector-Lauf, gilt das Haekchen als veraltet."""
    return hashlib.sha256(f"{titel}\n{beschreibung}\n{bild}".encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Frontmatter gezielt aendern (Kommentare/Reihenfolge bleiben erhalten)
# --------------------------------------------------------------------------

ERLAUBTE_FELDER = ("title", "description", "og_image_alt", "og_image")


class FrontmatterFehler(ValueError):
    pass


def _teile(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        raise FrontmatterFehler("Datei beginnt nicht mit YAML-Frontmatter")
    ende = text.find("\n---", 3)
    if ende < 0:
        raise FrontmatterFehler("Ende des Frontmatters nicht gefunden")
    return text[: ende + 1], text[ende + 1:]


def setze_felder(text: str, felder: dict[str, str]) -> str:
    """Ersetzt bzw. ergaenzt einzeilige Frontmatter-Felder. Werte werden als
    YAML-Strings in doppelten Anfuehrungszeichen geschrieben (json.dumps ist
    dafuer gueltiges YAML). Danach wird geprueft, dass genau diese Felder
    neue Werte haben und alles andere unveraendert ist."""
    for k in felder:
        if k not in ERLAUBTE_FELDER:
            raise FrontmatterFehler(f"Feld {k} darf hier nicht geändert werden")
    kopf, rest = _teile(text)
    alt = yaml.safe_load(kopf.strip("-\n")) or {}
    zeilen = kopf.split("\n")
    for k, v in felder.items():
        v = str(v).strip()
        if not v or "\n" in v:
            raise FrontmatterFehler(f"{k}: leerer oder mehrzeiliger Wert")
        neu = f"{k}: {json.dumps(v, ensure_ascii=False)}"
        idx = next((i for i, z in enumerate(zeilen) if re.match(rf"^{re.escape(k)}:", z)), None)
        if idx is not None:
            if re.match(rf"^{re.escape(k)}:\s*[>|]", zeilen[idx]) or (idx + 1 < len(zeilen) and zeilen[idx + 1].startswith((" ", "\t"))):
                raise FrontmatterFehler(f"{k} ist mehrzeilig – bitte von Hand ändern")
            zeilen[idx] = neu
        else:
            anker = None
            for ak in ("og_image", "thumb", "image", "description"):
                anker = next((i for i, z in enumerate(zeilen) if z.startswith(f"{ak}:")), None)
                if anker is not None:
                    break
            if anker is None:
                anker = len(zeilen) - 2
            zeilen.insert(anker + 1, neu)
    neuer_kopf = "\n".join(zeilen)
    neu_daten = yaml.safe_load(neuer_kopf.strip("-\n")) or {}
    for k, v in felder.items():
        if neu_daten.get(k) != str(v).strip():
            raise FrontmatterFehler(f"{k}: Prüfung nach dem Schreiben fehlgeschlagen")
    for k in set(alt) | set(neu_daten):
        if k not in felder and alt.get(k) != neu_daten.get(k):
            raise FrontmatterFehler(f"Unbeabsichtigte Änderung an {k}")
    return neuer_kopf + rest
