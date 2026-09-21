#!/usr/bin/env python3
"""Taeglicher Search-Console-Abruf fuer blog.brauckmann.ch (21.9.26,
Nutzerauftrag: eigenes Dienstkonto gsc-readonly@brauckmann-ch fuer Blog +
Hauptseite eingerichtet).

Rein lesend, nach demselben Muster wie www.brauckmann.ch/seo-log/
seo_taeglich.py: Suchanalyse der letzten 28 Tage, eingereichte Sitemaps,
Indexierungsstatus der Startseite und der beiden Artikel. Schreibt EIN JSON
pro Tag nach seo-log/YYYY-MM-DD.json und haengt eine Zeile an
seo-log/verlauf.jsonl an. Nimmt selbst NIE Aenderungen am Blog vor.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

HIER = pathlib.Path(__file__).resolve().parent
SCHLUESSEL = HIER.parent / ".secrets" / "search-console-dienstkonto.json"
# URL-Praefix-Property, nicht Domain-Property: das Dienstkonto wurde in der
# Search-Console-Oberfluche genau unter "https://blog.brauckmann.ch/" als
# Full-User eingetragen (21.9.26), nicht unter einer sc-domain:-Property.
SITE = "https://blog.brauckmann.ch/"

SEITEN = [
    "https://blog.brauckmann.ch/",
    "https://blog.brauckmann.ch/artikel/wirtschaftskalender-ohne-anmeldung/",
    "https://blog.brauckmann.ch/artikel/netdata-homelab-monitoring-claude/",
    "https://blog.brauckmann.ch/artikel/sieben-monate-elf-umbrueche/",
]


def _client():
    cred = service_account.Credentials.from_service_account_file(
        str(SCHLUESSEL), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    return build("searchconsole", "v1", credentials=cred, cache_discovery=False)


def _suchanalyse(sc, dims: list[str], n: int = 25) -> list[dict]:
    heute = dt.date.today()
    start = heute - dt.timedelta(days=28)
    rows = sc.searchanalytics().query(siteUrl=SITE, body={
        "startDate": str(start), "endDate": str(heute),
        "dimensions": dims, "rowLimit": n}).execute().get("rows", [])
    return [{"schluessel": r.get("keys", []), "klicks": r["clicks"],
              "impressionen": r["impressions"], "ctr": round(r["ctr"], 4),
              "position": round(r["position"], 1)} for r in rows]


def _indexstatus(sc, urls: list[str]) -> dict:
    aus = {}
    for u in urls:
        try:
            res = sc.urlInspection().index().inspect(
                body={"inspectionUrl": u, "siteUrl": SITE}).execute()
            r = res["inspectionResult"]["indexStatusResult"]
            aus[u] = {"verdict": r.get("verdict"), "abdeckung": r.get("coverageState"),
                      "letzter_crawl": r.get("lastCrawlTime"),
                      "google_canonical": r.get("googleCanonical")}
        except Exception as e:  # Quota/Netzwerk -- ein Tag ohne Wert ist kein Abbruch
            aus[u] = {"fehler": str(e)[:200]}
    return aus


def main() -> int:
    if not SCHLUESSEL.exists():
        print(f"Schluessel fehlt: {SCHLUESSEL}", file=sys.stderr)
        return 1
    sc = _client()
    heute = dt.date.today().isoformat()

    sitemaps = sc.sitemaps().list(siteUrl=SITE).execute().get("sitemap", [])
    bericht = {
        "datum": heute,
        "gesamt_28t": _suchanalyse(sc, [])[:1],
        "top_anfragen": _suchanalyse(sc, ["query"]),
        "top_seiten": _suchanalyse(sc, ["page"]),
        "sitemaps": [{"pfad": m["path"], "eingereicht": m.get("lastSubmitted"),
                       "gelesen": m.get("lastDownloaded"),
                       "fehler": m.get("errors", 0), "warnungen": m.get("warnings", 0)}
                      for m in sitemaps],
        "index_status": _indexstatus(sc, SEITEN),
    }

    (HIER / f"{heute}.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=2))

    g = bericht["gesamt_28t"][0] if bericht["gesamt_28t"] else {"klicks": 0, "impressionen": 0}
    zeile = {"datum": heute, "klicks_28t": g["klicks"], "impressionen_28t": g["impressionen"],
             "indexiert": sum(1 for v in bericht["index_status"].values()
                                if v.get("abdeckung") not in (None, "URL is unknown to Google")),
             "von": len(SEITEN)}
    with (HIER / "verlauf.jsonl").open("a") as f:
        f.write(json.dumps(zeile, ensure_ascii=False) + "\n")

    print(f"{heute}: {zeile['klicks_28t']} Klicks / {zeile['impressionen_28t']} Impressionen "
          f"(28T) -- {zeile['indexiert']}/{zeile['von']} Seiten indexiert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
