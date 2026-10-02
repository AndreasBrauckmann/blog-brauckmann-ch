"""Seiten zu „Alles in Ordnung bringen“: /verwaltung/ranking/<slug>/in-ordnung.

Logik in in_ordnung.py, Metas-Auswahl in metas_auswahl.py. Hier nur die
Verdrahtung mit Flask und dem echten Repo. Schreibende Aktionen (Uebernehmen,
Rueckgaengig) nur per POST mit Formular-Token, Ursprungspruefung und
ausdruecklicher Bestaetigung; committet, gepusht oder deployt wird hier nie.
"""

from __future__ import annotations

import hashlib
import tempfile
from datetime import date, datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

import bewertung as bw
import build
import deploy as dp
import gemeinsam
import in_ordnung as io
import llm
import metas_auswahl as ma
import ordnung_engine as eng
from build import ROOT, load_config
from gemeinsam import speicher

bp = Blueprint("inordnung", __name__, template_folder="templates")


# --------------------------------------------------------------------------
# Kontext mit dem echten Repo
# --------------------------------------------------------------------------


def _bewerte(slug: str):
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    meta = quellen[slug]
    b = bw.bewerte(meta, gemeinsam.koerper_html(meta), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                   dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=date.today(), alle_slugs=list(quellen))
    return meta, b


def _kennzahlen_text(b: bw.Bewertung) -> str:
    a = b.kennzahlen.get("amstad", {})
    return (f"Amstad-Index {a.get('index')}, Ø Satzlänge {a.get('asl')} Wörter, {b.kennzahlen.get('woerter')} Wörter, "
            f"visuelle Elemente {b.kennzahlen.get('visuell')}, größter Abstand ohne Grafik {b.kennzahlen.get('groesster_abstand')} Wörter, "
            f"regelbasierter Gesamtscore {b.gesamt}/100")


def _lektorat(meta: dict, b: bw.Bewertung) -> dict:
    koerper = gemeinsam.koerper_html(meta)
    ergebnis = llm.chat_json(llm.LEKTORAT_SYSTEM, llm.lektorat_prompt(meta, bw.lesetext(koerper, meta), _kennzahlen_text(b)), timeout=io.LLM_TIMEOUT, aufgabe="lektorat")
    speicher.lektorat_speichern(meta["slug"], {
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"), "modell": llm.modell_fuer("lektorat"),
        "text_hash": hashlib.sha256(meta["body_md"].encode()).hexdigest()[:16], "ergebnis": ergebnis})
    return ergebnis


def _simuliere(slug: str, neuer_text: str):
    """Wirkung berechnen, ohne etwas am Repo zu aendern: Entwurf in Wegwerf-Verzeichnis bauen und bewerten."""
    from pygments.formatters import HtmlFormatter
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / f"{slug}.md"
        p.write_text(neuer_text, encoding="utf-8")
        meta = build.parse_article(p)
        style = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        _s, seite = build.build_article(meta, cfg, build.load_template("article.html"), style, HtmlFormatter().get_style_defs(".codehilite"))
        ziel = Path(td) / "dist" / "artikel" / slug
        ziel.mkdir(parents=True)
        (ziel / "index.html").write_text(seite, encoding="utf-8")
        alle = list(quellen)
        return bw.bewerte(meta, build.render_markdown(meta["body_md"]), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                          dist_dir=Path(td) / "dist", heute=date.today(), alle_slugs=alle)


def _baue():
    erg = dp.bauen(ROOT, timeout=io.BUILD_TIMEOUT)
    speicher.schreiben(erg, "deploy", "build.json")
    return erg["ok"], erg["ausgabe"]


def _pflicht_fehlt(slug: str) -> list[str]:
    cfg = load_config()
    seite = ROOT / cfg["paths"]["dist_dir"] / "artikel" / slug / "index.html"
    if not seite.exists():
        return ["dist/-Seite fehlt"]
    text = seite.read_text(encoding="utf-8")
    return bw.pruefe_kopf(text[: text.find("</head>")])["fehlend"]


def kontext() -> io.Kontext:
    import vale_pruefung
    return io.Kontext(
        root=ROOT, speicher=speicher, chat=llm.chat, llm_aktiv=lambda: llm.llm_status()["aktiv"],
        bewerte=_bewerte, simuliere=_simuliere, lektorat=_lektorat, lektorat_alt=speicher.lektorat,
        lesetext=lambda meta: bw.lesetext(gemeinsam.koerper_html(meta), meta),
        vale=lambda p: vale_pruefung.pruefe(ROOT, p), baue=_baue, pflicht_fehlt=_pflicht_fehlt,
        quellen=lambda: gemeinsam.artikel_quellen(), gesundheit=llm.dienst_erreichbar)


def _quelle(slug: str) -> dict:
    quellen = gemeinsam.artikel_quellen()
    if slug not in quellen:
        abort(404)
    return quellen[slug]


def _md_oder_400(meta: dict) -> None:
    if meta.get("is_html"):
        abort(400, "HTML-Artikel werden nicht unterstützt (kein Frontmatter).")


def kurz_zustand(slug: str) -> dict | None:
    """Fuer den Knopf im Kopf der Detailseite."""
    z = io.zustand(kontext(), slug)
    if not z:
        return None
    return {"status": z.get("status"), "gestartet": z.get("gestartet"), "meldung": z.get("meldung", "")}


# --------------------------------------------------------------------------
# Seiten
# --------------------------------------------------------------------------


@bp.route("/verwaltung/ranking/<slug>/in-ordnung", methods=["GET"])
def seite(slug):
    gemeinsam.require_intern()
    meta = _quelle(slug)
    ctx = kontext()
    z = io.zustand(ctx, slug)
    if z and z.get("status") == "vorschlag":
        io.nachpruefen(ctx, slug, z)
    cfg = load_config()
    modell = {"slug": slug, "meta": meta, "z": z, "llm": llm.llm_status(), "gesperrt": io.ist_gesperrt(slug),
              "schritte": io.SCHRITTE, "meldung": request.args.get("meldung", ""), "fehler": request.args.get("fehler", ""),
              "live_url": gemeinsam.live_url(cfg, slug), "ist_html": bool(meta.get("is_html"))}
    if z:
        if z.get("vorher"):
            modell["vergleich"] = io.vergleich(z["vorher"], z.get("nachher") or z.get("erwartet"))
            modell["vergleich_erwartet"] = io.vergleich(z["vorher"], z.get("erwartet")) if z.get("erwartet") else None
            modell["vergleich_nachher"] = io.vergleich(z["vorher"], z.get("nachher")) if z.get("nachher") else None
        if z.get("status") == "vorschlag":
            _vorschau_modell(modell, ctx, meta, z)
        if z.get("nachher"):
            modell["aenderungen"] = io.kriterien_aenderungen(z["vorher"], z["nachher"])
            modell["fehlt"] = io.was_fehlt(z, z["nachher"])
            modell["fehlt_behebbar"] = any(f["art"] == "behebbar" for f in modell["fehlt"])
            modell["fehlt_mensch"] = [f for f in modell["fehlt"] if f["art"] == "mensch"]
    modell["domain"] = cfg["site"]["base_url"].split("//")[-1]
    return render_template("ranking_inordnung.html", seite="ranking", **modell)


def _vorschau_modell(modell: dict, ctx: io.Kontext, meta: dict, z: dict) -> None:
    benoetigt = set((z.get("metas") or {}).get("benoetigt") or [])
    a = ma.auswahl(ctx.root, meta, z.get("metas"), benoetigt)
    modell["ma"] = a
    wa = z.get("wirkung_auswahl")
    # vorgewaehlte Kombination: die zuletzt berechnete Auswahl des Nutzers, sonst die bestbewertete des Durchlaufs
    modell["ma_vorgabe"] = dict((wa or {}).get("meta_form") or z.get("meta_standard") or {})
    modell["auswahl_ids"] = set(wa["ids"]) if wa else None
    # Textstellen: nur der betroffene Absatz, Satz hervorgehoben, Vorher/Nachher satzweise mit Formatierung
    try:
        text = ctx.artikel_pfad(meta["slug"]).read_text(encoding="utf-8")
    except OSError:
        text = ""
    for s in list(z.get("stellen", [])) + list(z.get("stellen_abgelehnt", [])):
        art = s.get("art") or ("html" if s["alt"].lstrip().startswith("<p") else "md")
        s["ansicht"] = io.stelle_ansicht(art, s["alt_inner"], s.get("neu_inner") or "")
        s["ort"] = io.ort_fuer(text, s["start"]) or {"abschnitt": s.get("abschnitt", ""), "abschnitt_id": s.get("abschnitt_id", ""),
                                                      "absatz_nr": s.get("absatz_nr"), "zeile": s.get("zeile")}
    gruppen = []
    for gid, name in eng.GRUPPEN:
        if gid == "metas":
            continue
        items = [s for s in z.get("stellen", []) if (s.get("gruppe") or "saetze") == gid]
        if items:
            gruppen.append({"id": gid, "name": name, "stellen": items})
    modell["gruppen"] = gruppen
    bild = next((b for b in a["bilder"] if b["aktuell"]), None)
    modell["ma_bild_rel"] = bild["rel"] if bild else ""
    modell["ma_domain"] = modell.get("domain") or ""
    modell["offen_erwartet"] = z.get("offen_erwartet") or []
    modell["offen_behebbar"] = [o for o in modell["offen_erwartet"] if o.get("art") == "behebbar"]
    modell["offen_mensch"] = [o for o in modell["offen_erwartet"] if o.get("art") == "mensch"]


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/status", methods=["GET"])
def status(slug):
    gemeinsam.require_intern()
    _quelle(slug)
    z = io.zustand(kontext(), slug) or {}
    return jsonify({"status": z.get("status", "keiner"), "schritte": z.get("schritte", []), "meldung": z.get("meldung", ""),
                    "gesperrt": io.ist_gesperrt(slug), "fortschritt": z.get("fortschritt", {}), "warteplatz": z.get("warteplatz"),
                    "runden": [{"nr": r["nr"], "offen": [o["name"] for o in r.get("offen", [])], "neu": r.get("neu", 0)} for r in z.get("runden", [])],
                    "protokoll": z.get("protokoll", [])})


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/start", methods=["POST"])
def start(slug):
    gemeinsam.post_pruefen()
    meta = _quelle(slug)
    _md_oder_400(meta)
    ok, info = io.starte(kontext(), slug)
    if not ok:
        return redirect(url_for("inordnung.seite", slug=slug, fehler=info))
    return redirect(url_for("inordnung.seite", slug=slug))


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/abbrechen", methods=["POST"])
def abbrechen(slug):
    gemeinsam.post_pruefen()
    _quelle(slug)
    ok = io.abbruch_anfordern(slug)
    return redirect(url_for("inordnung.seite", slug=slug, meldung="Abbruch angefordert – der Auftrag endet nach dem laufenden Schritt." if ok else "Es läuft kein Auftrag."))


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/verwerfen", methods=["POST"])
def verwerfen(slug):
    gemeinsam.post_pruefen()
    _quelle(slug)
    io.verwerfen(kontext(), slug)
    return redirect(url_for("ranking.detail", slug=slug, meldung="Vorschlag verworfen – am Artikel wurde nichts geändert.") + "#in-ordnung")


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/uebernehmen", methods=["POST"])
def uebernehmen(slug):
    gemeinsam.post_pruefen()
    meta = _quelle(slug)
    _md_oder_400(meta)
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("inordnung.seite", slug=slug, fehler="Nicht bestätigt – nichts geändert."))
    meta_werte = {f: request.form.get(f, "") for f in ("title", "description", "og_image_alt") if f in request.form}
    if request.form.get("og_image"):
        meta_werte["og_image"] = request.form["og_image"]
    try:
        stellen = {int(x) for x in request.form.getlist("stelle")}
    except ValueError:
        abort(400)
    erg = io.uebernehmen(kontext(), slug, meta_werte, stellen)
    return redirect(url_for("inordnung.seite", slug=slug, **({"meldung": erg["meldung"]} if erg["ok"] else {"fehler": erg["meldung"]})))


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/rueckgaengig", methods=["POST"])
def rueckgaengig(slug):
    gemeinsam.post_pruefen()
    _quelle(slug)
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("inordnung.seite", slug=slug, fehler="Nicht bestätigt – nichts geändert."))
    erg = io.rueckgaengig(kontext(), slug)
    return redirect(url_for("inordnung.seite", slug=slug, **({"meldung": erg["meldung"]} if erg["ok"] else {"fehler": erg["meldung"]})))


def _formular_auswahl():
    meta_werte = {f: request.form.get(f, "") for f in ("title", "description", "og_image_alt") if f in request.form}
    if request.form.get("og_image"):
        meta_werte["og_image"] = request.form["og_image"]
    try:
        stellen = {int(x) for x in request.form.getlist("stelle")}
    except ValueError:
        abort(400)
    return meta_werte, stellen


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/wirkung", methods=["POST"])
def wirkung_route(slug):
    """Wirkung der aktuellen Auswahl neu rechnen (JS-frei, nur Simulation) und anzeigen, was dadurch wieder rot wuerde."""
    gemeinsam.post_pruefen()
    _md_oder_400(_quelle(slug))
    ctx = kontext()
    if request.form.get("aktion") == "zuruecksetzen":
        z = io.zustand(ctx, slug)
        if z:
            z.pop("wirkung_auswahl", None)
            io._sichern(ctx, slug, z)
        return redirect(url_for("inordnung.seite", slug=slug, meldung="Auswahl zurückgesetzt: alle Vorschläge sind wieder angehakt.") + "#wirkung")
    meta_werte, stellen = _formular_auswahl()
    erg = io.wirkung(ctx, slug, meta_werte, stellen)
    return redirect(url_for("inordnung.seite", slug=slug, **({"meldung": erg["meldung"]} if erg["ok"] else {"fehler": erg["meldung"]})) + "#wirkung")


@bp.route("/verwaltung/ranking/<slug>/in-ordnung/nachholen", methods=["POST"])
def nachholen(slug):
    """Nur die wegen eines Verbindungsproblems nicht bearbeiteten Stellen nochmals (nur Vorschlaege)."""
    gemeinsam.post_pruefen()
    _md_oder_400(_quelle(slug))
    ok, info = io.starte(kontext(), slug, modus="nachholen")
    return redirect(url_for("inordnung.seite", slug=slug, **({} if ok else {"fehler": info})))
