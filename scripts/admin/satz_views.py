"""Satz & Layout: /verwaltung/satz (Uebersicht ueber alle Artikel, Entwurfs-CSS ansehen, uebernehmen) und
Gutachten „Claude hinzuziehen“ je Artikel.

Messung: satzmessung.py (Playwright, deterministisch). Der Entwurf wird NUR ueber die Seite gelegt (nichts geaendert);
in static/style.css kommt er ausschliesslich nach Diff, Bestaetigung und Backup, danach Build mit automatischem Zurueckspielen.
"""

from __future__ import annotations

import difflib
import re
import shutil
from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

import bewertung as bw
import deploy as dp
import gemeinsam
import gutachten
import in_ordnung as io
import in_ordnung_views as iov
import satzmessung
from build import ROOT
from gemeinsam import speicher

bp = Blueprint("satz", __name__, template_folder="templates")
CSS = ROOT / "static" / "style.css"
KOPF = "/* ===== Typografie-Entwurf (übernommen {zeit}) ===== */\n"
FUSS = "\n/* ===== Ende Typografie-Entwurf ===== */\n"


def _slugs() -> list[str]:
    return [s for s, m in gemeinsam.artikel_quellen().items() if not m.get("is_html")]


@bp.route("/verwaltung/satz", methods=["GET"])
def seite():
    gemeinsam.require_intern()
    slugs = _slugs()
    satzmessung.im_hintergrund(ROOT, slugs)
    wahl = request.args.get("slug") or slugs[0]
    if wahl not in slugs:
        abort(404)
    entwurf = satzmessung.entwurf_gespeichert(ROOT, wahl)
    bilder = sorted(p.name for p in (satzmessung.verzeichnis(ROOT) / "bilder" / wahl).glob("*.png")) if (satzmessung.verzeichnis(ROOT) / "bilder" / wahl).exists() else []
    quellen = gemeinsam.artikel_quellen()
    vorher = satzmessung.uebersicht(ROOT, slugs)
    nachher = {}
    if entwurf:
        import bewertung
        nachher = {k.id: k for k in bewertung.bewerte_satz(entwurf)}
    css_stand = speicher.lesen("satz", "css_uebernommen.json")
    return render_template("satz.html", seite="ranking", slugs=slugs, quellen=quellen, uebersicht=vorher, wahl=wahl, entwurf=entwurf, nachher=nachher,
                           bilder=bilder, laeuft=[s for s in slugs if satzmessung.wird_gemessen(s)], css_stand=css_stand,
                           entwurf_da=satzmessung.entwurf_css(ROOT).exists(), meldung=request.args.get("meldung", ""), fehler=request.args.get("fehler", ""))


@bp.route("/verwaltung/satz/messen", methods=["POST"])
def messen():
    gemeinsam.post_pruefen()
    n = satzmessung.im_hintergrund(ROOT, _slugs(), nur_veraltete=False)
    return redirect(url_for("satz.seite", meldung=f"Messung gestartet ({n} Artikel, im Hintergrund)."))


@bp.route("/verwaltung/satz/entwurf", methods=["POST"])
def entwurf_ansehen():
    gemeinsam.post_pruefen()
    slug = request.form.get("slug") or ""
    if slug not in _slugs():
        abort(404)
    try:
        satzmessung.entwurf_messen(ROOT, slug)
    except RuntimeError as exc:
        return redirect(url_for("satz.seite", slug=slug, fehler=str(exc)))
    return redirect(url_for("satz.seite", slug=slug, meldung="Entwurf gemessen; Vorher/Nachher-Bilder erzeugt.") + "#entwurf")


@bp.route("/verwaltung/satz/bild/<slug>/<datei>", methods=["GET"])
def bild(slug, datei):
    gemeinsam.require_intern()
    if slug not in _slugs() or not re.fullmatch(r"(vorher|nachher|gutachten)-(hell|dunkel)-(desktop|handy)-(kopf|text)\.png", datei):
        abort(404)
    return send_from_directory(satzmessung.verzeichnis(ROOT) / "bilder" / slug, datei)


def css_mit_entwurf(alt: str, entwurf: str, zeit: str) -> str:
    """Haengt den Entwurf als abgegrenzten Block ans Ende der CSS; eine fruehere Uebernahme wird ersetzt, nie verdoppelt."""
    alt = re.sub(r"\n?/\* ===== Typografie-Entwurf \(übernommen [^)]*\) ===== \*/.*?/\* ===== Ende Typografie-Entwurf ===== \*/\n?", "\n", alt, flags=re.S).rstrip() + "\n"
    return alt + "\n" + KOPF.format(zeit=zeit) + entwurf.strip() + "\n" + FUSS


def _neuer_inhalt() -> tuple[str, str]:
    alt = CSS.read_text(encoding="utf-8")
    return alt, css_mit_entwurf(alt, satzmessung.entwurf_css(ROOT).read_text(encoding="utf-8"), datetime.now().strftime("%d.%m.%Y %H:%M"))


@bp.route("/verwaltung/satz/uebernehmen", methods=["GET"])
def bestaetigen():
    gemeinsam.require_intern()
    if not satzmessung.entwurf_css(ROOT).exists():
        abort(404)
    alt, neu = _neuer_inhalt()
    diff = list(difflib.unified_diff(alt.splitlines(), neu.splitlines(), "static/style.css (bisher)", "static/style.css (neu)", lineterm="", n=1))
    return render_template("satz_bestaetigen.html", seite="ranking", diff=diff, fehler=request.args.get("fehler", ""))


@bp.route("/verwaltung/satz/uebernehmen", methods=["POST"])
def uebernehmen():
    gemeinsam.post_pruefen()
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("satz.bestaetigen", fehler="Nicht bestätigt – nichts geändert."))
    if not io.sperre_nehmen("__css__"):
        return redirect(url_for("satz.seite", fehler="Es läuft gerade eine CSS-Änderung."))
    try:
        alt, neu = _neuer_inhalt()
        ziel = ROOT / "data" / "backups" / "css"
        ziel.mkdir(parents=True, exist_ok=True)
        backup = ziel / f"style.css.{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(CSS, backup)
        CSS.write_text(neu, encoding="utf-8")
        erg = dp.bauen(ROOT, timeout=io.BUILD_TIMEOUT)
        speicher.schreiben(erg, "deploy", "build.json")
        if not erg["ok"]:
            shutil.copy2(backup, CSS)
            dp.bauen(ROOT, timeout=io.BUILD_TIMEOUT)
            return redirect(url_for("satz.seite", fehler="Build fehlgeschlagen – style.css wurde automatisch zurückgespielt: " + erg["ausgabe"][-300:]))
        speicher.schreiben({"backup": str(backup), "zeit": datetime.now().isoformat(timespec="seconds")}, "satz", "css_uebernommen.json")
    finally:
        io.sperre_freigeben("__css__")
    satzmessung.im_hintergrund(ROOT, _slugs())
    return redirect(url_for("satz.seite", meldung="Entwurf in static/style.css übernommen und gebaut (Backup: " + str(backup.relative_to(ROOT)) + "). Nicht committet, nicht veröffentlicht."))


@bp.route("/verwaltung/satz/rueckgaengig", methods=["POST"])
def rueckgaengig():
    gemeinsam.post_pruefen()
    z = speicher.lesen("satz", "css_uebernommen.json")
    if not z or request.form.get("bestaetigt") != "ja":
        return redirect(url_for("satz.seite", fehler="Nichts rückgängig zu machen bzw. nicht bestätigt."))
    from pathlib import Path
    backup = Path(z["backup"])
    erlaubt = (ROOT / "data" / "backups" / "css").resolve()
    if not backup.exists() or erlaubt not in backup.resolve().parents:
        return redirect(url_for("satz.seite", fehler="Backup nicht gefunden."))
    if not io.sperre_nehmen("__css__"):
        return redirect(url_for("satz.seite", fehler="Es läuft gerade eine CSS-Änderung."))
    try:
        shutil.copy2(backup, CSS)
        erg = dp.bauen(ROOT, timeout=io.BUILD_TIMEOUT)
        speicher.schreiben(erg, "deploy", "build.json")
        speicher.schreiben(None, "satz", "css_uebernommen.json")
    finally:
        io.sperre_freigeben("__css__")
    satzmessung.im_hintergrund(ROOT, _slugs())
    return redirect(url_for("satz.seite", meldung="Rückgängig: static/style.css zurückgespielt und gebaut."))


# --- Gutachten (Claude) ---------------------------------------------------------------------------------------

@bp.route("/verwaltung/ranking/<slug>/gutachten/start", methods=["POST"])
def gutachten_start(slug):
    gemeinsam.post_pruefen()
    if slug not in _slugs():
        abort(404)
    ok, info = gutachten.starte(iov.kontext(), slug)
    return redirect(url_for("ranking.detail", slug=slug, **({"meldung": "Gutachten eingereiht – läuft im Hintergrund."} if ok else {"fehler": info})) + "#gutachten")


@bp.route("/verwaltung/ranking/<slug>/gutachten/abbrechen", methods=["POST"])
def gutachten_abbrechen(slug):
    gemeinsam.post_pruefen()
    if slug not in _slugs():
        abort(404)
    ok = io.abbruch_anfordern(slug)
    return redirect(url_for("ranking.detail", slug=slug, meldung="Abbruch angefordert." if ok else "Es läuft kein Auftrag.") + "#gutachten")


@bp.route("/verwaltung/ranking/<slug>/gutachten/status", methods=["GET"])
def gutachten_status(slug):
    gemeinsam.require_intern()
    if slug not in _slugs():
        abort(404)
    z = gutachten.zustand(iov.kontext(), slug) or {}
    return jsonify({"status": z.get("status", "keiner"), "schritt": z.get("schritt", ""), "meldung": z.get("meldung", "")})
