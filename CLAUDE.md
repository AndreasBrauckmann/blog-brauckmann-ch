# Projekt: blog.brauckmann.ch

Statischer Blog-Generator (`scripts/build.py`) + Verteilung an Social-Kanäle
(`scripts/publish.py`, `scripts/social/*`). Details zum Aufbau: siehe
`config.yaml` (Kanal-Konfiguration) und `publish-log.md` (Verlauf).

## Social-Kanäle: Zeichenlimits

- **LinkedIn**: harte Grenze **3.000 Zeichen**. Standard ist seit 1.10.2026
  die **Kurzform mit Karte**: `config.yaml` `format: kurz`, `min_chars: 150`,
  `max_chars: 300` (ganzer Beitrag inkl. Hashtags und URL). Aufbau
  (`summarize.summarize_linkedin_kurz`): 2–3 kurze Sätze mit Haken (Slogan
  zuerst), Leerzeile, höchstens 2 Hashtags, **Artikel-URL als letzte Zeile**.
  Begründung: vor „…mehr" sind nur die ersten ~140 Zeichen (mobil) bzw. ~210
  (Desktop) sichtbar, und bei langen Beiträgen zeigte LinkedIn in der
  Profil-Übersicht **keine Link-Karte** – die Karte ist nur bei kurzem Text
  sichtbar. Die Langform (`lang_min_chars: 1200`, `lang_max_chars: 1800`)
  bleibt über den Umschalter auf der LinkedIn-Seite der Verwaltung erreichbar.
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

## Verwaltung (Redaktions-Cockpit) – `scripts/admin/`

Flask-App, systemd-Dienst `blog-verwaltung` (127.0.0.1:5151), nur über den
edge-Caddy erreichbar: LAN `http://<LAN-Adresse des Servers>:8090/verwaltung`, Tailnet
`https://<Tailnet-Name des Servers>/verwaltung`. Neustart:
`sudo -n systemctl restart blog-verwaltung` (Vorlagen werden gecacht).

Tabs: Übersicht · Deploy · Ranking · mastodon · bluesky · linkedin · reddit ·
facebook · youtube_community · microsoft_tech_community.

- **Deploy** (`deploy.py`, `deploy_views.py`): Prüfen → Bauen → Diff ansehen →
  Veröffentlichen → Live prüfen → Post Inspector abhaken. Commit/Push **nur auf
  Knopfdruck mit Bestätigung**, nur ausgewählte Pfade (`git commit --only`).
  Vorausgewählt: `articles/`, `dist/`, `templates/`, `config.yaml`,
  `CLAUDE.md`, `publish-log.md`, Bilder unter `static/img/`, die ein
  geänderter Artikel referenziert. Nur mit ausdrücklicher Auswahl: `scripts/`,
  gelöschte Dateien, alles andere. **Nie**: `manual-posts.md`, `data/`, `.env*`,
  `.secrets/`. Der geprüfte Stand wird per Fingerabdruck festgehalten; ändert
  sich danach etwas, bricht das Veröffentlichen ab. Push nur, wenn der lokale
  Stand nicht hinter `origin/master` liegt. Git-Identität/SSH-Schlüssel sind
  die des Dienstnutzers. `scripts/publish.py` committet ebenfalls nur diese
  Whitelist; die Verwaltung ruft es mit `--nur-posten` auf.
- **Eigener Inspector** (`inspector.py`): Live-Abruf als LinkedInBot,
  Pflicht-Tags, og:image (200, Typ, Größe, Maße), Canonical,
  og:image:width/height, Cache, Live = Build. Ersetzt **nicht** den LinkedIn
  Post Inspector (Menschen-Schritt, siehe oben).
- **Ranking** (`bewertung.py`, `ranking_views.py`): regelbasiert, offline;
  Kriterien und Gewichte stehen auf der Seite. Kennzeichnung „Thema verfehlt?",
  „Design schwach", Auffälligkeiten. Fundstellen per **Vale** (Binary unter
  `data/werkzeuge/vale`, Regeln in `scripts/admin/vale/styles/BlogDE`).
  textstat wird bewusst nicht genutzt (zieht nltk nach; seine deutsche
  Silbenzählung über pyphen zählt Trennstellen statt Sprechsilben) – die
  Amstad-Formel ist selbst implementiert. LanguageTool ist nicht installiert.
- **Plattformseiten** (`plattformen.py`, `plattform_views.py`,
  `kennzahlen.py`): Vorschau-Nachbau, Pflicht-Tags, Vorschläge, Beitragstext,
  Auto-Analyse (LLM), Prüfliste, Ranking je Plattform, Kennzahlen (Mastodon/
  Bluesky öffentlich lesend, sonst Formular/CSV; kein Scraping).
- **LLM** (`llm.py`): nur über `BLOG_LLM_API_KEY`/`BLOG_LLM_BASE_URL`/
  `BLOG_LLM_MODEL` in `.env` (claude-wrapper). Nur auf Knopfdruck, ändert nie
  selbst Artikel; „Metas übernehmen" schreibt erst nach Bestätigung mit Diff
  und Backup ins Frontmatter, ohne zu bauen oder zu veröffentlichen.
- **Daten nie ins Repo**: alle Laufzeitdaten (Kennzahlen, Prüflisten,
  Inspector-Ergebnisse, Lektorat, Deploy-Verlauf, Backups, Vale-Binary) liegen
  unter `data/` (in `.gitignore`). `publish-log.md` ist im Repo – dort nie
  Kennzahlen eintragen.
- Tests: `.venv/bin/python -m unittest discover -s tests` (Git-Tests nur in
  Wegwerf-Repos unter tempfile, kein Netz).
