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
