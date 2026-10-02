"""Gemeinsame Bausteine der Blog-Verwaltung (alle Seiten).

- Zugriffsschutz: require_intern() (Header X-Blog-Verwaltung-Intern, nur von
  edge gesetzt) und post_pruefen() (zusaetzlich Formular-Token + Ursprung).
- Artikelquellen, gerenderter Artikelkoerper, Live-URL.
- Kopfnavigation (Tabs) und Artikel-Auswahl (kurzes Datum, gekuerzter Titel).

Laufzeitdaten liegen ausschliesslich unter data/ (in .gitignore).
"""

from __future__ import annotations

import os
import urllib.parse
from datetime import date
from pathlib import Path

from flask import abort, request

from build import ROOT, load_config, parse_article, parse_html_article, render_markdown
from ranking_daten import Speicher

speicher = Speicher(ROOT)

# Reihenfolge = Reihenfolge der Tabs
PLATTFORMEN = ["mastodon", "bluesky", "linkedin", "reddit", "facebook", "youtube_community",
               "microsoft_tech_community"]
PLATTFORM_NAMEN = {
    "mastodon": "Mastodon", "bluesky": "Bluesky", "linkedin": "LinkedIn", "reddit": "Reddit",
    "facebook": "Facebook", "youtube_community": "YouTube Posts", "microsoft_tech_community": "MS Tech Community",
}
NAV_REIHENFOLGE = ["mastodon", "bluesky", "linkedin", "reddit", "facebook", "youtube_community",
                   "microsoft_tech_community"]


def require_intern() -> None:
    if not request.headers.get("X-Blog-Verwaltung-Intern"):
        abort(403)


def post_pruefen() -> None:
    require_intern()
    if not speicher.csrf_ok(request.form.get("csrf")):
        abort(403, "Formular-Token ungültig – Seite neu laden und erneut versuchen.")
    herkunft = request.headers.get("Origin") or request.headers.get("Referer")
    if herkunft:
        netloc = urllib.parse.urlparse(herkunft).netloc
        if netloc not in {request.host, request.headers.get("X-Forwarded-Host", "")}:
            abort(403, "Fremder Ursprung")


def artikel_quellen(cfg: dict | None = None) -> dict[str, dict]:
    """slug -> Metadaten aller veroeffentlichten Artikel (ohne Entwuerfe)."""
    cfg = cfg or load_config()
    articles_dir = ROOT / cfg["paths"]["articles_dir"]
    out: dict[str, dict] = {}
    for path in sorted(articles_dir.glob("*.md")):
        meta = parse_article(path)
        if not meta.get("draft", False):
            out[meta["slug"]] = meta
    for path in sorted(articles_dir.glob("*.html")):
        meta = parse_html_article(path)
        out.setdefault(meta["slug"], meta)
    return out


def koerper_html(meta: dict) -> str:
    if meta.get("is_html"):
        roh = Path(meta["source"]).read_text(encoding="utf-8")
        start = roh.find("<article")
        ende = roh.find("</article>")
        return roh[start:ende] if start >= 0 and ende > start else roh
    return render_markdown(meta["body_md"])


def live_url(cfg: dict, slug: str) -> str:
    return f"{cfg['site']['base_url']}/artikel/{slug}/"


def kurz_datum(wert) -> str:
    """2026-09-28 -> 28.09.26"""
    try:
        d = wert if isinstance(wert, date) else date.fromisoformat(str(wert)[:10])
    except ValueError:
        return str(wert)
    return d.strftime("%d.%m.%y")


def kurz_titel(titel: str, n: int = 50) -> str:
    """Erste n Zeichen, an einer Wortgrenze gekuerzt, mit … (Volltitel als Tooltip)."""
    t = " ".join(str(titel).split())
    if len(t) <= n:
        return t
    schnitt = t[: n - 1]
    if t[n - 1] != " " and " " in schnitt[n // 2:]:
        schnitt = schnitt.rsplit(" ", 1)[0]
    return schnitt.rstrip(" ,.;:–—-") + "…"


def artikel_auswahl(quellen: dict[str, dict]) -> list[dict]:
    """Eintraege fuer das Artikel-Dropdown, neueste zuerst."""
    items = [{"slug": s, "titel": str(m.get("title", s)), "datum": str(m.get("date", "")),
              "kurz": f"{kurz_datum(m.get('date', ''))} {kurz_titel(m.get('title', s))}"}
             for s, m in quellen.items()]
    items.sort(key=lambda x: x["datum"], reverse=True)
    return items


def gewaehlter_slug(quellen: dict[str, dict]) -> str | None:
    auswahl = artikel_auswahl(quellen)
    slug = request.values.get("slug") or ""
    if slug in quellen:
        return slug
    return auswahl[0]["slug"] if auswahl else None


_KANAL_ENV = {
    "mastodon": ["MASTODON_ACCESS_TOKEN"],
    "bluesky": ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"],
    "linkedin": ["LINKEDIN_ACCESS_TOKEN"],
}


def _kanal_status(name: str, cfg: dict) -> str:
    """"ok" = per API verbunden, "fehlt" = Zugang nicht eingerichtet,
    "manuell" = Kanal wird von Hand gepostet. Fuer den Punkt im Menue."""
    ch = (cfg.get("channels") or {}).get(name) or {}
    if ch.get("manual", False):
        return "manuell"
    env = _KANAL_ENV.get(name)
    if not env:
        return "manuell"
    return "ok" if all(os.environ.get(v) for v in env) else "fehlt"


def nav_tabs() -> list[dict]:
    tabs = [{"id": "uebersicht", "name": "Übersicht", "url": "/verwaltung", "gruppe": "arbeit"},
            {"id": "ranking", "name": "Ranking", "url": "/verwaltung/ranking", "gruppe": "arbeit"},
            {"id": "deploy", "name": "Deploy", "url": "/verwaltung/deploy", "gruppe": "arbeit"}]
    try:
        cfg = load_config()
    except Exception:
        cfg = {}
    for p in NAV_REIHENFOLGE:
        tabs.append({"id": p, "name": PLATTFORM_NAMEN.get(p, p), "url": f"/verwaltung/plattform/{p}",
                     "gruppe": "kanal", "status": _kanal_status(p, cfg)})
    return tabs


def init_app(app) -> None:
    @app.context_processor
    def _gemeinsam():
        return {"nav_tabs": nav_tabs(), "csrf_token": speicher.csrf_token,
                "PLATTFORM_NAMEN": PLATTFORM_NAMEN}

    app.add_template_filter(kurz_datum, "kurzdatum")
    app.add_template_filter(kurz_titel, "kurztitel")
