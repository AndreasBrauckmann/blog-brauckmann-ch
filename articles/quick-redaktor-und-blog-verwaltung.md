---
slogan: "Eine Karte, die fehlt, und ein Text, den niemand gegengelesen hat: So kommt ein Blogartikel geprüft auf LinkedIn."
title: "Blog und LinkedIn: Ablauf, Redaktion und Post Inspector"
slug: quick-redaktor-und-blog-verwaltung
date: 2026-10-02
description: "Vom Entwurf bis zum Beitrag: was ein Redaktor prüft, wie Messwerte und Claude als Lektor helfen und warum die Link-Karte vor dem Posten kontrolliert wird."
summary: >-
  Ein Blogartikel braucht einen Ablauf: Idee, Gliederung, Entwurf, Redaktion, Messung, Veröffentlichung und Kontrolle der Link-Karte. Der Artikel erklärt, was ein Redaktor in diesem Ablauf tut und welche Prüfungen sich messen lassen. Er zeigt den LinkedIn Post Inspector, den nur wenige kennen, und erklärt, wie Claude als Lektor hilft, ohne dass Zahlen, Adressen oder Zitate verloren gehen. Dazu gibt es Code für die Messung, eine Schutzprüfung und eine Checkliste für den Alltag.
tags: [KI, Claude, LinkedIn, Schreiben, Automatisierung]
og_image: /static/img/og-quick-redaktor.jpg
og_image_alt: "Schema einer Textprüfung: Beitragstext mit roten Streichungen und grünen Ergänzungen, daneben drei Kennzahlen."
thumb: /static/img/thumbs/quick-redaktor-und-blog-verwaltung.jpg
draft: false
changelog:
  - datum: 2026-10-02
    text: "Artikel veröffentlicht: Anleitung zum Prüfen von LinkedIn-Beiträgen."
---

Bevor du einen Beitrag mit Link auf LinkedIn postest, kannst du die Link-Karte kostenlos prüfen. Viele überspringen diesen Schritt. Danach folgt der ganze Weg eines Blogartikels vom Entwurf bis zum Beitrag, mit den Prüfungen, die sich messen lassen, und mit Claude als Lektor, der Zahlen und Zitate nicht anfassen darf.

## Der LinkedIn Post Inspector: die Prüfseite für deine Link-Karte

LinkedIn liest die Karte aus den Open-Graph-Angaben im Kopf deiner Seite. Vier davon braucht LinkedIn laut eigener Entwicklerhilfe: `og:title`, `og:description`, `og:image` und `og:url`. Fehlt eine, rät LinkedIn aus dem Seiteninhalt. Das Ergebnis ist oft ein falsches oder gar kein Bild.

Das Bild sollte mindestens 1.200 Pixel breit sein, am besten im Verhältnis 1,91 zu 1, also 1.200 mal 627 Pixel. Mit kleineren Bildern zeigt LinkedIn oft keine große Karte.

Ob alles ankommt, siehst du im **LinkedIn Post Inspector**. Das Werkzeug ist kostenlos und gehört LinkedIn. Es ruft deine Seite so ab wie LinkedIn selbst und zeigt, welche Angaben es gefunden hat.

1. Öffne `linkedin.com/post-inspector` und melde dich an.
2. Füge die Adresse deines Artikels ein und klicke auf **Inspect**.
3. Lies Titel, Beschreibung und Bild in der Vorschau. Darunter stehen die gefundenen Angaben und mögliche Hinweise.
4. Stimmt etwas nicht, behebe es auf deiner Seite und klicke erneut auf **Inspect**.

Der letzte Schritt hat eine Nebenwirkung, die du kennen solltest. LinkedIn speichert die Karte zwischen. Der Post Inspector erneuert diesen Speicher, sobald du eine Adresse prüfst. Das gilt aber nur für neue Beiträge. Ein Beitrag, der bereits veröffentlicht ist, behält seine alte Karte. Fehlte das Bild beim ersten Posten, hilft nur ein neuer Beitrag.

Daraus folgt die wichtigste Regel: **Erst den Post Inspector, dann posten.** Prüfe jede neue Adresse, bevor sie in einem Beitrag steht.

## Der Ablauf eines Blogartikels

Ein Artikel entsteht in Schritten, und jeder Schritt hat eine eigene Frage. Wer sie in dieser Reihenfolge stellt, spart sich späte Umbauten.

**1. Leser und Ziel klären.** Wer liest den Artikel, und was kann er danach? Schreibe das in einem Satz auf. Ein Artikel, der zwei Zielgruppen bedient, dient meist keiner.

**2. Gliederung.** Lege Überschriften fest, bevor du Sätze schreibst. Jeder Abschnitt beantwortet eine Frage des Lesers. Eine gute Gliederung lässt sich in einer Minute überblicken.

**3. Entwurf.** Schreibe den ersten Text zügig und ohne Feinschliff. Der Entwurf darf schlecht sein, aber er muss vollständig sein.

**4. Redaktion.** Hier kommt der Redaktor ins Spiel. Ein Redaktor ist die zweite Person zwischen Autor und Leser. Er stellt vier Fragen: Stimmt der Inhalt? Ist der Aufbau schlüssig? Ist die Sprache klar? Hält jede Behauptung einer Nachfrage stand? Der Autor ist für diese Fragen betriebsblind, weil er weiß, was er meinte. Ein Redaktor liest, was dasteht. Seine Arbeit besteht aus Rückmeldungen und Änderungsvorschlägen. Entscheiden darf am Ende der Autor.

Diese Rolle kann Claude übernehmen, als Zweitleser mit klaren Grenzen. Es liest den Entwurf, nennt Schwächen und schlägt Änderungen mit Begründung vor. Wichtig bleibt die Aufteilung: Claude schlägt vor, du entscheidest, und eine Prüfung nach festen Regeln schützt, was nicht verändert werden darf.

**5. Messen.** Manches an einem Artikel lässt sich zählen, und das geht schneller und ehrlicher als ein Bauchgefühl. Folgende Werte haben sich als Richtwerte bewährt. Es sind Hausregeln und keine Gesetze:

| Bereich | Richtwert |
|---|---|
| Titel | 40 bis 70 Zeichen. Google kürzt Titel nach etwa 60 Zeichen. |
| Beschreibung | 120 bis 160 Zeichen, als Fortsetzung des Titels und ohne Wiederholung |
| Vorschaubild | 1.200 mal 630 Pixel, mit Alt-Text |
| Überschriften | eine pro Frage, kein Abschnitt ohne Überschrift |
| Absätze | kurz, in der Regel unter 50 Wörtern |
| Satzlänge | im Mittel höchstens 17 Wörter, kein Satz über 25 |
| Lesbarkeit | Index nach Amstad für Deutsch, nicht die englische Flesch-Formel |
| Füllwörter und KI-Muster | zählen und streichen: Gedankenstriche, „Kurz vorweg“, „wirklich“ |

Eine Besonderheit beim Titel und der Beschreibung: Sie sollen zusammen gelesen werden wie ein Satz. Der Titel nennt das Thema, die Beschreibung führt es weiter. Wiederholt die Beschreibung den Titel, verschenkst du die Hälfte des Platzes in der Suche und auf der Link-Karte.

**6. Veröffentlichen.** Baue die Seite und sieh dir vor dem Veröffentlichen an, was sich ändert. Ein Vergleich der Dateien zeigt dir, ob nur der Artikel betroffen ist. Prüfe, ob keine Zugangsdaten im Text stehen. Veröffentliche erst nach deiner Bestätigung und nur die Dateien, die du ausgewählt hast.

**7. Die Karte kontrollieren.** Jetzt kommt der Post Inspector aus dem ersten Abschnitt. Die Adresse muss live sein, damit LinkedIn sie abrufen kann.

**8. Posten und nachpflegen.** Poste den Beitrag mit dem Aufbau, den der letzte Abschnitt beschreibt. Später ergänzt du Korrekturen im Artikel selbst und notierst sie in einem Änderungsprotokoll, damit Leser sehen, was sich geändert hat.

## Den Text messen: Regeln für den LinkedIn-Beitrag

Ein Text lässt sich mit wenigen Regeln prüfen. Manche Regeln sind belegt, andere Erfahrung, andere Hausregeln. Trenne das, damit du nichts als Gesetz behandelst, was nur Geschmack ist.

| Regel | Wert | Art |
|---|---|---|
| Höchstlänge eines Beitrags | 3.000 Zeichen | belegt, harte Grenze |
| Sichtbar vor „mehr“ | mobil etwa 140, am Desktop etwa 210 Zeichen | Erfahrung, schwankt |
| Hashtags | höchstens drei, gesammelt am Ende | Hausregel |
| Absätze | höchstens 50 Wörter | Hausregel |
| Gedankenstriche | möglichst keine | Hausregel |

Die zweite Zeile ist die wichtigste. Alles nach etwa 140 Zeichen versteckt LinkedIn hinter „mehr“. Der erste Satz muss deshalb den Kern enthalten und vor dieser Grenze enden.

Gedankenstriche stehen hier, weil sie in KI-Texten auffallen. Ein einzelner stört nicht. Zehn in einem Beitrag lesen sich wie maschinell erzeugt.

So misst du das in Python, ohne Bibliothek:

```python
import re

def pruefe(text: str) -> dict:
    erste_zeile = text.strip().split("\n")[0]
    absaetze = [a for a in re.split(r"\n\s*\n", text.strip()) if a]
    return {
        "zeichen": len(text),
        "zu_lang": len(text) > 3000,
        "erster_satz_vor_140": bool(re.search(r"[.!?]", erste_zeile[:140])),
        "hashtags": len(re.findall(r"(?<!\w)#\w+", text)),
        "gedankenstriche": len(re.findall(r" [–—] |--", text)),
        "langer_absatz": max(len(a.split()) for a in absaetze) > 50,
        "adresse_im_text": bool(re.search(r"https?://", text)),
    }
```

Der Aufruf `pruefe(text)` liefert für einen Beitrag sofort ein Ergebnis. Wichtig ist die Reihenfolge der Ausgabe: Zahlen und Ja/Nein-Werte, keine Bewertung. Ob ein Wert stört, entscheidest du.

## Claude als Lektor, mit Schutzprüfung

Eine KI überarbeitet Text gut und verändert dabei gern mehr, als du willst. Sie rundet Zahlen, verschiebt Zahlen zwischen Sätzen, kürzt Zitate und baut Adressen um. Deshalb braucht jede Überarbeitung eine Prüfung, die nicht von der KI selbst stammt.

**Der Auftrag.** Gib Claude eine klare Rolle und enge Grenzen. Ein Beispiel:

```text
Du bist Lektor für LinkedIn-Beiträge. Überarbeite den Text so wenig wie nötig.
Behalte Zahlen, Namen, Adressen, Hashtags und wörtliche Zitate unverändert.
Streiche Floskeln und Gedankenstriche. Stelle den Kern in den ersten Satz.
Antworte als JSON: {"text": "...", "aenderungen": [{"was": "...", "warum": "..."}]}
```

Die Liste der Änderungen mit Begründung ist wichtig. Sie macht die Überarbeitung nachvollziehbar, und du siehst, wo Claude eingegriffen hat.

**Die Schutzprüfung.** Sie vergleicht Original und Vorschlag und verwirft jede Überarbeitung, bei der etwas Geschütztes fehlt:

```python
ZAHL = re.compile(r"\d+(?:[.,]\d+)*")
ADRESSE = re.compile(r"https?://\S+")

def schutzpruefung(original: str, vorschlag: str) -> list[str]:
    fehler = []
    if sorted(ZAHL.findall(original)) != sorted(ZAHL.findall(vorschlag)):
        fehler.append("Zahlen verändert")
    if sorted(ADRESSE.findall(original)) != sorted(ADRESSE.findall(vorschlag)):
        fehler.append("Adresse verändert")
    for zitat in re.findall(r"„[^“]+“", original):
        if zitat not in vorschlag:
            fehler.append(f"Zitat fehlt: {zitat}")
    return fehler
```

Probiere sie an einem Beispiel. Das Original sagt „3 Server in 12 Wochen“. Schreibt Claude „Drei Server in 12 Wochen“, meldet die Prüfung `Zahlen verändert`. Das ist Absicht: Die Prüfung vergleicht Zeichen und deutet keinen Sinn. Eine Umformung von „3“ zu „Drei“ lässt du dann von Hand zu. Das ist besser als eine Prüfung, die zu viel durchlässt.

**Nichts ohne dich.** Zeige den Vorschlag als Vergleich, am besten mit Streichungen in Rot und Ergänzungen in Grün, und übernimm ihn erst nach deiner Bestätigung. Lies den Vergleich zuerst und die Zahlen danach. Eine KI schwankt von Lauf zu Lauf, und derselbe Text kommt nicht jedes Mal gleich heraus.

**Antwort als JSON, mit Nachfrage.** Eine Falle für alle, die Claude in ein Programm einbinden: Zitate im Text enthalten oft gerade Anführungszeichen, und ein solches Zeichen beendet in JSON eine Zeichenkette. Prüfe die Antwort deshalb beim Einlesen. Gelingt es nicht, frage Claude einmal nach, statt abzubrechen.

## Der Aufbau am Schluss

Die Reihenfolge am Ende eines Beitrags zählt. Eine bewährte Anordnung ist diese:

1. der letzte Satz,
2. die Adresse direkt dahinter, im selben Absatz,
3. eine Leerzeile,
4. die Hashtags in der letzten Zeile.

Die Adresse steht dort, wo das Auge nach dem Lesen hinfällt. Hashtags sind das Unwichtigste und kommen zuletzt. Die Leerzeile hilft am Handy, damit der Daumen kein Hashtag statt der Adresse trifft. Ob die Stelle der Adresse die Anzeige der Karte beeinflusst, ist nicht belegt. Probiere es mit deinen eigenen Beiträgen aus.

## Datenschutz bei fremden Texten

Wenn du die Prüfung als Seite für Kollegen bereitstellst, gilt: Speichere keine Texte und schreibe sie in kein Protokoll. Zähle höchstens Länge, Dauer und Punktzahl. Ein Test, der nach jedem Lauf alle neuen Dateien nach dem eingegebenen Text durchsucht, schützt dich davor, dass ein Hilfsprogramm ihn doch ablegt. Weise auf der Seite darauf hin, dass niemand vertrauliche Firmeninhalte einfügen soll. Und kläre vorher die Nutzungsbedingungen deines KI-Zugangs, wenn Texte anderer Personen darüber laufen.

## Checkliste vor dem Posten

- Den Kern in den ersten Satz stellen und ihn vor Zeichen 140 beenden.
- Gedankenstriche, Floskeln wie „Kurz vorweg“ und Verstärker wie „wirklich“ streichen.
- Absätze über 50 Wörter teilen.
- Höchstens drei Hashtags, gesammelt am Ende nach einer Leerzeile.
- Die Adresse direkt hinter den letzten Satz setzen.
- Bei einer KI-Überarbeitung die Schutzprüfung laufen lassen und den Vergleich lesen.
- Die Adresse im Post Inspector prüfen: Titel, Beschreibung und Bild.
- Erst dann posten.

Der Post Inspector kostet eine Minute und erspart dir einen Beitrag ohne Bild.
