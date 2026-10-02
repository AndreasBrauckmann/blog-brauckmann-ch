#!/usr/bin/env python3
"""Messlauf fuer „Satz & Layout“ (wird von satzmessung.py als Unterprozess gestartet).

Laeuft mit dem Python, das Playwright installiert hat (BLOG_PLAYWRIGHT_PYTHON, Vorgabe: ~/TradingAgents/.venv/bin/python),
nicht im Venv der Verwaltung. Oeffnet die GEBAUTE Seite (dist/artikel/<slug>/index.html) in vier Zustaenden
(Desktop 1280 / Handy 393, hell / dunkel), misst deterministisch den Satz des Artikels und gibt JSON auf stdout aus.
Optional: --css <Datei> legt zusaetzliches CSS (Entwurf) ueber die Seite, ohne etwas zu aendern;
--bilder <Ordner> --praefix <name> speichert Bildschirmfotos (Kopf des Artikels und Textstelle).

Gemessen wird nur der Satz der Artikel (Fliesstext, Ueberschriften, Listen, Tabellen) - keine Seitenraender, keine Hauptseite.
"""

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ZUSTAENDE = [("hell", "desktop", 1280, 900), ("hell", "handy", 393, 800), ("dunkel", "desktop", 1280, 900), ("dunkel", "handy", 393, 800)]

JS = r"""() => {
  const q = (s) => document.querySelector(s);
  const cs = (e) => e ? getComputedStyle(e) : null;
  const px = (v) => parseFloat(v) || 0;
  const art = q('article') || document.body;
  const absaetze = [...art.querySelectorAll('p')].filter(p => !p.closest('figure, table, .callout, .kr-radar, pre, svg, details'));
  const lang = absaetze.sort((a, b) => b.textContent.length - a.textContent.length)[0] || art.querySelector('p');
  const sp = cs(lang);
  const lhPx = sp.lineHeight === 'normal' ? px(sp.fontSize) * 1.2 : px(sp.lineHeight);
  const c = document.createElement('canvas').getContext('2d');
  c.font = sp.fontWeight + ' ' + sp.fontSize + ' ' + sp.fontFamily;
  // mittlere Zeichenbreite am echten Text (Canvas-Messung), daraus Zeichen je Zeile
  const textBreite = c.measureText(lang.textContent.replace(/\s+/g, ' ')).width / Math.max(1, lang.textContent.replace(/\s+/g, ' ').length);
  const inhaltsbreite = lang.clientWidth - px(sp.paddingLeft) - px(sp.paddingRight);
  const lum = (rgb) => { const m = rgb.match(/[\d.]+/g).map(Number).slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
  const bgOf = (e) => { while (e) { const b = getComputedStyle(e).backgroundColor; if (b && !/rgba\(0, 0, 0, 0\)|transparent/.test(b)) return b; e = e.parentElement; } return 'rgb(255, 255, 255)'; };
  const kontrast = (e) => { if (!e) return null; const a = lum(cs(e).color), b = lum(bgOf(e)); return +((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(2); };
  const link = art.querySelector('p a, li a');
  const gedaempft = q('.teaser') || q('time.article-date') || q('footer.site-footer') || q('.tags');
  const h1 = q('h1'), h2 = art.querySelector('h2'), h3 = art.querySelector('h3');
  const hm = (e) => { if (!e) return null; const s = cs(e); const l = s.lineHeight === 'normal' ? px(s.fontSize) * 1.2 : px(s.lineHeight);
    return {px: px(s.fontSize), lh: l, mt: px(s.marginTop), mb: px(s.marginBottom), zeilen: Math.max(1, Math.round(e.getBoundingClientRect().height / l))}; };
  const vw = document.documentElement.clientWidth;
  const ownScroll = (e) => { let p = e.parentElement; while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; p = p.parentElement; } return false; };
  const breite = {tabellen_frei: 0, tabellen_box: 0, code_frei: 0, code_box: 0, bilder: 0};
  art.querySelectorAll('table').forEach(t => { if (t.getBoundingClientRect().width > vw + 1) { ownScroll(t) ? breite.tabellen_box++ : breite.tabellen_frei++; } });
  art.querySelectorAll('pre').forEach(t => { if (t.scrollWidth > vw + 1 || t.getBoundingClientRect().width > vw + 1) { (ownScroll(t) || getComputedStyle(t).overflowX !== 'visible') ? breite.code_box++ : breite.code_frei++; } });
  art.querySelectorAll('img').forEach(i => { if (i.getBoundingClientRect().width > vw + 1) breite.bilder++; });
  const li = art.querySelector('ul li, ol li'), ul = li ? li.parentElement : null;
  const liS = li ? cs(li) : null, ulS = ul ? cs(ul) : null;
  const liLh = li ? (liS.lineHeight === 'normal' ? px(liS.fontSize) * 1.2 : px(liS.lineHeight)) : 0;
  return {
    schrift_px: px(sp.fontSize), zeilenhoehe: +(lhPx / px(sp.fontSize)).toFixed(3), absatz_abstand_zeilen: +(px(sp.marginBottom) / lhPx).toFixed(3),
    spaltenbreite_px: Math.round(inhaltsbreite), zeichen_je_zeile: Math.round(inhaltsbreite / textBreite),
    kontrast_text: kontrast(lang), kontrast_link: kontrast(link), kontrast_gedaempft: kontrast(gedaempft),
    h1: hm(h1), h2: hm(h2), h3: hm(h3), absatz_mb: px(sp.marginBottom),
    seite_ueberlauf: document.documentElement.scrollWidth > vw + 1, breite: breite,
    liste: li ? {einzug_em: +(px(ulS.paddingLeft) / px(liS.fontSize)).toFixed(2), abstand_zeilen: +(Math.max(px(liS.marginTop), px(liS.marginBottom)) / liLh).toFixed(3)} : null,
    bilder_gesamt: art.querySelectorAll('img').length, bilder_ohne_alt: [...art.querySelectorAll('img')].filter(i => !(i.getAttribute('alt') || '').trim()).length,
  };
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seite")
    ap.add_argument("--css")
    ap.add_argument("--bilder")
    ap.add_argument("--praefix", default="satz")
    a = ap.parse_args()
    url = Path(a.seite).resolve().as_uri()
    extra = Path(a.css).read_text(encoding="utf-8") if a.css else ""
    erg = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for schema, geraet, w, h in ZUSTAENDE:
            ctx = br.new_context(viewport={"width": w, "height": h}, color_scheme="light" if schema == "hell" else "dark")
            pg = ctx.new_page()
            pg.goto(url, wait_until="load")
            if extra:
                pg.add_style_tag(content=extra)
            pg.wait_for_timeout(250)
            erg[f"{schema}|{geraet}"] = pg.evaluate(JS)
            if a.bilder:
                ordner = Path(a.bilder)
                ordner.mkdir(parents=True, exist_ok=True)
                pg.evaluate("window.scrollTo(0, 0)")
                pg.screenshot(path=str(ordner / f"{a.praefix}-{schema}-{geraet}-kopf.png"))
                pg.evaluate("(() => { const h = document.querySelector('article h2'); if (h) h.scrollIntoView(); })()")
                pg.screenshot(path=str(ordner / f"{a.praefix}-{schema}-{geraet}-text.png"))
            ctx.close()
        br.close()
    json.dump({"kontexte": erg}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
