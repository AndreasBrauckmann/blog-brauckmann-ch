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

from flask import Blueprint, abort, redirect, render_template, request, send_from_directory, url_for

import bewertung as bw
import linkedin_import as li
import llm
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
                       dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=heute, alle_slugs=list(quellen))
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


@bp.route("/verwaltung/ranking", methods=["GET"])
def uebersicht():
    _intern()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
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
    if metas and metas.get("vorschlaege"):
        v = metas["vorschlaege"]
        metas["bewertet"] = {
            "titel": [bewerte_vorschlag("titel", t) for t in v.get("titel", [])],
            "beschreibung": [bewerte_vorschlag("beschreibung", t) for t in v.get("beschreibung", [])],
            "og_image_alt": [bewerte_vorschlag("alt", v["og_image_alt"])] if v.get("og_image_alt") else [],
        }
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
    )


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
        return redirect(url_for("ranking.detail", slug=slug, meldung="Post-Inspector-Häkchen entfernt.") + "#vorschau")
    datum = request.form.get("datum") or date.today().isoformat()
    try:
        date.fromisoformat(datum)
    except ValueError:
        abort(400, "Ungültiges Datum")
    b = bw.bewerte(meta, _koerper_html(meta), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                   dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=date.today())
    speicher.inspector_setzen(slug, datum, _inspector_status(slug, b, {})["hash"])
    return redirect(url_for("ranking.detail", slug=slug, meldung=f"Post Inspector als ausgeführt am {datum} vermerkt.") + "#vorschau")


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
        antwort = llm.chat(llm.LEKTORAT_SYSTEM, llm.lektorat_prompt(meta, bw.lesetext(koerper, meta), _kennzahlen_text(b)))
        ergebnis = llm.json_aus_text(antwort)
    except llm.LLMFehler as exc:
        return redirect(url_for("ranking.detail", slug=slug, fehler=f"Lektorat fehlgeschlagen: {exc}") + "#lektorat")
    speicher.lektorat_speichern(slug, {
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
        "modell": llm.llm_status()["modell"],
        "text_hash": hashlib.sha256(meta["body_md"].encode()).hexdigest()[:16],
        "ergebnis": ergebnis,
    })
    return redirect(url_for("ranking.detail", slug=slug, meldung="Lektorat aktualisiert.") + "#lektorat")


@bp.route("/verwaltung/ranking/<slug>/metas", methods=["POST"])
def metas_erzeugen(slug):
    _post_pruefen()
    cfg = load_config()
    quellen = artikel_quellen(cfg)
    meta = _slug_oder_404(slug, quellen)
    koerper = _koerper_html(meta)
    try:
        antwort = llm.chat(llm.METAS_SYSTEM, llm.metas_prompt(meta, bw.lesetext(koerper, meta), str(meta.get("og_image_alt") or "")), max_tokens=1500)
        v = llm.json_aus_text(antwort)
    except llm.LLMFehler as exc:
        return redirect(url_for("ranking.detail", slug=slug, fehler=f"Meta-Vorschläge fehlgeschlagen: {exc}") + "#metas")
    vorschlaege = {
        "titel": [str(t).strip() for t in (v.get("titel") or [])][:3],
        "beschreibung": [str(t).strip() for t in (v.get("beschreibung") or [])][:3],
        "og_image_alt": str(v.get("og_image_alt") or "").strip(),
    }
    speicher.metas_speichern(slug, {"zeitpunkt": datetime.now().isoformat(timespec="seconds"),
                                    "modell": llm.llm_status()["modell"], "vorschlaege": vorschlaege})
    return redirect(url_for("ranking.detail", slug=slug, meldung="Neue Meta-Vorschläge erzeugt.") + "#metas")


def _gewaehlte_felder(meta: dict) -> dict[str, str]:
    felder = {}
    for f in ERLAUBTE_FELDER:
        if request.form.get(f"uebernehmen_{f}"):
            wert = (request.form.get(f) or "").strip()
            if not wert:
                abort(400, f"{f}: leerer Wert")
            if len(wert) > 400:
                abort(400, f"{f}: zu lang")
            if wert != str(meta.get(f) or ""):
                felder[f] = wert
    return felder


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
                           bewertet={k: bewerte_vorschlag({"title": "titel", "description": "beschreibung"}.get(k, "alt"), v) for k, v in felder.items()},
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
    sicherung = speicher.artikel_sichern(quelle)
    quelle.write_text(neu, encoding="utf-8")
    namen = ", ".join(felder)
    return redirect(url_for("ranking.detail", slug=slug, meldung=(
        f"Übernommen ({namen}). Backup: {sicherung.relative_to(ROOT)}. "
        "Nicht gebaut, nicht committet, nicht veröffentlicht. Nächste Schritte: bauen und deployen, "
        "dann im LinkedIn Post Inspector prüfen.")) + "#metas")


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
