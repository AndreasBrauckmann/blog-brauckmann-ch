"""Plattformseiten /verwaltung/plattform/<name>.

Logik: plattformen.py (Vorschau, Kuerzung, Eignung), kennzahlen.py (Zaehler, manuelle
Kennzahlen). Laufzeitdaten unter data/plattformen/ und data/kennzahlen/ (in .gitignore).

Sicherheit wie der Rest der Verwaltung: require_intern() in jeder Route, bei POST
zusaetzlich Formular-Token (csrf) und Ursprungspruefung (gemeinsam.post_pruefen()).
Plattformnamen nur aus gemeinsam.PLATTFORMEN, Slugs nur aus der Artikelliste.
Es wird nichts gebaut, committet oder veroeffentlicht - ausser ueber den Knopf
„jetzt posten“, der die bestehende Route /verwaltung/publish aufruft.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from datetime import date, datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for

import bewertung as bw
import gemeinsam
import kennzahlen as kz
import linkedin_import as li
import llm
import plattformen as pl
from build import ROOT, load_config
from gemeinsam import speicher
from ranking_daten import vorschau_hash

try:  # wird vom Hauptagenten parallel gebaut
    import inspector  # type: ignore
except Exception:  # noqa: BLE001
    inspector = None

bp = Blueprint("plattform", __name__, template_folder="templates")

ablage = pl.Ablage(ROOT)
kennz = kz.KennzahlenSpeicher(ROOT)


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------


def _name_pruefen(name: str) -> None:
    if name not in gemeinsam.PLATTFORMEN or name not in pl.PLATTFORM_DEF:
        abort(404)


def _sperre_pruefen(name: str, slug: str, cfg: dict, quellen: dict) -> None:
    """Gesperrte Artikel duerfen auch per Direktaufruf nicht bearbeitet, gepostet oder analysiert werden."""
    if name == "microsoft_tech_community" and slug in quellen:
        grund = pl.ms_sperre(quellen[slug], cfg)
        if grund:
            abort(403, grund)


def _slug_pruefen(slug: str, quellen: dict) -> dict:
    if slug not in quellen:
        abort(400, "Unbekannter Artikel")
    return quellen[slug]


def _zurueck(name: str, slug: str, anker: str = "", **kw):
    return redirect(url_for("plattform.seite", name=name, slug=slug, **kw) + (f"#{anker}" if anker else ""))


def _bewertungen(cfg: dict, quellen: dict) -> dict[str, bw.Bewertung]:
    heute = date.today()
    return {slug: bw.bewerte(meta, gemeinsam.koerper_html(meta), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                             dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=heute, alle_slugs=list(quellen))
            for slug, meta in quellen.items()}


def _fmt_datum(s: str | None) -> str:
    return gemeinsam.kurz_datum(s) if s else ""


def _gepostet(name: str, slug: str, log: dict, li_daten: dict | None = None) -> dict | None:
    """{"datum", "url", "quelle"} oder None."""
    pc = pl.PLATTFORM_DEF[name]
    if not pc["manuell"]:
        e = log.get((slug, pc["kanal"]))
        if e:
            return {"datum": e["datum"], "uhrzeit": e["uhrzeit"], "url": e["url"], "quelle": "publish-log.md", "hinweis": e["hinweis"], "anzahl": e["anzahl"]}
        return None
    e = ablage.posts(name).get(slug)
    if e:
        return {"datum": e.get("datum", ""), "uhrzeit": "", "url": e.get("url", ""), "quelle": "manuell erfasst", "hinweis": "", "anzahl": 1}
    if name == "linkedin":
        url = ((li_daten or speicher.linkedin())["beitraege"].get(slug) or {}).get("beitrag_url")
        if url:
            return {"datum": "", "uhrzeit": "", "url": url, "quelle": "LinkedIn-Erfassung", "hinweis": "", "anzahl": 1}
    return None


def _auto_url(name: str, log: dict) -> dict[str, str]:
    kanal = pl.PLATTFORM_DEF[name]["kanal"]
    return {s: e["url"] for (s, k), e in log.items() if k == kanal}


def _inspector_li(slug: str, ctx: dict) -> dict:
    """Stand des Post-Inspector-Haekchens (gemeinsam mit dem Ranking in data/ranking/inspector.json)."""
    pf = ctx["pflicht"]
    jetzt = vorschau_hash(pf.get("title/og:title") or "", pf.get("description/og:description") or "", pf.get("image/og:image") or "")
    e = speicher.inspector().get(slug)
    if not e:
        return {"status": "offen", "datum": None, "hash": jetzt}
    if e.get("vorschau_hash") != jetzt:
        return {"status": "veraltet", "datum": e["datum"], "hash": jetzt}
    return {"status": "ok", "datum": e["datum"], "hash": jetzt}


def _auto_hinweise(name: str, ctx: dict, z: dict, text: str) -> dict[str, str]:
    """Pruefpunkte, die sich selbst feststellen lassen: Punkt -> Hinweistext."""
    h: dict[str, str] = {}
    if name == "mastodon":
        h["fedi"] = "automatisch: " + ("vorhanden" if ctx["fedi"] else ("fehlt" if ctx["fedi"] is False else "nicht prüfbar (kein dist/)"))
        h["laenge"] = f"automatisch: {z['n']} Zeichen"
    if name == "bluesky":
        im = ctx["image"]
        h["thumb"] = "automatisch: " + (f"{im['kb']} KB" if im["vorhanden"] else "kein Bild (image fehlt)")
        h["laenge"] = f"automatisch: {z['n']} Grapheme"
    if name == "linkedin":
        h["kurz"] = f"automatisch: {len(text)} Zeichen"
    if name == "facebook":
        h["masse"] = "automatisch: " + {True: "og:image:width/height gesetzt", False: "og:image:width/height fehlen", None: "nicht prüfbar"}[ctx["bild_masse_tags"]]
    if name == "microsoft_tech_community":
        import re
        h["kein_link"] = "automatisch: " + ("Text enthält einen Link" if re.search(r"https?://", text) else "kein Link im Text")
    return h


# --------------------------------------------------------------------------
# Seite
# --------------------------------------------------------------------------


@bp.route("/verwaltung/plattform/<name>", methods=["GET"])
def seite(name):
    gemeinsam.require_intern()
    _name_pruefen(name)
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    auswahl = gemeinsam.artikel_auswahl(quellen)
    slug = gemeinsam.gewaehlter_slug(quellen)
    if not slug:
        return render_template("plattform.html", name=name, keine_artikel=True, slug=None, auswahl=[], seite=name)
    pc = pl.PLATTFORM_DEF[name]
    sperren = {s_: pl.ms_sperre(m_, cfg) for s_, m_ in quellen.items()} if name == "microsoft_tech_community" else {}
    for a_ in auswahl:
        if sperren.get(a_["slug"]):
            a_["kurz"] = a_["kurz"] + "  (gesperrt)"
    fmt = None
    if name == "linkedin":
        fmt = request.args.get("format")
        if fmt not in ("kurz", "lang"):
            fmt = cfg["channels"]["linkedin"].get("format", "kurz")

    bew = _bewertungen(cfg, quellen)
    ctxs = {s: pl.kontext(ROOT, m, bew[s], cfg) for s, m in quellen.items()}
    ctx = ctxs[slug]
    meta = quellen[slug]

    alle_texte = pl.texte(meta, cfg, fmt)
    t = alle_texte[name]
    text, titel = t["text"], t["titel"]
    z = pl.zaehlung(name, text, cfg, fmt or "kurz")
    zt = pl.zaehlung("reddit", titel, cfg)["n"] if titel else None
    schnitt = z["schnitt"]
    ok_teil = text[:schnitt] if schnitt is not None else text
    rest = text[schnitt:] if schnitt is not None else ""

    bild = ctx["image"] if name == "bluesky" else ctx["og"]
    bild_url = url_for("ranking.bild", pfad=bild["rel"]) if bild["vorhanden"] and bild["rel"] else None

    ev = pl.eignung(name, ctx, text, titel, cfg, fmt or "kurz")
    log = pl.gepostet_aus_log(ROOT)
    li_daten = speicher.linkedin()
    gepostet = _gepostet(name, slug, log, li_daten)

    # Pruefliste
    gespeichert = ablage.pruefliste(name, slug)
    insp_li = _inspector_li(slug, ctx) if name == "linkedin" else None
    auto = _auto_hinweise(name, ctx, z, text)
    punkte = []
    for pid, ptext, link in pc["pruefliste"]:
        datum = gespeichert.get(pid)
        extra = auto.get(pid, "")
        if pid == "inspector" and insp_li:
            datum = insp_li["datum"] if insp_li["status"] in ("ok", "veraltet") else None
            if insp_li["status"] == "veraltet":
                extra = "Vorschau seit dem Lauf geändert – bitte erneut ausführen"
        punkte.append({"id": pid, "text": ptext, "link": link, "datum": datum, "extra": extra,
                       "veraltet": bool(pid == "inspector" and insp_li and insp_li["status"] == "veraltet")})

    # Inspector (Ergebnis der Live-Pruefung, falls vorhanden)
    insp_erg = None
    insp_url = pl.POST_INSPECTOR
    if inspector is not None:
        try:
            insp_erg = inspector.letztes_ergebnis(slug)
            insp_url = inspector.post_inspector_url(ctx["live_url"])
        except Exception:  # noqa: BLE001 - Seite darf nie am Inspector scheitern
            insp_erg = None

    # Kennzahlen
    felder = li.FELDER_BEITRAG if name == "linkedin" else kz.FELDER.get(name, {})
    ks_auto = kennz.zaehler(name) if name in kz.ZAEHLER_ANZEIGE else None
    manuell = kennz.manuell(name).get(slug) if name not in kz.ZAEHLER_ANZEIGE and name != "linkedin" else None
    li_messungen = []
    if name == "linkedin":
        eintrag = li_daten["beitraege"].get(slug, {})
        li_messungen = [{"m": m, "w": li.wirkung(m)} for m in sorted(eintrag.get("messungen", []), key=lambda m: m.get("datum") or "", reverse=True)]

    # Ranking aller Artikel fuer diese Plattform
    zeilen = []
    for s, m in quellen.items():
        tt = alle_texte if s == slug else pl.texte(m, cfg, fmt)
        e = pl.eignung(name, ctxs[s], tt[name]["text"], tt[name]["titel"], cfg, fmt or "kurz")
        g = _gepostet(name, s, log, li_daten)
        w = kz.wirkung_text(name, s, kennz, li_daten)
        zeilen.append({"slug": s, "titel": str(m.get("title", s)), "datum": str(m.get("date", "")), "score": e["score"], "ampel": e["ampel"],
                       "woerter": ctxs[s]["woerter"], "gepostet": g, "wirkung": w,
                       "gesperrt": sperren.get(s)})
    zeilen.sort(key=lambda r: -r["score"])
    for i, r in enumerate(zeilen, 1):
        r["rang"] = i

    seiten_url = request.full_path.rstrip("?")
    return render_template(
        "plattform.html", seite=name, name=name, plattform=gemeinsam.PLATTFORM_NAMEN[name], pc=pc, keine_artikel=False,
        auswahl=auswahl, slug=slug, meta=meta, ctx=ctx, cfg_ch=cfg["channels"].get(name, {}),
        text=text, titel=titel, ok_teil=ok_teil, rest=rest, z=z, zt=zt, fmt=fmt, bild=bild, bild_url=bild_url,
        kartentyp=bild["kartentyp"], kartentext=pl.KARTENTYP_TEXT[bild["kartentyp"]],
        kachel=pl.linkedin_kachel(text, True) if name == "linkedin" else None,
        eignung=ev, vorschlaege=pl.vorschlaege(name, ctx, text, titel, cfg, fmt or "kurz"),
        analyse=_analyse_anzeige(name, slug, cfg, fmt), punkte=punkte, gepostet=gepostet,
        token=pl.token_status(name), log_eintrag=log.get((slug, pc["kanal"])),
        inspector=inspector is not None, insp_erg=insp_erg, insp_url=insp_url, insp_li=insp_li, zurueck=seiten_url,
        felder=felder, ks_auto=ks_auto, ks_anzeige=kz.ZAEHLER_ANZEIGE.get(name), keine_views=kz.KEINE_VIEWS,
        manuell=manuell, li_messungen=li_messungen, felder_profil=li.FELDER_PROFIL,
        li_url=(li_daten["beitraege"].get(slug) or {}).get("beitrag_url", "") if name == "linkedin" else "",
        sperre=sperren.get(slug), zeilen=zeilen, formel=dict(g=pl.GEWICHT_GESAMT, a=pl.GEWICHT_META, p=pl.GEWICHT_PLATTFORM, ms=pl.MS_DECKEL),
        heute=date.today().isoformat(), meldung=request.args.get("meldung", ""), fehler=request.args.get("fehler", ""),
        llm=llm.llm_status(), fmt_namen={"kurz": "Kurz mit Karte (Standard)", "lang": "Lang"},
        prozent=kz.PROZENT_FELDER, kn_fmt=_fmt_datum,
    )


def _analyse_anzeige(name: str, slug: str, cfg: dict, fmt: str | None) -> dict | None:
    a = pl.Ablage(ROOT).analyse(name, slug)
    if not a or not a.get("ergebnis"):
        return None
    e = a["ergebnis"]
    return {"zeitpunkt": a.get("zeitpunkt", ""), "modell": a.get("modell", ""), "e": e,
            "z": pl.zaehlung(name, e.get("text", ""), cfg, fmt or "kurz"),
            "zt": len(e.get("titel", "")) if e.get("titel") else None}


# --------------------------------------------------------------------------
# Aktionen
# --------------------------------------------------------------------------


@bp.route("/verwaltung/plattform/<name>/pruefliste", methods=["POST"])
def pruefliste_speichern(name):
    gemeinsam.post_pruefen()
    _name_pruefen(name)
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    slug = request.form.get("slug", "")
    meta = _slug_pruefen(slug, quellen)
    _sperre_pruefen(name, slug, load_config(), quellen)
    heute = date.today().isoformat()
    angekreuzt = request.form.getlist("punkt")
    neu = pl.pruefliste_auswerten(name, ablage.pruefliste(name, slug), angekreuzt, heute)
    if name == "linkedin":
        # Post-Inspector-Haekchen mit dem Ranking synchron halten (data/ranking/inspector.json)
        bew = bw.bewerte(meta, gemeinsam.koerper_html(meta), base_url=cfg["site"]["base_url"], static_dir=ROOT / "static",
                         dist_dir=ROOT / cfg["paths"]["dist_dir"], heute=date.today())
        ctx = pl.kontext(ROOT, meta, bew, cfg)
        st = _inspector_li(slug, ctx)
        if "inspector" in neu:
            if st["status"] != "ok":
                speicher.inspector_setzen(slug, heute, st["hash"])
            else:
                neu["inspector"] = st["datum"]
        else:
            if st["status"] != "offen":
                speicher.inspector_setzen(slug, None, "")
    ablage.pruefliste_setzen(name, slug, neu)
    return _zurueck(name, slug, "pruefliste", meldung="Prüfliste gespeichert.")


@bp.route("/verwaltung/plattform/<name>/gepostet", methods=["POST"])
def gepostet_markieren(name):
    gemeinsam.post_pruefen()
    _name_pruefen(name)
    if not pl.PLATTFORM_DEF[name]["manuell"]:
        abort(400, "Für diese Plattform wird aus publish-log.md gelesen.")
    quellen = gemeinsam.artikel_quellen(load_config())
    slug = request.form.get("slug", "")
    _slug_pruefen(slug, quellen)
    _sperre_pruefen(name, slug, load_config(), quellen)
    if request.form.get("aktion") == "zuruecksetzen":
        ablage.post_setzen(name, slug, None)
        return _zurueck(name, slug, "gepostet", meldung="Markierung entfernt.")
    datum = request.form.get("datum") or date.today().isoformat()
    try:
        date.fromisoformat(datum)
    except ValueError:
        abort(400, "Ungültiges Datum")
    url = (request.form.get("url") or "").strip()
    if url and not url.startswith("https://"):
        return _zurueck(name, slug, "gepostet", fehler="Beitrags-URL muss mit https:// beginnen.")
    ablage.post_setzen(name, slug, {"datum": datum, "url": url})
    if name == "linkedin" and url.startswith("https://www.linkedin.com/"):
        d = speicher.linkedin()
        d["beitraege"].setdefault(slug, {"beitrag_url": "", "messungen": []})["beitrag_url"] = url
        speicher.linkedin_speichern(d)
    return _zurueck(name, slug, "gepostet", meldung=f"Als gepostet markiert ({datum}).")


@bp.route("/verwaltung/plattform/<name>/analyse", methods=["POST"])
def analyse(name):
    gemeinsam.post_pruefen()
    _name_pruefen(name)
    cfg = load_config()
    quellen = gemeinsam.artikel_quellen(cfg)
    slug = request.form.get("slug", "")
    meta = _slug_pruefen(slug, quellen)
    _sperre_pruefen(name, slug, load_config(), quellen)
    fmt = request.form.get("format") if request.form.get("format") in ("kurz", "lang") else None
    pc = pl.PLATTFORM_DEF[name]
    pname = gemeinsam.PLATTFORM_NAMEN[name]
    regeln = "\n".join(f"- {r[1]}" for r in pc["regeln"])
    limit = {"mastodon": "höchstens 480 Zeichen, jeder Link zählt 23", "bluesky": "höchstens 290 Grapheme (hartes Limit 300, 3000 Bytes)",
             "linkedin": ("1200–1800 Zeichen (Langform)" if fmt == "lang" else "150–300 Zeichen, damit die Link-Karte sichtbar bleibt; erste ~140 Zeichen tragen den Haken"),
             "reddit": "Titel höchstens 300 Zeichen; Text als Markdown", "facebook": "kurzer Text, Link-Karte kommt aus den og:-Tags",
             "youtube_community": "höchstens 1000 Zeichen (Annahme, unbelegt)",
             "microsoft_tech_community": "Diskussionsfrage, höchstens 1500 Zeichen"}[name]
    koerper = gemeinsam.koerper_html(meta)
    try:
        antwort = llm.chat(llm.PLATTFORM_ANALYSE_SYSTEM,
                           llm.plattform_analyse_prompt(pname, regeln, limit, meta, bw.lesetext(koerper, meta), gemeinsam.live_url(cfg, slug),
                                                        titel_noetig=(name == "reddit"), link_erlaubt=(name != "microsoft_tech_community")),
                           max_tokens=2000, aufgabe="plattform")
        e = llm.json_aus_text(antwort)
    except llm.LLMFehler as exc:
        return _zurueck(name, slug, "analyse", fehler=f"Auto-Analyse fehlgeschlagen: {exc}")
    try:
        eignung_wert = max(0, min(100, int(round(float(e.get("eignung"))))))
    except (TypeError, ValueError):
        eignung_wert = None
    ergebnis = {"text": str(e.get("text") or "").strip(), "eignung": eignung_wert, "begruendung": str(e.get("begruendung") or "").strip(),
                "risiken": [str(r).strip() for r in (e.get("risiken") or []) if str(r).strip()][:10]}
    if name == "reddit":
        ergebnis["titel"] = str(e.get("titel") or "").strip()
    if not ergebnis["text"]:
        return _zurueck(name, slug, "analyse", fehler="Auto-Analyse lieferte keinen Text.")
    ablage.analyse_speichern(name, slug, {"zeitpunkt": datetime.now().isoformat(timespec="seconds"), "modell": llm.llm_status()["modell"],
                                          "text_hash": hashlib.sha256(str(meta.get("body_md", "")).encode()).hexdigest()[:16], "ergebnis": ergebnis})
    return _zurueck(name, slug, "analyse", meldung="Auto-Analyse gespeichert.")


@bp.route("/verwaltung/plattform/<name>/kennzahlen", methods=["POST"])
def kennzahlen_aktion(name):
    gemeinsam.post_pruefen()
    _name_pruefen(name)
    quellen = gemeinsam.artikel_quellen(load_config())
    slug = request.form.get("slug", "")
    _slug_pruefen(slug, quellen)
    _sperre_pruefen(name, slug, load_config(), quellen)
    aktion = request.form.get("aktion", "")
    if aktion == "aktualisieren":
        if name not in kz.ABRUF:
            abort(400)
        eintraege = _auto_url(name, pl.gepostet_aus_log(ROOT))
        if not eintraege:
            return _zurueck(name, slug, "kennzahlen", fehler="Kein Beitrag in publish-log.md gefunden.")
        daten = kennz.aktualisieren(name, eintraege)
        fehler = [s for s, e in daten["beitraege"].items() if e.get("fehler")]
        return _zurueck(name, slug, "kennzahlen", meldung=f"Kennzahlen aktualisiert ({len(eintraege) - len(fehler)} von {len(eintraege)} Beiträgen)."
                        + (f" Fehler bei: {', '.join(fehler)}." if fehler else ""))
    if aktion == "erfassen":
        if name in kz.ZAEHLER_ANZEIGE or name == "linkedin":
            abort(400)
        url = (request.form.get("beitrag_url") or "").strip()
        if url and not url.startswith("https://"):
            return _zurueck(name, slug, "kennzahlen", fehler="Beitrags-URL muss mit https:// beginnen.")
        m = kennz.messung_hinzufuegen(name, slug, request.form, request.form.get("datum"), url)
        if not m:
            return _zurueck(name, slug, "kennzahlen", fehler="Keine gültigen Zahlen eingegeben (0 bis 1 Mrd.; Prozent 0–100).")
        return _zurueck(name, slug, "kennzahlen", meldung="Kennzahlen gespeichert (nur lokal).")
    if aktion == "loeschen":
        try:
            idx = int(request.form.get("index", "-1"))
        except ValueError:
            abort(400)
        if not kennz.messung_loeschen(name, slug, idx):
            abort(400, "Messung nicht gefunden")
        return _zurueck(name, slug, "kennzahlen", meldung="Messung gelöscht.")
    abort(400)


@bp.route("/verwaltung/plattform/<name>/kennzahlen/import", methods=["POST"])
def kennzahlen_import(name):
    gemeinsam.post_pruefen()
    _name_pruefen(name)
    if name in kz.ZAEHLER_ANZEIGE or name == "linkedin":
        abort(400)
    quellen = gemeinsam.artikel_quellen(load_config())
    slug = request.form.get("slug", "")
    _slug_pruefen(slug, quellen)
    _sperre_pruefen(name, slug, load_config(), quellen)
    datei = request.files.get("datei")
    if not datei or not datei.filename:
        return _zurueck(name, slug, "kennzahlen", fehler="Keine Datei ausgewählt.")
    daten = datei.read(1024 * 1024 + 1)
    if len(daten) > 1024 * 1024:
        abort(413)
    try:
        erg = kennz.csv_importieren(name, daten, set(quellen))
    except Exception as exc:  # noqa: BLE001 - defekte Datei verstaendlich melden
        return _zurueck(name, slug, "kennzahlen", fehler=f"Datei nicht lesbar: {type(exc).__name__}")
    msg = f"{erg['gespeichert']} Zeile(n) importiert."
    if erg["fehler"]:
        return _zurueck(name, slug, "kennzahlen", meldung=msg, fehler=" ".join(erg["fehler"][:5]))
    return _zurueck(name, slug, "kennzahlen", meldung=msg)
