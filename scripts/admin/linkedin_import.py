"""LinkedIn-Kennzahlen: Felder, Import der Export-Dateien, Wirkungs-Kennzahl.

Eine offizielle API fuer die Beitragsanalysen eines PERSOENLICHEN Profils
gibt es fuer Privatpersonen nicht (Community Management API nur fuer
verifizierte Organisationen, r_member_social geschlossen) - siehe CLAUDE.md.
Deshalb: manuelle Erfassung plus Import der Datei, die LinkedIn unter
„Exportieren“ liefert (.xlsx; CSV wird ebenfalls angenommen).

Erkannte Formate (Spaltennamen nicht offiziell dokumentiert, aus
Praxis-Parsern abgeleitet - deshalb tolerant: Gross/Klein, Sonderzeichen,
Deutsch/Englisch egal):

1. Einzelbeitrag-Export („Analysen anzeigen“ am Beitrag → Exportieren):
   ein Blatt mit Paaren Bezeichnung | Wert, z. B. Post URL, Post Date,
   Impressions, Members reached, Profile viewers from this post, Followers
   gained from this post, Reactions, Comments, Reposts, Saves, Sends on
   LinkedIn.
2. Gesamt-Export (Analysen → Inhalte → Exportieren), Blaetter DISCOVERY,
   ENGAGEMENT, TOP POSTS, FOLLOWERS, DEMOGRAPHICS. Genutzt wird TOP POSTS
   (zwei Tabellen nebeneinander: Post URL | Post publish date |
   Engagements und Post URL | Post publish date | Impressions), dazu
   DISCOVERY (Impressions, Members reached im Zeitraum) und FOLLOWERS
   (Total followers).
3. Eigene Tabelle (CSV) mit Kopfzeile aus den Feldnamen unten, eine Zeile
   je Messung; Spalte slug oder Post URL ordnet zu.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

# Feld -> Beschriftung (Formular, Tabelle)
FELDER_BEITRAG = {
    "impressions": "Impressions",
    "mitglieder_erreicht": "Erreichte Mitglieder",
    "profilansichten": "Profilansichten (durch den Beitrag)",
    "neue_follower": "Neue Follower (durch den Beitrag)",
    "reaktionen": "Reaktionen",
    "kommentare": "Kommentare",
    "reposts": "Reposts",
    "gespeichert": "Gespeichert",
    "gesendet": "Gesendet",
    "link_klicks": "Link-Klicks",
    "anteil_netzwerk": "Anteil im Netzwerk (%)",
    "anteil_ausserhalb": "Anteil außerhalb des Netzwerks (%)",
}
FELDER_PROFIL = {
    "impressions_7t": "Impressions (7 Tage)",
    "follower_gesamt": "Follower gesamt",
    "profilbesucher_90t": "Profilbesucher (90 Tage)",
    "suchauftritte": "Suchauftritte",
}
PROZENT_FELDER = {"anteil_netzwerk", "anteil_ausserhalb"}

# Benchmark nur zur Einordnung - fliesst nirgends in den Score ein.
BENCHMARK = {
    "median_impressions": 860,
    "quelle": "AuthoredUp, „LinkedIn metrics to track“: Median 860 Impressions je Beitrag persönlicher Profile "
              "(Auswertung von über 3 Mio. Beiträgen, März 2025 – Februar 2026). Herstellerzahl, keine LinkedIn-Angabe; "
              "nur zur Einordnung, fließt nicht in den Score ein.",
    "url": "https://authoredup.com/blog/linkedin-metrics-to-track",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9äöü]", "", str(s).lower())


# Reihenfolge zaehlt: spezifischere Muster zuerst
_ZUORDNUNG = [
    ("beitrag_url", ("posturl", "beitragsurl", "beitragslink", "url", "link")),
    ("datum", ("postpublishdate", "postdate", "veröffentlichungsdatum", "veroeffentlicht", "datum", "date")),
    ("profilansichten", ("profileviewers", "profileviews", "profilbesucher", "profilansichten", "profilaufrufe")),
    ("neue_follower", ("followersgained", "newfollowers", "neuefollower", "gewonnenefollower", "followergewonnen")),
    ("mitglieder_erreicht", ("membersreached", "erreichtemitglieder", "mitgliedererreicht", "reach")),
    ("impressions", ("impressions", "impressionen")),
    ("reaktionen", ("reactions", "reaktionen")),
    ("kommentare", ("comments", "kommentare")),
    ("reposts", ("reposts", "shares", "geteilt")),
    ("gespeichert", ("saves", "gespeichert", "speicherungen")),
    ("gesendet", ("sendsonlinkedin", "sends", "gesendet", "versendet")),
    ("link_klicks", ("linkengagements", "linkclicks", "linkklicks")),
    ("interaktionen", ("socialengagements", "engagements", "interaktionen")),
    ("anteil_netzwerk", ("innetwork", "imnetzwerk")),
    ("anteil_ausserhalb", ("outofnetwork", "außerhalb", "ausserhalb")),
    ("slug", ("slug", "artikel")),
]


def feld_fuer(beschriftung: str) -> str | None:
    n = _norm(beschriftung)
    if not n:
        return None
    for feld, muster in _ZUORDNUNG:
        for m in muster:
            if m == "url" or m == "link" or m == "date" or m == "datum" or m == "reach":
                if n == m or n.endswith(m) and len(n) <= len(m) + 6:
                    return feld
                continue
            if m in n:
                return feld
    return None


def zahl(wert) -> float | None:
    """'1,234' / '1.234' / "1'006" / '12,5 %' / 1234.0 -> float"""
    if wert is None:
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    s = str(wert).strip().replace(" ", "").replace("\xa0", "").replace(" ", "").replace("'", "").replace("’", "").rstrip("%")
    if not s or s in ("-", "–"):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif "." in s and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def datum(wert) -> str | None:
    if wert is None or wert == "":
        return None
    if isinstance(wert, (int, float)) or re.fullmatch(r"\d{5}(\.0+)?", str(wert).strip()):
        try:
            return (date(1899, 12, 30) + timedelta(days=int(float(wert)))).isoformat()
        except (ValueError, OverflowError):
            return None
    s = str(wert).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", s)
    if m:
        j = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        return date(j, int(m[2]), int(m[1])).isoformat()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        j = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        return date(j, int(m[1]), int(m[2])).isoformat()  # LinkedIn: M/D/YYYY
    return None


def beitrags_id(url: str | None) -> str | None:
    """Zahl aus urn:li:activity:…, ugcPost:…, share:… oder …-activity-…-"""
    if not url:
        return None
    m = re.search(r"(?:activity|ugcPost|share)(?::|%3A|-)(\d{10,})", str(url))
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# Dateien lesen: CSV und XLSX (ohne openpyxl - xlsx ist ein ZIP mit XML)
# --------------------------------------------------------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _spalte(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def lies_xlsx(daten: bytes) -> dict[str, list[list]]:
    blaetter: dict[str, list[list]] = {}
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        namen = set(z.namelist())
        geteilt: list[str] = []
        if "xl/sharedStrings.xml" in namen:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                geteilt.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        ziele = {r.get("Id"): r.get("Target") for r in rels.findall("pr:Relationship", _NS)}
        for sh in wb.find("m:sheets", _NS).findall("m:sheet", _NS):
            rid = sh.get(f"{{{_NS['r']}}}id")
            ziel = ziele.get(rid, "")
            pfad = ziel.lstrip("/") if ziel.startswith("/") else "xl/" + ziel
            if pfad not in namen:
                continue
            zeilen: list[list] = []
            for row in ET.fromstring(z.read(pfad)).iter(f"{{{_NS['m']}}}row"):
                werte: dict[int, object] = {}
                for c in row.findall("m:c", _NS):
                    typ = c.get("t")
                    v = c.find("m:v", _NS)
                    if typ == "s" and v is not None:
                        wert = geteilt[int(v.text)]
                    elif typ == "inlineStr":
                        wert = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
                    elif v is not None and v.text is not None:
                        wert = v.text if typ in ("str", "b", "e") else (float(v.text) if re.fullmatch(r"-?\d+(\.\d+)?([eE]-?\d+)?", v.text) else v.text)
                    else:
                        wert = ""
                    werte[_spalte(c.get("r", "A1"))] = wert
                if werte:
                    zeilen.append([werte.get(i, "") for i in range(max(werte) + 1)])
                else:
                    zeilen.append([])
            blaetter[sh.get("name", f"Blatt{len(blaetter) + 1}")] = zeilen
    return blaetter


def lies_csv(daten: bytes) -> dict[str, list[list]]:
    try:
        text = daten.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = daten.decode("latin-1")
    try:
        dialekt = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialekt = csv.excel
    return {"CSV": [row for row in csv.reader(io.StringIO(text), dialekt)]}


def lies_datei(name: str, daten: bytes) -> dict[str, list[list]]:
    if daten[:2] == b"PK":
        return lies_xlsx(daten)
    if name.lower().endswith((".xls",)):
        raise ValueError("Altes .xls-Format wird nicht unterstützt – bitte als .xlsx oder .csv speichern.")
    return lies_csv(daten)


# --------------------------------------------------------------------------
# Auswerten
# --------------------------------------------------------------------------


def _leer(z) -> bool:
    return all(str(c).strip() == "" for c in z)


def _als_messung(roh: dict) -> dict:
    m: dict = {}
    for k, v in roh.items():
        if k in ("beitrag_url", "slug"):
            if str(v).strip():
                m[k] = str(v).strip()
        elif k == "datum":
            d = datum(v)
            if d:
                m["datum"] = d
        else:
            z = zahl(v)
            if z is not None:
                if k in PROZENT_FELDER and 0 < z <= 1 and "%" not in str(v):
                    z *= 100  # 0.62 -> 62 %
                m[k] = round(z, 2) if k in PROZENT_FELDER else int(round(z))
    return m


def auswerten(blaetter: dict[str, list[list]]) -> dict:
    """Liefert {"messungen": [...], "profil": {...} | None, "hinweise": [...]}."""
    messungen: list[dict] = []
    profil: dict = {}
    hinweise: list[str] = []
    for name, zeilen in blaetter.items():
        n = _norm(name)
        zeilen = [list(z) for z in zeilen]
        # --- Profil-Uebersicht aus DISCOVERY / FOLLOWERS
        if n in ("discovery", "followers"):
            for z in zeilen:
                if len(z) >= 2:
                    k = _norm(z[0])
                    if k == "totalfollowers":
                        profil["follower_gesamt"] = int(zahl(z[1]) or 0)
                    elif k == "impressions":
                        profil["impressions_zeitraum"] = int(zahl(z[1]) or 0)
                    elif k == "membersreached":
                        profil["mitglieder_erreicht_zeitraum"] = int(zahl(z[1]) or 0)
                if z and "overallperformance" in _norm(z[0]) and len(z) > 1:
                    profil["zeitraum"] = str(z[1])
            continue
        if n in ("engagement", "demographics"):
            continue
        # --- Format 1: Bezeichnung | Wert (Einzelbeitrag)
        paare = {}
        for z in zeilen:
            nicht_leer = [c for c in z if str(c).strip() != ""]
            if len(nicht_leer) == 2:
                f = feld_fuer(nicht_leer[0])
                if f and f not in paare:
                    paare[f] = nicht_leer[1]
        kennz = [f for f in paare if f in FELDER_BEITRAG or f == "interaktionen"]
        if len(kennz) >= 3:
            messungen.append({**_als_messung(paare), "quelle": f"Import ({name})"})
            continue
        # --- Format 2/3: Kopfzeile + Datenzeilen (ggf. mehrere Tabellen nebeneinander)
        for i, z in enumerate(zeilen):
            felder = [feld_fuer(c) if str(c).strip() else None for c in z]
            if sum(1 for f in felder if f) < 2 or not any(f in ("beitrag_url", "slug") for f in felder):
                continue
            # Bloecke: jede beitrag_url/slug-Spalte beginnt eine Tabelle
            starts = [j for j, f in enumerate(felder) if f in ("beitrag_url", "slug")]
            bloecke = []
            for s_idx, s in enumerate(starts):
                e = starts[s_idx + 1] if s_idx + 1 < len(starts) else len(felder)
                bloecke.append([(j, felder[j]) for j in range(s, e) if felder[j]])
            pro_url: dict[str, dict] = {}
            for daten_z in zeilen[i + 1:]:
                if _leer(daten_z):
                    continue
                if sum(1 for c in daten_z if feld_fuer(c)) >= 2:
                    break  # naechste Kopfzeile
                for block in bloecke:
                    roh = {f: daten_z[j] for j, f in block if j < len(daten_z)}
                    schluessel = str(roh.get("beitrag_url") or roh.get("slug") or "").strip()
                    if not schluessel:
                        continue
                    pro_url.setdefault(schluessel, {}).update({k: v for k, v in roh.items() if str(v).strip() != ""})
            for roh in pro_url.values():
                m = _als_messung(roh)
                if len(m) >= 2:
                    messungen.append({**m, "quelle": f"Import ({name})"})
            break
    if not messungen and not profil:
        hinweise.append("Keine bekannten Spalten gefunden. Erwartet: LinkedIn-Export (.xlsx) oder eine Tabelle mit "
                        "Kopfzeile (z. B. Post URL, Impressions, Reactions, Comments, Reposts).")
    return {"messungen": messungen, "profil": profil or None, "hinweise": hinweise}


def wirkung(messung: dict | None) -> dict | None:
    """Impressions und Interaktionsrate = (Reaktionen + Kommentare + Reposts) / Impressions.
    Fehlen die Einzelwerte (Gesamt-Export liefert nur „Engagements“), wird
    diese Summe verwendet und so gekennzeichnet."""
    if not messung or not messung.get("impressions"):
        return None
    imp = messung["impressions"]
    teile = [messung.get(k) for k in ("reaktionen", "kommentare", "reposts")]
    if any(t is not None for t in teile):
        summe = sum(t or 0 for t in teile)
        basis = "Reaktionen + Kommentare + Reposts"
    elif messung.get("interaktionen") is not None:
        summe = messung["interaktionen"]
        basis = "Engagements laut Export"
    else:
        return {"impressions": imp, "rate": None, "basis": "", "x_median": round(imp / BENCHMARK["median_impressions"], 2)}
    return {"impressions": imp, "rate": round(100 * summe / imp, 2), "basis": basis,
            "x_median": round(imp / BENCHMARK["median_impressions"], 2)}
