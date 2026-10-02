"""Deploy-Panel /verwaltung/deploy: Pruefen -> Bauen -> Diff -> Veroeffentlichen -> Live pruefen.

Logik in deploy.py, Live-Pruefung in inspector.py. Laufzeitdaten (letzter
Build, Deploy-Verlauf) unter data/ranking/deploy/ - nie im Repo.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

import bewertung as bw
import deploy as dp
import gemeinsam
import inspector
import versionen
from build import ROOT, load_config
from gemeinsam import speicher

bp = Blueprint("deploy", __name__, template_folder="templates")

SCHWELLE_ROT = 60  # Gesamtscore darunter: Veroeffentlichen nur mit zusaetzlicher Bestaetigung


def _bewertungen(cfg: dict, quellen: dict) -> dict[str, bw.Bewertung]:
    heute = date.today()
    return {s: bw.bewerte(m, gemeinsam.koerper_html(m), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                          dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=heute, alle_slugs=list(quellen))
            for s, m in quellen.items()}


def link_pruefung(meta: dict, quellen: dict) -> dict:
    """Interne Links (/artikel/…, /static/…, /tag/…) auf Existenz pruefen; externe nur zaehlen."""
    z = bw.zerlege_html(gemeinsam.koerper_html(meta))
    kaputt, extern = [], 0
    for ziel in list(z.links) + [b["src"] for b in z.bilder] + [v["poster"] for v in z.videos if v.get("poster")]:
        if not ziel or ziel.startswith(("#", "mailto:")):
            continue
        if ziel.startswith(("http://", "https://")):
            if "blog.brauckmann.ch" not in ziel:
                extern += 1
                continue
            ziel = urllib.parse.urlparse(ziel).path
        pfad = ziel.split("#")[0].split("?")[0]
        m = re.match(r"^/artikel/([^/]+)/?$", pfad)
        if m:
            if m.group(1) not in quellen:
                kaputt.append(ziel)
        elif pfad.startswith("/static/"):
            if not (ROOT / pfad.lstrip("/")).exists():
                kaputt.append(ziel)
        elif pfad.startswith("/tag/") or pfad in ("/", ""):
            continue
    return {"kaputt": kaputt, "extern": extern}


def vorab_pruefung(slugs: list[str], cfg: dict, quellen: dict, bewertungen: dict) -> list[dict]:
    werte = [b.gesamt for b in bewertungen.values()]
    schnitt = sum(werte) / len(werte) if werte else 0
    zeilen = []
    for slug in slugs:
        if slug not in quellen:
            zeilen.append({"slug": slug, "titel": slug, "fehlt": True})
            continue
        b = bewertungen[slug]
        meta = quellen[slug]

        def k(kid):
            return b.kriterium(kid)

        links = link_pruefung(meta, quellen)
        pruef = []
        pf = k("a_pflicht")
        pruef.append({"name": "Pflicht-Meta-Tags (dist/)", "stufe": "ok" if pf and pf.erfuellung == 100 else "fehler", "text": pf.messwert if pf else "?"})
        di = k("a_dist")
        pruef.append({"name": "Build aktuell", "stufe": "ok" if di and di.erfuellung == 100 else "fehler", "text": di.messwert if di else "?"})
        bi = k("a_bild")
        bm = b.kennzahlen.get("og_bild_masse")
        kt = inspector.kartentyp(*bm) if bm else "keine"
        pruef.append({"name": "Vorschaubild", "stufe": "fehler" if not bi or bi.erfuellung == 0 else ("ok" if kt == "gross" else "warn"),
                      "text": (bi.messwert if bi else "?") + f" → Karte: {kt}"})
        be = k("a_beschr")
        pruef.append({"name": "Beschreibungslänge", "stufe": "ok" if be.status == "ok" else "warn", "text": be.messwert + " (Soll 120–160)"})
        ti = k("a_titel")
        pruef.append({"name": "Titellänge", "stufe": "ok" if ti.status == "ok" else "warn", "text": ti.messwert + " (Soll 40–70)"})
        pruef.append({"name": "Links", "stufe": "fehler" if links["kaputt"] else "ok",
                      "text": (f"kaputt: {', '.join(links['kaputt'][:4])}" if links["kaputt"] else "interne Links/Bilder vorhanden") + f"; {links['extern']} externe"})
        km = b.kennzahlen.get("ki_muster")
        if km:
            import ki_muster
            treffer = [(r["name"], km[r["id"]]["anzahl"]) for r in ki_muster.REGELN if r["gewicht"] and not km[r["id"]]["ok"]]
            if treffer:
                # Nur ein Hinweis (gelb), NIE ein Sperrgrund: stufe "warn" blockiert das Veroeffentlichen nicht
                pruef.append({"name": "Klingt menschlich", "stufe": "warn",
                              "text": f"{sum(n for _x, n in treffer)} Hinweise (" + ", ".join(f"{name} {n}" for name, n in treffer) + ")",
                              "link": f"/verwaltung/ranking/{slug}#kriterien"})
            else:
                pruef.append({"name": "Klingt menschlich", "stufe": "ok", "text": "keine auffälligen KI-Muster"})
        stufe_s = "fehler" if b.gesamt < SCHWELLE_ROT else ("warn" if b.gesamt < schnitt else "ok")
        pruef.append({"name": "Bewertungsscore", "stufe": stufe_s,
                      "text": f"{b.gesamt:.0f}/100 (Schwelle {SCHWELLE_ROT}, Ø aller Artikel {schnitt:.0f})"
                      + (" – unter Durchschnitt" if b.gesamt < schnitt else "")})
        auff = bw.auffaelligkeiten(b, schnitt)
        zeilen.append({"slug": slug, "titel": b.titel, "gesamt": b.gesamt, "ampel": b.ampel, "pruefungen": pruef,
                       "auffaelligkeiten": auff, "blockiert": any(p["stufe"] == "fehler" for p in pruef),
                       "live_url": gemeinsam.live_url(cfg, slug)})
    return zeilen


def _verlauf() -> list[dict]:
    return speicher.lesen("deploy", "verlauf.json", standard=[]) or []


def _standard_meldung(slugs: list[str], quellen: dict) -> str:
    bekannte = [s for s in slugs if s in quellen]
    if len(bekannte) == 1:
        return f"Blog: {quellen[bekannte[0]]['title']}"
    if bekannte:
        return f"Blog: {len(bekannte)} Artikel aktualisiert ({', '.join(bekannte)})"
    return "Blog: Aktualisierung"


@bp.route("/verwaltung/deploy", methods=["GET"])
def seite():
    gemeinsam.require_intern()
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    versionen.abgleich_alle(ROOT, [s for s, m in quellen.items() if not m.get("is_html")])
    aenderungen = dp.klassifiziere(ROOT, dp.status(ROOT))
    # ?artikel=<slug>: Vorauswahl nur fuer diesen Artikel (Weiterleitung aus „Alles in Ordnung bringen“)
    fokus = request.args.get("artikel") or ""
    if fokus not in quellen:
        fokus = ""
    if fokus:
        aenderungen = dp.fokus_auf_artikel(aenderungen, fokus)
    slugs = dp.geaenderte_slugs(aenderungen)
    if fokus and fokus in slugs:
        slugs = [fokus]
    alle = request.args.get("alle") == "1"
    bewertungen = _bewertungen(cfg, quellen)
    pruef_slugs = list(quellen) if alle or not slugs else slugs
    pruefung = vorab_pruefung(pruef_slugs, cfg, quellen, bewertungen)
    gruppen: dict[str, list] = {}
    for a in aenderungen:
        gruppen.setdefault(a.bereich, []).append(a)
    diffs = {}
    for a in aenderungen:
        if a.pfad.startswith(("articles/", "templates/")) or a.pfad in ("config.yaml", "CLAUDE.md"):
            if a.art == "neu":
                continue
            d = dp.git(ROOT, "diff", "HEAD", "--", a.pfad).stdout
            diffs[a.pfad] = d[:30000] + ("\n[… gekürzt]" if len(d) > 30000 else "")
    stat = dp.git(ROOT, "diff", "HEAD", "--shortstat").stdout.strip()
    verlauf = _verlauf()
    letzter = verlauf[-1] if verlauf else None
    insp = speicher.inspector()
    li_status = {}
    if letzter:
        for s in letzter.get("slugs", []):
            li_status[s] = insp.get(s)
    return render_template(
        "deploy.html", seite="deploy", aenderungen=aenderungen, gruppen=gruppen, slugs=slugs, pruefung=pruefung,
        alle=alle, build=speicher.lesen("deploy", "build.json"), diffs=diffs, stat=stat,
        stand=dp.stand_fingerabdruck(ROOT), meldung_vorschlag=_standard_meldung(slugs, quellen),
        letzter=letzter, verlauf=list(reversed(verlauf[-8:])), live={s: inspector.letztes_ergebnis(s) for s in (letzter or {}).get("slugs", [])},
        li_status=li_status, post_inspector=inspector.POST_INSPECTOR, inspector_url=inspector.post_inspector_url,
        live_url=lambda s: gemeinsam.live_url(cfg, s), quellen=quellen, heute=date.today().isoformat(),
        meldung=request.args.get("meldung", ""), fehler=request.args.get("fehler", ""), schwelle=SCHWELLE_ROT,
        fokus=fokus,
    )


@bp.route("/verwaltung/deploy/verbindung", methods=["GET"])
def verbindung():
    gemeinsam.require_intern()
    return jsonify(dp.verbindung_pruefen(ROOT))


@bp.route("/verwaltung/deploy/bauen", methods=["POST"])
def bauen():
    gemeinsam.post_pruefen()
    erg = dp.bauen(ROOT)
    speicher.schreiben(erg, "deploy", "build.json")
    fokus = request.form.get("artikel") or ""
    if fokus not in gemeinsam.artikel_quellen(load_config()):
        fokus = ""
    return redirect(url_for("deploy.seite", meldung="Build erfolgreich." if erg["ok"] else "", fehler="" if erg["ok"] else "Build fehlgeschlagen – Ausgabe prüfen.",
                            **({"artikel": fokus} if fokus else {})) + "#bauen")


@bp.route("/verwaltung/deploy/veroeffentlichen", methods=["POST"])
def veroeffentlichen():
    gemeinsam.post_pruefen()
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("deploy.seite", fehler="Nicht bestätigt – nichts veröffentlicht.") + "#veroeffentlichen")
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    pfade = request.form.getlist("pfad")
    aenderungen = {a.pfad: a for a in dp.klassifiziere(ROOT, dp.status(ROOT))}
    slugs = dp.geaenderte_slugs([aenderungen[p] for p in pfade if p in aenderungen])
    # Warnungen der Vorab-Pruefung erfordern eine zweite, ausdrueckliche Bestaetigung
    pruefung = vorab_pruefung([s for s in slugs if s in quellen], cfg, quellen, _bewertungen(cfg, quellen))
    if any(z.get("blockiert") for z in pruefung) and request.form.get("trotzdem") != "ja":
        return redirect(url_for("deploy.seite", fehler="Die Vorab-Prüfung meldet Fehler. Zum Veröffentlichen zusätzlich „Trotz Fehlern veröffentlichen“ bestätigen.") + "#veroeffentlichen")
    nachricht = (request.form.get("nachricht") or "").strip()
    titel_zeile = nachricht.splitlines()[0] if nachricht else ""
    try:
        erg = dp.veroeffentlichen(ROOT, pfade, nachricht, erwarteter_fingerabdruck=request.form.get("stand", ""),
                                  verbotene_begriffe=cfg.get("forbidden_terms", []),
                                  log_zeilen=[f"deploy: {titel_zeile}" + (f" (Artikel: {', '.join(slugs)})" if slugs else "")
                                              + f", {len(pfade)} Dateien, über die Verwaltung"])
    except dp.DeployFehler as exc:
        return redirect(url_for("deploy.seite", fehler=str(exc)) + "#veroeffentlichen")
    verlauf = _verlauf()
    verlauf.append({**erg, "zeitpunkt": datetime.now().isoformat(timespec="seconds"), "slugs": slugs, "meldung": titel_zeile})
    speicher.schreiben(verlauf[-50:], "deploy", "verlauf.json")
    if erg["push_ok"]:
        return redirect(url_for("deploy.seite", meldung=f"Committet und gepusht ({erg['sha'][:8]}). Warte auf GitHub Pages …") + "#live")
    return redirect(url_for("deploy.seite", fehler=f"Commit {erg['sha'][:8]} angelegt, Push fehlgeschlagen: {erg['push_text'][-300:]}") + "#live")


@bp.route("/verwaltung/deploy/lauf/<sha>", methods=["GET"])
def lauf(sha):
    gemeinsam.require_intern()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        abort(400)
    eintrag = next((v for v in _verlauf() if v.get("sha") == sha), None)
    if eintrag is None:
        abort(404)
    if not eintrag.get("dist_geaendert"):
        return jsonify({"zustand": "kein_lauf", "text": "Keine Änderung unter dist/ – der Pages-Workflow startet nur bei dist/**."})
    return jsonify(dp.pages_lauf(ROOT, sha))


@bp.route("/verwaltung/deploy/live/<sha>", methods=["POST"])
def live(sha):
    gemeinsam.post_pruefen()
    eintrag = next((v for v in _verlauf() if v.get("sha") == sha), None)
    if eintrag is None:
        abort(404)
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    for s in eintrag.get("slugs", []):
        if s in quellen:
            inspector.pruefe_artikel(s, cfg)
    return redirect(url_for("deploy.seite", meldung="Live-Prüfung abgeschlossen.") + "#live")


@bp.route("/verwaltung/inspector/<slug>", methods=["POST"])
def inspector_pruefen(slug):
    """Live-Pruefung eines Artikels (Knopf in Panel, Ranking und Plattformseiten)."""
    gemeinsam.post_pruefen()
    cfg = load_config()
    if slug not in gemeinsam.artikel_quellen(cfg):
        abort(404)
    erg = inspector.pruefe_artikel(slug, cfg)
    zurueck = request.form.get("zurueck") or ""
    if not zurueck.startswith("/verwaltung") or "//" in zurueck or "\\" in zurueck:
        zurueck = url_for("ranking.detail", slug=slug)
    trenner = "&" if "?" in zurueck.split("#")[0] else "?"
    basis, _, anker = zurueck.partition("#")
    return redirect(f"{basis}{trenner}{urllib.parse.urlencode({'meldung': 'Inspector: ' + {'gruen': 'alles in Ordnung', 'gelb': 'Hinweise', 'rot': 'Fehler'}[erg['ampel']]})}" + (f"#{anker}" if anker else "#inspector"))
