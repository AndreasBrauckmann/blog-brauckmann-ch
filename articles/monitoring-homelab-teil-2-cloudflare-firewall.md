---
slogan: "Eine Woche nach dem ersten eigenen MCP-Server steht fest: Die KI hat das System innerhalb von 48 Stunden selbst so eingestellt, dass kleine Fehler sofort auffallen und behoben werden."
title: "Monitoring fürs Homelab, Teil II: Cloudflare, Firewall und das große Ganze"
slug: monitoring-homelab-teil-2-cloudflare-firewall
date: 2026-09-28
updated: 2026-09-28
description: "Eine Woche nach dem ersten selbstgebauten MCP-Server: sechs neue Dashboards, ein Sicherheitsnetz aus Cloudflare-Firewall und Tailscale-Funnel, und der Befund, dass Human-in-the-Loop für die kleinen Dinge immer unwichtiger wird."
summary: >-
  Vor einer Woche war der erste eigene, schreibfähige MCP-Server noch ein "grober Fahrplan" am Ende eines Artikels. Was seither daraus geworden ist: sechs Live-Dashboards (Gatekeeper, Ascent, Backup, System, Alerts, Connections), die innerhalb von 48 Stunden nach dem ersten Commit bereits eine echte Entra-ID-Anmeldung, echte Cloudflare-Firewall-Daten und einen Fix für einen selbst verursachten Fehler hatten. Der Artikel zeigt das neue Verbindungen-Dashboard, das auf einen Blick zeigt, was heute alles überwacht wird -- MCP-Server, Broker, Cloudflare, Search Console, Wirtschaftskalender, LLM-Wrapper -- und zeichnet das große Sicherheitsbild: zwei komplett getrennte Zugangswege (Cloudflare-Tunnel für brauckmann.ch, Tailscale Funnel für die eigene ts.net-Adresse), die beide auf dieselbe, nach außen portlose Infrastruktur treffen.
tags: [Monitoring, Cloudflare, Security, Homelab, Claude, MCP]
image: /static/img/monitoring2-verbindungen-light.png
draft: false
---

<p><em>Vor einer Woche endete <a href="/artikel/netdata-homelab-monitoring-claude/">der erste Artikel dieser Reihe</a> mit einem "groben Fahrplan": Wer aus dem reinen Lese-MCP-Server einen echten Assistenten machen will, der auch handeln darf, braucht eigene Tools, echte Authentifizierung, einen Bestätigungsschritt vor heiklen Aktionen und ein Protokoll, das mitschreibt. Eine Woche und 35 Commits später ist aus dem Fahrplan ein laufendes System geworden -- und ein paar Dinge daran haben mich selbst überrascht.</em></p>

<h2 id="teil-1-48-stunden">Eine Woche später: 48 Stunden bis zur Selbstjustierung</h2>

<p>Der neue Server ging am 20.9. um 21:57 Uhr in Betrieb -- read-only, nur intern über das eigene Tailscale-Netz erreichbar. Was in den folgenden gut 31 Stunden passierte, lässt sich lückenlos im Git-Log nachvollziehen, weil jede Änderung ein eigener Commit ist:</p>

<ul>
<li><strong>Innerhalb der ersten Stunde:</strong> aus einem geteilten Passwort wurde eine echte Microsoft-Entra-ID-Anmeldung mit Multi-Faktor -- inklusive der Kleinarbeit, die dazugehört (OAuth-Discovery-Dokument ergänzt, fehlender Standard-Scope nachgetragen, eigener App-Scope angelegt).</li>
<li><strong>Am nächsten Vormittag:</strong> ein erstes richtiges Dashboard ("Gatekeeper") mit echten Cloudflare-Firewall-Daten statt Platzhaltertext -- und noch am selben Vormittag der Fund, dass eine Kennzahl direkt und live bei Cloudflare abgefragt wurde, was bei jedem Seitenaufruf Kontingent gekostet hätte. Umgebaut auf einen Netdata-Sensor, der das im Hintergrund erledigt.</li>
<li><strong>Bis zum übernächsten Morgen, 31 Stunden nach dem ersten Commit:</strong> sechs vollständige Dashboards, ein zentrales Menü, eine Ampel-Färbung nach echtem Alarmstatus -- und mittendrin ein Moment, der die Sache auf den Punkt bringt: Ein automatischer "Beheben"-Knopf für einen vollen Arbeitsspeicher hatte den falschen Mechanismus benutzt (er leerte einen Cache, der mit dem eigentlichen Problem -- zu wenig Swap -- nichts zu tun hatte). Der Fehler wurde nicht von mir gefunden, sondern <strong>13 Minuten später im selben Lauf korrigiert</strong>, mit einem Commit, dessen Nachricht es selbst so benennt: "fixt eigenen Fehler".</li>
</ul>

<p>Das ist der eigentliche Befund dieser Woche, und er ist grösser als jedes einzelne Dashboard: Wenn ein System <strong>sich selbst beim Fehlermachen zusehen kann</strong> -- weil jeder Handgriff sofort als Metrik, Log-Zeile oder Alarm sichtbar wird -- dann muss ein Mensch nicht mehr jeden einzelnen Schritt kontrollieren. Kleinere Fehler fallen sofort auf und werden sofort behoben, oft bevor überhaupt jemand hinschaut. Genau dasselbe Muster zeigte sich diese Woche noch zweimal, in kleinerem Massstab: ein kurzzeitiger Cloudflare-API-Ausfall (sechs Minuten, danach von selbst wieder grün) und ein Wirtschaftskalender-Termin, der strukturell nie einen Wert bekommt und fälschlich als "überfällig" gemeldet wurde -- beides in derselben Sitzung gefunden und behoben, in der sie auffielen. Human-in-the-Loop wird damit nicht überflüssig -- aber für genau diese Klasse von Problemen, den kleinen, klar erkennbaren Fehlern, spürbar unwichtiger.</p>

<h2 id="teil-2-das-dashboard">Das neue Dashboard: alles auf einen Blick</h2>

<p><em>Nachtrag vom selben Abend:</em> Die komplette Oberfläche lief bis eben auf Deutsch -- auf ausdrücklichen Wunsch jetzt komplett Englisch, bis in die Menüs und die von der KI selbst zusammengebauten Statustexte hinein, damit auch ein internationales Publikum sofort versteht, was da steht. Alle sechs Seiten, als zwei durchlaufende Dreiergruppen:</p>

<p>
<img src="/static/img/monitoring2-dashboards-trio-a.gif" alt="Animation: Gatekeeper-, Ascent- und Backup-Dashboard im Wechsel" style="max-width:100%;border-radius:12px;border:1px solid var(--border)">
</p>

<p>
<img src="/static/img/monitoring2-dashboards-trio-b.gif" alt="Animation: System-, Alerts- und Connections-Dashboard im Wechsel" style="max-width:100%;border-radius:12px;border:1px solid var(--border)">
</p>

<p>Genau dieses Zusehen-können ist der Kern der "Connections"-Seite (im zweiten Loop oben). Sechs Gruppen, auf einen Blick:</p>

<ul>
<li><strong>MCP-Server</strong> -- alle laufenden MCP-Prozesse dieses Ökosystems (Wirtschaftskalender, Produkte, Kontor-Status, dieser Server selbst), inklusive der Frage, ob der öffentliche Zugang über brauckmann.ch tatsächlich noch dort ankommt, wo er soll.</li>
<li><strong>Broker</strong> -- vier unabhängige Saxo-Bank-Verbindungen (SIM, Live, Tour-Demo, ein separates Projekt), jede mit eigenem Keepalive-Log.</li>
<li><strong>Cloudflare</strong> -- zwei API-Tokens (eigene Zone, Website-Projekt) plus eine Live-Liste aller Subdomains inklusive HTTP-Status.</li>
<li><strong>Google / Search Console</strong> -- ob das Dienstkonto für die tägliche Indexierungsprüfung noch funktioniert.</li>
<li><strong>Wirtschaftskalender</strong> -- ob Termine, die schon vergangen sind, auch wirklich einen Ist-Wert bekommen haben.</li>
<li><strong>LLM-Wrapper</strong> -- die eigene, Claude-Abo-basierte OpenAI-kompatible Schnittstelle, über die sämtliche Analysen laufen.</li>
</ul>

<p>Das klingt nach viel -- und ist es auch. Das ganze Ökosystem ist über die Zeit gewachsen: mehrere Docker-Container, mehrere Host-systemd-Dienste, zwei getrennte öffentliche Zugänge, vier Broker-Verbindungen, ein Dutzend Subdomains. Unter der Haube stehen dafür heute weit über hundert einzelne Sensoren und Zusammenhänge. Der eigentliche Punkt ist aber nicht die Zahl, sondern dass sich all das mit einem kurzen Gespräch mit der KI durchsuchen, erklären und -- wie die beiden Fixes von heute Nachmittag zeigen -- auch korrigieren lässt, ohne dass ein Mensch selbst durch Log-Dateien, Cronjobs und Datenbanktabellen graben muss.</p>

<h2 id="teil-3-das-grosse-bild">Das große Bild: zwei Wege ins System, eine Kontrolle</h2>

<p>Der spannendere Teil ist aber, was hinter diesen grünen Punkten steckt -- speziell bei Cloudflare, wo öffentlich erreichbare Dienste am meisten Angriffsfläche bieten.</p>

<figure class="shot-pair">
<img class="bild-hell" src="/static/img/monitoring2-torwaechter-light.png" alt="Gatekeeper-Dashboard: Verkehrsweg Internet -> Cloudflare Proxy -> Cloudflare Tunnel -> Internes Netzwerk, ende-zu-ende ausgehend, kein eingehender Port">
<img class="bild-dunkel" src="/static/img/monitoring2-torwaechter-dark.png" alt="Gatekeeper-Dashboard: Verkehrsweg Internet -> Cloudflare Proxy -> Cloudflare Tunnel -> Internes Netzwerk, ende-zu-ende ausgehend, kein eingehender Port">
<figcaption>Das "Gatekeeper"-Dashboard: 8'935 Anfragen in 24 Stunden, 25 automatisch blockiert -- und der Weg, den jede einzelne davon nimmt.</figcaption>
</figure>

<p>Die kurze Fassung des Sicherheitsbilds: Es gibt zwei völlig unabhängige, öffentlich erreichbare Wege in dieses System hinein -- und keiner davon öffnet direkt einen Port am Server.</p>

<ul>
<li><strong>Weg 1, brauckmann.ch und Geschwister:</strong> Cloudflare als DNS- und Proxy-Schicht mit WAF, Bot-Schutz und Firewall-Regeln davor, dahinter ein Cloudflare-Tunnel (<code>cloudflared</code>), der die Verbindung <strong>ausgehend</strong> vom Server aus aufbaut -- am Router ist dafür kein einziger Port geöffnet. Der Tunnel liefert an einen zentralen Caddy-Edge, der je nach Pfad an den richtigen internen Dienst weiterreicht. Die eine dokumentierte Ausnahme: zwei technische Subdomains für MCP-Anbindungen zeigen direkt auf einen lokalen Port statt über den gemeinsamen Caddy-Edge zu laufen -- ohne die gemeinsamen Security-Header, dafür mit einem eigenen Bearer-Token als Schutz. Bewusst offen dokumentiert, nicht versteckt.</li>
<li><strong>Weg 2, die eigene ts.net-Adresse:</strong> Tailscale Funnel, also ein VPN-Mesh mit einer eigenen, öffentlich freigeschalteten Ausnahme -- komplett getrennt von Cloudflare, eigenes Zertifikat, eigener Pfad, landet aber am Ende beim selben internen Caddy-Edge.</li>
</ul>

<p>Beide Wege laufen am Ende durch dieselbe lokale Infrastruktur auf demselben Server -- aber jeder Dienst dahinter hat seine eigene, unabhängige Zugriffskontrolle: die Trading-Oberfläche selbst mit einer dreistufigen Vertrauenslogik (lokales Netz / Tailnet / öffentlicher Funnel, mit Passwort und Einmalcode für die zwei strengeren Stufen), die Status- und Admin-Dashboards über echte Microsoft-Entra-ID-Anmeldung mit Multi-Faktor. Fällt einer der beiden äusseren Wege aus oder wird missbraucht, ist der andere davon komplett unberührt -- zwei unabhängige Frontends vor derselben, nach aussen portlosen Basis.</p>

<h2 id="was-das-fuer-unternehmen-bedeutet">Was das für Unternehmen bedeutet</h2>

<p>Der Nutzen davon hört nicht beim eigenen Homelab auf. Kontinuierliches, KI-gestütztes Monitoring wirkt als Sicherheitsnetz, unabhängig davon, wer ein System im Tagesgeschäft betreut: Es prüft Konfiguration und Verhalten laufend gegen den Ist-Zustand, fängt Fehlkonfigurationen und Abweichungen ab, bevor sie zum Vorfall werden, und gibt dem Management eine objektive, nachvollziehbare Kontrollebene -- statt sich allein auf die Selbsteinschätzung einer einzelnen Fachkraft verlassen zu müssen. Das ist für jedes Unternehmen relevant, unabhängig davon, wie erfahren das eigene Team ist.</p>

<p>Ein Punkt daraus verdient es, offen ausgesprochen zu werden: In der Praxis erleben wir immer wieder, dass eigenes Versagen vertuscht und stattdessen dem externen Dienstleister angelastet wird -- bis hin zum Verlust von Kundenbeziehungen, die eigentlich intakt gewesen wären. Das ist keine Fachfrage mehr, das ist eine Schande für die Branche. Eine lückenlose, automatisiert mitschreibende Kontrollebene macht genau das unmöglich: Wenn jede Änderung, jeder Alarm und jeder Fix mit Zeitstempel dokumentiert ist, lässt sich im Streitfall objektiv klären, wo eine Ursache tatsächlich lag -- statt es bei Behauptung gegen Behauptung zu belassen.</p>

<blockquote>
<p>Läuft die eigene ICT-Landschaft über die Jahre zu einem unübersichtlichen Gewucher aus Diensten, Ausnahmen und Alt-Konfigurationen zusammen? Wir helfen gerne dabei, dieses Ökosystem zurechtzustutzen, das wilde Wachstum an Irritationen einzudämmen und es mit KI-gestützten Mechanismen dauerhaft in den Griff zu bekommen.</p>
</blockquote>

<h2 id="zusammengefasst">Zusammengefasst</h2>

<p>Eine Woche, 35 Commits, sechs Dashboards, ein selbst gefundener und selbst behobener Fehler binnen 13 Minuten -- und ein Sicherheitsbild mit zwei unabhängigen, portlosen Zugangswegen zu derselben Infrastruktur. Der grösste Unterschied zur Homelab-Realität von vorher ist nicht die Zahl der Sensoren, sondern dass kleine Fehler nicht mehr liegen bleiben, bis jemand zufällig draufschaut.</p>
