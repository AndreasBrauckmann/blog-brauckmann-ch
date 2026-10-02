"""Artikel-Ranking der Blog-Verwaltung: /verwaltung/ranking und Detailseiten.

Bewertung: bewertung.py (regelbasiert, offline). Lektorat und
Meta-Vorschlaege: llm.py (optional). Laufzeitdaten: ranking_daten.py unter
data/ranking/ (in .gitignore - nie ins oeffentliche Repo).

Sicherheit wie der Rest der Verwaltung: jede Route ruft require_internal()
(Header X-Blog-Verwaltung-Intern, gesetzt nur von edge). Zusaetzlich fuer
jedes POST: Formular-Token (HMAC aus einem lokalen Geheimnis) und
Ursprungspruefung (Origin/Referer muss zum eigenen Host passen). Slugs
werden nur aus der Artikelliste akzeptiert. Schreibende Aktionen am Artikel
(Frontmatter) nur nach ausdruecklicher Bestaetigung mit Diff, mit Backup,
ohne Build, ohne Commit, ohne Veroeffentlichung.
"""

from __future__ import annotations

import difflib
import hashlib
import urllib.parse
from datetime import date, datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

import bewertung as bw
import linkedin_import as li
import llm
import metas_auswahl as ma_mod
import in_ordnung
import ki_muster
import satzmessung
import versionen
from build import ROOT, load_config
import gemeinsam
import inspector as live_inspector
import vale_pruefung
from collections import Counter
from gemeinsam import speicher
from ranking_daten import ERLAUBTE_FELDER, FrontmatterFehler, setze_felder, vorschau_hash

bp = Blueprint("ranking", __name__, template_folder="templates")

MAX_UPLOAD = 5 * 1024 * 1024
POST_INSPECTOR = "https://www.linkedin.com/post-inspector/"


# --------------------------------------------------------------------------
# Hilfen (Zugriffsschutz, Artikelquellen: gemeinsam.py)
# --------------------------------------------------------------------------

_intern = gemeinsam.require_intern
_post_pruefen = gemeinsam.post_pruefen
artikel_quellen = gemeinsam.artikel_quellen
_koerper_html = gemeinsam.koerper_html


@bp.app_template_filter("hash16")
def _hash16(text) -> str:
    return hashlib.sha256(str(text).encode()).hexdigest()[:16]


def _slug_oder_404(slug: str, quellen: dict) -> dict:
    if slug not in quellen:
        abort(404)
    return quellen[slug]


def _live_url(cfg: dict, slug: str) -> str:
    return f"{cfg['site']['base_url']}/artikel/{slug}/"


def inspector_url(live_url: str) -> str:
    # Gaengiges, nicht offiziell dokumentiertes Muster (u. a. All in One SEO nutzt es)
    return POST_INSPECTOR + "inspect/" + urllib.parse.quote(live_url, safe="")


def _letzte_messung(eintrag: dict | None) -> dict | None:
    ms = (eintrag or {}).get("messungen") or []
    return max(ms, key=lambda m: m.get("datum") or "") if ms else None


def _bewerte_alle(cfg: dict, quellen: dict) -> list[tuple[dict, bw.Bewertung]]:
    heute = date.today()
    erg = []
    for slug, meta in quellen.items():
        b = bw.bewerte(meta, _koerper_html(meta), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                       dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=heute, alle_slugs=list(quellen),
                       satz=None if meta.get("is_html") else satzmessung.gespeichert(ROOT, slug))
        erg.append((meta, b))
    return erg


def _inspector_status(slug: str, b: bw.Bewertung, inspector: dict) -> dict:
    e = inspector.get(slug)
    kopf = b.kennzahlen.get("kopf") or {}
    pf = kopf.get("pflicht", {}) if kopf else {}
    jetzt = vorschau_hash(pf.get("title/og:title") or "", pf.get("description/og:description") or "", pf.get("image/og:image") or "")
    if not e:
        return {"status": "offen", "text": "noch nicht geprüft", "hash": jetzt}
    if e.get("vorschau_hash") != jetzt:
        return {"status": "veraltet", "text": f"am {e['datum']} – Vorschau seither geändert", "datum": e["datum"], "hash": jetzt}
    return {"status": "ok", "text": f"ausgeführt am {e['datum']}", "datum": e["datum"], "hash": jetzt}


def _lektorat_mittel(lk: dict | None) -> float | None:
    if not lk or not lk.get("ergebnis"):
        return None
    noten = [v.get("note") for v in (lk["ergebnis"].get("kriterien") or {}).values() if isinstance(v, dict) and isinstance(v.get("note"), (int, float))]
    return round(sum(noten) / len(noten), 1) if noten else None


def _kennzahlen_text(b: bw.Bewertung) -> str:
    a = b.kennzahlen.get("amstad", {})
    return (f"Amstad-Index {a.get('index')}, Ø Satzlänge {a.get('asl')} Wörter, {b.kennzahlen.get('woerter')} Wörter, "
            f"visuelle Elemente {b.kennzahlen.get('visuell')}, größter Abstand ohne Grafik {b.kennzahlen.get('groesster_abstand')} Wörter, "
            f"regelbasierter Gesamtscore {b.gesamt}/100")


def bewerte_vorschlag(art: str, text: str) -> dict:
    n = len(text)
    if art == "titel":
        score = bw.band(n, 40, 70, 15, 110)
        soll = "40–70"
    elif art == "beschreibung":
        score = bw.band(n, 120, 160, 50, 260)
        soll = "120–160"
    else:
        score = bw.band(n, 60, 160, 10, 300)
        soll = "60–160"
    erg = {"text": text, "laenge": n, "soll": soll, "score": score, "ok": score >= 75}
    if art == "beschreibung":
        erg["haken"], erg["haken_grund"] = bw.haken_in(text)
        erg["ok"] = erg["ok"] and erg["haken"]
    return erg


# --------------------------------------------------------------------------
# Seiten
# --------------------------------------------------------------------------


def _gutachten_lesen(slug: str):
    g = speicher.lesen("gutachten", f"{slug}.json")
    if g:
        from markdown.extensions.toc import slugify
        import re as _re
        for b in g.get("befunde", []):
            m = _re.search(r"Abschnitt\s*[„\"](.+?)[“\"]", b.get("fundstelle") or "")
            b["link"] = slugify(m.group(1), "-") if m else ""
    return g


def _gutachten_lauf(slug: str):
    import gutachten as gt
    from in_ordnung_views import kontext
    return gt.zustand(kontext(), slug)


def _behebbar_ids(b: bw.Bewertung) -> list[str]:
    import ordnung_engine
    return ordnung_engine.behebbar(in_ordnung.schnappschuss(b), True)


def _ordnung_kurz(slug: str) -> dict | None:
    """Zustand des letzten „Alles in Ordnung bringen“-Durchlaufs fuer die Ranking-Tabelle."""
    z = speicher.lesen("inordnung", f"{slug}.json")
    if not z:
        return None
    erw = (z.get("erwartet") or {}).get("gesamt")
    return {"status": z.get("status"), "erwartet": erw, "warteplatz": z.get("warteplatz")}


@bp.route("/verwaltung/ranking/alle-durchgehen", methods=["POST"])
def alle_durchgehen():
    """Reiht fuer jeden Artikel mit behebbaren roten Kriterien einen Durchlauf ein (nur Vorschlaege, nichts wird geschrieben)."""
    _post_pruefen()
    from in_ordnung_views import kontext
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    ctx = kontext()
    eingereiht, uebersprungen = [], []
    for meta, b in _bewerte_alle(cfg, quellen):
        if meta.get("is_html") or not _behebbar_ids(b):
            continue
        ok, info = in_ordnung.starte(ctx, b.slug)
        (eingereiht if ok else uebersprungen).append(b.slug)
    text = f"{len(eingereiht)} Artikel in der Warteschlange (einer nach dem anderen, nur Vorschläge – nichts wird geschrieben)."
    if uebersprungen:
        text += f" {len(uebersprungen)} übersprungen (läuft schon oder LLM nicht verfügbar)."
    return redirect(url_for("ranking.uebersicht", meldung=text))


@bp.route("/verwaltung/ranking", methods=["GET"])
def uebersicht():
    _intern()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    versionen.abgleich_alle(ROOT, [s for s, m in quellen.items() if not m.get("is_html")])
    satzmessung.im_hintergrund(ROOT, [s for s, m in quellen.items() if not m.get("is_html")])
    alle = _bewerte_alle(cfg, quellen)
    inspector = speicher.inspector()
    lidaten = speicher.linkedin()
    schnitt = sum(b.gesamt for _m, b in alle) / len(alle) if alle else 0
    zeilen = []
    for meta, b in alle:
        letzte = _letzte_messung(lidaten["beitraege"].get(b.slug))
        upd = meta.get("updated") or meta.get("date")
        zeilen.append({
            "slug": b.slug,
            "titel": b.titel,
            "gesamt": b.gesamt,
            "ampel": b.ampel,
            "kat": {k: b.kategorie_score(k) for k in bw.KATEGORIEN},
            "woerter": b.kennzahlen.get("woerter", 0),
            "datum": str(meta.get("date", "")),
            "updated": str(upd or ""),
            "pflicht_ok": b.pflicht_ok(),
            "inspector": _inspector_status(b.slug, b, inspector),
            "wirkung": li.wirkung(letzte),
            "wirkung_datum": (letzte or {}).get("datum"),
            "live_url": _live_url(cfg, b.slug),
            "inspector_url": inspector_url(_live_url(cfg, b.slug)),
            "lektorat": _lektorat_mittel(speicher.lektorat(b.slug)),
            "auff": bw.auffaelligkeiten(b, schnitt),
            "live": live_inspector.letztes_ergebnis(b.slug),
            "ordnung": _ordnung_kurz(b.slug),
            "behebbar": bool(_behebbar_ids(b)),
        })
    zeilen.sort(key=lambda z: -z["gesamt"])
    for i, z in enumerate(zeilen, 1):
        z["rang"] = i
    return render_template("ranking.html", zeilen=zeilen, kategorien=bw.KATEGORIEN, kriterien=bw.KRITERIEN,
                           llm=llm.llm_status(), benchmark=li.BENCHMARK, profil=lidaten["profil"],
                           felder_profil=li.FELDER_PROFIL, meldung=request.args.get("meldung", ""),
                           heute=date.today().isoformat())


@bp.route("/verwaltung/ranking/<slug>", methods=["GET"])
def detail(slug):
    _intern()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    if not meta.get("is_html"):
        versionen.abgleich(ROOT, slug)
        satzmessung.im_hintergrund(ROOT, [slug])
    alle = dict((b.slug, (m, b)) for m, b in _bewerte_alle(cfg, quellen))
    b = alle[slug][1]
    rang = 1 + sum(1 for _m, x in alle.values() if x.gesamt > b.gesamt)
    schnitt = sum(x.gesamt for _m, x in alle.values()) / len(alle)
    vale = vale_pruefung.pruefe(ROOT, Path(meta["source"])) if meta.get("source") else {"verfuegbar": False, "befunde": []}
    vale_zaehler = sorted(Counter(f["regel"] for f in vale.get("befunde", [])).items(), key=lambda kv: -kv[1])
    lidaten = speicher.linkedin()
    eintrag = lidaten["beitraege"].get(slug, {})
    messungen = sorted(eintrag.get("messungen", []), key=lambda m: m.get("datum") or "", reverse=True)
    kopf = b.kennzahlen.get("kopf") or {}
    pf = kopf.get("pflicht", {}) if kopf else {}
    og_bild = b.kennzahlen.get("og_bild")
    metas = speicher.metas(slug)
    ma = None
    ma_bild_rel = ""
    if not meta.get("is_html"):
        ma = ma_mod.auswahl(ROOT, meta, _metas_normalisiert(metas), None)
        aktuell = next((x for x in ma["bilder"] if x["aktuell"]), None)
        ma_bild_rel = aktuell["rel"] if aktuell else ""
    sicherung = speicher.letzte_sicherung(Path(meta["source"])) if meta.get("source") and not meta.get("is_html") else None
    inordnung = {"offen": in_ordnung.offene_punkte(b), "ist_html": bool(meta.get("is_html"))}
    from in_ordnung_views import kurz_zustand
    inordnung["zustand"] = kurz_zustand(slug)
    return render_template(
        "ranking_detail.html",
        meta=meta, b=b, rang=rang, anzahl=len(alle), kategorien=bw.KATEGORIEN,
        live_url=_live_url(cfg, slug), inspector_url=inspector_url(_live_url(cfg, slug)),
        inspector=_inspector_status(slug, b, speicher.inspector()),
        karte={"titel": pf.get("title/og:title") or meta["title"], "beschreibung": pf.get("description/og:description") or meta["description"],
               "bild": og_bild, "domain": urllib.parse.urlparse(cfg["site"]["base_url"]).hostname},
        lektorat=speicher.lektorat(slug), lektorat_kriterien=llm.LEKTORAT_KRITERIEN, metas=metas,
        llm=llm.llm_status(), messungen=messungen, beitrag_url=eintrag.get("beitrag_url", ""),
        felder=li.FELDER_BEITRAG, wirkung=li.wirkung(messungen[0] if messungen else None), benchmark=li.BENCHMARK,
        meldung=request.args.get("meldung", ""), fehler=request.args.get("fehler", ""),
        heute=date.today().isoformat(), og_image_gesetzt=bool(meta.get("og_image")),
        auff=bw.auffaelligkeiten(b, schnitt), live=live_inspector.letztes_ergebnis(slug), vale=vale, vale_zaehler=vale_zaehler,
        ma=ma, ma_domain=urllib.parse.urlparse(cfg["site"]["base_url"]).hostname, ma_bild_rel=ma_bild_rel,
        sicherung=sicherung.name if sicherung else "", inordnung=inordnung,
        vz=versionen.alle(ROOT, slug) if not meta.get("is_html") else None,
        satz_gemessen=bool(b.kennzahlen.get("satz")), satz_laeuft=satzmessung.wird_gemessen(slug),
        satz_alle=satzmessung.uebersicht(ROOT, [x for x, m in quellen.items() if not m.get("is_html")]),
        ki_regeln=ki_muster.REGELN, ki_quelle=ki_muster.QUELLE, ki_messung=b.kennzahlen.get('ki_muster'),
        ki_funde=(ki_muster.funde(in_ordnung.finde_bloecke(Path(meta['source']).read_text(encoding='utf-8'))) if not meta.get('is_html') else []),
        kategorie_f=bw.KATEGORIE_F, gewichte=b.gewichte(),
        kategorien_alle=list({**bw.KATEGORIEN, **({'F': bw.KATEGORIE_F} if b.kennzahlen.get('satz') else {})}.items()), gutachten=_gutachten_lesen(slug), gutachten_lauf=_gutachten_lauf(slug),
    )


@bp.route("/verwaltung/ranking/ueberschneidung", methods=["GET"])
def ueberschneidung_api():
    """Nur lesend: Regel „Titel und Beschreibung in einem Guss“ fuer die gewaehlte Kombination (Live-Anzeige der Auswahl)."""
    _intern()
    import titel_beschreibung as tb
    titel = (request.args.get("titel") or "")[:400]
    erg = tb.ueberschneidung(titel, (request.args.get("beschreibung") or "")[:600])
    erg["titel_zeilen"] = ma_mod.titel_zeilen(titel)
    return jsonify(erg)


@bp.route("/verwaltung/ranking/bild/<path:pfad>", methods=["GET"])
def bild(pfad):
    """Vorschaubilder aus static/img fuer die Vorschau-Karte (nur dieser Ordner)."""
    _intern()
    return send_from_directory(ROOT / "static" / "img", pfad)


# --------------------------------------------------------------------------
# Aktionen
# --------------------------------------------------------------------------


@bp.route("/verwaltung/ranking/<slug>/inspector", methods=["POST"])
def inspector_setzen(slug):
    _post_pruefen()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    if request.form.get("aktion") == "zuruecksetzen":
        speicher.inspector_setzen(slug, None, "")
        return redirect(url_for("ranking.detail", slug=slug, meldung="Post-Inspector-Häkchen entfernt.") + "#postinspector")
    datum = request.form.get("datum") or date.today().isoformat()
    try:
        date.fromisoformat(datum)
    except ValueError:
        abort(400, "Ungültiges Datum")
    b = bw.bewerte(meta, _koerper_html(meta), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                   dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=date.today())
    speicher.inspector_setzen(slug, datum, _inspector_status(slug, b, {})["hash"])
    return redirect(url_for("ranking.detail", slug=slug, meldung=f"Post Inspector als ausgeführt am {datum} vermerkt.") + "#postinspector")


@bp.route("/verwaltung/ranking/<slug>/lektorat", methods=["POST"])
def lektorat(slug):
    _post_pruefen()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    koerper = _koerper_html(meta)
    b = bw.bewerte(meta, koerper, base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                   dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=date.today())
    try:
        ergebnis = llm.chat_json(llm.LEKTORAT_SYSTEM, llm.lektorat_prompt(meta, bw.lesetext(koerper, meta), _kennzahlen_text(b)), aufgabe="lektorat", timeout=300)
    except llm.LLMFehler as exc:
        return redirect(url_for("ranking.detail", slug=slug, fehler=f"Lektorat fehlgeschlagen: {exc}") + "#lektorat")
    speicher.lektorat_speichern(slug, {
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
        "modell": llm.modell_fuer("lektorat"),
        "text_hash": hashlib.sha256(meta["body_md"].encode()).hexdigest()[:16],
        "ergebnis": ergebnis,
    })
    return redirect(url_for("ranking.detail", slug=slug, meldung="Lektorat aktualisiert.") + "#lektorat")


def _metas_normalisiert(metas: dict | None) -> dict | None:
    """Alte Speicherform (vorschlaege: titel/beschreibung/og_image_alt) in die neue (felder: texte) uebersetzen."""
    if not metas:
        return None
    if "felder" in metas:
        return metas
    v = metas.get("vorschlaege") or {}
    return {"felder": {"title": {"texte": list(v.get("titel") or [])}, "description": {"texte": list(v.get("beschreibung") or [])},
                       "og_image_alt": {"texte": [v["og_image_alt"]] if v.get("og_image_alt") else []}},
            "abgewiesen": [], "nachgefragt": False}


@bp.route("/verwaltung/ranking/<slug>/metas", methods=["POST"])
def metas_erzeugen(slug):
    _post_pruefen()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    if meta.get("is_html"):
        abort(400, "HTML-Artikel haben kein Frontmatter")
    koerper = _koerper_html(meta)
    felder = {"title", "description", "og_image_alt"}
    try:
        erg = ma_mod.anfordern(llm.chat, meta, bw.lesetext(koerper, meta), felder)
    except llm.LLMFehler as exc:
        return redirect(url_for("ranking.detail", slug=slug, fehler=f"Meta-Vorschläge fehlgeschlagen: {exc}") + "#metas")
    speicher.metas_speichern(slug, {"zeitpunkt": datetime.now().isoformat(timespec="seconds"),
                                    "modell": erg.get("modell") or llm.modell_fuer("metas"), **erg})
    return redirect(url_for("ranking.detail", slug=slug, meldung="Neue Meta-Vorschläge erzeugt (Grenzen programmatisch geprüft)." + (" Einmal mit Rückmeldung nachgefragt." if erg["nachgefragt"] else "")) + "#metas")


def _gewaehlte_felder(meta: dict) -> dict[str, str]:
    """Kombinationsmodus (kombi=1, Auswahl-Seite): jedes Feld, das vom aktuellen Wert abweicht, zaehlt als gewaehlt.
    Alter Modus: nur Felder mit gesetztem Haken uebernehmen_<feld>."""
    kombi = request.form.get("kombi") == "1"
    felder = {}
    for f in ERLAUBTE_FELDER:
        if kombi or request.form.get(f"uebernehmen_{f}"):
            wert = " ".join((request.form.get(f) or "").split())
            if not wert:
                if kombi:
                    continue
                abort(400, f"{f}: leerer Wert")
            if len(wert) > 400:
                abort(400, f"{f}: zu lang")
            if f == "og_image":
                if wert != str(meta.get(f) or ""):
                    grund = in_ordnung._pruefe_bild(ROOT, wert)
                    if grund:
                        abort(400, f"og_image: {grund}")
                    felder[f] = wert
                continue
            grund = ma_mod.pruefe_wert_hart(f, wert)
            if grund:
                abort(400, f"{f}: {grund}")
            if wert != str(meta.get(f) or ""):
                felder[f] = wert
    return felder


def _bewertet(feld: str, wert: str, meta: dict) -> dict:
    if feld == "og_image":
        masse = bw.bildmasse(ROOT / wert.lstrip("/"))
        gut = bool(masse and masse[0] >= 1200 and abs(masse[0] / masse[1] - 1.91) <= 0.08)
        return {"laenge": len(wert), "soll": "≥ 1200 px, ≈ 1,91:1", "ampel": "gruen" if gut else "gelb", "ok": gut,
                "info": f"{masse[0]}×{masse[1]} px" if masse else "Maße unbekannt"}
    lo, hi = ma_mod.META_GRENZEN[feld]
    erg = {"laenge": len(wert), "soll": f"{lo}–{hi}", "ampel": ma_mod.grenze_ampel(feld, len(wert)), "info": ""}
    erg["ok"] = erg["ampel"] == "gruen"
    if feld == "description":
        erg["haken"], erg["haken_grund"] = bw.haken_in(wert[:ma_mod.HAKEN_ZEICHEN])
        erg["ok"] = erg["ok"] and erg["haken"]
    return erg


@bp.route("/verwaltung/ranking/<slug>/metas/pruefen", methods=["POST"])
def metas_pruefen(slug):
    """Schritt 1 von 2: zeigt den Diff, schreibt NICHTS."""
    _post_pruefen()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    if meta.get("is_html"):
        abort(400, "HTML-Artikel haben kein Frontmatter")
    felder = _gewaehlte_felder(meta)
    if not felder:
        return redirect(url_for("ranking.detail", slug=slug, fehler="Nichts ausgewählt oder keine Änderung.") + "#metas")
    quelle = Path(meta["source"])
    alt = quelle.read_text(encoding="utf-8")
    try:
        neu = setze_felder(alt, felder)
    except FrontmatterFehler as exc:
        return redirect(url_for("ranking.detail", slug=slug, fehler=str(exc)) + "#metas")
    diff = list(difflib.unified_diff(alt.splitlines(), neu.splitlines(), f"articles/{quelle.name} (bisher)",
                                     f"articles/{quelle.name} (neu)", lineterm="", n=1))
    return render_template("ranking_bestaetigen.html", slug=slug, meta=meta, felder=felder, diff=diff,
                           bewertet={k: _bewertet(k, v, meta) for k, v in felder.items()}, kombi=request.form.get("kombi") == "1",
                           datei_hash=hashlib.sha256(alt.encode()).hexdigest(), og_image_gesetzt=bool(meta.get("og_image")))


@bp.route("/verwaltung/ranking/<slug>/metas/uebernehmen", methods=["POST"])
def metas_uebernehmen(slug):
    """Schritt 2 von 2: nach Bestaetigung Backup + Frontmatter schreiben. Kein Build, kein Commit."""
    _post_pruefen()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("ranking.detail", slug=slug, fehler="Nicht bestätigt – nichts geändert.") + "#metas")
    felder = _gewaehlte_felder(meta)
    quelle = Path(meta["source"])
    alt = quelle.read_text(encoding="utf-8")
    if hashlib.sha256(alt.encode()).hexdigest() != request.form.get("datei_hash"):
        return redirect(url_for("ranking.detail", slug=slug, fehler="Artikel wurde inzwischen geändert – bitte erneut prüfen.") + "#metas")
    try:
        neu = setze_felder(alt, felder)
    except FrontmatterFehler as exc:
        return redirect(url_for("ranking.detail", slug=slug, fehler=str(exc)) + "#metas")
    if not in_ordnung.sperre_nehmen(slug):
        return redirect(url_for("ranking.detail", slug=slug, fehler="Für diesen Artikel läuft gerade ein Auftrag.") + "#metas")
    try:
        versionen.vor_schreiben(ROOT, slug)
        sicherung = speicher.artikel_sichern(quelle)
        quelle.write_text(neu, encoding="utf-8")
        versionen.nach_schreiben(ROOT, slug, "metas", ", ".join(felder))
    finally:
        in_ordnung.sperre_freigeben(slug)
    namen = ", ".join(felder)
    return redirect(url_for("ranking.detail", slug=slug, meldung=(
        f"Übernommen ({namen}). Backup: {sicherung.relative_to(ROOT)}. "
        "Nicht gebaut, nicht committet, nicht veröffentlicht. Nächste Schritte: bauen und deployen, "
        "dann im LinkedIn Post Inspector prüfen.")) + "#metas")


@bp.route("/verwaltung/ranking/<slug>/metas/rueckgaengig", methods=["POST"])
def metas_rueckgaengig(slug):
    """Stellt die letzte Sicherung des Artikels wieder her (vorher wird der jetzige Stand gesichert). Kein Build."""
    _post_pruefen()
    cfg = load_config()
    meta = _slug_oder_404(slug, artikel_quellen(cfg))
    if meta.get("is_html"):
        abort(400, "HTML-Artikel haben kein Frontmatter")
    if request.form.get("bestaetigt") != "ja":
        return redirect(url_for("ranking.detail", slug=slug, fehler="Nicht bestätigt – nichts geändert.") + "#metas")
    if not in_ordnung.sperre_nehmen(slug):
        return redirect(url_for("ranking.detail", slug=slug, fehler="Für diesen Artikel läuft gerade ein Auftrag.") + "#metas")
    try:
        quelle = Path(meta["source"])
        sicherung = speicher.letzte_sicherung(quelle)
        if not sicherung:
            return redirect(url_for("ranking.detail", slug=slug, fehler="Keine Sicherung gefunden.") + "#metas")
        inhalt = sicherung.read_bytes()
        versionen.vor_schreiben(ROOT, slug)
        aktuell = speicher.artikel_sichern(quelle)
        quelle.write_bytes(inhalt)
        versionen.nach_schreiben(ROOT, slug, "rueckgaengig", "Metas")
    finally:
        in_ordnung.sperre_freigeben(slug)
    return redirect(url_for("ranking.detail", slug=slug, meldung=(
        f"Rückgängig: {sicherung.name} zurückgespielt (der vorherige Stand liegt unter {aktuell.relative_to(ROOT)}). "
        "Nicht gebaut, nicht committet, nicht veröffentlicht.")) + "#metas")


@bp.route("/verwaltung/ranking/<slug>/linkedin", methods=["POST"])
def linkedin_erfassen(slug):
    _post_pruefen()
    cfg = load_config()
    _slug_oder_404(slug, artikel_quellen(cfg))
    d = speicher.linkedin()
    eintrag = d["beitraege"].setdefault(slug, {"beitrag_url": "", "messungen": []})
    url = (request.form.get("beitrag_url") or "").strip()
    if url and not url.startswith("https://www.linkedin.com/"):
        return redirect(url_for("ranking.detail", slug=slug, fehler="Beitrags-Link muss mit https://www.linkedin.com/ beginnen.") + "#linkedin")
    if url:
        eintrag["beitrag_url"] = url
    roh = {k: request.form.get(k, "") for k in li.FELDER_BEITRAG}
    if any(str(v).strip() for v in roh.values()):
        datum = li.datum(request.form.get("datum")) or date.today().isoformat()
        m = li._als_messung({**roh, "datum": datum})
        for k, v in m.items():
            if isinstance(v, (int, float)) and (v < 0 or v > 10**9):
                return redirect(url_for("ranking.detail", slug=slug, fehler=f"Unplausibler Wert für {k}.") + "#linkedin")
        m["quelle"] = "manuell"
        eintrag["messungen"].append(m)
    speicher.linkedin_speichern(d)
    return redirect(url_for("ranking.detail", slug=slug, meldung="LinkedIn-Angaben gespeichert (nur lokal).") + "#linkedin")


@bp.route("/verwaltung/ranking/<slug>/linkedin/loeschen", methods=["POST"])
def linkedin_loeschen(slug):
    _post_pruefen()
    _slug_oder_404(slug, artikel_quellen(load_config()))
    d = speicher.linkedin()
    ms = d["beitraege"].get(slug, {}).get("messungen", [])
    ziel = request.form.get("schluessel", "")
    neu = [m for m in ms if f"{m.get('datum')}|{m.get('quelle')}|{m.get('impressions')}" != ziel]
    if len(neu) == len(ms):
        abort(400, "Messung nicht gefunden")
    d["beitraege"][slug]["messungen"] = neu
    speicher.linkedin_speichern(d)
    return redirect(url_for("ranking.detail", slug=slug, meldung="Messung gelöscht.") + "#linkedin")


@bp.route("/verwaltung/ranking/profil", methods=["POST"])
def profil_erfassen():
    _post_pruefen()
    d = speicher.linkedin()
    roh = {k: request.form.get(k, "") for k in li.FELDER_PROFIL}
    m = {k: int(z) for k, v in roh.items() if (z := li.zahl(v)) is not None and 0 <= z <= 10**9}
    if m:
        m["datum"] = li.datum(request.form.get("datum")) or date.today().isoformat()
        m["quelle"] = "manuell"
        d["profil"].append(m)
        speicher.linkedin_speichern(d)
    return redirect(url_for("ranking.uebersicht", meldung="Profil-Übersicht gespeichert (nur lokal)." if m else "Keine Werte eingegeben.") + "#profil")


@bp.route("/verwaltung/ranking/linkedin/import", methods=["POST"])
def linkedin_import():
    _post_pruefen()
    if request.content_length and request.content_length > MAX_UPLOAD + 10000:
        abort(413)
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    datei = request.files.get("datei")
    ziel_slug = request.form.get("slug") or ""
    if ziel_slug and ziel_slug not in quellen:
        abort(400, "Unbekannter Artikel")
    if not datei or not datei.filename:
        return redirect(url_for("ranking.uebersicht", meldung="Keine Datei ausgewählt.") + "#import")
    daten = datei.read(MAX_UPLOAD + 1)
    if len(daten) > MAX_UPLOAD:
        abort(413)
    try:
        ergebnis = li.auswerten(li.lies_datei(datei.filename, daten))
    except Exception as exc:  # defekte Datei: verstaendlich melden statt 500
        return render_template("ranking_import.html", fehler=f"Datei nicht lesbar: {type(exc).__name__}: {exc}",
                               zugeordnet=[], offen=[], profil=None, hinweise=[])
    d = speicher.linkedin()
    # Zuordnung Beitrags-ID -> Slug aus den hinterlegten Beitrags-Links
    id_zu_slug = {li.beitrags_id(e.get("beitrag_url")): s for s, e in d["beitraege"].items() if li.beitrags_id(e.get("beitrag_url"))}
    zugeordnet, offen = [], []
    einzel = len(ergebnis["messungen"]) == 1
    for m in ergebnis["messungen"]:
        slug = None
        s_roh = str(m.pop("slug", "") or "")
        if s_roh:
            kandidat = s_roh.rstrip("/").split("/artikel/")[-1].strip("/")
            slug = kandidat if kandidat in quellen else None
        if not slug:
            slug = id_zu_slug.get(li.beitrags_id(m.get("beitrag_url")))
        if not slug and ziel_slug and einzel:
            slug = ziel_slug
        if not slug:
            offen.append(m)
            continue
        m.setdefault("datum", date.today().isoformat())
        eintrag = d["beitraege"].setdefault(slug, {"beitrag_url": "", "messungen": []})
        if m.get("beitrag_url") and not eintrag.get("beitrag_url"):
            eintrag["beitrag_url"] = m["beitrag_url"]
        m.pop("beitrag_url", None)
        # gleiche Messung (Datum + Quelle) ersetzen statt doppeln
        eintrag["messungen"] = [x for x in eintrag["messungen"] if not (x.get("datum") == m["datum"] and x.get("quelle") == m["quelle"])]
        eintrag["messungen"].append(m)
        zugeordnet.append((slug, m))
    if ergebnis["profil"]:
        p = {**ergebnis["profil"], "datum": date.today().isoformat(), "quelle": "Import"}
        d["profil"].append(p)
    speicher.linkedin_speichern(d)
    return render_template("ranking_import.html", fehler="", zugeordnet=zugeordnet, offen=offen,
                           profil=ergebnis["profil"], hinweise=ergebnis["hinweise"])
