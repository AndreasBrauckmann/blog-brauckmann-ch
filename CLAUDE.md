# Projekt: blog.brauckmann.ch

Statischer Blog-Generator (`scripts/build.py`) + Verteilung an Social-Kanäle
(`scripts/publish.py`, `scripts/social/*`). Details zum Aufbau: siehe
`config.yaml` (Kanal-Konfiguration) und `publish-log.md` (Verlauf).

## Social-Kanäle: Zeichenlimits

- **LinkedIn**: harte Grenze **3.000 Zeichen** (seit Juni 2023 unverändert,
  Stand September 2026). Nur die ersten ~210 Zeichen (Desktop) bzw. ~140
  (Mobil) werden vor "…mehr" angezeigt — der erste Satz zählt am meisten.
  Bestes Engagement laut Datenlage bei **1.300–1.900 Zeichen**.
  `config.yaml` steht auf `min_chars: 1200, max_chars: 1800` — das liegt
  bewusst in diesem Bereich, nicht am harten Limit.
- **Mastodon**: `max_chars: 480` (mastodon.social-Standard), in
  `config.yaml` hinterlegt.
- **Bluesky**: `max_chars: 290` (Sicherheitsabstand zum echten Limit von
  300 Graphemen), in `config.yaml` hinterlegt.

Bei jeder Änderung an den Post-Texten (`scripts/summarize.py`) diese
Grenzen im Kopf behalten, bevor Inhalt ergänzt wird.

## Regel: Pflicht-Meta-Tags und LinkedIn Post Inspector (verbindlich)

**1. Jeder Artikel trägt diese fünf Meta-Tags, in genau dieser Form:**

```html
<meta name="title" property="og:title" content="[Titel]">
<meta property="og:type" content="[Typ, bei Artikeln: article]">
<meta name="image" property="og:image" content="[Bild-URL]">
<meta name="description" property="og:description" content="[Beschreibung]">
<meta name="author" content="[Autor]">
```

- Sie werden **nicht von Hand** in Artikel geschrieben. Sie entstehen beim Bauen
  aus `templates/article.html` und `scripts/build.py` (Funktion
  `article_head_extras`) aus dem Frontmatter: `title`, `description`, `image`
  (sonst `thumb`) und `site.author` in `config.yaml`.
- Jeder Artikel braucht deshalb im Frontmatter mindestens `title`,
  `description` und ein Bild (`image` oder `thumb`, mit einer wirklich
  vorhandenen Datei). `build.py` prüft die fünf Tags in jeder fertigen
  Artikelseite und **bricht den Build ab**, wenn eines fehlt oder leer ist.
- Zusätzlich vorhanden (nicht ersetzen): Open-Graph-Artikelangaben
  (`article:published_time`, `article:modified_time`, `article:author`,
  `article:tag`), `og:site_name`, `og:locale`, Twitter Card, Canonical,
  Robots, Theme-Color, RSS-Hinweis und JSON-LD.
- Das `name`- und das `property`-Attribut stehen bei Titel, Bild und
  Beschreibung **in einem Tag**. Kein zweites `<meta name="description">`
  danebensetzen.

**2. Vor dem Posten muss der Autor den LinkedIn Post Inspector ausführen:**
<https://www.linkedin.com/post-inspector/>

- Reihenfolge: Artikel bauen → deployen (der Inspector kann nur öffentlich
  erreichbare Adressen prüfen) → Live-URL des Artikels im Post Inspector
  eingeben und **Inspect** drücken → prüfen, dass Titel, Bild und Beschreibung
  stimmen → **erst dann** den Beitrag auf LinkedIn posten.
- Hat LinkedIn noch eine alte Vorschau im Zwischenspeicher (nach einer
  Änderung an Titel, Bild oder Beschreibung), den Inspector erneut ausführen:
  das erneuert den Cache.
- Das ist ein Schritt des Menschen und lässt sich nicht automatisieren.
  `scripts/publish.py` erinnert daran und schreibt eine Prüfzeile in
  `manual-posts.md`; abgehakt wird sie vom Autor.
