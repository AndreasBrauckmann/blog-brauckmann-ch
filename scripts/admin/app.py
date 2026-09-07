#!/usr/bin/env python3
"""Verwaltungsseite: Kanal-Übersicht, Verbindungsstatus, Veröffentlichen per Klick.

Nutzung:
    .venv/bin/python scripts/admin/app.py [--host 127.0.0.1] [--port 5151]

Nur intern erreichbar vorgesehen - Zugriff von aussen über
`tailscale serve` auf 127.0.0.1:<port>, nicht über einen offenen Port.
Zusätzlich durch ADMIN_PASSWORD (.env) geschützt.
"""

import argparse
import os
import secrets
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build import ROOT, load_config, parse_article  # noqa: E402
from envutil import load_dotenv  # noqa: E402
from social import bluesky, linkedin, mastodon  # noqa: E402
from summarize import summarize_all  # noqa: E402

import re

from flask import Flask, redirect, render_template_string, request, session, url_for

load_dotenv(ROOT / ".env")

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET_KEY") or secrets.token_hex(32)

ENV_VARS = {
    "mastodon": ["MASTODON_ACCESS_TOKEN"],
    "bluesky": ["BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"],
    "linkedin": ["LINKEDIN_ACCESS_TOKEN"],
    "x": ["X_BEARER_TOKEN"],
}

BASE_HTML = """
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blog-Verwaltung</title>
<style>
:root { --bg:#fff; --fg:#1a1a1a; --muted:#666; --border:#ddd; --ok:#1a7f37; --bad:#c0392b; --card:#f7f7f8; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#121212; --fg:#e6e6e6; --muted:#999; --border:#333; --ok:#5fd17c; --bad:#ff6b6b; --card:#1c1c1e; }
}
* { box-sizing: border-box; }
body { background:var(--bg); color:var(--fg); font-family:-apple-system,Segoe UI,Roboto,sans-serif; max-width:840px; margin:0 auto; padding:1.5rem; line-height:1.5; }
h1 { font-size:1.4rem; }
.card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:1rem; margin-bottom:1rem; }
.badge { display:inline-block; padding:0.1rem 0.6rem; border-radius:999px; font-size:0.8rem; }
.badge.ok { background:var(--ok); color:#fff; }
.badge.bad { background:var(--bad); color:#fff; }
.badge.manual { background:var(--muted); color:#fff; }
textarea { width:100%; min-height:6rem; background:var(--bg); color:var(--fg); border:1px solid var(--border); border-radius:6px; padding:0.5rem; font-family:inherit; }
button, select, input[type=password] { font:inherit; padding:0.4rem 0.8rem; border-radius:6px; border:1px solid var(--border); background:var(--bg); color:var(--fg); }
button { cursor:pointer; }
button.primary { background:var(--ok); color:#fff; border:none; }
a.deep-link { text-decoration:none; }
.row { display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.5rem; }
pre.log { white-space:pre-wrap; background:var(--card); border:1px solid var(--border); border-radius:6px; padding:0.8rem; max-height:20rem; overflow-y:auto; }
</style>
</head>
<body>
{{ body|safe }}
</body>
</html>
"""

LOGIN_HTML = """
<h1>Blog-Verwaltung</h1>
<form method="post">
  <input type="password" name="password" placeholder="Passwort" autofocus>
  <button class="primary" type="submit">Anmelden</button>
</form>
{% if error %}<p style="color:var(--bad)">{{ error }}</p>{% endif %}
"""

DASHBOARD_HTML = """
<h1>Blog-Verwaltung</h1>

<form method="get" class="row">
  <label for="slug">Artikel:</label>
  <select name="slug" id="slug" onchange="this.form.submit()">
    {% for a in articles %}
    <option value="{{ a.slug }}" {% if a.slug == slug %}selected{% endif %}>{{ a.date }} – {{ a.title }}</option>
    {% endfor %}
  </select>
</form>

{% if log %}<h2>Ergebnis</h2><pre class="log">{{ log }}</pre>{% endif %}

<form method="post" action="{{ url_for('publish') }}">
<input type="hidden" name="slug" value="{{ slug }}">

{% for name, ch in channels.items() %}
<div class="card">
  <div class="row">
    <strong>{{ name }}</strong>
    {% if ch.manual %}
      <span class="badge manual">manuell</span>
    {% elif ch.connected %}
      <span class="badge ok">verbunden</span>
    {% else %}
      <span class="badge bad">kein Token</span>
    {% endif %}
    {% if not ch.manual %}
    <label><input type="checkbox" name="channels" value="{{ name }}" {% if ch.enabled %}checked{% endif %}> jetzt posten</label>
    {% endif %}
  </div>
  {% if ch.note %}<p style="color:var(--muted); font-size:0.9rem">{{ ch.note }}</p>{% endif %}
  {% if ch.text %}
    <textarea readonly>{{ ch.text }}</textarea>
    <div class="row">
      <button type="button">In Zwischenablage kopieren</button>
      {% if ch.deep_link %}<a class="deep-link" href="{{ ch.deep_link }}" target="_blank"><button type="button">Compose öffnen</button></a>{% endif %}
    </div>
  {% endif %}
</div>
{% endfor %}

<button class="primary" type="submit">Ausgewählte Kanäle veröffentlichen</button>
</form>

<p style="color:var(--muted); font-size:0.9rem; margin-top:1.5rem">Dauerhaft als automatischen Kanal aktivieren/deaktivieren (unabhängig vom aktuellen Veröffentlichen):</p>
<form method="post" action="{{ url_for('toggle') }}">
<input type="hidden" name="slug" value="{{ slug }}">
{% for name, ch in channels.items() %}
  {% if not ch.manual %}
  <label style="margin-right:1rem"><input type="checkbox" name="enabled_{{ name }}" {% if ch.enabled %}checked{% endif %} onchange="this.form.submit()"> {{ name }} dauerhaft aktiv</label>
  {% endif %}
{% endfor %}
</form>

<script>
document.querySelectorAll('textarea[readonly]').forEach(function(ta, i) {
  var btn = ta.nextElementSibling.querySelector('button');
  if (btn) btn.addEventListener('click', function() {
    navigator.clipboard.writeText(ta.value);
    btn.textContent = 'Kopiert!';
    setTimeout(function(){ btn.textContent = 'In Zwischenablage kopieren'; }, 1500);
  });
});
</script>
"""


def require_login():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if request.method == "POST":
        if not admin_password:
            error = "ADMIN_PASSWORD ist in .env nicht gesetzt."
        elif secrets.compare_digest(request.form.get("password", ""), admin_password):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        else:
            error = "Falsches Passwort."
    return render_template_string(BASE_HTML, body=render_template_string(LOGIN_HTML, error=error))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def list_articles(cfg: dict) -> list[dict]:
    articles_dir = ROOT / cfg["paths"]["articles_dir"]
    items = []
    for path in sorted(articles_dir.glob("*.md")):
        meta = parse_article(path)
        if meta.get("draft", False):
            continue
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


@app.route("/", methods=["GET"])
def dashboard():
    redirect_resp = require_login()
    if redirect_resp:
        return redirect_resp

    cfg = load_config()
    articles = list_articles(cfg)
    if not articles:
        return render_template_string(BASE_HTML, body="<h1>Blog-Verwaltung</h1><p>Keine Artikel gefunden.</p>")

    slug = request.args.get("slug", articles[0]["slug"])
    path = ROOT / cfg["paths"]["articles_dir"] / f"{slug}.md"
    meta = parse_article(path)
    canonical_url = f"{cfg['site']['base_url']}/artikel/{slug}/"
    summaries = summarize_all(meta, cfg)

    channels = {}
    for name, ch_cfg in cfg["channels"].items():
        entry = {
            "manual": ch_cfg.get("manual", False),
            "enabled": ch_cfg.get("enabled", False),
            "note": ch_cfg.get("note"),
            "connected": all(os.environ.get(v) for v in ENV_VARS.get(name, [])) if ENV_VARS.get(name) else None,
        }
        text = summaries.get(name)
        if entry["manual"]:
            if text is None:
                text = f"{meta['description']}\n\n{canonical_url}"
            entry["text"] = text["body"] if isinstance(text, dict) else text
            entry["deep_link"] = deep_link_for(name, cfg, canonical_url, meta, text)
        channels[name] = entry

    log = request.args.get("log", "")
    return render_template_string(
        BASE_HTML,
        body=render_template_string(
            DASHBOARD_HTML, articles=articles, slug=slug, channels=channels, log=log
        ),
    )


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


@app.route("/toggle", methods=["POST"])
def toggle():
    redirect_resp = require_login()
    if redirect_resp:
        return redirect_resp

    cfg_path = ROOT / "config.yaml"
    cfg = load_config()
    for name, ch_cfg in cfg["channels"].items():
        if ch_cfg.get("manual"):
            continue
        set_channel_enabled(cfg_path, name, f"enabled_{name}" in request.form)
    return redirect(url_for("dashboard", slug=request.form.get("slug", "")))


@app.route("/publish", methods=["POST"])
def publish():
    redirect_resp = require_login()
    if redirect_resp:
        return redirect_resp

    slug = request.form["slug"]
    selected = request.form.getlist("channels")
    cmd = [sys.executable, str(ROOT / "scripts" / "publish.py"), slug, "--yes"]
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

    if not os.environ.get("ADMIN_PASSWORD"):
        print("WARNUNG: ADMIN_PASSWORD ist in .env nicht gesetzt - Login schlägt fehl.", file=sys.stderr)

    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
