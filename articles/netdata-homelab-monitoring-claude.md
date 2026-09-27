---
slogan: "Netdata bringt seit Version 2.6 einen eigenen MCP-Server mit — ganz ohne Zusatzinstallation."
title: "Monitoring fürs Homelab in 15 Minuten: Netdata + Claude als MCP-Server (read & write*)"
slug: netdata-homelab-monitoring-claude
date: 2026-09-20
updated: 2026-09-20
description: "Netdata installieren, das eingebaute Dashboard nutzen und Claude per MCP direkt an die eigenen Metriken anschließen — für ein Homelab oder eine Umgebung mit weniger als fünf Nodes, ohne Cloud-Konto und ohne Yaml-Wüste."
summary: >-
  Netdata bringt seit Version 2.6 einen eigenen MCP-Server mit — ganz ohne Zusatzinstallation. Wer ein Homelab oder eine kleine Umgebung mit ein paar Nodes betreibt, hat in gut 15 Minuten ein vollständiges Monitoring mit Hunderten Metriken pro Sekunde, plus einen KI-Assistenten, der die Daten tatsächlich versteht: Claude fragt "Warum ist der Server langsam?" nicht mehr rhetorisch, sondern zieht sich die echten Zahlen. Installation, erste Ansicht, MCP-Anbindung, eine Beispielfrage — und ein Hinweis, worauf zu achten ist, sobald man das Ganze von außerhalb des eigenen Netzes erreichbar machen will.
tags: [Monitoring, Netdata, Claude, Homelab, MCP]
image: /static/img/netdata-dashboard-uebersicht.png
draft: false
---

<p><em>Netdata installieren, das Dashboard einmal ansehen, Claude als MCP-Client anschließen — fertig. Kein Cloud-Konto nötig, keine Konfigurationsdatei, die erst verstanden werden muss.</em></p>
<p>Netdatas eigene Oberfläche ist absichtlich umfangreich — Hunderte Metriken, Dutzende Ansichten, für tiefe Analyse genau richtig. Für den täglichen Blick reicht das oft zu viel. Das folgende Dashboard hat Claude für genau diesen Fall gebaut: ein eigenes, schlankes Layout, das die wichtigsten Zahlen aus Netdata auf einen Blick zusammenfasst, statt sich durch die volle Netdata-Oberfläche zu klicken.</p>
<p>
<img alt="Torwächter-Dashboard-Entwurf: Perimeter-Monitoring für Cloudflare-Proxy und internes Netzwerk" src="/static/img/torwaechter-mockup-light.png">
</p>
<p>Für die meisten Homelabs und kleinen Setups — ein Server, ein NAS, ein paar Raspberry Pis, vielleicht ein Handvoll Container — ist professionelles Monitoring bisher an zwei Dingen gescheitert: entweder es brauchte eine eigene Prometheus/Grafana-Installation mit Zeit, die man an einem Wochenende nicht wirklich übrig hat, oder es war eine der leichteren Lösungen, die dann doch nur eine Handvoll Kennzahlen zeigen. Netdata liegt dazwischen — und bringt seit Kurzem etwas mit, das den Unterschied macht: einen eingebauten MCP-Server, über den ein KI-Assistent wie Claude direkt auf die Live-Metriken zugreifen kann.</p>
<h2 id="installation-ein-befehl">Installation: ein Befehl</h2>
<p>Netdata hat ein offizielles Installationsskript, das auf so gut wie jeder gängigen Linux-Distribution funktioniert (Debian, Ubuntu, Raspberry Pi OS, Fedora, Arch — auch auf ARM, also problemlos auf einem Raspberry Pi):</p>
<div class="codehilite"><pre><span></span><code>curl<span class="w"> </span>-Ss<span class="w"> </span>https://get.netdata.cloud/kickstart.sh<span class="w"> </span><span class="p">|</span><span class="w"> </span>bash
</code></pre></div>

<p>Das Skript erkennt die Distribution selbst, installiert die passenden Pakete und startet den Netdata-Dienst direkt im Anschluss. Nach ein bis zwei Minuten ist das Dashboard erreichbar:</p>
<div class="codehilite"><pre><span></span><code>http://&lt;deine-server-ip&gt;:19999
</code></pre></div>

<p>Kein Login, kein Cloud-Konto nötig — das Dashboard funktioniert vollständig lokal und zeigt sofort an, was gerade passiert: CPU pro Kern, Arbeitsspeicher, Netzwerkdurchsatz, Festplatten-I/O, laufende Prozesse, und bei den meisten Distributionen automatisch erkannt auch Docker-Container, laufende Datenbanken oder Webserver, falls welche installiert sind.</p>
<h2 id="die-erste-ansicht">Die erste Ansicht</h2>
<p>Das Dashboard sammelt ab der ersten Sekunde und aktualisiert sich laufend — pro Sekunde, nicht alle fünf Minuten wie bei den meisten klassischen Lösungen. Das merkt man sofort, wenn ein kurzer CPU-Spike auftaucht: er ist als einzelner Zacken sichtbar, nicht als geglättete Linie, die den eigentlichen Moment verschluckt.</p>
<p><img alt="Alerts-Ansicht mit einem ausgelösten Alarm" src="/static/img/netdata-alerts-ansicht.png" /></p>
<p>Netdata bringt außerdem von Haus aus rund 300 vordefinierte Alarme mit — Festplatte fast voll, Swap-Nutzung zu hoch, ein Dienst nicht erreichbar, und so weiter. Die muss man nicht selbst konfigurieren; sie laufen von Anfang an mit und tauchen im Reiter „Alerts" auf, sobald einer davon anschlägt.</p>
<h2 id="claude-als-mcp-client-anschlieen">Claude als MCP-Client anschließen</h2>
<p>Das ist der Teil, der den Unterschied macht. Ab Netdata Agent Version 2.6.0 läuft automatisch ein MCP-Server mit — ohne jede Zusatzinstallation, ohne eigenen Prozess, ohne Konfigurationsdatei. Erreichbar ist er unter:</p>
<div class="codehilite"><pre><span></span><code>http://&lt;deine-server-ip&gt;:19999/mcp
</code></pre></div>

<p>In Claude Desktop (oder Claude Code) trägt man diesen Endpunkt als benutzerdefinierten Connector ein:</p>
<ul>
<li><strong>Einstellungen → Connectors → Benutzerdefinierten Connector hinzufügen</strong></li>
<li>URL: <code>http://&lt;deine-server-ip&gt;:19999/mcp</code></li>
<li>Authentifizierung: <strong>Keine Anmeldung</strong> — solange Claude im selben Netz läuft wie der Server, ist kein zusätzliches Passwort nötig</li>
</ul>
<p>Nach dem Verbinden stehen Claude gut ein Dutzend Werkzeuge zur Verfügung: Metriken durchsuchen, Anomalien der letzten Stunden finden, Alarme auflisten, Knoten-Details abrufen, laufende Prozesse einsehen. Alles live, alles echte Daten vom eigenen Server.</p>
<h2 id="eine-beispielfrage">Eine Beispielfrage</h2>
<p>Statt selbst durchs Dashboard zu klicken, kann man jetzt einfach fragen:</p>
<blockquote>
<p>„Warum war mein Server heute Nachmittag zwischen 14 und 16 Uhr langsam?"</p>
</blockquote>
<p>Claude sucht sich über die MCP-Werkzeuge selbstständig zusammen, welche Metriken in diesem Zeitraum ungewöhnlich waren, ob es einen CPU- oder Speicher-Ausreißer gab, und ob ein Alarm ausgelöst wurde — und antwortet mit der tatsächlichen Ursache statt mit einer allgemeinen Vermutung. Das Dashboard bleibt trotzdem da — für den Blick aufs große Bild ist die grafische Ansicht weiterhin die bessere Wahl, für die gezielte Nachfrage danach ist der MCP-Server der schnellere Weg.</p>
<h2 id="wenns-uber-das-eigene-netz-hinausgehen-soll">Wenn's über das eigene Netz hinausgehen soll</h2>
<p>Für ein Homelab mit Claude auf demselben Rechner oder im selben WLAN reicht das oben Beschriebene komplett aus. Sobald der MCP-Server aber von claude.ai oder der Claude-Desktop-App aus erreichbar sein soll, während man selbst unterwegs ist, ändert sich eine Sache grundlegend: Der Verbindungsversuch kommt dann nicht mehr vom eigenen Gerät, sondern aus der Cloud-Infrastruktur von Anthropic — eine Adresse, die nur im eigenen (V)LAN oder nur im eigenen VPN erreichbar ist, funktioniert von dort aus nicht, egal wie korrekt sie sonst konfiguriert ist. Für diesen Fall braucht es einen öffentlich erreichbaren HTTPS-Endpunkt und einen echten Zugriffsschutz (Token oder OAuth) davor — das sprengt für unter fünf Nodes den Rahmen dieses Artikels, ist aber der Punkt, an dem man aufpassen muss, bevor man sich wundert, warum die Verbindung „einfach nicht geht", obwohl lokal alles funktioniert.</p>
<h2 id="vom-lesen-zum-handeln-ein-eigener-mcp-server-mit-schreibzugriff">Vom Lesen zum Handeln: ein eigener MCP-Server mit Schreibzugriff mit MFA</h2>
<figure class="mcp-diagramm">
<div class="chain">

  <div class="node">
    <div class="circ" style="background:var(--md-accent-bg)"><i class="ti ti-microphone" style="font-size:24px;color:var(--md-accent-fg)"></i></div>
    <div class="lbl">Handy</div>
    <div class="sub">Sprachmodus</div>
  </div>

  <div class="link voicewrap">
    <div class="top-label">Frage über</div>
    <div class="wavebars">
      <div class="wavebar" style="height:6px;animation-delay:0s"></div>
      <div class="wavebar" style="height:14px;animation-delay:.15s"></div>
      <div class="wavebar" style="height:20px;animation-delay:.3s"></div>
      <div class="wavebar" style="height:14px;animation-delay:.45s"></div>
      <div class="wavebar" style="height:6px;animation-delay:.6s"></div>
    </div>
    <div class="bottom-label">Sprachmodus</div>
  </div>

  <div class="node">
    <div class="circ" style="background:var(--md-coral-bg)"><i class="ti ti-server-2" style="font-size:24px;color:var(--md-coral-fg)"></i></div>
    <div class="lbl">MCP-Server</div>
    <div class="sub">Schnittstelle</div>
  </div>

  <div class="link">
    <i class="ti ti-arrows-left-right" style="font-size:15px"></i>
    <span class="top-label">API</span>
    <span class="bottom-label">read/write</span>
  </div>

  <div class="node">
    <div class="circ" style="background:var(--md-success-bg)"><i class="ti ti-activity" style="font-size:24px;color:var(--md-success-fg)"></i></div>
    <div class="lbl">Monitoring</div>
    <div class="sub">z.&#8201;B. Netdata</div>
  </div>

  <div class="link">
    <i class="ti ti-arrow-right" style="font-size:15px"></i>
    <span class="top-label">Agent</span>
    <span class="bottom-label">HTTP · SSH<br>PowerShell usw.</span>
  </div>

  <div class="node">
    <div class="circ" style="background:var(--md-warning-bg)"><i class="ti ti-cpu" style="font-size:24px;color:var(--md-warning-fg)"></i></div>
    <div class="lbl">Hypervisor</div>
    <div class="sub">oder Cloud</div>
  </div>

</div>

<svg class="returnrow" width="100%" viewBox="0 0 680 70">
  <defs><marker id="mcp-rarrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>
  <path class="returnpath" d="M255,15 C195,45 130,45 65,15" fill="none" stroke="var(--md-accent-fg)" stroke-width="1.2" marker-end="url(#mcp-rarrow)"/>
  <circle cx="160" cy="42" r="11" fill="var(--md-accent-bg)"/>
  <text x="160" y="42" text-anchor="middle" dominant-baseline="central" font-size="12" fill="var(--md-accent-fg)">&#9834;</text>
  <text x="160" y="64" text-anchor="middle" font-size="12" fill="var(--fg-muted)">Antwort (Sprachmodus)</text>
</svg>
<figcaption>Der volle Pfad: Sprachbefehl auf dem Handy → MCP-Server als Schnittstelle → Monitoring liest/schreibt über die API → der eigentliche Agent (SSH, HTTP, PowerShell) handelt auf Hypervisor oder Cloud. Die Antwort läuft denselben Weg zurück.</figcaption>
</figure>
<p>Der oben beschriebene MCP-Server ist bewusst nur lesend — Claude kann Metriken abfragen, aber nichts am System verändern. Für den eigentlichen Wunschtraum vieler Homelab-Betreiber reicht das aber nicht: „Sag mir per Sprachbefehl, ob das Backup heute Nacht geklappt hat, und wenn nicht, stoß es einfach neu an" — während man im Auto sitzt und keine Hand frei hat, um selbst nachzuschauen. Das kann Netdatas eingebauter MCP-Server nicht, und soll er auch nicht: Lesen und Handeln sind zwei völlig unterschiedliche Risikostufen, und Netdata trennt sie absichtlich.</p>
<p>Wer wirklich handeln lassen will — einen Dienst neu starten, ein Backup-Skript anstoßen, einen Alarm quittieren —, braucht dafür einen <strong>eigenen, zusätzlichen</strong> MCP-Server, den man selbst baut und selbst absichert. Grober Fahrplan, wie das in der Praxis aussieht:</p>
<ul>
<li><strong>Eigene Tools statt Netdata-Tools:</strong> ein kleiner, selbst geschriebener MCP-Server (z. B. mit dem offiziellen Python- oder TypeScript-SDK) mit gezielten, benannten Funktionen wie <code>backup_jetzt_starten()</code> oder <code>dienst_neu_starten(name)</code> — keine generische „Shell-Befehl ausführen"-Funktion, die alles und damit auch zu viel könnte.</li>
<li><strong>Echte Authentifizierung, nicht nur ein Token:</strong> sobald ein Werkzeug etwas verändert, reicht „im selben Netz" als Zugriffsschutz nicht mehr. OAuth mit einem echten Identitätsanbieter (Microsoft Entra ID, Google, Authentik o. Ä.) plus Multi-Faktor-Anmeldung ist hier die Grundvoraussetzung, kein optionales Extra.</li>
<li><strong>Bestätigung vor Ausführung bei heiklen Aktionen:</strong> ein Neustart oder ein Backup-Anstoß sollte einen expliziten Bestätigungsschritt verlangen (Claude fragt zurück, bevor es ausführt), statt beim ersten Missverständnis gleich zu handeln — gerade bei einer Sprachanfrage im Auto, wo Spracherkennungsfehler realistisch sind.</li>
<li><strong>Ein Protokoll, das mitschreibt:</strong> jede ausgeführte Aktion landet mit Zeitstempel in einem eigenen Audit-Log — nicht, weil man niemandem vertraut, sondern weil man hinterher genau nachvollziehen können muss, was wann warum passiert ist.</li>
</ul>
<p>Das ist mehr Aufwand als der Read-only-Server oben — aber genau der Aufwand, der den Unterschied ausmacht zwischen „ich kann meine Daten abfragen" und „ich kann von unterwegs, freihändig, tatsächlich etwas reparieren lassen".</p>
<h2 id="zusammengefasst">Zusammengefasst</h2>
<p>Ein Installationsbefehl, zwei Minuten Wartezeit, ein Connector-Eintrag in Claude — und ein Homelab mit weniger als fünf Nodes hat ein vollständiges, sekundengenaues Monitoring samt KI-Assistent, der die eigenen Metriken tatsächlich versteht. Kein Grafana-Stack, kein Yaml, kein Cloud-Zwang.</p>
