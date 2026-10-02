#!/usr/bin/env python3
"""Chart-Szenen fuer den Kalender-Rundgang (Schritte 7-9): das Modul
"Makrodaten im Chart" in Kontor, aufgenommen in der Demo-Instanz ``kontor-tour``
(/kontor/auth/demo, nur lesend, keine echten Konten).

Kerzen: frische H4-Daten aus ``--kerzen`` (JSON, aufgenommen mit
scripts/tour_daten/aufnehmen.py im TradingAgents-Repo), Termine: echte
Schnittstelle der Demo-Instanz. Die Demo-Position wird nur im Browser
ausgeblendet; es wird nichts gespeichert.

    ~/TradingAgents/.venv/bin/python scripts/rundgang_chart.py --thema light \
        --kerzen xagusd-h4-neu.json --aus <ordner>
"""
from __future__ import annotations

import argparse, calendar, json, re, sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.home() / "TradingAgents" / "scripts"))
import rundgang_kalender as rk  # noqa: E402
import build_tour as bt         # noqa: E402

B, H = rk.B, rk.H
TAG = (0, 48, 898, 720)          # Chart-Flaeche in CSS-Pixeln (ohne rechte Spalte)


def chart_bild(hi, marke=None, hell=True):
    f = H / (TAG[3] - TAG[1])
    crop = hi.crop(TAG).resize((int((TAG[2] - TAG[0]) * f), H), Image.LANCZOS)
    grund = (250, 250, 250) if hell else (12, 14, 20)
    leinwand = Image.new("RGB", (B, H), grund)
    off = (B - crop.width) // 2
    leinwand.paste(crop, (off, 0))
    if marke:
        x, y = marke
        mx, my = off + (x - TAG[0]) * f, (y - TAG[1]) * f
        leinwand = rk.hervorheben(leinwand, (mx - 16, my - 16, mx + 16, my + 16), abdunkeln=False)
    return leinwand


def aufnehmen(thema, kerzen, aus):
    hell = thema == "light"
    daten = json.load(open(kerzen))
    bt._aufnahme = lambda: daten
    aus.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 1240, "height": 744}, device_scale_factor=1)
        pg = ctx.new_page()

        def handler(route):
            d = bt.attrappe(route.request.url)
            if d is None:
                return route.continue_()
            route.fulfill(status=200, content_type="application/json", body=json.dumps(d))
        pg.route(re.compile(r".*/(udf/symbols|udf/history).*|.*/kontor/api/quote/.*"), handler)
        pg.goto("http://127.0.0.1:8021/kontor/auth/demo", wait_until="load")
        pg.evaluate(f"localStorage.setItem('kontor-theme','{thema}');"
                    "localStorage.setItem('kontor-news-wirtschaftsdaten',JSON.stringify({impact:{High:true,Medium:false,Low:false},alte:false}))")
        pg.reload(wait_until="load"); pg.wait_for_timeout(6000)
        pg.evaluate('tvWidget.activeChart().setResolution("240")'); pg.wait_for_timeout(4000)
        pg.evaluate("refreshNews('XAGUSD')"); pg.wait_for_timeout(2500)
        # ACHTUNG: kein tvWidget.changeTheme() aufrufen. Das Chart-Layout wird serverseitig je
        # Konto gespeichert, die Demo-Instanz bliebe dauerhaft im anderen Stil (8.10.2026 passiert).
        pg.evaluate("syncPositionLines=()=>{}; redrawTrades=()=>{}; try{eraseAllTrades()}catch(e){}; try{Object.keys(_posLines).forEach(_removePositionLine)}catch(e){}")
        pg.evaluate("""()=>{const ch=tvWidget.activeChart(); ch.getAllShapes().forEach(s=>{try{ch.removeEntity(s.id)}catch(e){}})}""")
        a, b = calendar.timegm((2026, 9, 22, 0, 0, 0)), calendar.timegm((2026, 10, 5, 0, 0, 0))
        pg.evaluate(f"tvWidget.activeChart().setVisibleRange({{from:{a},to:{b}}})"); pg.wait_for_timeout(3000)
        from io import BytesIO
        shot = lambda: Image.open(BytesIO(pg.screenshot())).convert("RGB")
        marke = (657, 677)

        hi = shot()
        r1 = rk.beschriften(chart_bild(hi, marke, hell), "7/9", "Derselbe Kalender im Chart",
                            "Im Kontor-Chart sitzt das Modul „Makrodaten im Chart“. Die rote 3 auf der Zeitleiste steht für drei wichtige Termine am Freitag, 2. Oktober.", hell)
        pg.mouse.move(*marke); pg.mouse.click(*marke); pg.wait_for_timeout(1800)
        hi2 = shot()
        r2 = rk.beschriften(chart_bild(hi2, None, hell), "8/9", "Ein Klick zeigt die drei Termine",
                            "Durchschnittslöhne, Non-Farm Payrolls und Arbeitslosenquote, jeweils mit Prognose und Vorwert. Der Chart bleibt dabei offen, kein Tab-Wechsel.", hell)
                # Hinweis des Moduls (Kopf der rechten Spalte), im Zusammenhang mit dem Chart
        pg.evaluate("try{closeNewsPopup()}catch(e){}"); pg.wait_for_timeout(600); hi2 = shot()
        voll = hi2.resize((B, int(hi2.height * B / hi2.width)), Image.LANCZOS)
        fs = B / hi2.width
        voll = rk.hervorheben(voll, (908 * fs, 90 * fs, 1232 * fs, 134 * fs), abdunkeln=False)
        leinwand = Image.new("RGB", (B, H), (250, 250, 250) if hell else (12, 14, 20))
        leinwand.paste(voll, (0, 0))
        r3 = rk.beschriften(leinwand, "9/9", "Der Chart sagt vorher Bescheid",
                            "Kurz vor einem wichtigen Termin meldet Kontor die „nächste News“ mit Restzeit. Der Analyse-Agent kennt dieselben Termine und rät in diesem Zeitfenster bewusst vom Traden ab.", hell)
        br.close()
    for i, fr in enumerate((r1, r2, r3), 1):
        fr.save(aus / f"chart-{thema}-{i}.png")
    print("Chart-Szenen:", aus)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--thema", default="light", choices=("light", "dark"))
    ap.add_argument("--kerzen", required=True)
    ap.add_argument("--aus", required=True)
    a = ap.parse_args()
    aufnehmen(a.thema, a.kerzen, Path(a.aus))
