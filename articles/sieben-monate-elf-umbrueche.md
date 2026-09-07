---
title: "KI-Tempo, Nov.25 – Sep.26: Elf Monate, zwei Wellen — warum jetzt andere Regeln gelten"
slug: sieben-monate-elf-umbrueche
date: 2026-09-07
updated: 2026-09-07
description: "Elf Monate, zwei Wellen, ein Ebenenwechsel: Bei monatlichen Modellsprüngen ist die Fähigkeit, Kontext sauber zu übergeben, wertvoller als die Beherrschung eines bestimmten Modells. Fünf Techniken dagegen."
tags: [KI, Automatisierung, Skills]
image: /static/img/00-eyecatcher-fuenf-techniken.png
draft: false
---

*Von November 2025 bis September 2026 hat sich nicht nur das Tempo erhöht — die Ebene hat gewechselt: vom Modell zum Werkzeug drumherum. Wer weiter nach dem einen besten Modell sucht, spielt das falsche Spiel.*

![Fünf Techniken, damit Wissen den Modellwechsel überlebt](/static/img/00-eyecatcher-fuenf-techniken.png)

 **Fünf Techniken in fünf Sätzen**

<ul class="funf-techniken-liste">
  <li><span class="fte">🔒</span> <strong>Isolieren:</strong> Die Sandbox-Grenze einmal ziehen — dann kostet ein neues Modell nur einen Versuch, kein Freigabeverfahren.</li>
  <li><span class="fte">📄</span> <strong>Kodifizieren:</strong> Wissen einmal als Skill aufschreiben — dann überlebt es jede Modellgeneration, die danach kommt.</li>
  <li><span class="fte">🔁</span> <strong>Übergeben:</strong> Den Stand in einem Handover festhalten — dann verrottet er nicht im Chatverlauf.</li>
  <li><span class="fte">🎫</span> <strong>Priorisieren:</strong> Jeder Neuigkeit eine Kategorie und Priorität geben — dann schlägt Tempo nicht in Hektik um.</li>
  <li><span class="fte">🎯</span> <strong>Dirigieren:</strong> Das Ziel nennen, den Weg nicht vorschreiben — dann wird Autonomie nicht zum Ratespiel.</li>
</ul>

## Der Prompt, der alle fünf Techniken zusammenbringt

So sieht das in der Praxis aus — nicht an einem Software-Beispiel, sondern an einer Frage, die gerade jeder Autokäufer umtreibt: Verbrenner, Hybrid oder Elektro — und lohnt sich ein chinesisches Modell gegenüber einer etablierten Marke? Ein einzelner Prompt, aufgebaut wie ein Ticket, nicht wie eine Bitte. Fünf Techniken in einem Prompt — und jeder versteht sofort, worum es geht.

```
[Request · Priorität B]

Ziel: Ich will wissen, ob ein Elektroauto, ein Hybrid oder ein Verbrenner
für meine Situation (20'000 km/Jahr, eigene Garage mit Lademöglichkeit,
Budget bis 35'000) über 5 Jahre günstiger ist — und ob ein chinesisches
Modell (z. B. BYD, MG) gegenüber einer etablierten Marke mithalten kann.
Ich brauche die drei besten Optionen mit Gesamtkosten (Anschaffung,
Energie, Wertverlust, Versicherung), nicht nur eine Liste von
Testberichten.

Was gilt sowieso: Nutze den Skill `autokauf-vergleich` für den Aufbau
(Kriterien, Tabelle mit Gesamtkosten über 5 Jahre, Quelle pro Zahl) und
`quellen-check`, um zu prüfen, ob ein Testportal unabhängig ist oder vom
Hersteller mitfinanziert wird.

Wie viel Freiheit: Recherchiere selbstständig bei ADAC/TCS,
unabhängigen Testportalen und Herstellerseiten — auch zu chinesischen
Marken (Crashtests, Ersatzteilversorgung, Garantiebedingungen). Frag nur
nach, bevor du eine Probefahrt vereinbarst oder irgendwo eine Anzahlung
leistest.

Wenn fertig: Lass einen frischen Subagenten die Zahlen gegenprüfen
(adversarial review) — stimmen Verbrauchsangaben und Restwert-Schätzungen
mit unabhängigen Quellen überein? Schreib danach ein Handover: Ziel, die
drei Top-Kandidaten mit Begründung, verworfene Alternativen, ein Befehl
zur Verifikation (Link zur Vergleichstabelle), der nächste Schritt — mit
Ablaufdatum: Ende der aktuellen Förder- oder Rabattaktion.
```

**① Isolieren** — die Recherche bleibt auf öffentlichen Test- und Herstellerseiten, Probefahrt oder Anzahlung brauchen ausdrückliches Okay. **② Kodifizieren** — die Skills `autokauf-vergleich` und `quellen-check` müssen nicht bei jeder Kaufentscheidung neu erklärt werden. **③ Übergeben** — das Handover am Ende, mit Ablaufdatum (der Förderfrist). **④ Priorisieren** — die Kategorie `Request · Priorität B` im Kopf: wichtig, aber nicht brennend. **⑤ Dirigieren** — Ziel, "was gilt sowieso", der Freiheits-Regler und der Gegenlese-Schritt.

## Der Realitätscheck

Der Bruch liegt nicht im Februar. Er liegt in den letzten Wochen des Jahres 2025 — und ein Rückblick, der erst im Februar beginnt, schneidet den eigentlichen Auslöser ab. Der ehrliche Zeitraum reicht von November 2025 bis September 2026: elf Monate, zwei Spitzen.

![Elf Monate, zwei Wellen — Realitätscheck November 2025 bis September 2026](/static/img/01-realitaetscheck-zeitstreifen.png)

Die Schlagzeilen liefern die beiden Ränder: November/Dezember 2025 mit vier Flaggschiff-Modellen in Wochen und dem Start der Agent-Frameworks, Juli bis September 2026 mit explodierenden Kontextfenstern und einem Preiszusammenbruch von 80 Prozent. Die Details dazu stehen in der Grafik oben.

Interessant ist aber nicht der Rand — interessant ist die Mitte. Zwischen April und Juni wurde es scheinbar ruhig. Tatsächlich verschob sich in diesen drei Monaten etwas Grundlegenderes: Nicht mehr das Modell entschied über den Vorsprung, sondern das Harness — die Orchestrierung drumherum. Die Konsolidierung war keine Pause. Sie war ein Ebenenwechsel.

![Zwei Wellen, ein Ebenenwechsel — was sich zwischen November 2025 und September 2026 wirklich verschoben hat](/static/img/02-zwei-wellen-vergleich.png)

Wer in dieser Umgebung versucht, "auf dem Laufenden zu bleiben", verliert. Nicht aus Mangel an Fleiss, sondern aus einem strukturellen Grund: Das Wissen, das man sich aneignet, ist an Artefakte gebunden, die schneller veralten, als man sie aufbaut. Und weil sich die Ebene selbst verschoben hat, gelten ab jetzt andere Regeln: Nicht das beste Modell gewinnt, sondern das robusteste Werkzeug drumherum.

*Quellen: [10 moments that defined AI's turbulent first half of 2026 — The New Stack](https://thenewstack.io/biggest-ai-moments-2026/) &middot; [The AI Model Reset: February 2026 — Context Studios](https://www.contextstudios.ai/blog/the-ai-model-reset-the-most-important-releases-of-february-2026) &middot; [March 2026 AI Roundup — Digital Applied](https://www.digitalapplied.com/blog/march-2026-ai-roundup-month-that-changed-everything) &middot; [Neue KI-Modelle August 2026 im Vergleich — OptimusFlow](https://optimusflow.consulting/blog/neue-ki-modelle-august-2026-vergleich) &middot; [New AI Model Releases Timeline — LLM Gateway](https://llmgateway.io/timeline) &middot; [AI Timeline 2020–2026 — Machine Brief](https://www.machinebrief.com/timeline)

## Der eigentliche Fehler

Die meisten Menschen legen ihr KI-Wissen an zwei Orten ab, die beide nicht haltbar sind.

Der erste Ort ist der **Chatverlauf**. Ein langes Gespräch, in dem über Wochen Kontext gewachsen ist: Entscheidungen, Präferenzen, Erklärungen, halbfertige Gedanken. Das fühlt sich produktiv an. Es ist aber die flüchtigste Form von Wissen, die es gibt. Der Verlauf lässt sich nicht auf ein neues Modell übertragen. Er lässt sich nicht mit Kollegen teilen. Er wird mit jeder Nachricht teurer, weil das komplette Fenster erneut verarbeitet wird. Und er wird nachweislich schlechter: Chroma hat unter dem Namen *Context Rot* dokumentiert, dass die Antwortqualität mit wachsender Kontextlänge sinkt — auch weit unterhalb des technischen Limits. Das Modell verliert die Mitte, klammert sich an frühe Festlegungen und wiederholt Fehler, die es einmal gemacht hat.

Der zweite Ort ist der **eigene Kopf** — konkret: das Wissen, wie man *dieses eine Modell* am besten anspricht. Welche Formulierung funktioniert, wo es zickt, welcher Umweg nötig ist. Diese Investition hat eine Halbwertszeit von etwa acht Wochen. Sie ist beim nächsten Release teilweise wertlos, und das Ärgerliche ist: Man merkt es nicht sofort. Man merkt es, wenn die Ergebnisse schleichend schlechter werden und man nicht weiss, warum.

💡 **Die Kompensation besteht nicht darin, schneller zu lernen. Sie besteht darin, Wissen an Orte zu legen, die den Modellwechsel überleben.**

## Fünf Techniken

### 1. Isolieren, damit Ausprobieren billig wird

🔒 **Die Grenze einmal ziehen, statt bei jedem Befehl neu — dann kostet ein neues Modell nur einen Versuch, kein Freigabeverfahren.**

Der Grund, warum viele Teams neue Modelle spät testen, ist selten Desinteresse. Es ist Reibung. Ein neues Werkzeug auf einem Arbeitsrechner auszuprobieren, auf dem Kundendaten, Zugangsdaten und produktive Konfigurationen liegen, erfordert entweder Mut oder ein Freigabeverfahren. Beides bremst.

Sandboxing löst das, indem es die Grenze einmal zieht statt bei jedem Befehl neu. Der Agent bekommt eine isolierte Umgebung — je nach Risiko eine OS-native Sandbox (unter macOS Seatbelt, unter Linux bubblewrap, unter Windows die von OpenAI für Codex entwickelte Windows-Sandbox), einen Devcontainer, oder eine microVM in der Cloud. Innerhalb dieser Grenze darf er arbeiten, ohne dass jede Aktion bestätigt werden muss. Ausserhalb kommt er nicht heran.

Der Effekt auf das Tempo ist unmittelbar: Ein neues Modell lässt sich am Freitagnachmittag an einer echten Aufgabe testen, statt im nächsten Change-Fenster. Der Autonomiegrad steigt, das Risiko nicht.

Zwei Dinge sollte man dabei wissen. Erstens ist die Netzwerkgrenze wichtiger als die Dateigrenze. Eine Sandbox mit grosszügiger Egress-Freigabe ist kaum eine Sandbox — Daten fliessen dann über erlaubte Kanäle ab. *Default-deny* mit expliziter Allowlist ist der einzige sinnvolle Ausgangspunkt. Zweitens: Sandboxing schützt nicht vor Prompt Injection. Ein manipulierter Agent nutzt innerhalb der Sandbox genau die Rechte, die er legitimerweise hat. Eine Sandbox begrenzt den Schaden. Sie verhindert den Angriff nicht.

### 2. Kodifizieren, damit Wissen den Modellwechsel überlebt

📄 **Einmal sauber als Skill aufgeschrieben, übersteht Wissen jede Modellgeneration, die danach kommt.**

Ein *Skill* ist im Kern unspektakulär: ein Ordner mit einer Markdown-Datei, die beschreibt, wie eine wiederkehrende Aufgabe zu erledigen ist — plus optional Vorlagen und Skripte. Die Datei trägt einen Namen und eine Beschreibung, und die Beschreibung ist der Auslöser: Erkennt das Modell, dass die aktuelle Aufgabe dazu passt, lädt es den Skill nach.

Der technische Kniff heisst *progressive disclosure*. Dauerhaft im Kontext liegt nur die Beschreibung, etwa hundert Token. Der eigentliche Inhalt kommt erst beim Auslösen dazu, Detaildateien und Skriptausgaben noch später. Man kann hundert Skills bereithalten, ohne den Kontext zu fluten.

Der strategische Wert liegt woanders. Das SKILL.md-Format ist ein offener Standard und läuft mittlerweile in mehreren Werkzeugen verschiedener Anbieter. Wenn ein neues Modell erscheint, wird die Skill-Bibliothek **nachgetestet, nicht neu geschrieben**. Was einmal sauber aufgeschrieben wurde — wie ein Bericht in diesem Haus aussieht, wie ein Skript hier strukturiert wird, welche Prüfschritte vor einer Auslieferung kommen — überlebt die Modellgeneration, in der es entstanden ist.

Damit verschiebt sich auch die Ökonomie des Lernens. Die Stunde, die man in einen guten Skill investiert, zahlt bei jeder künftigen Ausführung und bei jedem künftigen Modell. Die Stunde, die man investiert, um ein bestimmtes Modell besser zu überreden, zahlt bis zum nächsten Release.

Ein Wort zu den Fehlern, die dabei üblich sind: Die häufigste Ursache dafür, dass ein Skill nie greift, ist eine vage Beschreibung. "Hilft mit Dokumenten" löst nichts aus. Die Beschreibung muss sagen, *was* der Skill tut und *wann* er einzusetzen ist. Die zweithäufigste Ursache ist der Alleskönner-Skill, der so viel umfasst, dass unklar ist, wann er passt — zwei kleine Skills mit klaren Grenzen schlagen einen grossen.

### 3. Übergeben, damit die Session nicht der Speicher ist

🔁 **Ein Handover-Dokument macht den Stand anschlussfähig — für den nächsten Menschen, die nächste Session, das nächste Modell.**

> **Neu, nicht etabliert.** Handover als benannte, portable Technik — Kontext sauber zwischen Sessions übergeben, statt ihn im Chatverlauf verrotten zu lassen — ist zum Zeitpunkt dieses Artikels rund **vier Monate alt**. Erstmals als eigenständiges, werkzeugübergreifendes Konzept beschrieben im **Mai 2026**. Das ist der Grund, warum sie in den meisten Teams noch keine Routine ist, obwohl sie hier als die zentrale der fünf Techniken behandelt wird: Die Praxis ist jünger als die Modelle, für die man sie am dringendsten braucht — und genau das ist ihr Sinn: Wissen "anders ablegen", statt es weiter im Chatverlauf zu vergraben.

Jede Session endet. Durch das Kontextlimit, durch einen Neustart, durch Feierabend, durch einen Modellwechsel. Die Frage ist nur, ob das geplant passiert oder nicht.

Ein Handover ist ein Dokument im Projekt — kein Chat, keine Notiz im Kopf —, das den Zustand so festhält, dass jemand anderes (oder dasselbe Modell in einer neuen Session, oder ein anderes Modell nächsten Monat) daran anknüpfen kann. Was hineingehört: das Ziel in einem Satz. Der verifizierbare Stand — was fertig ist, was läuft, was noch niemand angefasst hat. Die getroffenen Entscheidungen **mit Begründung**, ausdrücklich einschliesslich der verworfenen Alternativen; das ist der Teil, der verhindert, dass der Nachfolger dieselbe Sackgasse erneut betritt. Die Fallstricke, die schon einmal Zeit gekostet haben. Ein Befehl, mit dem sich der Zustand überprüfen lässt. Und der nächste konkrete Schritt — ausformuliert, sofort ausführbar, nicht "weitermachen".

Für die Übergabe zwischen Agenten gilt dasselbe Prinzip in kompakterer Form. Ein Subagent, der eine Recherche durchführt, verbrennt womöglich hunderttausend Token. Zurück gibt er ein bis zwei Seiten. Dass er den Rest *nicht* zurückgibt, ist kein Verlust, sondern der Zweck der Übung: Der Hauptagent bleibt schlank und klar, während die Detailarbeit anderswo stattfindet.

Es gibt einen Fehler, der schlimmer ist als kein Handover — nämlich ein veraltetes. Wer ein Dokument findet, das den Stand von vor drei Wochen als aktuell beschreibt, handelt vertrauensvoll auf falscher Grundlage. Deshalb gehört in jedes Handover ein Ablaufdatum, und deshalb ist das Schreiben Teil der Arbeit, nicht ihre Nachbereitung.

Wenn man diesen Artikel auf einen Satz reduzieren müsste, wäre es dieser: **Bei monatlichen Modellsprüngen ist die Fähigkeit, Kontext sauber zu übergeben, wertvoller als die Beherrschung eines bestimmten Modells.** Wer Handovers beherrscht, profitiert von jedem Upgrade sofort. Wer im Endlos-Chat arbeitet, fängt bei jedem Upgrade von vorne an.

### 4. Priorisieren, damit Tempo nicht in Aktionismus umschlägt

🎫 **Jede Neuigkeit bekommt einen Platz, an dem sie wartet — statt sofort Aufmerksamkeit zu erzwingen.**

Die drei bisherigen Techniken machen einen schneller. Die vierte verhindert, dass Geschwindigkeit in Hektik umschlägt.

Der Ansatz stammt aus der IT-Betriebspraxis und ist alt genug, um belastbar zu sein: Jede offene Sache wird zu einem Ticket mit einer Kategorie und einer Priorität.

Die Kategorie sagt, um welche Art von Sache es sich handelt. Ein **Incident** ist eine ungeplante Störung — etwas Funktionierendes ist kaputt. Ein **Request** ist der Wunsch nach etwas Neuem; nichts ist kaputt. Ein **Change** ist eine geplante Änderung an etwas Bestehendem. (Ein **Problem** ist die gemeinsame Ursache mehrerer Incidents — die Kategorie, die man am häufigsten übersieht.)

Die Priorität folgt dem ABC-Schema: A ist kritisch und wird sofort bearbeitet, B ist wichtig und läuft im normalen Rhythmus, C kann warten und wird gebündelt.

Der Nutzen dieser Kombination zeigt sich genau bei KI-Themen, weil sie sonst schwer einzuordnen sind. Ein bisher funktionierender Skill bricht nach einem Anbieter-Update — das ist ein Incident, Priorität A, obwohl niemand ihn gemeldet hat. Ein neues Flaggschiff-Modell erscheint — das ist ein Change mit Priorität A, obwohl nichts brennt: Es hat hohen strategischen Wert und niedrige Dringlichkeit, eine Kombination, die klassische Impact-mal-Urgency-Matrizen systematisch unterbewerten. Genau deshalb lohnt sich die zusätzliche ABC-Achse. Eine angekündigte Deprecation in drei Monaten ist ein Change mit Priorität B — wichtig, aber planbar. Ein Kollege, der Zugang zu einem neuen Tool möchte, ist ein Request mit Priorität B. Die Dokumentation, die nach dem Modellwechsel nachgezogen werden muss, ist ein Change mit Priorität C und wandert ins nächste Sammelfenster.

Das Werkzeug ist zweitrangig. Eine Markdown-Tabelle im Projektordner erfüllt den Zweck genauso wie ein ITSM-System. Entscheidend ist, dass jede Neuigkeit einen Ort bekommt, an dem sie wartet — statt sofort Aufmerksamkeit zu fordern.

### 5. Dirigieren, damit Autonomie nicht zum Ratespiel wird

🎯 **Ziel nennen, Weg nicht vorschreiben — das ist der schnellste Punkt zwischen Rätselraten und Mikromanagement.**

Mit steigender Modellfähigkeit stellt sich eine Frage immer wieder: Ist es schneller, dem Agenten alles allein zu überlassen, oder das Ziel genau zu benennen? Die Antwort widerspricht der Intuition. "Mach einfach alles" fühlt sich schnell an, weil es wenig Tipparbeit kostet — es ist aber häufig der langsamere Weg. Der Agent muss raten, wohin die Aufgabe eigentlich führt, trifft eine plausible, aber falsche Annahme, und die Korrekturschleife danach kostet mehr Zeit, als die ursprüngliche Präzisierung gekostet hätte. Am anderen Ende steht das Gegenteil: jeden Schritt vorschreiben. Auch das ist nicht schnell — wer den Lösungsweg im Detail vorgibt, tippt im Grunde die Lösung selbst, nur in Prosa statt in Code, und verschenkt genau den Autonomievorteil, für den man den Agenten überhaupt einsetzt.

Der schnellste Weg liegt dazwischen und lässt sich auf eine feste Reihenfolge bringen, die sich auch an Teams weitergeben lässt, die nicht jeden Tag mit Agenten arbeiten: **Ziel nennen, Weg nicht vorschreiben.** Drei Fragen tragen jeden Prompt. *Wohin?* — das konkrete Ergebnis, nicht der Lösungsweg ("behebe den Login-Fehler, sodass sich Nutzer X wieder anmelden kann", nicht "ändere Zeile 42"). *Was gilt sowieso?* — das, was nicht wiederholt werden muss, weil es bereits kodifiziert ist (siehe oben: Skills, CLAUDE.md). *Wie viel Freiheit?* — der explizite Regler zwischen Tempo und Kontrolle: "leg direkt los" oder "frag nach, bevor du X änderst".

Bei mehreren Agenten gleichzeitig kommt eine vierte Dimension dazu, die schon im Wort steckt: Es heisst nicht umsonst **Orchestrierung**. Die Agenten liefern die Musik — sie recherchieren, schreiben, testen, parallel und im eigenen Tempo. Der Mensch bleibt am Pult: gibt den Einsatz, hört zu, korrigiert. Das ist keine Nebensächlichkeit, sondern der Kern des Modells: **Tempo ersetzt kein Gegenlesen.** Jedes Ergebnis, das ein Agent zurückliefert, bleibt prüfpflichtig, bevor es übernommen wird — unabhängig davon, wie autonom es entstanden ist.

Das ist keine private Faustregel. Anthropics eigener Best-Practices-Leitfaden für Claude Code führt beides getrennt auf: präzise Ziele statt vager Prompts als Hebel für weniger Korrekturschleifen, und einen "adversarial review step" — ein frischer Subagent, der das Ergebnis in eigenem Kontext gegenprüft, bevor es als fertig gilt, ausdrücklich unabhängig von der Session, die es erzeugt hat.

## Was noch dazugehört

Vier Konzepte liegen so nah an diesen Techniken, dass sie in der Praxis mitlaufen.

**Versions-Pinning** ist die direkteste Antwort auf das Tempo überhaupt: Wer eine feste Modellversion referenziert statt "das neueste", entscheidet selbst, wann sich das Verhalten seiner Systeme ändert. Wer Modellwahl und Prompt sauber trennt, kann das eine wechseln, ohne das andere anzufassen.

**Evals** sind der Grund, warum man einen Wechsel überhaupt bemerkt. Eine kleine Sammlung von Testfällen, die nach jedem Modellupdate durchläuft, ist der Unterschied zwischen "wir haben es beim Rollout gesehen" und "der Kunde hat es gesehen". Zwanzig Testfälle sind besser als keine.

**Git für Prompts und Skills.** Sobald Skills in Versionsverwaltung liegen, gelten die Werkzeuge, die man ohnehin beherrscht: Diff, Review, Rollback, Blame. Die Frage "wann hat sich das Verhalten geändert und wer hat es geändert" wird beantwortbar.

**Kostentransparenz.** Autonome Agenten, die parallel arbeiten, skalieren Verbrauch schnell. Ein Monitoring, das Token und Kosten pro Aufgabe sichtbar macht, kostet einen Nachmittag Einrichtung und verhindert unangenehme Monatsabrechnungen.

## Der Kern

Die fünf Techniken sind nicht fünf Themen, sondern fünf Achsen desselben Prinzips:

**Isolieren**, damit Ausprobieren billig wird. **Kodifizieren**, damit sich Wiederholtes nicht wiederholt erklären lässt. **Übergeben**, damit Wissen nicht in der Session stirbt. **Priorisieren**, damit nicht jede Neuigkeit zum Notfall wird. **Dirigieren**, damit Autonomie nicht zum Ratespiel wird.

Was dabei entsteht, ist eine Wissensschicht ausserhalb des Modells: Skills, die beschreiben, wie hier gearbeitet wird. Handovers, die festhalten, wo man steht. Sandboxes, in denen Neues gefahrlos getestet wird. Ein Ticketbestand, der Wichtiges von Lautem trennt. Ein Dirigent, der jedes Ergebnis hört, bevor es übernommen wird.

Diese Schicht ist der eigentliche Besitz. Modelle werden dagegen austauschbar — und das ist keine Kapitulation, sondern das Ziel. Wenn im November das nächste Modell erscheint, ist die Frage nicht mehr, wie viel man neu lernen muss. Die Frage ist nur noch, ob die Evals durchlaufen.

Das ist der Unterschied zwischen Hinterherlaufen und Profitieren.

---

*Grundlage: Recherche vom 7. September 2026 zu Sandboxing, Agent Skills, Kontext-Handovers und ITIL-basierter Priorisierung, erstellt in einer orchestrierten Multi-Agenten-Struktur. Belegte Ereignisdaten stammen aus Primär- und Sekundärquellen des Zeitraums November 2025 bis September 2026.*