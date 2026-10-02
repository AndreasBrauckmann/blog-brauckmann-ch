# Projekt: blog.brauckmann.ch

Statischer Blog-Generator (`scripts/build.py`) + Verteilung an Social-Kanäle
(`scripts/publish.py`, `scripts/social/*`). Details zum Aufbau: siehe
`config.yaml` (Kanal-Konfiguration) und `publish-log.md` (Verlauf).

## Social-Kanäle: Zeichenlimits

- **LinkedIn**: harte Grenze **3.000 Zeichen**. Standard ist seit 1.10.2026
  die **Kurzform mit Karte**: `config.yaml` `format: kurz`, `min_chars: 150`,
  `max_chars: 300` (ganzer Beitrag inkl. Hashtags und URL). Aufbau
  (`summarize.summarize_linkedin_kurz`): 2–3 kurze Sätze mit Haken (Slogan
  zuerst), Leerzeile, höchstens 2 Hashtags, **Artikel-URL direkt hinter dem Text (selber Absatz), Hashtags als letzte Zeile**.
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
- **Alles in Ordnung bringen** (`in_ordnung.py`, `in_ordnung_views.py`,
  `metas_auswahl.py`): Knopf im Kopf der Ranking-Detailseite. Hintergrundauftrag
  (Sperre je Artikel) erzeugt nur Vorschläge (Lektorat, Metas, Textstellen) mit
  programmatischer Schutzprüfung (URLs, Bilder, Code, Überschriften, Zahlen) und
  Grenzprüfung der Metas (Titel 40–70, Beschreibung 120–160, Alt 60–160). Erst
  „Übernehmen“ nach Bestätigung schreibt: Backup nach `data/backups/artikel/`,
  schreiben, `scripts/build.py`, bei Fehler automatisch zurückspielen; danach
  Vorher/Nachher-Bewertung. Nie committen/pushen. „Weiter zum Veröffentlichen“
  öffnet `/verwaltung/deploy?artikel=<slug>` mit Vorauswahl nur dieses Artikels.
- **Daten nie ins Repo**: alle Laufzeitdaten (Kennzahlen, Prüflisten,
  Inspector-Ergebnisse, Lektorat, Deploy-Verlauf, Backups, Vale-Binary) liegen
  unter `data/` (in `.gitignore`). `publish-log.md` ist im Repo – dort nie
  Kennzahlen eintragen.
- Tests: `.venv/bin/python -m unittest discover -s tests` (Git-Tests nur in
  Wegwerf-Repos unter tempfile, kein Netz).

## Regel: Titel und Beschreibung lesen sich in einem Guss (verbindlich)

**Die Beschreibung (`description` / `og:description`) setzt den Titel fort. Sie wiederholt
keine Zahl, kein Schlüsselwort und keine Wortfolge aus dem Titel.** Titel und Beschreibung
hintereinander gelesen ergeben einen flüssigen Text. **Keine Auslassungspunkte („…") am Anfang
der Beschreibung, weder im Text noch in der Vorschau.**

- Schlecht: Titel „Wirtschaftskalender: 84.000 Termine, kostenlos, ohne Login", Beschreibung
  „Über 84.000 Konjunkturtermine seit 2010, ohne Login: …" (Zahl und „ohne Login" doppelt).
- Gut: Titel „Wirtschaftskalender: 84.000 Termine, kostenlos, ohne Login", Beschreibung
  „Seit 2010 mit kostenloser API, sechs Download-Formaten und KI-Recherche per Klick; jeder
  Termin verlinkt zur Originalquelle."
- Grenzen unverändert: Titel 40–70, Beschreibung 120–160 Zeichen, Haken in den ersten ~90
  Zeichen der Beschreibung.
- **Gilt überall, wo ein Titel oder eine Beschreibung entsteht:** Vorschläge der KI (Metas
  optimieren, „Alles in Ordnung bringen"), von Hand geschriebene Texte, neue Artikel und die
  Prüfung beim Bauen. Ein Vorschlag, der den Titel wiederholt, wird nicht empfohlen und nicht
  vorgewählt; beim Bauen und im Ranking (Teilnote A) erscheint ein Hinweis.
- Wer neue Artikel schreibt oder ändert (auch Claude), prüft Titel und Beschreibung gemeinsam
  und formuliert die Beschreibung als Fortsetzung, nicht als zweiten Anfang.

**Umsetzung (Stand 1.10.2026):**

- Die Messung steht an genau einer Stelle: `scripts/titel_beschreibung.py`,
  `ueberschneidung(titel, beschreibung) -> {wiederholt, ok, hinweis}` (keine Abhängigkeiten, kein
  Flask). Sie wird von `scripts/build.py` (Warnung, nie Abbruch), `scripts/admin/bewertung.py`
  (Kriterium `a_guss`, Teilnote A), `scripts/admin/metas_auswahl.py` (Grenzprüfung, Auswahl-Seite)
  und der Live-Route `/verwaltung/ranking/ueberschneidung` genutzt.
- Schwellen: eine gemeinsame Zahl mit mindestens zwei Ziffern, **oder** mindestens 2 gemeinsame
  bedeutungstragende Wörter (kein Stoppwort, ab 4 Buchstaben, grob auf den Stamm gekürzt), **oder**
  eine gemeinsame Wortfolge ab 2 Wörtern mit einem bedeutungstragenden Wort.
- Führende Auslassungspunkte in LLM-Vorschlägen werden vor dem Messen entfernt
  (`titel_beschreibung.bereinige`); Beschreibungen beginnen normal mit einem Großbuchstaben.
- Ranking: `a_guss` (2 Punkte) wurde aus „Beschreibungslänge" und „Haken vorn" (je 3 → 2)
  umverteilt; die Kategoriegewichte (A = 25) sind unverändert.
- Die LLM-Prompts (`llm.METAS_SYSTEM`, `llm.metas_prompt`, die Nachfragen in
  `metas_auswahl.anfordern`, bis zu zwei Runden mit gemessener Überlänge) enthalten die Regel mit
  Beispiel; „Alles in Ordnung bringen" nutzt dieselben Funktionen.

## Modellwahl nach Aufgabe (Regel)

Regel des Nutzers (1.10.2026): Das Modell richtet sich nach der Aufgabe, nicht nach Gewohnheit.
Reicht das Standardmodell erkennbar nicht, wird eine Stufe höher gegangen.

| Aufgabe | Stufe | Modell |
|---|---|---|
| Mechanisch (Umbenennen, Formatieren, Zählen, Sortieren) | einfach | Haiku |
| Standardumsetzung, Metas-Vorschläge, Plattformtexte, Link-Vorschläge | Standard | Sonnet |
| Lektorat, Textüberarbeitung, Abwägen, Gegenlesen, Architektur, Korrektheit | stark | Opus |
| Tiefenrecherche mit Quellenbewertung, große Analysen, komplexe Grafiken oder Animationen | höchste | Fable, sonst Opus |

- **Eskalation:** Besteht ein Ergebnis die programmatische Prüfung zweimal nicht (ungültiges JSON,
  Schutzprüfung, Grenzen), wird mit der nächsthöheren Stufe wiederholt.
- **Verwaltung:** Die Stufen stehen in `.env` (`BLOG_LLM_MODEL` = Standard, `BLOG_LLM_MODEL_STARK`,
  `BLOG_LLM_MODEL_MAX`). Der Wrapper bietet derzeit höchstens Opus 4.6 an (Stand 1.10.2026);
  fehlt eine Stufe, gilt die nächstniedrigere.
- **Claude-Sitzungen:** Teilaufgaben an Unteragenten werden nach derselben Tabelle vergeben.

**Umsetzung der Modellwahl in der Verwaltung (Stand 1.10.2026):**

- `scripts/admin/llm.py`: `modell_fuer(aufgabe)` und `eskalations_modell(aufgabe)`; `chat()`/`chat_json()` nehmen
  `aufgabe=` (und `modell=`) an, Altaufrufe ohne Parameter bleiben beim Standardmodell. Aufgaben: `metas`, `links`,
  `plattform` → Standard (`BLOG_LLM_MODEL`); `lektorat`, `text_umschreiben`, `gegenlesen` → stark
  (`BLOG_LLM_MODEL_STARK`, Vorgabe `claude-opus-4-6`); `tiefenanalyse` → max (`BLOG_LLM_MODEL_MAX`, leer = stark).
- Eskalation (`scripts/admin/ordnung_engine.py`): scheitert eine Aufgabe nach allen Nachversuchen an der Prüfung,
  wird sie genau einmal mit der nächsthöheren Stufe wiederholt (Protokoll: „eskaliert von X auf Y, Grund …"). Nie
  nach unten; gibt es keine höhere Stufe (max leer), bleibt es beim Ergebnis.
- Abgeschnittene Antworten (`finish_reason=length`, `llm.LLMAbgeschnitten`): der Stapel wird halbiert und einzeln
  wiederholt; die Textüberarbeitung nutzt `max_tokens=8000` und Stapel zu 2 Stellen.

**„Alles in Ordnung bringen" (Mehrrunden, Stand 1.10.2026):** `scripts/admin/ordnung_engine.py` bewertet den Entwurf
nach jeder Runde neu (Simulation, nichts wird geschrieben) und macht mit den noch roten, behebbaren Kriterien weiter
(höchstens 8 Runden, 45 Minuten, Abbruch nach zwei Runden ohne messbare Verbesserung). Interne Links werden nur an
wörtlich vorhandenen Textstellen gesetzt (nie auf sich selbst, höchstens 3); die Schutzprüfung erlaubt ausdrücklich nur
diese neuen internen Links. Was nur ein Mensch beheben kann (Grafiken, Alt-Texte, Videos, Fazit, Einleitung …), steht
auf der Vorschau-Seite unter „Braucht einen Menschen". Es läuft immer nur ein Auftrag (Warteschlange); „Alle Artikel
durchgehen" auf der Ranking-Seite reiht alle Artikel mit behebbaren roten Kriterien ein.

## Schreibregeln gegen KI-Muster (Regel)

Die Texte sollen menschlich klingen. Für jeden neuen oder überarbeiteten Artikel (auch wenn Claude
ihn schreibt) gilt, abgeleitet aus den Ideen von „stop-slop", deutsch angepasst und ohne Fremdinstallation:

- **Keine Gedankenstriche** („ — ", „ -- ", „ – ") als Stilmittel. Stattdessen Punkt, Komma, Doppelpunkt oder Klammer.
  Bindestriche in Wörtern und Zahlenbereiche („2010–2026") sind erlaubt.
- **Kein „nicht X, sondern Y"** als Dauerfigur. Direkt sagen, was es ist.
- **Keine Einleiter und Floskeln:** „Kurz vorweg", „Vorab", „Der Punkt ist", „Das ist der eigentliche …",
  „Und genau das", „im Grunde", „gewissermaßen", „sozusagen".
- **Keine Verstärker und Füllwörter** auf Vorrat: genau, ganz, wirklich, echt, durchaus, schlicht, einfach, eigentlich.
- **Aktiv, mit einem Menschen oder einer klaren Sache als Subjekt.** Kein „es wird …" ohne Not.
- **Konkret statt vage.** Zahl, Name, Beispiel statt „deutlich", „viele", „enorm".
- **Satzrhythmus mischen.** Nie drei gleich lange Sätze hintereinander; im Mittel höchstens 17 Wörter.
- **Keine rhetorischen Frage-Antwort-Muster** und keine „zitierfähigen" Sprüche zum Mitschreiben.
- **Prüfung:** Kriterium „Klingt menschlich (KI-Muster)" in Teilnote B (gemessen), Lektorat (Urteil), Vorabprüfung beim Deploy (Hinweis, kein Sperrgrund).

**Umsetzung „Satz & Layout", „Claude hinzuziehen", „Klingt menschlich" (Stand 1.10.2026):**

- **F · Satz & Layout** (`satzmessung.py`, `satz_messlauf.py`, `bewertung.bewerte_satz`): Playwright misst die gebaute Seite
  (Desktop 1280 / Handy 393, hell / dunkel), ganz ohne KI; Ergebnis je Build unter `data/ranking/satz/<slug>.json`
  (Hash der dist-Seite). F zählt mit 10 % in den Gesamtscore, A–E werden dann proportional auf 90 % skaliert; ohne Messung
  gelten die üblichen Gewichte (und das „Alles in Ordnung bringen" rechnet ohne F). Übersicht und Entwurfs-CSS unter
  `/verwaltung/satz`; der Entwurf kommt nur nach Diff, Bestätigung und Backup (`data/backups/css/`) ans Ende der
  `static/style.css`, danach Build, bei Fehler automatisch zurück.
- **Claude hinzuziehen** (`gutachten.py`): headless `claude -p … --model opus --output-format json --max-turns 12` im Repo mit
  `--tools Read,Grep,Glob` (kein Bash, kein Edit/Write, kein Netz), Timeout 10 Minuten, Abbrechen-Knopf, über die
  Auftrags-Warteschlange mit Sperre je Artikel. **Sicherheitscheck:** Der Dienstbenutzer ist derselbe Benutzer wie in der
  interaktiven Sitzung; die CLI nutzt dessen Anmeldung (`HOME`, `~/.claude`), die Verwaltung braucht keine zusätzlichen Rechte.
  Dem Kindprozess wird nur eine minimale Umgebung (PATH, HOME, LANG …) ohne die Schlüssel aus der `.env` mitgegeben; das Lesen von
  `.env`, `.secrets` und `~/.claude` ist ausdrücklich verboten. Fehlt die CLI oder ist sie nicht angemeldet, gibt es eine klare Meldung.
- **Klingt menschlich (KI-Muster)** (`ki_muster.py`, B): Regelliste als Datenstruktur `REGELN`, gemessen ohne KI; das Lektorat
  (`klingt_menschlich`), die Textüberarbeitung, die Metas-Prompts und die Vorabprüfung beim Deploy (gelber Hinweis, nie
  Sperrgrund) nutzen dieselben Regeln. Die Gewichtsumverteilung in B (4 Punkte) steht auf der Detailseite.
