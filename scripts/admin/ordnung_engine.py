"""Mehrrunden-Engine von „Alles in Ordnung bringen“.

Ablauf je Runde (hoechstens io.MAX_RUNDEN, Gesamtfrist io.GESAMT_FRIST):
  1. Den Entwurf (Original + bisher angenommene Aenderungen) in einem Wegwerf-Verzeichnis bauen und
     mit der echten Bewertung neu bewerten (Simulation, nichts wird geschrieben).
  2. Die noch nicht bestandenen, automatisch behebbaren Kriterien bestimmen.
  3. Gezielt verbessern: Metas (Titel/Beschreibung/Bild-Alt), lange Saetze, Woerter (Fuellwoerter,
     Wiederholungen), Uebergaenge, Absatzlaengen, interne Links. Jede Aenderung wird programmatisch gegen
     das ORIGINAL geschuetzt (Zahlen, Fachbegriffe, Links, Code, Ueberschriften, Bilder; nur ausdruecklich
     gewollte neue interne Links duerfen hinzukommen). Abgelehnte Stellen werden mit der konkreten
     Begruendung noch zweimal versucht.
  4. Ohne Fortschritt (keine neue Aenderung) endet die Schleife; was dann noch rot ist, wird ehrlich benannt.

Bewertung, Schwellen und Gewichte werden hier nie veraendert.
"""

from __future__ import annotations

import hashlib
import math
import re
import time

import bewertung as bw
import in_ordnung as io
import llm
import metas_auswahl as ma

GRUPPEN = [
    ("metas", "Titel und Beschreibung"),
    ("saetze", "Lange Sätze"),
    ("woerter", "Wortwiederholungen und Füllwörter"),
    ("uebergang", "Übergänge"),
    ("absatz", "Absatzlängen"),
    ("ki", "Klingt menschlich (KI-Muster)"),
    ("links", "Interne Links"),
]
ZWECK_GRUPPE = {"kuerzen": "saetze", "woerter": "woerter", "uebergang": "uebergang", "absatz": "absatz", "link": "links", "ki_muster": "ki"}
META_KRITERIEN = {"a_titel", "a_beschr", "a_hook", "a_guss", "a_alt", "e_fokus"}
TEXT_KRITERIEN = {"b_amstad", "b_satzlaenge", "b_lange_saetze", "b_uebergaenge", "b_wiederholung", "b_fuellwoerter", "b_absaetze", "b_menschlich"}
STAPEL = 2        # kleine Stapel: kuerzere Antworten, weniger Abschneiden
TEXT_TOKENS = 8000
VERBINDUNG = "__verbindung__"
NACHVERSUCHE = 2
MAX_LINKS = 3


# --------------------------------------------------------------------------
# Kleine Helfer
# --------------------------------------------------------------------------


def behebbar(snap: dict, hat_bild: bool) -> list[str]:
    """Kriterien, die nicht bestanden sind und die der Durchlauf beheben kann."""
    erg = []
    for kid, v in snap["kriterien"].items():
        if v["status"] not in ("teils", "nein"):
            continue
        bereich = io.AUTOMATISCH.get(kid)
        if bereich in ("metas", "text", "links"):
            if kid == "a_alt" and not hat_bild:
                continue
            erg.append(kid)
    return erg


def _chat_json(ctx, system: str, prompt: str, max_tokens: int = 4000, aufgabe: str | None = None, modell: str | None = None) -> dict:
    """LLM-Aufruf mit JSON-Antwort. Kaputtes JSON: genau ein zweiter Versuch mit Hinweis. Eine abgeschnittene Antwort
    (Antwortlimit) wird als llm.LLMAbgeschnitten gemeldet - der Aufrufer teilt die Aufgabe."""
    extra = {}
    if aufgabe:
        extra["aufgabe"] = aufgabe
    if modell:
        extra["modell"] = modell
    antwort = ctx.chat(system, prompt, timeout=io.LLM_TIMEOUT, max_tokens=max_tokens, **extra)
    try:
        return llm.json_aus_text(antwort)
    except llm.LLMAbgeschnitten:
        raise
    except llm.LLMFehler:
        return llm.json_aus_text(ctx.chat(system, prompt + '\n\nWICHTIG: gültiges JSON; Anführungszeichen im Text mit \\" maskieren.',
                                          timeout=io.LLM_TIMEOUT, max_tokens=max_tokens, **extra))


def warte_auf_dienst(ctx, slug, z, frist_ende: float) -> None:
    """Gesundheitstest vor dem Start: ist der LLM-Dienst weg, bis zu ctx.gesundheit_frist Sekunden warten (sichtbar)."""
    if ctx.gesundheit():
        return
    _schritt_neu(ctx, slug, z, "warte-dienst", "Warte auf LLM-Dienst")
    ende = time.time() + ctx.gesundheit_frist
    while time.time() < ende:
        io._pruefe_abbruch(slug, frist_ende)
        if ctx.gesundheit():
            _schritt_ende(ctx, slug, z, "warte-dienst", "ok", "Dienst wieder erreichbar")
            return
        time.sleep(ctx.gesundheit_takt)
    _schritt_ende(ctx, slug, z, "warte-dienst", "fehler", f"nach {ctx.gesundheit_frist} s nicht erreichbar")
    raise llm.LLMVerbindung(f"LLM-Dienst nicht erreichbar (nach {ctx.gesundheit_frist} Sekunden Warten)")


def protokoll(ctx, slug, z, text: str) -> None:
    z.setdefault("protokoll", []).append(text)
    io._sichern(ctx, slug, z)


def eskalation(ctx, slug, z, aufgabe: str, grund: str):
    """Naechsthoehere Modellstufe fuer GENAU eine Wiederholung (None, wenn es keine hoehere gibt oder schon eskaliert wurde)."""
    if z.setdefault("eskaliert", {}).get(aufgabe):
        return None
    hoeher = llm.eskalations_modell(aufgabe)
    if hoeher is None:
        return None
    z["eskaliert"][aufgabe] = hoeher[0]
    protokoll(ctx, slug, z, f"{aufgabe}: eskaliert von {llm.modell_fuer(aufgabe)} auf {hoeher[0]} ({hoeher[1]}), Grund: {grund}")
    return hoeher[0]


def _fortschritt(ctx, slug, z, **kw) -> None:
    z.setdefault("fortschritt", {}).update(kw)
    io._sichern(ctx, slug, z)


def _schritt_neu(ctx, slug, z, key: str, name: str) -> None:
    z["schritte"].append({"key": key, "name": name, "status": "laeuft", "text": "", "start": time.time()})
    io._sichern(ctx, slug, z)


def _schritt_ende(ctx, slug, z, key: str, status: str, text: str = "") -> None:
    io._schritt(ctx, slug, z, key, status, text)


# --------------------------------------------------------------------------
# Entwurf: Original + angenommene Aenderungen, mit Positionsabbildung
# --------------------------------------------------------------------------


def entwurf_mit_karte(orig: str, records: dict, meta_werte: dict) -> tuple[str, int, list[dict]]:
    """(Entwurfstext, Verschiebung durch das Frontmatter, Karte [{rec, d_start, d_ende}])."""
    recs = sorted(records.values(), key=lambda r: r["start"])
    out, pos, karte, laenge = [], 0, [], 0
    for r in recs:
        stueck = orig[pos:r["start"]]
        out.append(stueck)
        laenge += len(stueck)
        karte.append({"rec": r, "d_start": laenge, "d_ende": laenge + len(r["neu"])})
        out.append(r["neu"])
        laenge += len(r["neu"])
        pos = r["ende"]
    out.append(orig[pos:])
    text = "".join(out)
    delta = 0
    if meta_werte:
        text2, fehler = io.entwurf(text, dict(meta_werte), [])
        if not fehler:
            delta = len(text2) - len(text)
            text = text2
    return text, delta, karte


def entwurfs_absaetze(orig: str, orig_bloecke: dict, records: dict, meta_werte: dict):
    """Absatzbloecke des Entwurfs; je Block der zugehoerige Originalblock und ggf. der Datensatz."""
    text, delta, karte = entwurf_mit_karte(orig, records, meta_werte)
    erg = []
    for b in io.finde_bloecke(text):
        if b.art not in ("html", "md"):
            continue
        pos = b.start - delta
        treffer = next((k for k in karte if k["d_start"] <= pos < k["d_ende"]), None)
        if treffer:
            rec = treffer["rec"]
            ob = orig_bloecke.get(rec["start"])
            erg.append({"block": b, "ob": ob, "rec": rec, "gesperrt": bool(rec.get("gesperrt"))})
            continue
        verschiebung = sum(len(k["rec"]["neu"]) - (k["rec"]["ende"] - k["rec"]["start"]) for k in karte if k["d_ende"] <= pos)
        ob = orig_bloecke.get(pos - verschiebung)
        if ob is not None:
            erg.append({"block": b, "ob": ob, "rec": None, "gesperrt": False})
    return text, erg


# --------------------------------------------------------------------------
# Kandidaten fuer Textstellen
# --------------------------------------------------------------------------


def _satz_maxima(klar: str) -> list[int]:
    return [len(bw.woerter(s)) for s in bw.saetze(klar)]


def sammle_runde(absaetze: list[dict], snap: dict, offen: set[str], vale: dict | None, lek: dict | None, themen: set[str]) -> list[dict]:
    """Waehlt die Absaetze, die in dieser Runde bearbeitet werden - ohne Obergrenze: die mit den laengsten
    Saetzen zuerst, bis die Ziele (≤ 10 % sehr lange Saetze, Ø ≤ 17 Woerter) erreichbar sind."""
    kz = snap["kriterien"]
    frei = [a for a in absaetze if not a["gesperrt"]]
    kandidaten: dict[int, dict] = {}

    def kand(a):
        k = kandidaten.setdefault(a["ob"].start, {"a": a, "zweck": [], "hinweise": [], "prio": 0, "woerter_hinweis": ""})
        return k

    infos = []
    for a in frei:
        inner = a["rec"]["neu_inner"] if a["rec"] else a["ob"].inner
        klar = io.klartext(io.block_html(a["ob"].art, inner))
        infos.append((a, inner, klar, _satz_maxima(klar)))

    # --- lange Saetze
    lang_offen = "b_lange_saetze" in offen
    asl_offen = bool(offen & {"b_satzlaenge", "b_amstad"})
    if lang_offen or asl_offen:
        schwelle = 25 if lang_offen else 18
        for a, inner, klar, ms in infos:
            ueber = [m for m in ms if m > schwelle]
            if ueber:
                k = kand(a)
                if "kuerzen" not in k["zweck"]:
                    k["zweck"].append("kuerzen")
                k["prio"] += 10 * len(ueber) + max(ueber)
    # --- Fuellwoerter und Wiederholungen
    gesamt_w = sum(len(bw.woerter(klar)) for _a, _i, klar, _m in infos) or 1
    if "b_fuellwoerter" in offen:
        treffer = []
        for a, inner, klar, ms in infos:
            fw = [w for w in bw.woerter(klar) if w.lower() in bw.FUELLWOERTER]
            if fw:
                treffer.append((len(fw), a, fw))
        zu_streichen = sum(n for n, _a, _f in treffer) - int(0.008 * gesamt_w)
        for n, a, fw in sorted(treffer, key=lambda t: -t[0]):
            if zu_streichen <= 0:
                break
            k = kand(a)
            if "woerter" not in k["zweck"]:
                k["zweck"].append("woerter")
            k["woerter_hinweis"] += ("Füllwörter: " + ", ".join(sorted(set(w.lower() for w in fw))) + ". ")
            k["prio"] += n
            zu_streichen -= n
    if "b_wiederholung" in offen:
        treffer = []
        for a, inner, klar, ms in infos:
            n, top = bw.nahwiederholungen(klar, ausnahmen=themen)
            if n:
                treffer.append((n, a, top))
        for n, a, top in sorted(treffer, key=lambda t: -t[0]):
            k = kand(a)
            if "woerter" not in k["zweck"]:
                k["zweck"].append("woerter")
            k["woerter_hinweis"] += ("Wiederholungen: " + ", ".join(top) + ". ")
            k["prio"] += n
    # --- Uebergaenge
    if "b_uebergaenge" in offen:
        folge = [a for a, _i, _k, _m in infos if not a["block"].nach_ueberschrift and a is not absaetze[0]]
        verbunden = [a for a in folge if (bw.woerter(io.klartext(a["block"].inner)) or [""])[0].lower() in bw.UEBERGANGSWOERTER]
        offen_folge = [a for a in folge if a not in verbunden and len(bw.woerter(io.klartext(a["block"].inner))) >= 8]
        brauche = max(1, min(8, math.ceil(0.25 * max(1, len(folge))) - len(verbunden) + 1))
        if offen_folge:
            schritt = max(1, len(offen_folge) // brauche)
            for a in offen_folge[::schritt][:brauche]:
                k = kand(a)
                if "uebergang" not in k["zweck"]:
                    k["zweck"].append("uebergang")
                k["prio"] += 1
    # --- zu lange Absaetze
    if "b_absaetze" in offen:
        for a, inner, klar, ms in infos:
            if len(bw.woerter(klar)) > 100 and not a["rec"]:
                k = kand(a)
                if "absatz" not in k["zweck"]:
                    k["zweck"].append("absatz")
                k["prio"] += 5
    # --- KI-Muster (klingt menschlich): Absaetze mit den meisten Treffern zuerst
    if "b_menschlich" in offen:
        import ki_muster
        for a, inner, klar, ms in infos:
            n = ki_muster.treffer_summe(klar)
            if n:
                k = kand(a)
                if "ki_muster" not in k["zweck"]:
                    k["zweck"].append("ki_muster")
                gefunden = [r["name"] for r in ki_muster.REGELN if r["gewicht"] and ki_muster.messe([klar])[r["id"]]["anzahl"]]
                k["hinweise"].append("Muster: " + ", ".join(gefunden))
                k["prio"] += 3 * n
    # --- Hinweise (Vale, Lektorat) nur fuer ohnehin gewaehlte Stellen
    vale_zeilen = [(f["zeile"], f.get("regel", "")) for f in (vale or {}).get("befunde", [])]
    zitate = io._lektorat_zitate(lek)
    for k in kandidaten.values():
        ob = k["a"]["ob"]
        hits = sorted({r for z, r in vale_zeilen if ob.zeile <= z <= ob.zeile_ende})
        if hits:
            k["hinweise"].append("Vale: " + ", ".join(hits))
        kl = io.klartext(ob.inner).lower()
        if any(z in kl for z in zitate):
            k["hinweise"].append("Lektorat nennt diese Stelle")
    return sorted(kandidaten.values(), key=lambda k: (-k["prio"], k["a"]["ob"].start))


def _stelle_dict(k: dict, davor: str) -> dict:
    a = k["a"]
    ob = a["ob"]
    inner = a["rec"]["neu_inner"] if a["rec"] else ob.inner
    return {"id": ob.start, "start": ob.start, "ende": ob.ende, "zeile": ob.zeile, "abschnitt": ob.abschnitt, "abschnitt_id": ob.abschnitt_id,
            "absatz_nr": ob.absatz_nr, "art": ob.art, "oeffner": ob.oeffner, "alt": ob.text, "alt_inner": inner, "orig_inner": ob.inner,
            "davor": davor, "zweck": list(k["zweck"]), "hinweise": list(k["hinweise"]), "woerter_hinweis": k.get("woerter_hinweis", ""),
            "links": list(a["rec"]["links"]) if a["rec"] else []}


def _neu_inner_pruefen(s: dict, neu_inner: str) -> list[str]:
    """Gruende fuer eine Ablehnung; leer = angenommen. Geprueft wird gegen das ORIGINAL."""
    neu_inner = neu_inner.strip()
    if "absatz" in s["zweck"]:
        teile = [t for t in re.split(r"\n\s*\n", neu_inner) if t.strip()]
        if not 2 <= len(teile) <= 4:
            return ["Der Absatz sollte in 2 bis 4 Absätze geteilt werden (getrennt durch eine Leerzeile)."]
    return io.schutzpruefung_stelle(s["orig_inner"], neu_inner, s["zweck"], links=tuple(s["links"]), vorher=s["alt_inner"])


def _record_aus(s: dict, neu_inner: str, records: dict) -> dict:
    neu_inner = neu_inner.strip()
    rec = records.get(s["start"]) or {
        "start": s["start"], "ende": s["ende"], "zeile": s["zeile"], "abschnitt": s["abschnitt"], "abschnitt_id": s["abschnitt_id"],
        "absatz_nr": s["absatz_nr"], "art": s["art"], "oeffner": s["oeffner"], "alt": s["alt"], "alt_inner": s["orig_inner"],
        "zweck": [], "gruppe": "", "hinweise": [], "links": []}
    if "absatz" in s["zweck"]:
        teile = [t.strip() for t in re.split(r"\n\s*\n", neu_inner) if t.strip()]
        neu = "\n\n".join((f"{s['oeffner']}{t}</p>" if s["art"] == "html" else t) for t in teile)
        rec["gesperrt"] = True
    else:
        neu = f"{s['oeffner']}{neu_inner}</p>" if s["art"] == "html" else neu_inner
    rec["neu_inner"], rec["neu"] = neu_inner, neu
    for zw in s["zweck"]:
        if zw not in rec["zweck"]:
            rec["zweck"].append(zw)
    for h in s["hinweise"]:
        if h not in rec["hinweise"]:
            rec["hinweise"].append(h)
    if not rec["gruppe"]:
        rec["gruppe"] = ZWECK_GRUPPE.get(s["zweck"][0], "saetze") if s["zweck"] else "saetze"
    if "uebergang" in s["zweck"]:
        rec["uebergang_erkannt"] = (bw.woerter(io.klartext(neu_inner)) or [""])[0].lower() in bw.UEBERGANGSWOERTER
    records[s["start"]] = rec
    return rec


def _stapel_antworten(ctx, stapel: list[dict], modell: str | None) -> list[tuple[dict, dict | None, str]]:
    """Fragt einen Stapel an. Wird die Antwort abgeschnitten, wird der Stapel halbiert und einzeln wiederholt.
    Ergebnis je Stelle: (stelle, antwort-dict | None, Fehlertext)."""
    prompt_stellen = [dict(s, id=s["_id"]) for s in stapel]
    try:
        antwort = _chat_json(ctx, io.TEXT_SYSTEM, io.text_prompt(prompt_stellen), TEXT_TOKENS, "text_umschreiben", modell)
    except llm.LLMAbgeschnitten:
        if len(stapel) > 1:
            mitte = len(stapel) // 2
            return _stapel_antworten(ctx, stapel[:mitte], modell) + _stapel_antworten(ctx, stapel[mitte:], modell)
        return [(stapel[0], None, "Die Antwort wurde abgeschnitten (Antwortlimit) – diese Stelle wird einzeln und knapper wiederholt.")]
    except llm.LLMVerbindung as exc:
        return [(s, None, VERBINDUNG + str(exc)) for s in stapel]  # Dienst weg: KEIN Ablehnungsgrund der Stelle
    except llm.LLMFehler as exc:
        return [(s, None, f"LLM-Aufruf fehlgeschlagen: {exc}") for s in stapel]
    nach_id = {int(e.get("id")): e for e in (antwort.get("stellen") or []) if str(e.get("id", "")).isdigit()}
    erg = []
    for s in stapel:
        e = nach_id.get(s["_id"])
        erg.append((s, e, "" if e is not None else "Das Modell hat für diese Stelle keine Antwort geliefert."))
    return erg


def text_runde(ctx, slug, z, orig, records, kandidaten: list[dict], abgelehnt: dict, frist_ende: float, schluessel: str,
               stellen_vorgabe: list[dict] | None = None) -> int:
    """Bearbeitet die Kandidaten in kleinen Stapeln; abgelehnte Stellen werden einzeln mit der konkreten Begruendung erneut
    versucht, danach genau einmal mit der naechsthoeheren Modellstufe. Gibt die Zahl neuer Aenderungen zurueck."""
    stellen = [dict(v) for v in stellen_vorgabe] if stellen_vorgabe is not None else [_stelle_dict(k, "") for k in kandidaten]
    for v in stellen:
        v.pop("rueckmeldung", None)
        v.pop("verbindung", None)
    bloecke = [b for b in io.finde_bloecke(orig) if b.art in ("html", "md")]
    vor = {b.start: (bloecke[i - 1].klar[-300:] if i else "") for i, b in enumerate(bloecke)}
    for i, s in enumerate(stellen, 1):
        s["davor"] = vor.get(s["start"], "")
        s["_id"] = i
    neu = 0
    verbindung: list[dict] = []
    offene = list(stellen)
    durchgang = 0
    modell = None
    z.setdefault("modelle", {})["text"] = llm.modell_fuer("text_umschreiben")
    while offene and durchgang <= NACHVERSUCHE + 1:
        if durchgang == NACHVERSUCHE + 1:  # alles bisher gescheitert: einmal mit der hoeheren Stufe
            modell = eskalation(ctx, slug, z, "text_umschreiben",
                                f"{len(offene)} Stelle(n) scheiterten {NACHVERSUCHE + 1}-mal an der Prüfung")
            if modell is None:
                break
            z["modelle"]["text"] = modell
        naechste = []
        groesse = STAPEL if durchgang == 0 else 1  # Nachversuche einzeln, mit konkreter Rueckmeldung
        for i in range(0, len(offene), groesse):
            io._pruefe_abbruch(slug, frist_ende)
            for s, e, fehler in _stapel_antworten(ctx, offene[i:i + groesse], modell):
                if e is None and fehler.startswith(VERBINDUNG):  # Verbindungsproblem: nicht ablehnen, spaeter nochmals
                    verbindung.append(s)
                    continue
                if e is None:
                    s["rueckmeldung"] = fehler
                    naechste.append(s)
                    continue
                neu_inner = str(e.get("neu") or "")
                gemeldet = " ".join(bw.woerter(str(e.get("alt") or ""))[:3]).lower()
                kontrolle = " ".join(bw.woerter(io.klartext(s["alt_inner"]))[:3]).lower()
                gruende = []
                if gemeldet and kontrolle and gemeldet != kontrolle:
                    gruende.append("Die Antwort gehört nicht zu dieser Stelle (der Anfang stimmt nicht).")
                gruende += _neu_inner_pruefen(s, neu_inner)
                if gruende:
                    s["rueckmeldung"] = " ".join(gruende)
                    s["letzte_antwort"] = neu_inner
                    naechste.append(s)
                else:
                    _record_aus(s, neu_inner, records)
                    neu += 1
                    abgelehnt.pop(s["start"], None)
        offene = naechste
        durchgang += 1
        _fortschritt(ctx, slug, z, stellen_erledigt=len(records), schluessel=schluessel)
    if verbindung:  # am Ende automatisch nochmals versuchen, sobald der Dienst wieder antwortet
        try:
            warte_auf_dienst(ctx, slug, z, frist_ende)
        except llm.LLMVerbindung:
            pass
        rest = []
        for i in range(0, len(verbindung), 1):
            io._pruefe_abbruch(slug, frist_ende)
            for s, e, fehler in _stapel_antworten(ctx, verbindung[i:i + 1], None):
                if e is None:
                    (rest if fehler.startswith(VERBINDUNG) else offene).append(s)
                    if not fehler.startswith(VERBINDUNG):
                        s["rueckmeldung"] = fehler
                    continue
                neu_inner = str(e.get("neu") or "")
                gruende = _neu_inner_pruefen(s, neu_inner)
                if gruende:
                    s["rueckmeldung"], s["letzte_antwort"] = " ".join(gruende), neu_inner
                    offene.append(s)
                else:
                    _record_aus(s, neu_inner, records)
                    neu += 1
                    abgelehnt.pop(s["start"], None)
        z.setdefault("nicht_bearbeitet", [])
        neue_starts = {s["start"] for s in rest}
        z["nicht_bearbeitet"] = [x for x in z["nicht_bearbeitet"] if x["start"] not in neue_starts]  # keine Doppelten ueber Runden
        for s in rest:
            z["nicht_bearbeitet"].append({k: v for k, v in s.items() if not k.startswith("_") and k not in ("rueckmeldung", "letzte_antwort")})
    for s in offene:  # endgueltig abgelehnt (nach allen Nachversuchen und der Eskalation)
        abgelehnt[s["start"]] = {k: s.get(k) for k in ("start", "ende", "zeile", "abschnitt", "abschnitt_id", "absatz_nr", "art", "zweck", "hinweise", "alt", "alt_inner")}
        abgelehnt[s["start"]].update(neu_inner=s.get("letzte_antwort", ""), neu="", grund=s.get("rueckmeldung", ""), id=s["start"])
    return neu


# --------------------------------------------------------------------------
# Interne Links
# --------------------------------------------------------------------------


def verwandte_artikel(meta: dict, quellen: dict, n: int = 4) -> list[dict]:
    """Passende andere Artikel nach Tags, Titel- und Beschreibungswoertern (nie der Artikel selbst)."""
    mein = {str(t).lower() for t in meta.get("tags") or []}
    woerter = {w.lower() for w in bw.woerter(str(meta.get("title", "")) + " " + str(meta.get("description", ""))) if len(w) > 4}
    erg = []
    for slug, m in quellen.items():
        if slug == meta.get("slug") or m.get("is_html"):
            continue
        tags = {str(t).lower() for t in m.get("tags") or []}
        ww = {w.lower() for w in bw.woerter(str(m.get("title", "")) + " " + str(m.get("description", ""))) if len(w) > 4}
        punkte = 3 * len(mein & tags) + len(woerter & ww)
        erg.append((punkte, str(m.get("date", "")), slug, m))
    erg.sort(key=lambda t: (-t[0], t[1]), reverse=False)
    erg = sorted(erg, key=lambda t: (-t[0], t[1]))
    return [{"slug": s, "titel": str(m.get("title", "")), "tags": [str(t) for t in m.get("tags") or []],
             "beschreibung": str(m.get("description", ""))[:200], "punkte": p} for p, _d, s, m in erg[:n]]


def fuege_link_ein(art: str, inner: str, anker: str, url: str) -> str | None:
    """Setzt den Link um genau EINEN wörtlich vorhandenen Textausschnitt. Der Text bleibt sonst unveraendert.
    None, wenn der Ausschnitt nicht genau einmal ausserhalb von Tags, Links und Code vorkommt."""
    anker = anker.strip()
    if len(anker) < 4 or "<" in anker or ">" in anker or "\n" in anker:
        return None
    if art == "html":
        teile = re.split(r"(<[^>]+>)", inner)
        in_a = in_code = 0
        treffer = []
        for i, t in enumerate(teile):
            if t.startswith("<"):
                tag = re.match(r"</?\s*(\w+)", t)
                if tag:
                    name = tag.group(1).lower()
                    delta = -1 if t.startswith("</") else 1
                    if name == "a":
                        in_a = max(0, in_a + delta)
                    if name == "code":
                        in_code = max(0, in_code + delta)
                continue
            if not in_a and not in_code:
                treffer += [(i, m.start()) for m in re.finditer(re.escape(anker), t)]
        gesamt = sum(len(re.findall(re.escape(anker), t)) for t in teile if not t.startswith("<"))
        if len(treffer) != 1 or gesamt != 1:
            return None
        i, pos = treffer[0]
        teile[i] = teile[i][:pos] + f'<a href="{url}">{anker}</a>' + teile[i][pos + len(anker):]
        return "".join(teile)
    # Markdown: nicht in Code oder bestehenden Links
    if inner.count(anker) != 1:
        return None
    pos = inner.index(anker)
    for m in re.finditer(r"`[^`]*`|\[[^\]]*\]\([^)]*\)", inner):
        if m.start() <= pos < m.end():
            return None
    return inner[:pos] + f"[{anker}]({url})" + inner[pos + len(anker):]


LINK_SYSTEM = """Du bist Redakteur eines deutschsprachigen IT-Fachblogs und setzt interne Links zu verwandten Artikeln.
Du änderst keinen Text, du wählst nur Stellen aus. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt."""


def link_prompt(ziele: list[dict], absaetze: list[tuple[int, str]], maximal: int, rueckmeldung: str = "") -> str:
    z = "\n".join(f"- {t['slug']}: „{t['titel']}“ (Tags: {', '.join(t['tags'])}) – {t['beschreibung']}" for t in ziele)
    a = "\n".join(f"[{i}] {text[:420]}" for i, text in absaetze)
    return f"""Setze 1 bis {maximal} interne Links in diesen Artikel.

Zielartikel (nur diese sind erlaubt):
{z}

Absätze des Artikels:
{a}

Regeln:
- Je Link: id = Nummer des Absatzes, ankertext = ein WÖRTLICHER, zusammenhängender Ausschnitt (2 bis 6 Wörter) genau so, wie er im Absatz steht
  (gleiche Schreibweise, ohne Tags), der thematisch zum Zielartikel passt; artikel = der Slug des Zielartikels.
- Jeder Absatz höchstens ein Link, jeder Zielartikel höchstens einmal. Lieber ein guter Link als ein erzwungener.
- Der Ankertext muss im Absatz genau EINMAL vorkommen.
{('- ACHTUNG, dein letzter Versuch scheiterte: ' + rueckmeldung) if rueckmeldung else ''}

Antworte nur mit diesem JSON:
{{"links": [{{"id": 3, "ankertext": "wörtlicher Ausschnitt", "artikel": "slug-des-zielartikels"}}]}}"""


def links_runde(ctx, slug, z, meta, orig_bloecke: dict, absaetze: list[dict], records: dict, frist_ende: float) -> int:
    quellen = ctx.quellen() or {}
    ziele = verwandte_artikel(meta, quellen)
    if not ziele:
        return 0
    frei = [a for a in absaetze if not a["gesperrt"] and a["ob"].art in ("html", "md")
            and len(bw.woerter(io.klartext(a["rec"]["neu_inner"] if a["rec"] else a["ob"].inner))) >= 8]
    if not frei:
        return 0
    nummern = {i: a for i, a in enumerate(frei, 1)}
    vorlage = [(i, io.klartext(a["rec"]["neu_inner"] if a["rec"] else a["ob"].inner)) for i, a in nummern.items()]
    erlaubt = {t["slug"] for t in ziele}
    gesetzt: list[str] = []
    benutzte_abs: set[int] = set()
    rueckmeldung = ""
    neu = 0
    for versuch in range(NACHVERSUCHE + 1):
        io._pruefe_abbruch(slug, frist_ende)
        try:
            antwort = _chat_json(ctx, LINK_SYSTEM, link_prompt(ziele, vorlage, MAX_LINKS - len(gesetzt), rueckmeldung), 1500, "links")
        except llm.LLMFehler as exc:
            rueckmeldung = str(exc)
            continue
        fehler = []
        for e in (antwort.get("links") or [])[:MAX_LINKS]:
            if len(gesetzt) >= MAX_LINKS:
                break
            try:
                nr = int(e.get("id"))
            except (TypeError, ValueError):
                continue
            ziel = str(e.get("artikel") or "").strip()
            anker = str(e.get("ankertext") or "").strip()
            a = nummern.get(nr)
            if a is None or nr in benutzte_abs:
                fehler.append(f"Absatz {nr} ist ungültig oder schon verlinkt.")
                continue
            if ziel not in erlaubt or ziel == meta.get("slug") or ziel in gesetzt:
                fehler.append(f"Zielartikel „{ziel}“ ist nicht erlaubt oder schon verlinkt.")
                continue
            url = f"/artikel/{ziel}/"
            cur = a["rec"]["neu_inner"] if a["rec"] else a["ob"].inner
            kandidat = fuege_link_ein(a["ob"].art, cur, anker, url)
            if kandidat is None:
                fehler.append(f"Der Ausschnitt „{anker}“ kommt in Absatz {nr} nicht genau einmal wörtlich vor.")
                continue
            s = {"start": a["ob"].start, "ende": a["ob"].ende, "zeile": a["ob"].zeile, "abschnitt": a["ob"].abschnitt,
                 "abschnitt_id": a["ob"].abschnitt_id, "absatz_nr": a["ob"].absatz_nr, "art": a["ob"].art, "oeffner": a["ob"].oeffner,
                 "alt": a["ob"].text, "alt_inner": cur, "orig_inner": a["ob"].inner, "zweck": ["link"], "hinweise": [],
                 "links": list(a["rec"]["links"]) + [url] if a["rec"] else [url]}
            gruende = io.schutzpruefung_stelle(s["orig_inner"], kandidat, s["zweck"], links=tuple(s["links"]), vorher=s["alt_inner"])
            if gruende:
                fehler.append(" ".join(gruende))
                continue
            rec = _record_aus(s, kandidat, records)
            rec["links"] = s["links"]
            rec["hinweise"] = [h for h in rec["hinweise"] if not h.startswith("Link zu ")] + [f"Link zu „{ziel}“ (Ankertext „{anker}“)"]
            gesetzt.append(ziel)
            benutzte_abs.add(nr)
            neu += 1
        if gesetzt and not fehler:
            break
        if gesetzt and len(gesetzt) >= 1 and versuch >= 1:
            break
        rueckmeldung = " ".join(fehler)[:500] or "Es wurde kein gültiger Link geliefert."
    return neu


# --------------------------------------------------------------------------
# Metas
# --------------------------------------------------------------------------


def _meta_schluessel(snap: dict, titel: str = ""):
    """Kleiner ist besser: weniger offene Metas, hoehere Punkte A+E (auf ganze Punkte gerundet = „gleich gut“),
    bei Gleichstand weniger Titelzeilen am Handy."""
    offen = sum(1 for k in META_KRITERIEN if snap["kriterien"].get(k, {}).get("status") in ("teils", "nein"))
    a = snap["kategorien"]["A"]["score"]
    e = snap["kategorien"]["E"]["score"]
    return (offen, -round(a + e), ma.titel_zeilen(titel)["handy"])


def metas_runde(ctx, slug, z, meta, orig, records, meta_werte: dict, offen: set[str], snap: dict) -> dict | None:
    """Fragt Metas an und waehlt unter den gueltigen Kombinationen die bestbewertete (Simulation). Gibt die neuen Werte zurueck."""
    benoetigt: set[str] = set()
    if "a_titel" in offen:
        benoetigt.add("title")
    if offen & {"a_beschr", "a_hook", "a_guss"}:
        benoetigt.add("description")
    if "e_fokus" in offen:
        benoetigt |= {"title", "description"}
    if "a_alt" in offen and meta.get("og_image"):
        benoetigt.add("og_image_alt")
    if not benoetigt:
        return None
    aktuell = dict(meta)
    aktuell.update(meta_werte)
    tags = [str(t) for t in meta.get("tags") or []]
    extra = "\n\nNoch offene Kriterien (gemessen): " + "; ".join(
        f"{snap['kriterien'][k]['name']}: {snap['kriterien'][k]['messwert']}" for k in sorted(offen & META_KRITERIEN)) + "."
    if "e_fokus" in offen and tags:
        extra += " Mindestens die Hälfte dieser Schlüsselbegriffe soll in Titel oder Beschreibung vorkommen: " + ", ".join(tags) + "."
    erg = ma.anfordern(ctx.chat, aktuell, ctx.lesetext(meta), set(benoetigt), extra)
    erg["benoetigt"] = sorted(benoetigt)
    modell = ma.auswahl(ctx.root, aktuell, erg, benoetigt)
    optionen = {f: [k["text"] for k in modell["felder"][f]["karten"] if k["ok"]] for f in benoetigt}
    fehlend = [f for f in benoetigt if not optionen[f]]
    if fehlend:  # Standardmodell hat nach allen Nachfragen nichts Gueltiges geliefert: einmal die hoehere Stufe
        hoeher = eskalation(ctx, slug, z, "metas", f"{', '.join(ma.FELD_NAMEN[f] for f in fehlend)}: nach den Nachfragen kein Vorschlag im Soll")
        if hoeher:
            erg2 = ma.anfordern(ctx.chat, aktuell, ctx.lesetext(meta), set(fehlend), extra, modell=hoeher)
            erg2["benoetigt"] = sorted(benoetigt)
            for f in fehlend:  # nur die fehlenden Felder uebernehmen
                erg["felder"][f] = erg2["felder"][f]
            erg["abgewiesen"] += erg2["abgewiesen"]
            erg["nachgefragt"] = True
            erg["modell"] = f"{erg.get('modell')} → {hoeher}"
            modell = ma.auswahl(ctx.root, aktuell, erg, benoetigt)
            optionen = {f: [k["text"] for k in modell["felder"][f]["karten"] if k["ok"]] for f in benoetigt}
    z["metas"] = erg
    z.setdefault("modelle", {})["metas"] = erg.get("modell")
    if not any(optionen.values()):
        return None
    # alle Kombinationen (hoechstens 3 x 3) simulieren, die bestbewertete nehmen
    import itertools
    felder = sorted(optionen)
    kombis = list(itertools.product(*[(optionen[f] or [None]) for f in felder]))[:9]
    beste, bester_schluessel = None, None
    for kombi in kombis:
        werte = dict(meta_werte)
        for f, t in zip(felder, kombi):
            if t is not None:
                werte[f] = t
        try:
            text, _delta, _k = entwurf_mit_karte(orig, records, werte)
            b2 = ctx.simuliere(slug, text)
        except BaseException:
            b2 = None
        if b2 is None:
            beste = werte if beste is None else beste
            continue
        schl = _meta_schluessel(io.schnappschuss(b2), werte.get("title", aktuell.get("title", "")))
        if bester_schluessel is None or schl < bester_schluessel:
            beste, bester_schluessel = werte, schl
    return beste


# --------------------------------------------------------------------------
# Der Lauf
# --------------------------------------------------------------------------


def _offen_info(snap: dict, ids) -> list[dict]:
    return [{"id": k, "name": snap["kriterien"][k]["name"], "messwert": snap["kriterien"][k]["messwert"],
             "status": snap["kriterien"][k]["status"], "kat": snap["kriterien"][k]["kat"]} for k in ids]


def lauf(ctx, slug: str, z: dict, frist_ende: float) -> None:
    pfad = ctx.artikel_pfad(slug)
    io._pruefe_abbruch(slug, frist_ende)  # im Wartestand abgebrochen?
    io._schritt(ctx, slug, z, "pruefen", "laeuft")
    meta, b = ctx.bewerte(slug)
    orig = pfad.read_text(encoding="utf-8")
    z["datei_hash"] = hashlib.sha256(orig.encode()).hexdigest()
    z["vorher"] = io.schnappschuss(b)
    op = io.offene_punkte(b)
    z["offen_vorher"] = sorted(kid for kid, _v in op["kriterien"])
    hat_bild = bool(meta.get("og_image"))
    start_behebbar = behebbar(z["vorher"], hat_bild)
    if not op["kriterien"] and not op["kategorien"]:
        io._schritt(ctx, slug, z, "pruefen", "ok", "Alles bereits grün.")
        for s in z["schritte"][1:]:
            s["status"] = "uebersprungen"
        z["status"] = "nichts_zu_tun"
        z["meldung"] = "Alle Teilnoten sind grün und alle Kriterien bestanden – nichts zu tun."
        return
    io._schritt(ctx, slug, z, "pruefen", "ok",
                f"{len(op['kriterien'])} Kriterien nicht bestanden, {len(op['kategorien'])} Teilnote(n) nicht grün; "
                f"{len(start_behebbar)} davon behebt der Durchlauf, {len(op['kriterien']) - len(start_behebbar)} brauchen einen Menschen.")
    z["nicht_bearbeitet"], z["nicht_bearbeitet_bereiche"] = [], []
    io._pruefe_abbruch(slug, frist_ende)
    warte_auf_dienst(ctx, slug, z, frist_ende)

    # ---- Lektorat (Hinweise fuer die Textstellen)
    lek = None
    if ctx.lektorat is None:
        io._schritt(ctx, slug, z, "lektorat", "uebersprungen", "kein Lektorat verfügbar")
    else:
        alt = ctx.lektorat_alt(slug)
        thash = hashlib.sha256(str(meta.get("body_md", "")).encode()).hexdigest()[:16]
        if alt and alt.get("text_hash") == thash and alt.get("ergebnis"):
            lek = alt
            io._schritt(ctx, slug, z, "lektorat", "ok", f"aktuell vom {alt.get('zeitpunkt', '?')} wiederverwendet")
        else:
            io._schritt(ctx, slug, z, "lektorat", "laeuft")
            try:
                lek = {"ergebnis": ctx.lektorat(meta, b)}
                io._schritt(ctx, slug, z, "lektorat", "ok", f"neu ausgeführt (Modell: {llm.modell_fuer('lektorat')})")
            except (llm.LLMFehler, io.AuftragFehler) as exc:
                io._schritt(ctx, slug, z, "lektorat", "fehler", f"{exc} – weiter ohne Lektorat")
        if lek and lek.get("ergebnis"):
            z["lektorat_verbesserungen"] = (lek["ergebnis"].get("verbesserungen") or [])[:3]
    io._pruefe_abbruch(slug, frist_ende)

    orig_bloecke = {bl.start: bl for bl in io.finde_bloecke(orig) if bl.art in ("html", "md")}
    vale = ctx.vale(pfad)
    themen = {w.lower() for w in bw.woerter(str(meta.get("title", "")) + " " + " ".join(str(t) for t in meta.get("tags") or []))}
    records: dict = {}
    abgelehnt: dict = {}
    meta_werte_ref: dict = {"w": {}}
    try:
        _runden(ctx, slug, z, meta, orig, orig_bloecke, vale, lek, themen, records, abgelehnt, meta_werte_ref, frist_ende, hat_bild)
    except io.AuftragFehler as exc:
        if "Zeitlimit" not in str(exc):
            raise
        z["meldung_frist"] = "Zeitlimit erreicht – es gilt der Stand der bisherigen Runden."
    meta_werte = meta_werte_ref["w"]
    snap = meta_werte_ref.get("snap", z["vorher"])
    _ergebnis(ctx, slug, z, orig, records, abgelehnt, meta_werte, snap, hat_bild)


def _runden(ctx, slug, z, meta, orig, orig_bloecke, vale, lek, themen, records, abgelehnt, ref, frist_ende, hat_bild) -> None:
    meta_werte: dict = {}
    meta_versuche = 0
    link_versucht = False
    z["runden"] = []
    z["metas"] = None
    snap = z["vorher"]
    simuliert = False
    stagnation = 0
    vorher_stand = None  # (Zahl offener Kriterien, Gesamtscore) der Vorrunde
    for runde in range(1, io.MAX_RUNDEN + 1):
        ref["w"], ref["snap"] = meta_werte, snap
        io._pruefe_abbruch(slug, frist_ende)
        if not simuliert and runde > 1:
            break  # ohne Simulation laesst sich der Fortschritt nicht messen
        _fortschritt(ctx, slug, z, runde=runde, max=io.MAX_RUNDEN, schritt="Entwurf bewerten", stellen_erledigt=len(records))
        key = f"r{runde}"
        _schritt_neu(ctx, slug, z, f"{key}-bewerten", f"Runde {runde}: Entwurf bewerten")
        text_entwurf, _d, _k = entwurf_mit_karte(orig, records, meta_werte)
        sim = None
        try:
            sim = ctx.simuliere(slug, text_entwurf)
        except BaseException:
            sim = None
        if sim is not None:
            snap = io.schnappschuss(sim)
            simuliert = True
        offen_liste = behebbar(snap, hat_bild)
        offen = set(offen_liste)
        z["runden"].append({"nr": runde, "offen": _offen_info(snap, offen_liste), "gesamt": snap["gesamt"],
                            "stellen": len(records), "neu": 0})
        _schritt_ende(ctx, slug, z, f"{key}-bewerten", "ok",
                      f"{len(offen_liste)} behebbare Kriterien offen" + (": " + ", ".join(snap["kriterien"][k]["name"] for k in offen_liste[:6]) if offen_liste else "")
                      + f" · Gesamt {snap['gesamt']:.0f}")
        if not offen:
            break
        stand = (len(offen_liste), snap["gesamt"])
        if vorher_stand is not None:
            besser = stand[0] < vorher_stand[0] or stand[1] > vorher_stand[1] + 0.05
            stagnation = 0 if besser else stagnation + 1
            if stagnation >= 2:
                break  # zwei Runden ohne messbare Verbesserung: ehrlich beenden
        vorher_stand = stand
        neu = 0
        # ---- Metas (hoechstens zweimal: Nachfrage mit gemessenen Resten)
        if offen & META_KRITERIEN and meta_versuche < 2:
            meta_versuche += 1
            _fortschritt(ctx, slug, z, schritt="Titel, Beschreibung, Bild-Alt")
            _schritt_neu(ctx, slug, z, f"{key}-metas", f"Runde {runde}: Titel und Beschreibung")
            try:
                beste = metas_runde(ctx, slug, z, meta, orig, records, meta_werte, offen, snap)
            except llm.LLMVerbindung as exc:
                beste = None
                z["nicht_bearbeitet_bereiche"].append("metas")
                _schritt_ende(ctx, slug, z, f"{key}-metas", "fehler", f"nicht bearbeitet (Dienst nicht erreichbar): {exc}")
            except (llm.LLMFehler,) as exc:
                beste = None
                _schritt_ende(ctx, slug, z, f"{key}-metas", "fehler", str(exc))
            else:
                if beste and beste != meta_werte:
                    meta_werte = beste
                    neu += 1
                    _schritt_ende(ctx, slug, z, f"{key}-metas", "ok", "bestbewertete gültige Kombination gewählt")
                else:
                    _schritt_ende(ctx, slug, z, f"{key}-metas", "ok", "kein gültiger Vorschlag im Soll")
            io._pruefe_abbruch(slug, frist_ende)
        # ---- Textstellen
        if offen & TEXT_KRITERIEN:
            _, absaetze = entwurfs_absaetze(orig, orig_bloecke, records, meta_werte)
            kandidaten = sammle_runde(absaetze, snap, offen, vale, lek, themen)
            if kandidaten:
                _fortschritt(ctx, slug, z, schritt=f"{len(kandidaten)} Textstellen")
                _schritt_neu(ctx, slug, z, f"{key}-text", f"Runde {runde}: {len(kandidaten)} Textstellen")
                n_text = text_runde(ctx, slug, z, orig, records, kandidaten, abgelehnt, frist_ende, key)
                neu += n_text
                _schritt_ende(ctx, slug, z, f"{key}-text", "ok", f"{n_text} Stelle(n) verbessert, {len(abgelehnt)} endgültig abgelehnt")
        # ---- interne Links (einmal)
        if "e_intern" in offen and not link_versucht:
            link_versucht = True
            _fortschritt(ctx, slug, z, schritt="Interne Links")
            _schritt_neu(ctx, slug, z, f"{key}-links", f"Runde {runde}: Interne Links")
            _, absaetze = entwurfs_absaetze(orig, orig_bloecke, records, meta_werte)
            try:
                n_link = links_runde(ctx, slug, z, meta, orig_bloecke, absaetze, records, frist_ende)
            except llm.LLMVerbindung as exc:
                n_link = 0
                z["nicht_bearbeitet_bereiche"].append("links")
                _schritt_ende(ctx, slug, z, f"{key}-links", "fehler", f"nicht bearbeitet (Dienst nicht erreichbar): {exc}")
            except llm.LLMFehler as exc:
                n_link = 0
                _schritt_ende(ctx, slug, z, f"{key}-links", "fehler", str(exc))
            else:
                _schritt_ende(ctx, slug, z, f"{key}-links", "ok" if n_link else "fehler",
                              f"{n_link} Link(s) gesetzt" if n_link else "kein passender Link gefunden")
            neu += n_link
        z["runden"][-1]["neu"] = neu
        io._sichern(ctx, slug, z)
        ref["w"], ref["snap"] = meta_werte, snap
        if neu == 0:
            break  # kein Fortschritt: ehrlich beenden
    ref["w"], ref["snap"] = meta_werte, snap


def _ergebnis(ctx, slug, z, orig, records, abgelehnt, meta_werte, snap, hat_bild) -> None:
    text_final, _d, _k = entwurf_mit_karte(orig, records, meta_werte)
    z["meta_standard"] = dict(meta_werte)
    liste = sorted(records.values(), key=lambda r: r["start"])
    for i, r in enumerate(liste, 1):
        r["id"] = i
        if not r.get("gruppe"):
            r["gruppe"] = "saetze"
    z["stellen"] = liste
    z["nicht_bearbeitet"] = [x for x in (z.get("nicht_bearbeitet") or []) if x["start"] not in records]
    z["stellen_abgelehnt"] = [dict(v, id=i) for i, v in enumerate(sorted(abgelehnt.values(), key=lambda v: v["start"]), 1)
                              if v["start"] not in records]
    z["kandidaten_gesamt"] = len(liste) + len(z["stellen_abgelehnt"])
    if not liste and not meta_werte:
        z["erwartet"] = None
        io._schritt(ctx, slug, z, "vorschau", "uebersprungen", "kein Vorschlag, der angewendet werden könnte")
        z["status"] = "keine_vorschlaege"
        z["meldung"] = "Es gibt keinen Vorschlag, der die Schutzprüfung besteht."
        return
    _, fehler = io.entwurf(orig, dict(meta_werte), liste)
    z["warnungen"] = fehler
    erwartet = None
    if not fehler:
        try:
            b2 = ctx.simuliere(slug, text_final)
            erwartet = io.schnappschuss(b2) if b2 else None
        except BaseException as exc:
            z["warnungen"] = [f"Wirkung konnte nicht berechnet werden: {type(exc).__name__}"]
    z["erwartet"] = erwartet
    z["offen_erwartet"] = offen_nach_lauf(erwartet or snap, hat_bild, bool(erwartet))
    _schritt_neu(ctx, slug, z, "vorschau", "Schutzprüfung und Wirkung")
    io._schritt(ctx, slug, z, "vorschau", "ok", "Schutzprüfung bestanden" if not fehler else "; ".join(fehler))
    z["status"] = "vorschlag"
    z["meldung"] = ""
    _fortschritt(ctx, slug, z, schritt="fertig")


def offen_nach_lauf(snap: dict, hat_bild: bool, simuliert: bool) -> list[dict]:
    """Was nach dem Lauf noch nicht bestanden ist, mit Art (behebbar = Durchlauf kam nicht ans Ziel, mensch = Handgriff noetig)."""
    erg = []
    for kid, v in snap["kriterien"].items():
        if v["status"] not in ("teils", "nein"):
            continue
        bereich = io.AUTOMATISCH.get(kid)
        if bereich == "build":
            continue
        if bereich in ("metas", "text", "links") and not (kid == "a_alt" and not hat_bild):
            erg.append({"id": kid, "name": v["name"], "messwert": v["messwert"], "kat": v["kat"], "art": "behebbar",
                        "grund": "Der Durchlauf hat es in den Runden nicht ganz erreicht (letzter Messwert siehe oben). "
                                 "Ein weiterer Durchlauf kann weiterkommen."})
        else:
            erg.append({"id": kid, "name": v["name"], "messwert": v["messwert"], "kat": v["kat"], "art": "mensch",
                        "grund": io.MENSCH.get(kid, "Nicht automatisch behebbar – bitte von Hand prüfen.")
                        + (" Der Alt-Text wirkt nur mit gesetztem og_image." if kid == "a_alt" else "")})
    return erg


def nachholen_lauf(ctx, slug: str, z: dict, frist_ende: float) -> None:
    """Holt nur nach, was wegen eines Verbindungsproblems nicht bearbeitet wurde, und fuehrt es in den vorhandenen
    Vorschlag ein. Der Rest des Vorschlags bleibt unveraendert."""
    pfad = ctx.artikel_pfad(slug)
    orig = pfad.read_text(encoding="utf-8")
    if hashlib.sha256(orig.encode()).hexdigest() != z.get("datei_hash"):
        raise io.AuftragFehler("Der Artikel wurde seit dem Vorschlag geändert – bitte einen neuen Durchlauf starten.")
    meta, _b = ctx.bewerte(slug)
    hat_bild = bool(meta.get("og_image"))
    records = {r["start"]: r for r in (z.get("stellen") or [])}
    abgelehnt = {v["start"]: v for v in (z.get("stellen_abgelehnt") or [])}
    meta_werte = dict(z.get("meta_standard") or {})
    todo = [dict(s) for s in (z.get("nicht_bearbeitet") or [])]
    bereiche = list(z.get("nicht_bearbeitet_bereiche") or [])
    z["nicht_bearbeitet"], z["nicht_bearbeitet_bereiche"] = [], []
    _schritt_neu(ctx, slug, z, "nachholen", "Nachholen (nur nicht bearbeitete Teile)")
    warte_auf_dienst(ctx, slug, z, frist_ende)
    snap = z.get("erwartet") or z["vorher"]
    offen = {k for k in behebbar(snap, hat_bild)}
    if "metas" in bereiche:
        try:
            beste = metas_runde(ctx, slug, z, meta, orig, records, meta_werte, offen, snap)
            if beste:
                meta_werte = beste
        except llm.LLMVerbindung:
            z["nicht_bearbeitet_bereiche"].append("metas")
    if todo:
        text_runde(ctx, slug, z, orig, records, [], abgelehnt, frist_ende, "nachholen", stellen_vorgabe=todo)
    if "links" in bereiche:
        orig_bloecke = {bl.start: bl for bl in io.finde_bloecke(orig) if bl.art in ("html", "md")}
        _, absaetze = entwurfs_absaetze(orig, orig_bloecke, records, meta_werte)
        try:
            links_runde(ctx, slug, z, meta, orig_bloecke, absaetze, records, frist_ende)
        except llm.LLMVerbindung:
            z["nicht_bearbeitet_bereiche"].append("links")
    rest = len(z.get("nicht_bearbeitet") or []) + len(z.get("nicht_bearbeitet_bereiche") or [])
    _schritt_ende(ctx, slug, z, "nachholen", "ok" if not rest else "fehler",
                  "alles nachgeholt" if not rest else f"{rest} Teil(e) weiterhin nicht erreichbar")
    z.pop("wirkung_auswahl", None)
    _ergebnis(ctx, slug, z, orig, records, abgelehnt, meta_werte, snap, hat_bild)
