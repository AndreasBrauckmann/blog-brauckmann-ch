#!/usr/bin/env python3
"""Titelbild (1200x630) und Vorschaubild (480x480) fuer den Entwurf „Quick-Redaktor und Blog-Verwaltung“.
Stil wie scripts/eyecatcher_kalender.py (dunkler Verlauf, Gruen als Akzent, DejaVu). Schematisch, kein Bildschirmfoto:
links ein Beitragstext mit roten (gestrichen) und gruenen (neu) Markierungen, rechts drei Kennzahlen aus dem Probelauf.

    ~/TradingAgents/.venv/bin/python scripts/eyecatcher_redaktor.py --aus static/img
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GRUEN = (164, 214, 50)
ROT = (235, 110, 100)
HELL = (225, 232, 235)
GEDAEMPFT = (150, 168, 172)


def F(sz, fett=False):
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if fett else ""), sz)


def grund(w, h):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(12 + 8 * t), int(24 + 12 * t), int(27 + 8 * t)))
    return im


def zeile(d, x, y, teile, sz=25):
    """teile = [(text, art)] mit art gleich|weg|neu."""
    for text, art in teile:
        f = F(sz, art == "neu")
        farbe = {"gleich": HELL, "weg": ROT, "neu": GRUEN}[art]
        breite = d.textlength(text, font=f)
        if art == "weg":
            d.text((x, y), text, font=f, fill=farbe)
            d.line([(x, y + sz * 0.62), (x + breite, y + sz * 0.62)], fill=farbe, width=3)
        elif art == "neu":
            d.rounded_rectangle((x - 4, y - 2, x + breite + 4, y + sz + 6), 6, fill=(30, 58, 34))
            d.text((x, y), text, font=f, fill=farbe)
        else:
            d.text((x, y), text, font=f, fill=farbe)
        x += breite


def titelbild() -> Image.Image:
    w, h = 1200, 630
    im = grund(w, h)
    d = ImageDraw.Draw(im)
    d.text((60, 46), "Quick-Redaktor", font=F(72, True), fill=(255, 255, 255))
    d.text((63, 136), "LinkedIn-Beitrag prüfen, behutsam verbessern", font=F(32), fill=GRUEN)
    # Beitragskarte
    d.rounded_rectangle((60, 214, 760, 570), 22, fill=(26, 40, 44), outline=(60, 84, 90), width=2)
    y = 246
    for teile in (
        [("Kurz vorweg ", "weg"), ("– ", "weg"), ("14 VMs in die Cloud", "neu")],
        [("migriert. ", "gleich"), ("Es war wirklich ", "weg"), ("Lange Abende,", "neu")],
        [("viele Erkenntnisse. ", "gleich"), ("https://…", "neu")],
        [("", "gleich")],
        [("#Cloud #Migration #DevOps", "gleich")],
        [("#Innovation #Leadership …", "weg")],
    ):
        zeile(d, 92, y, teile)
        y += 44
    # Kennzahlen
    items = [("61 → 94", "Punkte im Probelauf"), ("8 → 3", "Hashtags"), ("0", "gespeicherte Texte")]
    for i, (a, t) in enumerate(items):
        y0 = 214 + i * 124
        d.rounded_rectangle((800, y0, 1140, y0 + 108), 20, fill=(26, 40, 44), outline=(60, 84, 90), width=2)
        d.text((826, y0 + 10), a, font=F(48, True), fill=GRUEN)
        d.text((828, y0 + 70), t, font=F(24), fill=HELL)
    return im


def vorschau() -> Image.Image:
    s = 480
    im = grund(s, s)
    d = ImageDraw.Draw(im)
    d.text((34, 40), "Quick-", font=F(64, True), fill=(255, 255, 255))
    d.text((34, 112), "Redaktor", font=F(64, True), fill=(255, 255, 255))
    zeile(d, 36, 226, [("Kurz vorweg", "weg")], 34)
    zeile(d, 36, 280, [("14 VMs migriert", "neu")], 34)
    d.text((36, 372), "61 → 94 Punkte", font=F(40, True), fill=GRUEN)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aus", required=True)
    a = ap.parse_args()
    aus = Path(a.aus)
    titelbild().save(aus / "og-quick-redaktor.jpg", quality=88, optimize=True)
    vorschau().save(aus / "thumbs" / "quick-redaktor-und-blog-verwaltung.jpg", quality=88, optimize=True)


if __name__ == "__main__":
    main()
