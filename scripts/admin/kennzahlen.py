"""Kennzahlen je Plattform: Mastodon/Bluesky automatisch (nur lesend, oeffentliche
Endpunkte, ohne Login), alle anderen manuell erfasst.

Ablage unter data/kennzahlen/ (in .gitignore):
    mastodon.json, bluesky.json   Zwischenspeicher {"stand": ISO, "beitraege": {slug: {...}}}
    manuell.json                  {plattform: {slug: {"beitrag_url": ..., "messungen": [...]}}}

Keine Views: weder Mastodon noch Bluesky liefern Aufrufzahlen. Kein Scraping.
Der HTTP-Abruf ist austauschbar (Parameter `http`), damit Tests ohne Netz laufen.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import linkedin_import as li

USER_AGENT = "blog-brauckmann-verwaltung/1.0 (read-only counters; +https://blog.brauckmann.ch)"
TIMEOUT = 10
BSKY_API = "https://public.api.bsky.app/xrpc"
KEINE_VIEWS = "Views: von der Plattform nicht geliefert"

MASTODON_ID = re.compile(r"^https://([A-Za-z0-9.-]+)/@[^/\s]+/(\d+)/?$")
BLUESKY_POST = re.compile(r"^https://bsky\.app/profile/([^/\s]+)/post/([A-Za-z0-9]+)/?$")


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def mastodon_status(url: str) -> tuple[str, str] | None:
    m = MASTODON_ID.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def bluesky_post(url: str) -> tuple[str, str] | None:
    m = BLUESKY_POST.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def _zahl(d: dict, *keys):
    for k in keys:
        if isinstance(d.get(k), int):
            return d[k]
    return None


def mastodon_zaehler(url: str, http=http_get_json) -> dict:
    ident = mastodon_status(url)
    if not ident:
        return {"fehler": "Beitrags-URL nicht erkannt"}
    host, sid = ident
    try:
        d = http(f"https://{host}/api/v1/statuses/{sid}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"fehler": f"Abruf fehlgeschlagen ({type(exc).__name__})"}
    return {"reblogs": _zahl(d, "reblogs_count"), "favourites": _zahl(d, "favourites_count"),
            "replies": _zahl(d, "replies_count"), "quotes": _zahl(d, "quotes_count")}


def bluesky_zaehler(url: str, http=http_get_json) -> dict:
    ident = bluesky_post(url)
    if not ident:
        return {"fehler": "Beitrags-URL nicht erkannt"}
    handle, rkey = ident
    try:
        if handle.startswith("did:"):
            did = handle
        else:
            did = http(f"{BSKY_API}/com.atproto.identity.resolveHandle?handle={urllib.parse.quote(handle)}").get("did")
        if not did:
            return {"fehler": "Handle nicht aufgelöst"}
        uri = f"at://{did}/app.bsky.feed.post/{rkey}"
        d = http(f"{BSKY_API}/app.bsky.feed.getPosts?uris={urllib.parse.quote(uri, safe='')}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"fehler": f"Abruf fehlgeschlagen ({type(exc).__name__})"}
    posts = d.get("posts") or []
    if not posts:
        return {"fehler": "Beitrag nicht gefunden (gelöscht?)"}
    p = posts[0]
    return {"likes": _zahl(p, "likeCount"), "reposts": _zahl(p, "repostCount"),
            "replies": _zahl(p, "replyCount"), "quotes": _zahl(p, "quoteCount")}


ABRUF = {"mastodon": mastodon_zaehler, "bluesky": bluesky_zaehler}

# Anzeige: (Schluessel, Beschriftung)
ZAEHLER_ANZEIGE = {
    "mastodon": [("favourites", "Favoriten"), ("reblogs", "Boosts"), ("replies", "Antworten"), ("quotes", "Zitate")],
    "bluesky": [("likes", "Likes"), ("reposts", "Reposts"), ("replies", "Antworten"), ("quotes", "Zitate")],
}


class KennzahlenSpeicher:
    def __init__(self, root: Path):
        self.basis = root / "data" / "kennzahlen"

    def lesen(self, name: str, standard=None):
        try:
            return json.loads((self.basis / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return standard

    def schreiben(self, daten, name: str) -> None:
        self.basis.mkdir(parents=True, exist_ok=True)
        p = self.basis / name
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, p)

    # -- automatisch
    def zaehler(self, plattform: str) -> dict:
        return self.lesen(f"{plattform}.json", standard=None) or {"stand": None, "beitraege": {}}

    def aktualisieren(self, plattform: str, eintraege: dict[str, str], http=http_get_json) -> dict:
        """eintraege: slug -> Beitrags-URL. Fehler je Beitrag tolerant; ein zuvor gespeicherter
        Wert bleibt bei einem Fehler erhalten (mit Fehlerhinweis)."""
        alt = self.zaehler(plattform)["beitraege"]
        neu: dict[str, dict] = {}
        for slug, url in eintraege.items():
            erg = ABRUF[plattform](url, http=http)
            if erg.get("fehler"):
                vorher = {k: v for k, v in (alt.get(slug) or {}).items() if k not in ("fehler",)}
                neu[slug] = {**vorher, "url": url, "fehler": erg["fehler"]}
            else:
                neu[slug] = {**erg, "url": url, "abgerufen": datetime.now().isoformat(timespec="seconds")}
        daten = {"stand": datetime.now().isoformat(timespec="seconds"), "beitraege": neu}
        self.schreiben(daten, f"{plattform}.json")
        return daten

    # -- manuell
    def manuell(self, plattform: str | None = None) -> dict:
        d = self.lesen("manuell.json", standard={}) or {}
        return d.get(plattform, {}) if plattform else d

    def messung_hinzufuegen(self, plattform: str, slug: str, felder: dict, datum_roh: str | None, beitrag_url: str = "") -> dict | None:
        """Speichert eine Messung; Zahlen ueber linkedin_import.zahl, Prozentwerte 0-100. None, wenn nichts eingegeben."""
        erlaubt = FELDER[plattform]
        m: dict = {}
        for k in erlaubt:
            z = li.zahl(felder.get(k))
            if z is None or z < 0 or z > 10**9:
                continue
            if k in PROZENT_FELDER and z > 100:
                continue
            m[k] = round(z, 1) if k in PROZENT_FELDER else int(round(z))
        if not m:
            return None
        m["datum"] = li.datum(datum_roh) or date.today().isoformat()
        d = self.lesen("manuell.json", standard={}) or {}
        e = d.setdefault(plattform, {}).setdefault(slug, {"beitrag_url": "", "messungen": []})
        if beitrag_url:
            e["beitrag_url"] = beitrag_url
        m["quelle"] = "manuell"
        e["messungen"].append(m)
        self.schreiben(d, "manuell.json")
        return m

    def messung_loeschen(self, plattform: str, slug: str, index: int) -> bool:
        d = self.lesen("manuell.json", standard={}) or {}
        ms = d.get(plattform, {}).get(slug, {}).get("messungen", [])
        if not 0 <= index < len(ms):
            return False
        del ms[index]
        self.schreiben(d, "manuell.json")
        return True

    def csv_importieren(self, plattform: str, daten: bytes, quellen: set[str]) -> dict:
        """CSV/Tabelle: Kopfzeile = Feldnamen + slug (+ datum). Unbekannte Slugs/Zeilen werden gemeldet."""
        blaetter = li.lies_csv(daten)
        zeilen = next(iter(blaetter.values()), [])
        zeilen = [z for z in zeilen if any(str(c).strip() for c in z)]
        if len(zeilen) < 2:
            return {"gespeichert": 0, "fehler": ["Keine Datenzeilen gefunden (Kopfzeile + mindestens eine Zeile)."]}
        kopf = [str(c).strip().lower() for c in zeilen[0]]
        if "slug" not in kopf:
            return {"gespeichert": 0, "fehler": ["Spalte „slug“ fehlt in der Kopfzeile."]}
        bekannt = [k for k in kopf if k in FELDER[plattform]]
        if not bekannt:
            return {"gespeichert": 0, "fehler": ["Keine bekannte Spalte. Erwartet: slug, datum, " + ", ".join(FELDER[plattform])]}
        n, fehler = 0, []
        for nr, z in enumerate(zeilen[1:], start=2):
            row = dict(zip(kopf, z))
            slug = str(row.get("slug", "")).strip().rstrip("/").split("/artikel/")[-1].strip("/")
            if slug not in quellen:
                fehler.append(f"Zeile {nr}: unbekannter Artikel „{slug}“")
                continue
            if self.messung_hinzufuegen(plattform, slug, row, row.get("datum"), str(row.get("beitrag_url", "")).strip()):
                n += 1
            else:
                fehler.append(f"Zeile {nr}: keine verwertbaren Zahlen")
        return {"gespeichert": n, "fehler": fehler}


FELDER: dict[str, dict[str, str]] = {}
PROZENT_FELDER: set[str] = set()


def _felder_setzen() -> None:
    import plattformen as pl
    FELDER.update(pl.MANUELLE_FELDER)
    FELDER["linkedin"] = dict(li.FELDER_BEITRAG)
    PROZENT_FELDER.update(pl.PROZENT_FELDER)


_felder_setzen()


def letzte_messung(eintrag: dict | None) -> dict | None:
    ms = (eintrag or {}).get("messungen") or []
    return max(ms, key=lambda m: m.get("datum") or "") if ms else None


def wirkung_text(plattform: str, slug: str, ks: KennzahlenSpeicher, linkedin_daten: dict | None = None) -> dict:
    """Kurztext fuer die Ranking-Tabelle: {"text": str, "datum": str|None}."""
    if plattform in ZAEHLER_ANZEIGE:
        e = ks.zaehler(plattform)["beitraege"].get(slug)
        if not e:
            return {"text": "", "datum": None}
        teile = [f"{lbl} {e[k]}" for k, lbl in ZAEHLER_ANZEIGE[plattform] if e.get(k) is not None]
        if not teile:
            return {"text": e.get("fehler", ""), "datum": None}
        return {"text": ", ".join(teile), "datum": (e.get("abgerufen") or "")[:10]}
    if plattform == "linkedin":
        m = letzte_messung(((linkedin_daten or {}).get("beitraege") or {}).get(slug))
        w = li.wirkung(m)
        if not w:
            return {"text": "", "datum": (m or {}).get("datum")}
        rate = f", {str(w['rate']).replace('.', ',')} % Interaktion" if w.get("rate") is not None else ""
        return {"text": f"{w['impressions']} Impressions{rate}", "datum": m.get("datum")}
    m = letzte_messung(ks.manuell(plattform).get(slug))
    if not m:
        return {"text": "", "datum": None}
    felder = FELDER[plattform]
    teile = [f"{felder[k].split(' (')[0]} {m[k]}" for k in felder if k in m]
    return {"text": ", ".join(teile[:3]), "datum": m.get("datum")}
