#!/usr/bin/env python3
"""Animierter Rundgang durch den oeffentlichen Wirtschaftskalender
(brauckmann.ch/kalender/) fuer den Blogartikel "wirtschaftskalender-ohne-anmeldung".

Nimmt die LIVE-Seite mit Playwright auf (echte Daten, kein Nachbau) und zeichnet
Hervorhebung und Beschriftung mit Pillow darueber. Zwei Fassungen, hell und dunkel.

    ~/TradingAgents/.venv/bin/python scripts/rundgang_kalender.py --thema light
    ~/TradingAgents/.venv/bin/python scripts/rundgang_kalender.py --thema dark

Ausgabe: <--aus>/rundgang-kalender-<thema>.gif  (Standard: static/img)
Optional: --chart-dir mit chart-<thema>-*.png haengt die Chart-Szenen an.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

URL = "https://brauckmann.ch/kalender/"
B, H = 1200, 620
ROOT = Path(__file__).resolve().parent.parent


def font(sz: int, bold: bool = False):
    return ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""), sz)


def umbruch(d, text, f, breite):
    zeilen, z = [], ""
    for w in text.split():
        t = (z + " " + w).strip()
        if d.textlength(t, font=f) <= breite:
            z = t
        else:
            zeilen.append(z)
            z = w
    if z:
        zeilen.append(z)
    return zeilen


def beschriften(bild: Image.Image, schritt: str, titel: str, text: str, hell: bool) -> Image.Image:
    grund = (250, 250, 250) if hell else (12, 14, 20)
    ft, fx = font(24, True), font(18)
    probe = ImageDraw.Draw(bild)
    zeilen = umbruch(probe, text, fx, bild.width - 56)
    hoehe = 24 + 34 + 26 * len(zeilen) + 14
    b = Image.new("RGB", (bild.width, bild.height + hoehe), grund)
    b.paste(bild, (0, 0))
    d = ImageDraw.Draw(b)
    d.rectangle([0, bild.height, b.width, bild.height + 4], fill=(110, 170, 20))
    y = bild.height + 18
    farbe_t = (20, 23, 31) if hell else (255, 255, 255)
    farbe_x = (70, 78, 95) if hell else (200, 206, 218)
    d.text((28, y), f"{schritt}  {titel}", font=ft, fill=farbe_t)
    for i, z in enumerate(zeilen):
        d.text((28, y + 40 + 26 * i), z, font=fx, fill=farbe_x)
    return b


def hervorheben(bild: Image.Image, kasten, abdunkeln: bool = True) -> Image.Image:
    x1, y1, x2, y2 = [int(v) for v in kasten]
    x1, y1, x2, y2 = max(x1 - 6, 0), max(y1 - 6, 0), min(x2 + 6, bild.width), min(y2 + 6, bild.height)
    b = bild.convert("RGBA")
    if abdunkeln:
        schleier = Image.new("RGBA", b.size, (8, 10, 14, 55))
        ImageDraw.Draw(schleier).rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 0))
        b = Image.alpha_composite(b, schleier)
    b = b.convert("RGB")
    ImageDraw.Draw(b).rectangle([x1, y1, x2, y2], outline=(110, 170, 20), width=4)
    return b


def zoom(hi: Image.Image, kasten, faktor: float) -> Image.Image:
    """Ausschnitt aus dem 2x-Bild, mittig auf dem Kasten, auf Bildgroesse."""
    x1, y1, x2, y2 = [int(v * 2) for v in kasten]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    w, h = int(2 * B / faktor), int(2 * H / faktor)
    l = min(max(cx - w // 2, 0), hi.width - w)
    t = min(max(cy - h // 2, 0), hi.height - h)
    return hi.crop((l, t, l + w, t + h)).resize((B, H), Image.LANCZOS)


def passend(hi: Image.Image, kasten, breite: int, hell: bool, pad: int = 24) -> Image.Image:
    """Ausschnitt (CSS-Koordinaten) scharf aus dem 2x-Bild, proportional auf ``breite``,
    mittig auf einer Leinwand in Seitenfarbe. Nie verzerrt."""
    x1, y1, x2, y2 = kasten
    box = [int(v * 2) for v in (max(x1 - pad, 0), max(y1 - pad, 0), min(x2 + pad, B), min(y2 + pad, H))]
    c = hi.crop(box)
    f = breite / c.width
    c = c.resize((breite, int(c.height * f)), Image.LANCZOS)
    if c.height > H - 20:
        f = (H - 20) / c.height
        c = c.resize((int(c.width * f), H - 20), Image.LANCZOS)
    leinwand = Image.new("RGB", (B, H), (250, 250, 250) if hell else (12, 14, 20))
    leinwand.paste(c, ((B - c.width) // 2, (H - c.height) // 2))
    ImageDraw.Draw(leinwand).rectangle([(B - c.width) // 2, (H - c.height) // 2,
                                        (B + c.width) // 2, (H + c.height) // 2],
                                       outline=(110, 170, 20), width=3)
    return leinwand


def kasten_von(el):
    r = el.bounding_box()
    return (r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])


def aufnehmen(thema: str):
    hell = thema == "light"
    frames: list[tuple[Image.Image, int]] = []

    def knips(page):
        from io import BytesIO
        return Image.open(BytesIO(page.screenshot())).convert("RGB")

    def klein(hi):
        return hi.resize((B, H), Image.LANCZOS)

    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": B, "height": H}, color_scheme=thema, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(URL, wait_until="networkidle")
        pg.evaluate("document.documentElement.setAttribute('data-kalender-thema','%s')"
                    % ("hell" if hell else "dunkel"))
        pg.wait_for_timeout(800)

        # 1 Uebersicht: ein Tag mit seinen Terminen (nur der erste Tagesblock). Kurz: der Einstieg
        # muss sofort weitergehen, sonst ist der Leser schon weitergescrollt.
        pg.evaluate("document.querySelector('table thead').scrollIntoView({block:'start'})")
        pg.evaluate("window.scrollBy(0, -130)")
        pg.wait_for_timeout(500)
        bild = klein(knips(pg))
        tage = pg.locator("tr.k-tag-zeile")
        k1 = kasten_von(tage.first)
        k2 = kasten_von(tage.nth(1))
        tagname = tage.first.inner_text().strip()
        frames.append((beschriften(hervorheben(bild, (k1[0], k1[1], k1[2], k2[1] - 1), abdunkeln=False), "1/9",
                                   "Alle Termine eines Tages auf einen Blick",
                                   f"{tagname}: Zeit, Währung, Wichtigkeit, Ist, Prognose, Vorherig. Drei Punkte = hohe Wichtigkeit.",
                                   hell), 1300))

        # 2 Termin aufklappen
        ziel = pg.locator("tr.k-termin-zeile", has_text="Unemployment Rate").first
        ziel.click()
        pg.wait_for_timeout(1500)
        pg.evaluate("""(()=>{const z=[...document.querySelectorAll('tr.k-termin-zeile')].find(r=>r.innerText.includes('Unemployment Rate'));
                       window.scrollTo(0, z.getBoundingClientRect().top + window.scrollY - 120);})()""")
        pg.wait_for_timeout(600)
        hi = knips(pg)
        bild = klein(hi)
        ks = kasten_von(pg.locator(".k-detail-spark").first)
        frames.append((beschriften(bild, "2/9", "Ein Klick öffnet den Termin",
                                   "Hier die US-Arbeitslosenquote: links die Fakten, rechts das Diagramm, darunter die Historie.", hell), 2600))

        # 3 Diagramm einzoomen
        frames.append((beschriften(passend(hi, ks, 900, hell, pad=14), "3/9", "Ist und Prognose im Vergleich",
                                   "Blau der tatsächliche Wert (Ist), grau gestrichelt die Prognose. Beide Linien laufen meist dicht beieinander.",
                                   hell), 3400))

        # 4 Historie
        pg.evaluate("document.querySelector('.k-detail-zeile table').scrollIntoView({block:'start'})")
        pg.evaluate("window.scrollBy(0, -110)")
        pg.wait_for_timeout(500)
        bild = klein(knips(pg))
        kt = kasten_von(pg.locator(".k-detail-zeile table").first)
        frames.append((beschriften(hervorheben(bild, (kt[0], max(kt[1], 0), kt[2], min(kt[3], H - 4))), "4/9",
                                   "Auch die Historie ist da",
                                   "Jede frühere Veröffentlichung mit Ist, Prognose und Vorherig, zurück bis 2010. Man sieht sofort, wie gut die Prognosen trafen.",
                                   hell), 3400))

        # 5 Nachlesen / Originalquelle / Kategorie
        pg.evaluate("document.querySelector('.k-detail-zeile .k-detail-fakten').scrollIntoView({block:'start'})")
        pg.evaluate("window.scrollBy(0, -130)")
        pg.wait_for_timeout(500)
        bild = klein(knips(pg))
        fakten = pg.locator(".k-detail-zeile .k-detail-fakten").first
        gesucht = {}
        for dt in fakten.locator("dt").all():
            gesucht[dt.inner_text().strip()] = (dt, dt.locator("xpath=following-sibling::dd[1]"))

        def zeile(name):
            dt, dd = gesucht[name]
            a_, c_ = kasten_von(dt), kasten_von(dd)
            return (a_[0], min(a_[1], c_[1]), max(a_[2], c_[2]), max(a_[3], c_[3]))
        frames.append((beschriften(hervorheben(bild, zeile("Nachlesen")), "5/9", "Nachlesen",
                                   "Ein Klick startet die KI-Recherche zum Termin: Überblick, Verlauf, Prognose und Marktwirkung.", hell), 2600))
        frames.append((beschriften(hervorheben(bild, zeile("Originalquelle")), "5/9", "Originalquelle",
                                   "Der Link führt direkt zur amtlichen Stelle, hier dem US-Arbeitsministerium (BLS). Die Zahl lässt sich nachprüfen.", hell), 2600))
        frames.append((beschriften(hervorheben(bild, zeile("Kategorie")), "5/9", "Kategorie",
                                   "Sagt, was der Termin misst, hier der Arbeitsmarkt: Beschäftigung, Arbeitslosenquote, Löhne, Erstanträge.", hell), 2600))

        # 6 Sortieren und filtern (Spaltenmenue)
        pg.evaluate("document.querySelector('table thead').scrollIntoView({block:'start'})")
        pg.evaluate("window.scrollBy(0, -260)")
        pg.wait_for_timeout(400)
        th_w = pg.locator("th", has_text="Wichtigkeit").first
        th_w.click()
        pg.wait_for_timeout(800)
        bild = klein(knips(pg))
        frames.append((beschriften(hervorheben(bild, kasten_von(th_w)),
                                   "6/9", "Nach Wichtigkeit sortieren und filtern",
                                   "Jede Spalte hat ein Menü: sortieren, oder zum Beispiel nur die wichtigsten Termine („Hoch“) zeigen.", hell), 3000))
        for name in ("Mittel", "Niedrig"):
            pg.get_by_label(name, exact=True).first.uncheck()
        pg.get_by_role("button", name="Anwenden").last.click()
        pg.wait_for_timeout(1200)
        pg.evaluate("document.querySelector('table thead').scrollIntoView({block:'start'})")
        pg.evaluate("window.scrollBy(0, -250)")
        pg.wait_for_timeout(500)
        hi = knips(pg)
        kt = kasten_von(pg.locator("table").first)
        seite = klein(hi)
        weiss = Image.new("RGB", (B, H), (250, 250, 250) if hell else (12, 14, 20))
        grenze = int(kt[3] + 30)
        weiss.paste(seite.crop((0, 0, B, grenze)), (0, 0))   # Seitenfuss abschneiden
        frames.append((beschriften(hervorheben(weiss, (kt[0], kt[1], kt[2], kt[3]), abdunkeln=False),
                                   "6/9", "Nur wichtige Termine",
                                   "Mit dem Filter „Hoch“ bleiben nur die drei Termine mit der größten Marktwirkung stehen.", hell), 3000))
        pg.evaluate("document.querySelector('table thead').scrollIntoView({block:'start'})")
        pg.evaluate("window.scrollBy(0, -260)")
        pg.wait_for_timeout(300)
        th_c = pg.locator("th", has_text="Währung").first
        th_c.click()
        pg.wait_for_timeout(800)
        bild = klein(knips(pg))
        frames.append((beschriften(hervorheben(bild, kasten_von(th_c)), "6/9", "Oder nach Währung",
                                   "Ein Haken pro Währung: nur USD, nur EUR oder CHF, oder beliebig kombiniert.", hell), 2400))
        br.close()
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thema", default="light", choices=("light", "dark"))
    ap.add_argument("--aus", default=str(ROOT / "static" / "img"))
    ap.add_argument("--chart-dir", default="")
    a = ap.parse_args()
    frames = aufnehmen(a.thema)
    if a.chart_dir:
        for pfad in sorted(Path(a.chart_dir).glob(f"chart-{a.thema}-*.png")):
            frames.append((Image.open(pfad).convert("RGB"), 4500))
    breite = max(f.width for f, _ in frames)
    hoehe = max(f.height for f, _ in frames)
    hell = a.thema == "light"
    grund = (250, 250, 250) if hell else (12, 14, 20)
    norm = []
    for f, _ in frames:
        c = Image.new("RGB", (breite, hoehe), grund)
        c.paste(f, (0, 0))
        norm.append(c.convert("P", palette=Image.ADAPTIVE, colors=128))
    ziel = Path(a.aus) / f"rundgang-kalender-{a.thema}.gif"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    norm[0].save(ziel, save_all=True, append_images=norm[1:], duration=[d for _, d in frames],
                 loop=0, optimize=True)
    print(f"{ziel}  {len(norm)} Bilder  {ziel.stat().st_size // 1024} KB  {breite}x{hoehe}")


if __name__ == "__main__":
    main()
