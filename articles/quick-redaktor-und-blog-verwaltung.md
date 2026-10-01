---
slogan: "Mein Quick-Redaktor hob drei schwache LinkedIn-Beiträge von 61 bis 77 auf 75 bis 99 Punkte. Zahlen, Namen und Zitate erfindet er nie."
title: "Quick-Redaktor: Wie Claude meine LinkedIn-Texte lektoriert"
slug: quick-redaktor-und-blog-verwaltung
date: 2026-10-02
description: "Aus einer Blog-Verwaltung mit 6 Teilnoten, Schutzprüfung und Deploy-Panel entstand ein Werkzeug für Kollegen: mit Messwerten, Pannen und Probeläufen."
summary: >-
  In zwei Tagen habe ich mit Claude eine Verwaltung für meinen Blog gebaut. Sie hat ein Ranking mit sechs Teilnoten, ein Lektorat per KI und eine Schutzprüfung für Zahlen und Zitate. Dazu kommen ein Versionsverlauf und ein Deploy-Panel mit Menschen-Schritt. Daraus ist der Quick-Redaktor entstanden, eine kleine Seite für zwei bis vier Kollegen. Man fügt einen LinkedIn-Beitrag ein und bekommt den verbesserten Text, eine Liste der Änderungen mit Begründung, die offenen Punkte und eine Prüfliste mit Punktzahl. In drei Probeläufen mit absichtlich schwachen Beiträgen stieg die Punktzahl im Modus „Behutsam“ von 61 bis 77 auf 75 bis 99. Der Artikel zeigt Aufbau, Werkzeuge, Pannen und was Leser für ihre eigenen Beiträge mitnehmen können.
tags: [KI, Claude, LinkedIn, Schreiben, Automatisierung]
og_image: /static/img/og-quick-redaktor.jpg
og_image_alt: "Schema des Quick-Redaktors: Beitragstext mit roten Streichungen und grünen Ergänzungen, daneben drei Kennzahlen aus dem Probelauf."
thumb: /static/img/thumbs/quick-redaktor-und-blog-verwaltung.jpg
draft: true
changelog:
  - datum: 2026-10-02
    text: "Entwurf: Blog-Verwaltung, Quick-Redaktor und Ergebnisse der Probeläufe."
---

## Ein Titel mit 124 Zeichen

Mein längster Artikeltitel hatte 124 Zeichen. LinkedIn schneidet die Überschrift einer Link-Karte nach zwei Zeilen ab, Google schon nach etwa 60 Zeichen. Gemerkt habe ich das erst, als ich alle fünf Artikel nebeneinander gemessen habe. Heute liegen die Titel zwischen 54 und 62 Zeichen.

Gemessen hat eine Verwaltung, die ich in zwei Tagen mit Claude gebaut habe. Ich bin Senior System Engineer und kein Texter. Mir fehlte ein Lektorat, das nachzählt, statt zu loben. Aus dieser Verwaltung ist ein zweites Werkzeug entstanden: der Quick-Redaktor für Kollegen, die selbst auf LinkedIn schreiben.

Dieser Text beschreibt beides. Er nennt die Werkzeuge, die Pannen und die Zahlen aus drei Probeläufen.

## Was die Verwaltung misst

Die Verwaltung ist eine kleine Flask-Anwendung neben dem statischen Blog-Generator. Sie läuft auf einem Raspberry Pi und ist nur im eigenen Netz erreichbar. Das Herz ist ein Ranking mit sechs Teilnoten:

- **A · Vorschau und Meta:** Titellänge, Beschreibung, Vorschaubild, Pflicht-Meta-Tags.
- **B · Lesbarkeit und Fluss:** Lesbarkeitsindex nach Amstad, Satzlänge, Füllwörter und „Klingt menschlich“.
- **C · Struktur:** Überschriften, Listen, Abschnittslängen.
- **D · Grafiken:** Abstand zwischen Bildern, Alt-Texte, Bildgewichte.
- **E · SEO:** Schlüsselbegriffe, Links, Aktualität.
- **F · Satz und Layout:** Playwright öffnet die gebaute Seite am Desktop mit 1.280 Pixeln und am Handy mit 393 Pixeln, jeweils hell und dunkel. Es misst Schriftgröße, Zeilenlänge und Kontrast.

Die Amstad-Formel habe ich selbst umgesetzt. Die übliche Bibliothek zählt deutsche Silben über Trennstellen, und das verfälscht den Wert. Für Fundstellen im Text läuft Vale mit eigenen Regeln.

„Klingt menschlich“ zählt Muster, die Texte nach KI klingen lassen. Dazu gehören Gedankenstriche, die Figur „nicht X, sondern Y“, Einleiter wie „Kurz vorweg“ und Verstärker wie „wirklich“. Die Ideen stammen aus stop-slop. Vor der Überarbeitung standen in allen fünf Artikeln zwischen 22 und 29 Gedankenstriche je 1.000 Wörter. Das Soll liegt bei höchstens vier.

| Artikel | Titel vorher | Titel nachher |
|---|---|---|
| KVM-Switch per Siri | 87 Zeichen | 62 Zeichen |
| Monitoring, Teil 2 | 94 Zeichen | 60 Zeichen |
| Netdata und Claude | 100 Zeichen | 54 Zeichen |
| KI-Tempo und Skills | 85 Zeichen | 54 Zeichen |
| Wirtschaftskalender | 124 Zeichen | 58 Zeichen |

[PRÜFEN: Gesamtnoten vor der Überarbeitung 80,8 bis 93,6, erwartet danach 89,2 bis 98,5 laut Simulation. Im Repo nicht belegt.]

## Claude als Lektor, mit Leitplanken

Gebaut habe ich die Verwaltung im Gespräch mit Claude Code. Ich habe beschrieben, was ich brauche, Zwischenstände angesehen und Regeln nachgeschärft. Größere Teilaufgaben gingen an Unteragenten. Auch deren Modell folgt einer festen Tabelle: Haiku für Mechanisches, Sonnet für die Umsetzung, Opus für Lektorat, Abwägung und Korrektheit. Jede Regel, die sich bewährt hat, steht heute in der Projektdatei CLAUDE.md. So beginnt die nächste Sitzung mit demselben Stand.

Über die Messung hinaus arbeitet die Verwaltung mit Claude. Ein Knopf startet das Lektorat: Claude bewertet neun Kriterien und nennt drei konkrete Verbesserungen. Ein zweiter Knopf heißt „Alles in Ordnung bringen“. Er schreibt bis zu acht Runden lang Vorschläge, misst nach jeder Runde neu und hört auf, wenn sich zweimal nichts verbessert.

[PRÜFEN: Die Artikel entstanden mit Claude Sonnet 5.] Die Überarbeitung lief mit Claude Opus 4.6. Die Anfragen gehen über den claude-code-openai-wrapper auf dem Raspberry Pi. Das Modell richtet sich nach der Aufgabe. Metas und Plattformtexte bekommt das Standardmodell, Lektorat und Textüberarbeitung die starke Stufe. Besteht ein Ergebnis die Prüfung zweimal nicht, wiederholt die Verwaltung den Auftrag eine Stufe höher.

Die wichtigste Leitplanke ist die Schutzprüfung. Sie vergleicht jeden Vorschlag mit dem Original. Zahlen, Links, Code, Fachbegriffe und wörtliche Zitate müssen erhalten bleiben. Fehlt eine Zahl oder taucht eine neue auf, verwirft die Verwaltung die Stelle und erklärt den Grund in einem Satz.

Nichts davon schreibt ungefragt in einen Artikel. Ein Vorschlag landet erst nach Diff, Bestätigung und Backup in der Datei. Ein Versionsverlauf hält jede Fassung fest und stellt sie auf Knopfdruck wieder her.

## Das Deploy-Panel und der Menschen-Schritt

Veröffentlichen folgt einer festen Reihenfolge: prüfen, bauen, Diff ansehen, veröffentlichen, live prüfen. Ein eigener Inspector ruft die Live-Seite so ab, wie es der Bot von LinkedIn tut. Er prüft die fünf Pflicht-Meta-Tags, das Vorschaubild und den Zwischenspeicher. Commit und Push laufen nur auf Knopfdruck und nur für ausgewählte Pfade.

Zwei Schritte bleiben bei mir. Den Knopf „Veröffentlichen“ drücke ich selbst. Danach gebe ich die Live-Adresse im LinkedIn Post Inspector ein und kontrolliere Titel, Bild und Beschreibung. Der Inspector erneuert auch den Zwischenspeicher von LinkedIn. Diesen Schritt automatisiere ich nicht, und LinkedIn selbst bediene ich nie per Skript.

Die Testsuite wuchs während der Arbeit von 62 auf 232 Tests. Mit dem Quick-Redaktor kamen 33 dazu.

## Was schiefging

Drei Pannen haben mich am meisten gelehrt.

**Der Wrapper startete mitten im Lauf neu.** Die Verwaltung bekam einen ConnectionResetError und brach ab. Jetzt wiederholt sie Anfragen bei Verbindungsfehlern nach 5, 15, 30, 60 und 120 Sekunden. Inhaltliche Fehler wiederholt sie nie.

**Anführungszeichen zerbrachen das JSON.** Claude antwortet in JSON und übernimmt dabei Zitate aus dem Artikel. Ein gerades Anführungszeichen mitten im Text beendet aber eine JSON-Zeichenkette. Die Auswertung repariert solche Stellen jetzt selbst. Beim Quick-Redaktor kam die Panne zurück: In den ersten fünf Probeläufen scheiterten alle fünf Antworten. Das Modell schrieb deutsche Anführungszeichen unten auf, oben aber gerade. Eine gezielte Reparatur und eine Nachfrage lösten das.

**Die Schutzprüfung war strenger als gedacht.** Claude wollte wörtliche Zitate glätten. Die Prüfung lehnte das ab, und das ist richtig so. Ein Zitat gehört dem, der es gesagt hat.

Daraus habe ich gelernt: Ein Sprachmodell braucht eine Prüfung, die nicht von ihm selbst stammt. Die Regeln stehen im Code, und ein Test belegt jede einzelne.

## Der Quick-Redaktor für Kollegen

Zwei bis vier Kollegen schreiben ebenfalls auf LinkedIn. Für sie gibt es jetzt eine kleine Seite. Man fügt den Beitrag ein, wählt einen Modus und drückt einen Knopf. Zurück kommen vier Dinge:

1. der verbesserte Text mit Kopier-Knopf und einem Wortvergleich in Rot und Grün,
2. die Liste „Was ich geändert habe“, je Änderung mit Begründung,
3. „Was noch nicht gut ist“, je Punkt mit einem konkreten Handgriff,
4. eine Prüfliste mit Messwert, Soll und Punktzahl von 0 bis 100, vorher und nachher.

Es gibt drei Modi. „Behutsam“ behebt Fehler, KI-Muster und schwere Sätze und lässt die Stimme des Autors stehen. „Straffen“ kürzt auf 300, 600 oder 1.300 Zeichen. „Nur prüfen“ misst ohne KI und kostet nichts.

Die Prüfliste kennzeichnet jede Regel. Belegt ist die harte Grenze von 3.000 Zeichen. Ein Praxiswert ist die Sichtbarkeit vor „…mehr“: mobil etwa 140 Zeichen, am Desktop etwa 210. Ebenfalls aus der Praxis stammt mein Befund, dass die Link-Karte in der Profil-Übersicht nur bei kurzem Text erschien. Ob die Stelle der Adresse dafür eine Rolle spielt, ist nicht belegt. Kurze Absätze und höchstens drei Hashtags sind Hausregeln, ebenso der Aufbau am Schluss. Die Seite markiert sie als „nicht geprüft“.

Der Aufbau am Schluss folgt einer festen Reihenfolge. Die Adresse steht direkt hinter dem letzten Satz, im selben Absatz. Dann folgt eine Leerzeile, und in der letzten Zeile stehen die Hashtags. So steht die Adresse dort, wo das Auge nach dem Lesen hinfällt, und nichts drängt sich davor. Hashtags sind das Unwichtigste und kommen zuletzt. Die Leerzeile verhindert am Handy, dass der Daumen ein Hashtag statt der Adresse trifft.

Im Hintergrund laufen dieselben Bausteine wie in der Verwaltung: Musterzählung, Amstad, Schutzprüfung und Modellwahl. Neu ist eine Ebene ohne KI. Sie entfernt Markdown-Sterne, wandelt Unicode-„Fett“ zurück und stellt auf Wunsch Adresse und Hashtags in diese Reihenfolge. Erwähnungen, Hashtags, Links und Zahlen schützt die Schutzprüfung zusätzlich.

Für den Probelauf habe ich drei absichtlich schwache Beiträge geschrieben: Floskeln, Gedankenstriche, acht oder neun Hashtags, ein Link mitten im Satz, eine Textwand.

| Beitrag | Modus | Punkte vorher | Punkte nachher | Zeichen | Dauer |
|---|---|---|---|---|---|
| Cloud-Migration | Behutsam | 61 | 75 | 1.010 → 860 | 30 s |
| Cloud-Migration | Straffen auf 600 | 61 | 94 | 1.010 → 460 | 44 s |
| Zertifizierung | Behutsam | 77 | 99 | 681 → 419 | 24 s |
| Konferenzbericht | Behutsam | 69 | 89 | 1.004 → 812 | 28 s |
| Konferenzbericht | Straffen auf 300 | 69 | 92 | 1.004 → 318 | 19 s |

Die fünf Läufe brauchten zusammen 143 Sekunden und sechs KI-Aufrufe. Beim Konferenzbericht verwarf die Schutzprüfung drei Änderungen. Claude hatte zwei Zahlen von einem Satz in einen anderen verschoben und eine Stelle auf ein Viertel gekürzt. Beim Straffen auf 300 Zeichen kamen 318 heraus; die Prüfliste zeigt das offen an.

Die Ergebnisse schwanken. Ein früherer Lauf mit demselben Migrationsbeitrag kam auf 98 Punkte. Claude hatte damals den ersten Satz umgebaut; diesmal verwarf die Schutzprüfung diesen Umbau als zu starke Kürzung. Wer das Werkzeug nutzt, liest deshalb zuerst den Vergleich in Rot und Grün und erst danach die Punktzahl.

Datenschutz hat Vorrang. Die Seite speichert keine Texte und protokolliert sie nicht. Sie zählt nur Länge, Modus, Dauer und Punktzahl. Ein Test sucht nach jedem Lauf alle neuen Dateien und die Logausgabe nach dem eingegebenen Text. Ein Hinweis auf der Seite bittet, keine vertraulichen Firmeninhalte einzufügen. Ohne ausdrückliche Einstellung läuft nur „Nur prüfen“. Ob die KI-Modi über mein persönliches Abo für andere laufen dürfen, kläre ich vor der Freigabe.

## Fazit: Messen, bevor man postet

Zwei Tage reichten für eine Verwaltung und ein Werkzeug für Kollegen. Den größten Gewinn brachte die Messung. Claude formuliert gut, und die Prüfung danach sorgt dafür, dass dabei keine Zahl und kein Zitat verloren geht.

Wer selbst auf LinkedIn postet, kann fünf Punkte ohne jedes Werkzeug prüfen:

- Den Kern in den ersten Satz stellen und den Satz vor Zeichen 140 beenden.
- Gedankenstriche, „Kurz vorweg“ und „wirklich“ streichen.
- Absätze mit mehr als 50 Wörtern teilen.
- Höchstens drei Hashtags setzen, gesammelt am Ende.
- Die Adresse direkt hinter den letzten Satz setzen, nach einer Leerzeile die Hashtags.

Und vor jedem Beitrag mit Link gilt: erst den Post Inspector, dann posten.
