#!/usr/bin/env python3
"""Animiertes Titelbild (1400x1400) fuer den Wirtschaftskalender-Artikel:
Kopf mit Boersenfassade und Ueberschrift, in der Mitte der Rundgang
(aus rundgang-kalender-<thema>.gif), unten drei Kennzahlen.

    ~/TradingAgents/.venv/bin/python scripts/eyecatcher_kalender.py \
        --rundgang <ordner>/rundgang-kalender-light.gif --kopf <ordner>/hdr.jpg --aus static/img
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageSequence

W = 1400
AUS = 1200   # Ausgabegroesse in Pixeln (Quadrat)
GRUEN = (164, 214, 50)
F = lambda sz, b=False: __import__("PIL.ImageFont", fromlist=["x"]).truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if b else ""), sz)

KOPF_H = 470
KASTEN_H, KASTEN_Y = 150, 1220
MITTE = (495, 1195)   # y von/bis fuer den Rundgang


def grund():
    im = Image.new("RGB", (W, W)); d = ImageDraw.Draw(im)
    for y in range(W):
        t = y / W
        d.line([(0, y), (W, y)], fill=(int(12 + 8 * t), int(24 + 12 * t), int(27 + 8 * t)))
    return im


def kopf(hdr_pfad):
    hdr = Image.open(hdr_pfad).convert("RGB")
    s = max(W / hdr.width, KOPF_H / hdr.height)
    im = hdr.resize((int(hdr.width * s) + 1, int(hdr.height * s) + 1), Image.LANCZOS)
    x = (im.width - W) // 2
    im = ImageEnhance.Brightness(im.crop((x, 0, x + W, KOPF_H))).enhance(0.42)
    d = ImageDraw.Draw(im)
    d.text((60, 120), "Wirtschaftskalender", font=F(92, True), fill=(255, 255, 255))
    d.text((62, 242), "kostenlos · ohne Login · mit KI-Recherche", font=F(40), fill=GRUEN)
    return im


# Schritt je Bild des Rundgangs (13 Bilder, 9 Schritte; 5 und 6 haben mehrere Bilder)
SCHRITTE = [1, 2, 3, 4, 5, 5, 5, 6, 6, 6, 7, 8, 9]
STICHWORTE = ["Überblick", "Termin", "Diagramm", "Historie", "Details", "Filter", "Im Chart", "Klick", "Warnung"]
BOX_Y, BOX_H, BOX_W, BOX_ABST = 352, 84, 132, 12


def boxen(im, aktiv):
    """Neun Kaestchen im Kopf: das aktive leuchtet gruen, gezeigte bleiben umrandet."""
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    x0 = (W - (9 * BOX_W + 8 * BOX_ABST)) // 2
    for i in range(9):
        n = i + 1
        x = x0 + i * (BOX_W + BOX_ABST)
        r = (x, BOX_Y, x + BOX_W, BOX_Y + BOX_H)
        if n == aktiv:
            d.rounded_rectangle((r[0] - 5, r[1] - 5, r[2] + 5, r[3] + 5), 18, fill=(164, 214, 50, 90))
            d.rounded_rectangle(r, 14, fill=(164, 214, 50, 255))
            zahl, text = (18, 28, 8), (18, 28, 8)
        elif n < aktiv:
            d.rounded_rectangle(r, 14, fill=(14, 24, 26, 215), outline=(164, 214, 50, 255), width=3)
            zahl, text = (164, 214, 50), (205, 222, 170)
        else:
            d.rounded_rectangle(r, 14, fill=(14, 24, 26, 215), outline=(90, 110, 100, 255), width=2)
            zahl, text = (150, 165, 160), (150, 165, 160)
        d.text((x + 14, BOX_Y + 6), str(n), font=F(40, True), fill=zahl)
        d.text((x + 14, BOX_Y + 56), STICHWORTE[i], font=F(19, n == aktiv), fill=text)
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def kennzahlen(im):
    d = ImageDraw.Draw(im)
    items = [("84.000+", "Termine seit 2010"), ("6", "Download-Formate"), ("0 €", "keine Anmeldung")]
    bw = (W - 120 - 60) // 3
    for i, (a, t) in enumerate(items):
        x = 60 + i * (bw + 30)
        d.rounded_rectangle((x, KASTEN_Y, x + bw, KASTEN_Y + KASTEN_H), 20, fill=(26, 40, 44),
                            outline=(60, 84, 90), width=2)
        d.text((x + 28, KASTEN_Y + 16), a, font=F(54, True), fill=GRUEN)
        d.text((x + 28, KASTEN_Y + 92), t, font=F(28), fill=(215, 225, 228))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rundgang", required=True)
    ap.add_argument("--kopf", required=True)
    ap.add_argument("--aus", required=True)
    ap.add_argument("--standbild", default="")
    a = ap.parse_args()
    basis = grund(); basis.paste(kopf(a.kopf), (0, 0)); kennzahlen(basis)
    quelle = Image.open(a.rundgang)
    hoehe = MITTE[1] - MITTE[0]
    frames, dauern = [], []
    n_frames = quelle.n_frames
    assert n_frames == len(SCHRITTE), f"{n_frames} Bilder, aber {len(SCHRITTE)} Schritt-Zuordnungen"
    for k, fr in enumerate(ImageSequence.Iterator(quelle)):
        dauern.append(fr.info.get("duration", 3000))
        f = fr.convert("RGB")
        breite = int(f.width * hoehe / f.height)
        f = f.resize((breite, hoehe), Image.LANCZOS)
        c = boxen(basis, SCHRITTE[k])
        x = (W - breite) // 2
        sh = Image.new("RGBA", (breite + 100, hoehe + 100), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((50, 60, breite + 50, hoehe + 60), 20, fill=(0, 0, 0, 170))
        sh = sh.filter(ImageFilter.GaussianBlur(18)); c.paste(sh, (x - 50, MITTE[0] - 50), sh)
        m = Image.new("L", f.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0) + f.size, 18, fill=255)
        c.paste(f, (x, MITTE[0]), m)
        frames.append(c.resize((AUS, AUS), Image.LANCZOS))
    # EINE Palette fuer alle Bilder, ohne Dithering: unveraenderte Flaechen bleiben
    # Pixel fuer Pixel gleich, und das GIF speichert nur die Unterschiede.
    kachel = 500
    mosaik = Image.new("RGB", (kachel * 4, kachel * ((len(frames) + 3) // 4)))
    for i, f in enumerate(frames):
        mosaik.paste(f.resize((kachel, kachel), Image.LANCZOS), ((i % 4) * kachel, (i // 4) * kachel))
    pal = mosaik.quantize(colors=255, method=Image.FASTOCTREE, dither=Image.NONE)
    standbilder = frames[0].copy()
    frames = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    ziel = Path(a.aus) / "wirtschaftskalender-eyecatcher-square.gif"
    frames[0].save(ziel, save_all=True, append_images=frames[1:], duration=dauern, loop=0, optimize=True)
    # erstes Bild als Standbild (Vorschau, Vergleich)
    if a.standbild:
        standbilder.save(a.standbild)
    print(ziel, len(frames), "Bilder", ziel.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
