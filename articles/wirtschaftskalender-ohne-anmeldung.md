---
slogan: "Der Wirtschaftskalender unter brauckmann.ch/kalender/ zeigt über 84.000 Konjunkturtermine seit 2010, ohne Login, ohne Bezahlschranke: JSON-API, sechs Downloadformate (CSV, Excel, SQLite, NDJSON, ICS), Sparkline-Verlauf pro Kennzahl, ein Recherche-Link direkt in Googles KI-Modus und für 98 Prozent aller Kennzahlen die amtliche Originalquelle verlinkt."
title: "Der kostenlose, KI-gesteuerte Wirtschaftskalender von Kontor: über 84.000 Termine — modern, schnell, ohne Ballast und Kosten"
short_title: "Der kostenlose, KI-gesteuerte Wirtschaftskalender von Kontor: über 84.000 Termine — modern & schnell"
slug: wirtschaftskalender-ohne-anmeldung
date: 2026-09-20
updated: 2026-09-29
description: "Über 84.000 Konjunkturtermine seit 2010, ohne Login: kostenlose API, sechs Download-Formate, KI-Recherche per Klick und Link zur Originalquelle jedes Termins."
summary: >-
  Der Wirtschaftskalender unter brauckmann.ch/kalender/ zeigt über 84.000 Konjunkturtermine seit 2010, ohne Login, ohne Bezahlschranke: JSON-API, sechs Downloadformate (CSV, Excel, SQLite, NDJSON, ICS), Sparkline-Verlauf pro Kennzahl, ein Recherche-Link direkt in Googles KI-Modus und für 98 Prozent aller Kennzahlen die amtliche Originalquelle verlinkt. Kostet nirgends etwas — die Zahlen sind ohnehin öffentlich, also bleiben sie hier frei zugänglich, ganz ohne Einschränkung.
tags: [Kontor, Wirtschaftsdaten, Open Data, API]
image: /static/img/wirtschaftskalender-eyecatcher-square.gif
og_image: /static/img/og-wirtschaftskalender-ohne-anmeldung.jpg
og_image_alt: "Wirtschaftskalender von Kontor mit aufgeklapptem Termin und Sparkline-Verlauf der Arbeitslosenquote, im Hintergrund die Fassade der New Yorker Börse."
thumb: /static/img/thumbs/wirtschaftskalender-ohne-anmeldung.jpg
draft: false
changelog:
  - datum: 2026-10-01
    text: "Titelbild ersetzt: Chart-Foto raus, stattdessen animierter Rundgang durch den Kalender (Termine, Diagramm, Historie, Nachlesen, Originalquelle, Filter) bis in den Chart."
  - datum: 2026-09-29
    text: "Neuer Abschnitt zur Chart-Anbindung (\"Makrodaten im Chart\"), echten CSS-Bug behoben (Chip-Grafiken waren nie richtig gestylt), Chips verkleinert, schwarze Chart-Grafik entfernt, echtes Google-Antwort-Beispiel ergänzt."
  - datum: 2026-09-28
    text: "Titel gestrafft, quadratisches Vorschaubild für die Startseite ergänzt."
  - datum: 2026-09-20
    text: "Artikel veröffentlicht."
---

<p><em>Ein Wirtschaftskalender, für den man sich nirgends anmelden muss — nicht für die Ansicht, nicht für die API, nicht für den Download. Zahlen, die ohnehin öffentlich sind, gehören niemandem.</em></p>
<p>Kurz vorweg, damit von Anfang an klar ist, was dieser Kalender kann: Jeder Termin lässt sich <strong>herunterladen</strong> (sechs Formate, dazu unten mehr), erscheint als <strong>Diagramm</strong> (Sparkline-Verlauf pro Kennzahl), verlinkt zum <strong>Nachlesen</strong> direkt zur amtlichen Originalquelle — und taucht, das ist der eigentliche Kern dieses Artikels, genau so auch direkt im <strong>Chart</strong> der eigenen Handelsoberfläche „Kontor" auf.</p>
<h2 id="der-eigentliche-punkt-makrodaten-direkt-im-chart">Der eigentliche Punkt: Makrodaten direkt im Chart</h2>
<p>Einen Wirtschaftskalender mit Sparkline und Originalquelle hat inzwischen fast jeder Anbieter. Neu ist die Verknüpfung: In der eigenen Handelsoberfläche „Kontor" taucht genau derselbe Kalender als Modul <strong>„Makrodaten im Chart"</strong> direkt auf der Zeitleiste des Charts auf — als farbiges Symbol genau dort, wo der Termin liegt, filterbar nach Wichtigkeit (Hoch/Mittel/Niedrig, plus ältere Termine optional dazuschaltbar). Ein Klick auf den Marker öffnet direkt über dem Chart eine kleine Box mit Flagge, Titel, Ist-Wert/Prognose/Vorwert und einer kurzen Einordnung — und demselben grünen „Nachlesen"-Knopf wie auf der öffentlichen Kalenderseite. Der Chart selbst muss dafür nie verlassen werden.</p>
<p>Das ist der eigentliche Sinn dieses ganzen Aufbaus: Wer im Chart sitzt und eine Kursbewegung beobachtet, sieht im selben Moment, ob unten auf der Zeitleiste gerade ein Termin ansteht, der die Bewegung erklärt — kein Tab-Wechsel, keine zweite Anwendung. Kontors Analyse-Agent kennt dieselben Termine: Steht ein wichtiger Termin unmittelbar bevor, blendet er das Traden in diesem Zeitfenster bewusst aus und sagt auch, warum — statt eine Zahl zu ignorieren, die er kennt.</p>
<p>Und auch auf der öffentlichen Kalenderseite selbst bleibt der Weg zurück in den eigenen Kalender kurz: Jeder aufgeklappte Termin trägt neben der Originalquelle einen eigenen Knopf „In meinen Kalender (ICS)" — ein Klick, und genau dieser eine Termin landet in Outlook, Apple Kalender oder Google Kalender, ohne gleich den kompletten Datenbestand abonnieren zu müssen. Damit vergisst man ihn garantiert nicht.</p>
<p>Kontor selbst ist als Weiterentwicklung eines Forks von <a href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a> entstanden, einem quelloffenen Multi-Agenten-Framework fürs automatisierte Trading — der Wirtschaftskalender samt Chart-Anbindung ist eine der Erweiterungen, die seither dazugekommen sind.</p>
<style>
.chip-abschnitt::after { content: ""; display: table; clear: both; }
.chip-abschnitt img.chip-bild {
  width: 96px; max-width: 24%; height: auto;
  margin-bottom: 0.4rem;
}
.chip-abschnitt.chip-rechts img.chip-bild { float: right; margin-left: 0.6rem; }
.chip-abschnitt.chip-links img.chip-bild { float: left; margin-right: 0.6rem; }
.chip-abschnitt h2 { clear: both; width: 100%; }
.chip-abschnitt p { text-align: justify; }
.chip-abschnitt .table-wrap { clear: both; }
.durchgestrichen { position: relative; display: inline-block; }
.durchgestrichen::before, .durchgestrichen::after {
  content: ""; position: absolute; left: -6%; right: -6%; top: 50%; height: 3.15px;
  background: #d21f1f; border-radius: 2px; transform-origin: center;
}
.durchgestrichen::before { transform: translateY(-52%) rotate(9deg); }
.durchgestrichen::after { transform: translateY(-48%) rotate(-8deg); }
@media (max-width: 520px) {
  .chip-abschnitt img.chip-bild { float: none; display: block; margin: 0 auto 1rem; max-width: 55%; }
}
</style>
<h2 id="schluss-mit-der-anmeldepflicht-fur-oeffentliche-zahlen">Schluss mit der <span class="durchgestrichen">Anmeldepflicht</span> für öffentliche Zahlen</h2>
<p>Konjunkturdaten — wann die US-Notenbank tagt, wie hoch die Inflation in der Eurozone ausfällt, was die wöchentlichen Erstanträge auf Arbeitslosenhilfe sagen — sind öffentliche Zahlen. Sie stammen von Zentralbanken, Statistikämtern und Ministerien, finanziert aus Steuergeldern, für jeden gedacht. Trotzdem verlangt praktisch jeder Wirtschaftskalender im Netz erst ein Konto, oft eine Kreditkarte, bevor er mehr als die nächsten drei Termine zeigt.</p>
<p><em>Das ist der Teil, der sich nicht rechtfertigen lässt — und genau den räumt dieser Kalender weg. Alles, was ohnehin öffentlich ist, bleibt hier öffentlich: keine Paywall vor der Ansicht, keine Anmeldung vor der API, kein Konto vor dem Download.</em></p>
<p>Hier wird nichts verlangt. Zahlen, die von Zentralbanken und Statistikämtern stammen, aus Steuergeldern finanziert sind, gehören niemandem — also bleiben sie frei, ohne Kleingedrucktes, ohne "Premium"-Stufe, ohne Kreditkarte im Kleingedruckten.</p>
<div class="chip-abschnitt chip-rechts"><h2 id="was-drinsteckt-84000-termine-16-jahre">Was drinsteckt: über 84.000 Termine, 16 Jahre</h2>
<p>Unter <a href="https://brauckmann.ch/kalender/">brauckmann.ch/kalender</a> steht kein Ausschnitt, sondern ein vollständiges Archiv:</p>
<ul>
<li><strong>über 84.000 Konjunkturtermine</strong>, lückenlos seit <strong>1. Januar 2010</strong> bis in die kommenden Wochen</li>
<li><strong>10 Währungsräume</strong>, <strong>19 Länder</strong></li>
<li><strong>1.492 unterschiedliche Kennzahlen-Reihen</strong> — von der Fed-Zinsentscheidung bis zu den wöchentlichen ADP-Beschäftigungsdaten</li>
<li>Zuletzt aktualisiert: automatisch, mehrmals täglich — der genaue Zeitpunkt steht live auf der Seite (<code>Stand: …</code>)</li>
</ul>
<img class="chip-bild" src="/static/img/chips/19-laender.png" alt="19 Länder, 10 Währungsräume">
<p>Jeder einzelne Termin trägt Ist-Wert, Prognose und Vorwert, Kategorie, Marktwirkung (Hoch/Mittel/Niedrig) und — wo bekannt — einen kleinen <strong>Sparkline-Verlauf</strong>: die letzten zwölf Veröffentlichungen derselben Kennzahl als Diagramm, Ist-Werte als durchgezogene Linie, Prognosen gestrichelt daneben. Auf einen Blick sieht man, ob eine Zahl gerade steigt, fällt oder seitwärts pendelt — ohne eine einzige Tabellenzelle lesen zu müssen.</p>
</div>
<div class="chip-abschnitt chip-links"><h2 id="warum-16-jahre-historie-mehr-sind-als-ein-archiv">Warum 16 Jahre Historie mehr sind als ein Archiv</h2>
<p>Eine einzelne Veröffentlichung sagt wenig. Erst im Vergleich über Jahre wird eine Kennzahl aussagekräftig: Wie oft lag die Prognose daneben? In welche Richtung? Und wie schnell hat sich die Lücke zwischen Ist und Prognose danach wieder geschlossen?</p>
<p>Genau das lässt sich mit 16 Jahren Historie beantworten, nicht nur mit den letzten drei Terminen. Als Beispiel die komplette US-Arbeitslosenquote seit 2010 — Ist-Wert und Prognose direkt übereinandergelegt:</p>
<p><img alt="US-Arbeitslosenquote, Ist gegen Prognose, 2010 bis 2026" src="/static/img/01-arbeitslosenquote-usa-light.png" /></p>
<img class="chip-bild" src="/static/img/chips/16-jahre.png" alt="16 Jahre Historie seit 2010">
<p>Über weite Strecken liegen beide Linien fast deckungsgleich — der Markt preist diese Kennzahl gut ein. Auffällig wird es genau dort, wo sie auseinanderlaufen: im Frühjahr 2020, mit dem Corona-Schock, springt die Quote von 4,4 % im März auf 14,7 % im Mai — und selbst diese Prognose lag mit 16,0 % noch darüber, im Folgemonat mit 19,4 % gegen tatsächliche 13,3 % sogar noch deutlicher daneben. Ein sichtbares Zeichen dafür, wie schwer diese Phase einzuschätzen war. Wer solche Muster über eine ganze Kennzahlen-Reihe sieht statt nur den letzten Termin, bekommt ein Gefühl dafür, wie verlässlich der Marktkonsens bei genau dieser Zahl normalerweise ist — und wann er es ausnahmsweise nicht war.</p>
<p>Dieselbe Auswertung lässt sich für jede der 1.492 Kennzahlen-Reihen selbst nachbauen: die komplette Historie steht als Download bereit (dazu gleich mehr), keine Programmierkenntnisse nötig, ein Tabellenprogramm reicht.</p>
</div>
<div class="chip-abschnitt chip-rechts"><h2 id="die-api-kostenlos-dokumentiert-mit-vernunftigem-limit">Die API: kostenlos, dokumentiert, mit vernünftigem Limit</h2>
<p>Wer selbst etwas bauen will, muss nicht scrapen. Es gibt eine echte JSON-API:</p>
<div class="codehilite"><pre><span></span><code>GET https://brauckmann.ch/kalender/api/v1/termine
</code></pre></div>

<img class="chip-bild" src="/static/img/chips/kostenlose-app.png" alt="Kostenlose API">
<p>Filterbar nach Zeitraum, Währung, Wichtigkeit, Kategorie, Freitextsuche. Ohne jeden Schlüssel stehen <strong>10 Abfragen pro Stunde</strong> zur Verfügung — reicht für normales Stöbern und kleine Skripte. Wer mehr braucht, holt sich kostenlos einen API-Schlüssel und bekommt <strong>100 Abfragen pro Stunde</strong>. Die vollständige Referenz liegt als OpenAPI-Spezifikation direkt auf der Seite, keine separate Anmeldung für die Doku nötig.</p>
<p>Diese Grenzen sind bewusst so gesetzt, dass "einfach mal alles auf Verdacht abziehen" nicht funktioniert — wer aber gezielt filtert und nur lädt, was er braucht, kommt jederzeit klar durch.</p>
</div>
<div class="chip-abschnitt chip-links"><h2 id="sechs-downloadformate-fur-jedes-werkzeug-das-passende">Sechs Downloadformate — für jedes Werkzeug das passende</h2>
<img class="chip-bild" src="/static/img/chips/sechs-formate.png" alt="Sechs Downloadformate">
<p>Nicht jeder will mit einer API arbeiten. Deshalb gibt es den kompletten Datenbestand auch direkt zum Herunterladen, in sechs Formaten — als eigene Knöpfe direkt auf der Seite, jeder mit eigenem Icon:</p>
<style>
.dl-format-tabelle svg { width: 22px; height: 22px; display: block; }
.dl-format-tabelle td:first-child { width: 44px; text-align: center; }
</style>
<p>Auch die Downloads sind kostenlos, mit einem knapperen Limit (1× pro Stunde ohne Schlüssel, 4× mit Schlüssel) — wieder: gegen Massenabzug, nicht gegen normale Nutzung.</p>
<div class="table-wrap"><table class="dl-format-tabelle">
<thead>
<tr>
<th></th>
<th>Format</th>
<th>Wofür</th>
</tr>
</thead>
<tbody>
<tr>
<td><svg viewBox="0 0 20 20" aria-hidden="true" style="color:#185abd"><path d="M4.5 2h7l4 4v12h-11z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M11.5 2v4h4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><line x1="6.5" y1="10.5" x2="13.5" y2="10.5" stroke="currentColor" stroke-width="1.3"/><line x1="6.5" y1="13.3" x2="13.5" y2="13.3" stroke="currentColor" stroke-width="1.3"/><line x1="6.5" y1="16.1" x2="11" y2="16.1" stroke="currentColor" stroke-width="1.3"/></svg></td>
<td><strong>CSV</strong> (klassisch)</td>
<td>Skripte, jede Programmiersprache</td>
</tr>
<tr>
<td><svg viewBox="0 0 20 20" aria-hidden="true" style="color:#185abd"><path d="M4.5 2h7l4 4v12h-11z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M11.5 2v4h4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><line x1="6.5" y1="10.5" x2="13.5" y2="10.5" stroke="currentColor" stroke-width="1.3"/><line x1="6.5" y1="13.3" x2="13.5" y2="13.3" stroke="currentColor" stroke-width="1.3"/><line x1="6.5" y1="16.1" x2="11" y2="16.1" stroke="currentColor" stroke-width="1.3"/></svg></td>
<td><strong>CSV (Excel-Variante)</strong></td>
<td>öffnet sich in Excel/Numbers/Google Sheets ohne Umwege bei Umlauten und Zahlenformat</td>
</tr>
<tr>
<td><svg viewBox="0 0 20 20" aria-hidden="true" style="color:#107c41"><rect x="2.5" y="3" width="15" height="14" fill="none" stroke="currentColor" stroke-width="1.4"/><line x1="2.5" y1="7.7" x2="17.5" y2="7.7" stroke="currentColor" stroke-width="1.4"/><line x1="2.5" y1="12.3" x2="17.5" y2="12.3" stroke="currentColor" stroke-width="1.4"/><line x1="7.5" y1="3" x2="7.5" y2="17" stroke="currentColor" stroke-width="1.4"/><line x1="12.5" y1="3" x2="12.5" y2="17" stroke="currentColor" stroke-width="1.4"/></svg></td>
<td><strong>XLSX</strong></td>
<td>fertige Excel-Arbeitsmappe, direkt weiterrechnen — öffnet auch in Apple Numbers</td>
</tr>
<tr>
<td><svg viewBox="0 0 20 20" aria-hidden="true" style="color:#0f80cc"><ellipse cx="10" cy="4.3" rx="6.5" ry="2.3" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M3.5 4.3v11.4c0 1.27 2.91 2.3 6.5 2.3s6.5-1.03 6.5-2.3V4.3" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M3.5 10c0 1.27 2.91 2.3 6.5 2.3s6.5-1.03 6.5-2.3" fill="none" stroke="currentColor" stroke-width="1.4"/></svg></td>
<td><strong>SQLite</strong></td>
<td>die komplette Datenbank als eine Datei — eigene Abfragen, eigene Auswertungen</td>
</tr>
<tr>
<td><svg viewBox="0 0 20 20" aria-hidden="true" style="color:#e8730c"><path d="M4.5 2h7l4 4v12h-11z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M11.5 2v4h4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><line x1="6.5" y1="10.5" x2="13.5" y2="10.5" stroke="currentColor" stroke-width="1.3"/><line x1="6.5" y1="13.3" x2="13.5" y2="13.3" stroke="currentColor" stroke-width="1.3"/><line x1="6.5" y1="16.1" x2="11" y2="16.1" stroke="currentColor" stroke-width="1.3"/></svg></td>
<td><strong>NDJSON</strong></td>
<td>Zeile für Zeile ein JSON-Objekt, ideal für Datenpipelines</td>
</tr>
<tr>
<td><svg viewBox="0 0 20 20" aria-hidden="true" style="color:#d13438"><rect x="2.5" y="3.5" width="15" height="14" fill="none" stroke="currentColor" stroke-width="1.4"/><line x1="2.5" y1="7.3" x2="17.5" y2="7.3" stroke="currentColor" stroke-width="1.4"/><line x1="6" y1="2" x2="6" y2="5" stroke="currentColor" stroke-width="1.4"/><line x1="14" y1="2" x2="14" y2="5" stroke="currentColor" stroke-width="1.4"/><rect x="5.3" y="10" width="2.6" height="2.6" fill="currentColor"/></svg></td>
<td><strong>ICS</strong></td>
<td>als Kalenderabo in Outlook, Apple Kalender oder Google Kalender einbinden — Termine erscheinen direkt im eigenen Kalender</td>
</tr>
</tbody>
</table></div>
</div>
<div class="chip-abschnitt chip-rechts"><h2 id="originalquellen-bei-98-direkt-zur-amtlichen-stelle">Originalquellen: bei 98 % direkt zur amtlichen Stelle</h2>
<img class="chip-bild" src="/static/img/chips/amtliche-quellen.png" alt="98 Prozent amtliche Quellen">
<p>Eine Zahl ohne Herkunft ist nur eine Behauptung. Deshalb verlinkt praktisch jede Kennzahl direkt auf die <strong>amtliche Originalquelle</strong> — die Statistikbehörde, Zentralbank oder Institution, die die Zahl tatsächlich veröffentlicht hat, nicht auf eine dritte Website, die sie nur zitiert.</p>
<p>Die eigene <a href="https://brauckmann.ch/kalender/quellen">Quellen-Übersicht</a> zeigt den Stand ehrlich:</p>
<ul>
<li><strong>929 von 947 Kennzahlen-Mustern</strong> (<strong>98,1 %</strong>) sind bis zur Originalquelle zurückverfolgt</li>
<li><strong>119 verschiedene Herausgeber</strong> — von der Federal Reserve über Eurostat bis zum Schweizer Bundesamt für Statistik</li>
<li>Die verbleibenden 1,9 % sind offen ausgewiesen, nicht versteckt — bekannte Lücke, keine Behauptung</li>
</ul>
<p>Im Termin-Detail steht die Quelle direkt unter „Originalquelle": Titel der amtlichen Seite, ein Klick genügt.</p>
</div>
<div class="chip-abschnitt chip-links"><h2 id="nachlesen-recherche-in-googles-ki-modus-ein-klick">„Nachlesen": Recherche in Googles KI-Modus, ein Klick</h2>
<img class="chip-bild" src="/static/img/chips/ki-recherche.png" alt="KI-Recherche und Analyse">
<p>Jeder Termin trägt zusätzlich einen Knopf: <strong>Nachlesen</strong>. Der öffnet keine Stichwortsuche, sondern einen vollständig ausformulierten Recherche-Auftrag in Googles KI-Modus (<code>udm=50</code>) — mit dem Termin, dem Datum und den bereits bekannten Zahlen (Ist/Prognose/Vorherig) direkt im Prompt, damit die Antwort nicht selbst nach der Zahl suchen und sie dabei verwechseln muss.</p>
<p>So sieht das in echt aus — Zeile anklicken, Detail öffnet mit Ist/Prognose/Originalquelle und Sparkline, „Nachlesen" ist als grüner Knopf kaum zu übersehen:</p>
<p><img src="/static/img/02-kalender-detail-demo.gif" alt="Kalender-Detail öffnet sich, Ist/Prognose/Originalquelle erscheinen, der Nachlesen-Knopf wird hervorgehoben" style="max-width:100%;border-radius:6px;border:1px solid #e4e6ea"></p>
<p>Die Antwort kommt jedes Mal in derselben Gliederung:</p>
<ol>
  <li><strong>📌 Überblick</strong> — die Kernzahlen zuerst, klar beschriftet</li>
  <li><strong>📊 Hintergrund &amp; Historie</strong> — was sich seit der letzten Veröffentlichung geändert hat</li>
  <li><strong>📈 Ausblick &amp; Prognosen</strong> — was die Zahl für die kommenden Termine bedeutet</li>
  <li><strong>🔍 Analysten- und Broker-Konsens</strong></li>
  <li><strong>🎓 Für Einsteiger</strong> — kurze Einordnung, was die Kennzahl überhaupt misst</li>
</ol>
<p>Immer dieselbe Reihenfolge, dieselben Überschriften, dieselben Emoji als Wiedererkennung — wer eine Kennzahl nicht kennt, muss nicht erst googeln, wie sie einzuordnen ist, der Klick liefert die Einordnung fertig mit.</p>
<p>Damit das kein abstraktes Versprechen bleibt, hier die echte Antwort zu einem realen Termin (Revised UoM Inflation Expectations, 25.9.2026) — unverändert, so wie Google sie liefert, inklusive der Quellen-Fussnoten am Ende:</p>
<p><img src="/static/img/03-nachlesen-google-beispiel.png" alt="Echtes Beispiel der Google-KI-Modus-Antwort: Überblick, Hintergrund, Ausblick, Analysten-Konsens, für Einsteiger, mit Quellen" style="max-width:100%;border-radius:8px;border:1px solid var(--border)"></p>
</div>
<h2 id="modern-schnell-ohne-ballast">Modern, schnell, ohne Ballast</h2>
<p>Die Seite selbst ist bewusst schlank gebaut: eine eigene, kleine Flask-Anwendung statt eines vollen CMS, live gefiltert ohne Neuladen, mit Excel-artigen Spaltenfiltern in der Kopfzeile, hell und dunkel passend zum System-Theme des Browsers. Keine Werbung, kein Tracking über das technisch Nötige hinaus, keine Cookie-Banner-Orgie.</p>
<h2 id="zusammengefasst">Zusammengefasst</h2>
<p>Ansehen, filtern, als CSV/Excel/SQLite/NDJSON/ICS herunterladen, per API abfragen, jede Zahl bis zur Originalquelle zurückverfolgen, per Klick tiefer recherchieren — alles kostenlos, alles ohne Konto. Der Kalender selbst gehört allen.</p>
<p>👉 <a href="https://brauckmann.ch/kalender/">brauckmann.ch/kalender</a></p>
