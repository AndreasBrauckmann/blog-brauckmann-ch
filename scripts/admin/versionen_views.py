"""Versionsverlauf: Ansehen (Diff zur aktuellen Fassung) und Wiederherstellen mit Bestaetigung.

Logik in versionen.py (Verlauf) und in_ordnung.wiederherstellen (Schreiben, Bauen, Rollback).
Geschrieben wird nur per POST mit Formular-Token und ausdruecklicher Bestaetigung; committet
oder veroeffentlicht wird nie.
"""

from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

import gemeinsam
import in_ordnung as io
import in_ordnung_views as iov
import versionen
from build import ROOT

bp = Blueprint("versionen", __name__, template_folder="templates")


def _lade(slug: str, vid: str):
    meta = iov._quelle(slug)
    if meta.get("is_html"):
        abort(400, "HTML-Artikel haben keinen Versionsverlauf")
    versionen.abgleich(ROOT, slug)
    zeile = versionen.zeile(ROOT, slug, vid)
    text = versionen.text_von(ROOT, slug, vid)
    if zeile is None or text is None:
        abort(404)
    aktuell = (ROOT / "articles" / f"{slug}.md").read_text(encoding="utf-8")
    diff = versionen.diff_zeilen(aktuell, text, "aktuelle Fassung", "gewählte Version")
    return meta, zeile, text, aktuell, diff


@bp.route("/verwaltung/ranking/<slug>/version/<vid>", methods=["GET"])
def ansehen(slug, vid):
    gemeinsam.require_intern()
    meta, zeile, text, aktuell, diff = _lade(slug, vid)
    return render_template("ranking_version.html", seite="ranking", slug=slug, meta=meta, z=zeile, diff=diff,
                           gleich=(text == aktuell), bestaetigen=False, ungueltig=versionen.frontmatter_gueltig(text, slug),
                           fehler=request.args.get("fehler", ""))


@bp.route("/verwaltung/ranking/<slug>/version/<vid>/wiederherstellen", methods=["GET"])
def bestaetigen(slug, vid):
    gemeinsam.require_intern()
    meta, zeile, text, aktuell, diff = _lade(slug, vid)
    return render_template("ranking_version.html", seite="ranking", slug=slug, meta=meta, z=zeile, diff=diff,
                           gleich=(text == aktuell), bestaetigen=True, ungueltig=versionen.frontmatter_gueltig(text, slug),
                           fehler=request.args.get("fehler", ""))


@bp.route("/verwaltung/ranking/<slug>/version/<vid>/wiederherstellen", methods=["POST"])
def ausfuehren(slug, vid):
    gemeinsam.post_pruefen()
    meta = iov._quelle(slug)
    if meta.get("is_html"):
        abort(400)
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("versionen.bestaetigen", slug=slug, vid=vid, fehler="Nicht bestätigt – nichts geändert."))
    erg = io.wiederherstellen(iov.kontext(), slug, vid)
    if erg["ok"]:
        return redirect(url_for("inordnung.seite", slug=slug, meldung=erg["meldung"]))
    return redirect(url_for("versionen.bestaetigen", slug=slug, vid=vid, fehler=erg["meldung"]))
