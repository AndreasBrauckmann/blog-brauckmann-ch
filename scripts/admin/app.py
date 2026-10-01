#!/usr/bin/env python3
"""Verwaltungsseite: Kanal-Übersicht, Verbindungsstatus, Veröffentlichen per Klick.

Nutzung:
    .venv/bin/python scripts/admin/app.py [--host 127.0.0.1] [--port 5151]

Nur intern erreichbar: der Kontor-edge-Caddy (trader-kontor/edge/Caddyfile)
reicht /verwaltung/* unveraendert (handle, nicht handle_path) an
127.0.0.1:5151 durch - deshalb tragen alle Routen hier das Praefix
/verwaltung selbst, genau wie Kontors eigene Routen /kontor tragen. Nur auf
den Tailnet- und LAN-Listenern erreichbar, nicht ueber den oeffentlichen
Cloudflare-Listener - kein Passwort, kein Login, dieselbe
Vertrauensannahme wie bei Kontors LAN/Tailnet-Stufen (siehe require_internal
unten): wer hierher durchkommt, kam schon durch edge, und edge ist die
einzige Stelle, die den Flask-Prozess ueberhaupt erreichen kann (bindet nur
an 127.0.0.1, edge selbst laeuft mit network_mode: host).
"""

import argparse
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import ROOT, load_config, load_meta, parse_article, parse_html_article  # noqa: E402
from envutil import load_dotenv  # noqa: E402
from social import bluesky, linkedin, mastodon  # noqa: E402
from summarize import headline, summarize_all  # noqa: E402

import re

from flask import Flask, abort, redirect, render_template, request, url_for

load_dotenv(ROOT / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # LinkedIn-Export-Upload im Ranking

# Gemeinsame Vorlagen-Hilfen (Tabs, Artikel-Auswahl, Formular-Token)
import gemeinsam  # noqa: E402

gemeinsam.init_app(app)

# Artikel-Ranking (/verwaltung/ranking), Deploy-Panel (/verwaltung/deploy),
# Plattformseiten (/verwaltung/plattform/<name>): eigene Module
from deploy_views import bp as deploy_bp  # noqa: E402
from plattform_views import bp as plattform_bp  # noqa: E402
from ranking_views import bp as ranking_bp  # noqa: E402

app.register_blueprint(ranking_bp)
app.register_blueprint(deploy_bp)
app.register_blueprint(plattform_bp)


@app.before_request
def gleicher_ursprung() -> None:
    """Schutz gegen Formular-Posts von fremden Seiten (CSRF): schickt der
    Browser Origin oder Referer mit, muss der Host zu dieser Verwaltung
    passen. Die Ranking-Formulare tragen zusaetzlich ein Token."""
    if request.method != "POST":
        return
    herkunft = request.headers.get("Origin") or request.headers.get("Referer")
    if herkunft:
        netloc = urllib.parse.urlparse(herkunft).netloc
        if netloc not in {request.host, request.headers.get("X-Forwarded-Host", "")}:
            abort(403)

ENV_VARS = {
    "mastodon": ["MASTODON_ACCESS_TOKEN"],
    "bluesky": ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"],
    "linkedin": ["LINKEDIN_ACCESS_TOKEN"],
    "x": ["X_BEARER_TOKEN"],
}

def require_internal() -> None:
    """Bricht mit 403 ab, wenn die Anfrage nicht ueber edge kam. Praktisch
    unerreichbar, solange edge/Caddyfile /verwaltung nur auf den beiden
    internen Listenern (Tailnet :8088, LAN :8090) einhaengt und den Header
    dort immer setzt - das ist das Sicherheitsnetz, falls diese App je
    direkt (ohne edge davor) erreichbar gemacht wird."""
    if not request.headers.get("X-Blog-Verwaltung-Intern"):
        abort(403)


def list_articles(cfg: dict) -> list[dict]:
    articles_dir = ROOT / cfg["paths"]["articles_dir"]
    items = []
    for path in sorted(articles_dir.glob("*.md")):
        meta = parse_article(path)
        if meta.get("draft", False):
            continue
        items.append({"slug": meta["slug"], "title": meta["title"], "date": str(meta["date"])})
    for path in sorted(articles_dir.glob("*.html")):
        meta = parse_html_article(path)
        items.append({"slug": meta["slug"], "title": meta["title"], "date": str(meta["date"])})
    items.sort(key=lambda m: m["date"], reverse=True)
    return items


def deep_link_for(channel: str, cfg: dict, canonical_url: str, meta: dict, text) -> str | None:
    if channel == "reddit":
        subs = cfg["channels"]["reddit"].get("subreddits", [])
        sub = subs[0] if subs else "test"
        title = urllib.parse.quote(text["title"] if isinstance(text, dict) else meta["title"])
        body = urllib.parse.quote(text["body"] if isinstance(text, dict) else "")
        return f"https://www.reddit.com/r/{sub}/submit?type=TEXT&title={title}&text={body}"
    if channel == "facebook":
        return f"https://www.facebook.com/sharer/sharer.php?u={urllib.parse.quote(canonical_url)}"
    if channel == "youtube_community":
        return "https://studio.youtube.com/"
    if channel == "microsoft_tech_community":
        return "https://techcommunity.microsoft.com/"
    return None


@app.route("/verwaltung", methods=["GET"])
def dashboard():
    require_internal()

    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    if not quellen:
        return render_template("uebersicht.html", seite="uebersicht", auswahl=[], slug=None, channels={}, log="")

    slug = gemeinsam.gewaehlter_slug(quellen)
    meta = load_meta(cfg, slug)
    canonical_url = f"{cfg['site']['base_url']}/artikel/{slug}/"
    summaries = summarize_all(meta, cfg)

    channels = {}
    for name, ch_cfg in cfg["channels"].items():
        entry = {
            "manual": ch_cfg.get("manual", False),
            "enabled": ch_cfg.get("enabled", False),
            "note": ch_cfg.get("note"),
            "connected": all(os.environ.get(v) for v in ENV_VARS.get(name, [])) if ENV_VARS.get(name) else None,
            "seite": name in gemeinsam.PLATTFORMEN,
        }
        text = summaries.get(name)
        if entry["manual"]:
            if text is None:
                # Kanaele ohne eigene summarize_*-Funktion (Facebook, YouTube
                # Community, Microsoft Tech Community): derselbe Aufbau wie
                # ueberall sonst - Slogan zuerst, dann Titel, dann Beschreibung.
                text = f"{headline(meta)}\n\n{meta['description']}\n\n{canonical_url}"
            entry["text"] = text["body"] if isinstance(text, dict) else text
            entry["deep_link"] = deep_link_for(name, cfg, canonical_url, meta, text)
        channels[name] = entry

    log = request.args.get("log", "")
    return render_template("uebersicht.html", seite="uebersicht", auswahl=gemeinsam.artikel_auswahl(quellen),
                           slug=slug, meta=meta, channels=channels, log=log, live_url=canonical_url)


def set_channel_enabled(cfg_path: Path, name: str, enabled: bool) -> None:
    """Patcht nur die enabled-Zeile des betroffenen Kanals per Text-Ersetzung,
    statt die Datei mit yaml.dump() komplett neu zu schreiben - das würde alle
    Kommentare und die Formatierung in config.yaml zerstören."""
    text = cfg_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(\n  {re.escape(name)}:\n    enabled: )(true|false)")
    new_value = "true" if enabled else "false"
    patched, count = pattern.subn(rf"\g<1>{new_value}", text, count=1)
    if count != 1:
        raise RuntimeError(f"Konnte enabled-Zeile für Kanal '{name}' nicht eindeutig finden")
    cfg_path.write_text(patched, encoding="utf-8")


@app.route("/verwaltung/toggle", methods=["POST"])
def toggle():
    gemeinsam.post_pruefen()

    cfg_path = ROOT / "config.yaml"
    cfg = load_config()
    for name, ch_cfg in cfg["channels"].items():
        if ch_cfg.get("manual"):
            continue
        set_channel_enabled(cfg_path, name, f"enabled_{name}" in request.form)
    return redirect(url_for("dashboard", slug=request.form.get("slug", "")))


@app.route("/verwaltung/publish", methods=["POST"])
def publish():
    gemeinsam.post_pruefen()

    slug = request.form["slug"]
    if slug not in gemeinsam.artikel_quellen():
        abort(404)
    selected = [k for k in request.form.getlist("channels") if k in load_config()["channels"]]
    cmd = [sys.executable, str(ROOT / "scripts" / "publish.py"), slug, "--yes", "--nur-posten"]
    if selected:
        cmd += ["--channels", ",".join(selected)]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    log = result.stdout + "\n" + result.stderr
    return redirect(url_for("dashboard", slug=slug, log=log))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5151)
    args = parser.parse_args()

    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
