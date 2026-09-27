---
slogan: "„Hey Siri, Windows.“ – der Samsung-Monitor mit eingebautem KVM-Switch schaltet um, Maus und Tastatur wandern mit. Per Sprache, mit Gratis-Software."
title: "„Hey Siri, Windows“: Samsung-Monitor mit eingebautem KVM-Switch per Sprache umschalten – Mac- und Windows-Notebook"
slug: kvm-switch-per-sprache
date: 2026-09-27
updated: 2026-09-27
description: "Videoschnitt auf dem Mac, PowerShell und Azure auf Windows: Für mein Zero-Trust-Assessment-Video wechsle ich dutzende Male pro Stunde das Notebook. Jetzt genügt ein Satz zu Siri – Bildschirm, Maus und Tastatur schalten um. So habe ich es gebaut."
summary: >-
  Für ein Video zum Zero Trust Assessment arbeite ich parallel auf zwei Notebooks: Auf dem Mac schneide und rendere ich, auf dem Windows-Notebook laufen PowerShell-Skripte und die Verbindungen zu Azure und Microsoft Entra. Jeder Wechsel kostete drei Knöpfe – dutzende Male pro Stunde. Mit vier Gratis-Bausteinen geht das jetzt per Sprache: ddcctl schaltet den Eingang des Monitors, Deskflow reicht Maus, Tastatur und Zwischenablage über das Netzwerk an das Windows-Notebook weiter, und ein Apple-Kurzbefehl verbindet beides mit Siri. Der Artikel zeigt den Aufbau, die Komponenten, sechs Stolpersteine und wie man den SSH-Zugang dafür sauber absichert.
tags: [Arbeitsplatz, Automatisierung, Zero Trust, macOS, Windows]
image: /static/img/kvm-per-sprache-eyecatcher.png
draft: false
---

*Videoschnitt auf dem Mac, PowerShell und Azure auf Windows – und dazwischen ein einziger Satz: „Hey Siri, Windows.“ Der Monitor schaltet um, Maus und Tastatur wandern mit, die Zwischenablage auch. Kein Knopf, keine Kabel umstecken.*

<p style="text-align:center"><video src="/static/img/kvm-per-sprache-animation.mp4" poster="/static/img/kvm-per-sprache-animation-poster.jpg" playsinline controls style="max-width:100%;border-radius:12px" aria-label="Animation: Hey Siri, Mac – Hey Siri, Windows – Hey Siri, shutdown – Hey Siri, wake up"></video></p>

## Das Ergebnis in einem Satz

**„Hey Siri, Windows.“** – und in wenigen Sekunden zeigt der Monitor das Windows-Notebook. Maus und Tastatur werden gleich mit umgeschaltet – **und sogar der Ton**: Die Boxen hängen am Monitor und spielen automatisch das Notebook, das gerade zu sehen ist.

**„Hey Siri, Mac.“** – und alles ist wieder beim Mac.

**Der eigentliche Wow-Effekt:** Ich fahre mit der Maus vom Bildschirm des MacBook Pro links über den grossen Monitor bis auf das Windows-Notebook rechts – **in einem einzigen Zug**, als wären alle Bildschirme eine einzige Oberfläche. Kein Umstecken, kein Knopf, kein Sprachbefehl nötig: Die Maus kennt keine Gerätegrenzen mehr.

Als Bonus wandert die Zwischenablage mit: Was ich auf dem Mac kopiere, füge ich unter Windows ein. Und es ist egal, ob gerade der Mac, das iPhone oder die Apple Watch zuhört.

![Der Arbeitsplatz als Skizze: MacBook Pro links, 34-Zoll-Monitor in der Mitte, HP EliteBook rechts – eine Tastatur, eine Maus](/static/img/kvm-per-sprache-skizze.png)

*Links das MacBook Pro für den Videoschnitt, in der Mitte der 34-Zoll-Monitor, rechts das HP EliteBook. Eine Tastatur, eine Maus – für beide Notebooks.*

<p style="text-align:center"><img src="/static/img/kvm-per-sprache-ablauf.svg" alt="Ablauf: Sprachbefehl – iPhone oder Apple Watch – Mac – Monitor – Windows-Notebook"></p>

## Der Arbeitsplatz

| Gerät | Rolle |
|---|---|
| **MacBook Pro** (links) | Haupt-Notebook für Videoschnitt – hier hängen Tastatur und Maus |
| **Samsung ViewFinity S65TC**, 34 Zoll, 3440 × 1440 (Mitte) | ein Bildschirm für beide Notebooks, mit eingebautem KVM-Switch |
| **HP EliteBook** (rechts) | Notebook für PowerShell und Azure |
| **Apple Magic Keyboard** · **Apple Magic Trackpad** | Tastatur und Trackpad – über Deskflow auch für Windows |
| **Logitech MX Keys for Business** | zweite Tastatur mit drei Kanälen |
| **3Dconnexion CadMouse Pro Wireless** | Maus – eine für beide Notebooks |
| **Edifier-Boxen** | klein, weiss, passend zum Monitor |

Der Monitor ist der heimliche Star: Ein einziges **Thunderbolt-4-Kabel** zum Mac überträgt das Bild, **lädt den Mac mit 90 Watt** und bindet den USB-Hub und das Netzwerk des Monitors an. Er hat zusätzlich HDMI, DisplayPort, einen zweiten Thunderbolt-Anschluss und einen eingebauten KVM-Switch (dazu gleich mehr). Und das Beste: Ich habe ihn bei Galaxus als Occasion gekauft – **gebraucht, voll funktionsfähig** – für **CHF 250.00**. Für einen 34-Zöller mit Thunderbolt und 90 Watt Ladeleistung ein echtes Schnäppchen. Tipp: Der Blick in die Rubriken „Gebraucht & geprüft“ und „B-Ware“ lohnt sich.

Ein persönliches Highlight sind die **Edifier-Boxen** links und rechts vom Monitor: klein, weiss, passend zum Monitor – und sie klingen deutlich grösser, als sie aussehen. Der eigentliche Clou: Sie hängen **am Kopfhörer-Ausgang des Monitors** – ein simples Kabel von 3,5-mm-Klinke auf Cinch. Der Monitor gibt immer den Ton des Notebooks aus, das er gerade zeigt. Schalte ich auf Windows, kommt auch der Ton von Windows – ohne Kabel umzustecken, ohne Audio-Einstellungen. Beim Videoschnitt höre ich den Mac – ein Satz zu Siri, und der Ton kommt vom Windows-Notebook.

Das Windows-Notebook hängt per **HDMI** am Monitor und hat sein eigenes Netzteil. Das ist nicht elegant, stört mich aber nicht – das Kabel war vorhanden. (Wie es auch mit einem Kabel ginge, steht weiter unten.)

## Warum ich das gebraucht habe

Ich produziere gerade ein Video zum **Zero Trust Assessment** – also zur Prüfung, wie gut eine Microsoft-365- und Azure-Umgebung nach dem Zero-Trust-Prinzip abgesichert ist. Dafür brauche ich zwei Welten gleichzeitig:

- **Auf dem Mac** entsteht das Video: Das Storyboard erstelle ich mit **Cursor**, einem KI-Code-Editor, und schicke es von dort **per API an [HeyGen](https://www.heygen.com)**. HeyGen erzeugt daraus die Szenen mit meinem KI-Avatar. Danach schaue ich mir eine Vorschau an, komponiere die Szenen, bearbeite Bilder und rendere. Dafür ist der Mac gemacht.
- **Auf dem Windows-Notebook** laufen die PowerShell-Skripte, die Verbindungen zu Azure und Microsoft Entra und das Assessment selbst. Dafür ist Windows gemacht.

**Optional, für mehr Sicherheit:** Der kleine MikroTik-Switch unter dem Schreibtisch läuft mit RouterOS und kann mehr als nur verteilen. Wer möchte, kann damit das HP EliteBook und das Teams-Telefon in ein **eigenes, abgeschottetes Netz** nehmen, das aus dem Heimnetz nicht erreichbar ist – die beiden Netze sehen sich dann nicht. Die einzige gewollte Ausnahme: Der Mac darf das EliteBook über den Deskflow-Port erreichen, sonst wandern Maus und Tastatur nicht mehr mit.

Das heisst: Skript starten auf Windows, Ergebnis ansehen, zurück auf den Mac, Szene schneiden, wieder auf Windows, nächster Befehl, Screenshot, zurück zum Schnitt … Jeder Wechsel bedeutete bisher drei Knöpfe: am Monitor den Eingang, an der Tastatur die Kanaltaste, unten an der Maus den Umschalter. Dutzende Male pro Stunde. Und irgendwann tippt man den Befehl ins falsche Fenster.

Im Alltag wäre das ein nettes Extra. Bei so einem Projekt spart es richtig Zeit – und der Kopf bleibt beim Video statt bei den Knöpfen.

Ein zusätzliches KVM-Kästchen auf dem Tisch brauchte ich dafür nicht. Der Monitor hatte es schon eingebaut.

## Tipp: Der KVM-Switch steckt schon im Monitor

Das wissen viele nicht: Der **Samsung ViewFinity S65TC hat einen KVM-Switch eingebaut.** Wer diesen Monitor kauft, braucht kein zusätzliches Umschalt-Kästchen.

So funktioniert er: Tastatur und Maus (oder deren Funkempfänger) stecken **am USB-Hub des Monitors**. Beide Notebooks hängen per USB-C/Thunderbolt am Monitor – der Monitor hat zwei Thunderbolt-4-Anschlüsse (einer mit 90 W, einer mit 15 W). Wechselt man den Eingang, wandern Tastatur und Maus automatisch mit zum anderen Notebook.

Und das Schöne: Der Sprachbefehl funktioniert damit genauso. `ddcctl` schaltet den Eingang – und der eingebaute KVM nimmt Tastatur und Maus gleich mit. **Monitor kaufen, zwei Kabel stecken, Kurzbefehl anlegen – fertig.**

Warum ich trotzdem Deskflow nutze: Mein Windows-Notebook hängt per HDMI am Monitor (HDMI überträgt kein USB), meine Tastatur und Maus sind per Bluetooth und Funk mit dem Mac verbunden, und ich wollte die gemeinsame Zwischenablage. Wer es einfacher mag: Der eingebaute KVM reicht völlig.

## Vier Bausteine, alle kostenlos

### 1. Der Monitor wechselt den Eingang: `ddcctl`

Fast jeder Monitor versteht Befehle über das Bildschirmkabel – der Standard heisst **DDC/CI**. Das kleine Open-Source-Tool **ddcctl** schickt so einen Befehl vom Mac an den Monitor: „Wechsle auf Eingang 17“ (HDMI, Windows) oder „Wechsle auf Eingang 56“ (Thunderbolt, Mac).

```bash
ddcctl -d 1 -i 17   # Monitor zeigt das Windows-Notebook
ddcctl -d 1 -i 56   # Monitor zeigt wieder den Mac
```

Welche Zahl zu welchem Eingang gehört, ist je nach Monitor verschieden – einmal ausprobieren, dann steht es fest.

### 2. Maus und Tastatur wandern mit: Deskflow

**Deskflow** ist ein kostenloser Software-KVM (der Nachfolger von Synergy und Barrier). Tastatur und Maus bleiben per Funk bzw. Bluetooth fest am Mac. Deskflow schickt die Bewegungen und Tastendrücke **über das Heimnetz** an das Windows-Notebook – verschlüsselt (TLS). Für Windows sieht das aus wie eine angeschlossene Maus.

Der Mac ist der **Server**, das Windows-Notebook der **Client**. Im Server steht nur, wo der zweite Bildschirm liegt, plus zwei Tastenkürzel:

```text
section: links
	mac:
		right = windows
	windows:
		left = mac
end
section: options
	clipboardSharing = true
	keystroke(Control+Alt+Super+w) = switchToScreen(windows)
	keystroke(Control+Alt+Super+m) = switchToScreen(mac)
end
```

So entsteht die durchgehende Oberfläche: Der Mauszeiger läuft über die Bildschirmkante einfach weiter auf das andere Notebook. Damit gibt es drei Wege zum Umschalten: die Maus einfach über den rechten Bildschirmrand schieben, **ctrl + opt + cmd + W / M** drücken – oder Siri fragen.

### 3. Siri verbindet beides: ein Kurzbefehl per SSH

Ein Apple-Kurzbefehl „Windows“ enthält genau **eine** Aktion: *Skript über SSH ausführen* – auf dem Mac selbst. Das hat einen Grund: Sagt man „Hey Siri“, hört oft das iPhone oder die Watch zu, und dort können keine Mac-Skripte laufen. Über SSH landet der Befehl trotzdem immer auf dem Mac.

Das Skript schaltet den Monitor um und stösst dann Deskflow an. Das war der kniffligste Teil – dazu gleich mehr.

**Per Sprache oder per Tipp:** Der Kurzbefehl läuft vom Mac, vom iPhone und von der Apple Watch – und wer gerade nicht sprechen will, tippt einfach:

- **iPhone:** als Widget auf dem Home-Bildschirm, im Kontrollzentrum oder auf der Aktionstaste
- **Apple Watch:** als Komplikation direkt auf dem Zifferblatt – ein Tipp aufs Handgelenk
- **Mac:** in der Menüleiste oder per Tastenkürzel

### 4. Das Hilfsprogramm „DF-Umschalter“

Deskflow reagiert nur auf **echte** Tastendrücke – ein per Skript gesendetes ctrl + opt + cmd + W ignoriert es (siehe Stolperstein 2). Was Deskflow aber zuverlässig erkennt: wenn die Maus über den Bildschirmrand fährt. Genau das macht **DF-Umschalter**: ein winziges, selbst gebautes Mac-Programm ohne Fenster, das den Mauszeiger kurz über den rechten Rand schiebt (→ Windows) oder nach links zurück (→ Mac).

Der ganze Code, rund 30 Zeilen Swift:

```swift
// DF-Umschalter: schaltet Deskflow um, indem es die
// Maus kurz ueber den Bildschirmrand schiebt.
// Aufruf: DF-Umschalter windows | mac
// (Windows liegt in Deskflow rechts vom Mac)
import CoreGraphics
import Foundation

let args = CommandLine.arguments.dropFirst()
let ziel = args.first?.lowercased() ?? ""
let src = CGEventSource(stateID: .hidSystemState)

func stoss(bei p: CGPoint, dx: Int64) {
    let e = CGEvent(mouseEventSource: src,
                    mouseType: .mouseMoved,
                    mouseCursorPosition: p,
                    mouseButton: .left)!
    e.setIntegerValueField(.mouseEventDeltaX,
                           value: dx)
    e.post(tap: .cghidEventTap)
}

if ziel == "windows" {
    // rechte Kante aller Mac-Bildschirme finden
    var ids = [CGDirectDisplayID](repeating: 0,
                                  count: 16)
    var n: UInt32 = 0
    CGGetActiveDisplayList(16, &ids, &n)
    var maxX: CGFloat = 0, midY: CGFloat = 0
    for i in 0..<Int(n) {
        let b = CGDisplayBounds(ids[i])
        if b.maxX > maxX { maxX = b.maxX; midY = b.midY }
    }
    // Maus in kleinen Schritten ueber den Rand schieben
    for s in 0...10 {
        let x = min(maxX - 1, maxX - 30 + CGFloat(s * 6))
        stoss(bei: CGPoint(x: x, y: midY), dx: 8)
        usleep(20_000)
    }
} else if ziel == "mac" {
    // nach links, bis Deskflow zum Mac zurueckwechselt
    let pos = CGEvent(source: nil)!.location
    for _ in 1...80 {
        stoss(bei: pos, dx: -120)
        usleep(8_000)
    }
}
```

So wird daraus ein Programm:

```bash
APP="$HOME/Applications/DF-Umschalter.app"
mkdir -p "$APP/Contents/MacOS"
swiftc -O umschalter.swift \
  -o "$APP/Contents/MacOS/DF-Umschalter"
# dazu eine kleine Info.plist: CFBundleIdentifier,
# CFBundleExecutable und LSUIElement = true
# (kein Dock-Symbol, kein Fenster)
codesign --force -s - "$APP"
```

Danach einmal unter *Datenschutz & Sicherheit → Bedienungshilfen* **DF-Umschalter** hinzufügen und einschalten – nur dieses eine Programm darf die Maus bewegen. Warum ein eigenes Programm und nicht einfach ein Skript? Weil macOS die Berechtigung an ein Programm bindet. Ein eigenes, kleines Programm bekommt eine eigene, stabile Freigabe; die Kurzbefehle-App bekam sie bei mir nicht zuverlässig.

Der Siri-Kurzbefehl „Windows“ schickt per SSH nur ein Stichwort an den Mac:

```text
umschalten windows
```

Was daraufhin genau passiert – Monitor-Eingang umschalten und DF-Umschalter starten –, legt ein kleines Skript auf dem Mac fest. Das ist gleichzeitig die Sicherheitsschranke, dazu gleich mehr.

## Mit dabei: Easy-Switch an der Tastatur

Die **Logitech MX Keys** hat oben links drei **Easy-Switch-Tasten** – und weil sie schon da sind, gehören sie fest zum Aufbau. Jede Taste ist ein eigener Kanal, also ein eigenes gekoppeltes Gerät:

- **Taste 1 = Mac** – das MacBook Pro, über den Logi-Bolt-Empfänger
- **Taste 2 = Windows** – das HP EliteBook
- **Taste 3** – frei für ein drittes Gerät

Ein kurzer Druck, und die Tastatur tippt direkt auf dem anderen Notebook. Die kleine LED auf der Taste zeigt, welcher Kanal gerade aktiv ist. Die Kanäle lassen sich sogar per Software umschalten – der Mac kann die Tastatur selbst auf Kanal 2 schicken.

![Detail-Illustration der Easy-Switch-Tasten: 1 = Mac, 2 = Windows, 3 = frei](/static/img/kvm-per-sprache-easyswitch.png)

Zwei Tipps dazu:

- **Tastenbelegung pro Kanal:** Die MX Keys merkt sich für jeden Kanal das Betriebssystem. Einmal **fn + O** (3 Sekunden) auf Kanal 1 stellt auf Mac um – dann liegen ⌘ und ⌥ dort, wo sie hingehören. **fn + P** ist Windows.
- **Nicht mischen:** Wer Deskflow nutzt, lässt die Tastatur auf Kanal 1 am Mac. Drückt man Taste 2, verbindet sie sich direkt mit Windows – und Deskflow verliert sie (siehe Stolperstein 5). Die Easy-Switch-Tasten sind dann für die Momente da, in denen ich direkt am Windows-Notebook tippen will.

## Die sechs Stolpersteine (und wie ich sie gelöst habe)

**1. Die Tastenbelegung – der grösste Stolperstein!**
Für eingefleischte Mac-Nutzer ist eine fremde Tastatur ein Horror: Das Mac-Keyboard hat links unten **vier** Tasten – fn, control, option, command. Die Logitech MX Keys hat nur **drei**: ctrl, opt/start und cmd/alt. Steht sie im Windows-Modus, landet ⌘ auf der Taste „start“ – und cmd + C, cmd + V, cmd + X greifen ins Leere. Jeder Kopiervorgang wird zum Suchspiel.

![Tastenvergleich: Apple Magic Keyboard mit vier Tasten, Logitech MX Keys mit drei – ⌘ gehört auf die Taste „cmd/alt“](/static/img/kvm-per-sprache-tasten.png)

Die Lösung für alle, die auf beiden Plattformen arbeiten: Die MX Keys merkt sich pro Kanal das Betriebssystem. Einmal **fn + O** (3 Sekunden gedrückt halten) auf dem Mac-Kanal – dann liegt ⌘ auf „cmd/alt“, genau dort, wo der Daumen es vom Mac gewohnt ist. Damit unter Windows trotzdem alles wie beschriftet bleibt (Strg + C, Windows-Taste auf „start“, Alt auf „alt“), tauscht Deskflow für den Windows-Bildschirm Alt und Windows-Taste wieder zurück – zwei Zeilen in der Konfiguration:

```text
section: screens
	windows:
		alt = super
		super = alt
end
```

**2. Deskflow reagiert nicht auf „künstliche“ Tastendrücke.**
Die naheliegende Idee – der Kurzbefehl drückt per AppleScript ctrl + opt + cmd + W – funktioniert nicht. Deskflow nimmt Hotkeys nur von echten Tasten an. Die Lösung: Das Hilfsprogramm **DF-Umschalter** (siehe oben) schiebt stattdessen den Mauszeiger kurz über den rechten Bildschirmrand. Das erkennt Deskflow zuverlässig und wechselt. Für den Rückweg schiebt es die Maus nach links.

**3. macOS fragt nach Berechtigungen – und merkt sie sich nicht immer.**
Programme, die Maus oder Tastatur steuern, brauchen die Freigabe unter *Datenschutz & Sicherheit → Bedienungshilfen*. Die Kurzbefehle-App selbst bekam sie bei mir trotz Häkchen nicht zuverlässig. Ein eigenes kleines Hilfsprogramm mit eigener Freigabe war die stabile Lösung. Tipp: Nach dem Freigeben das betroffene Programm neu starten.

**4. Die Maus ruckelt? WLAN-Energiesparen unter Windows.**
Die Verbindung zum Windows-Notebook hatte anfangs Aussetzer: im Schnitt 33 ms, Spitzen über 100 ms. Schuld war der Energiesparmodus der WLAN-Karte. Im Geräte-Manager abgeschaltet – danach 3,5 ms und eine flüssige Maus.

**5. Tastatur und Maus nur an *einem* Notebook koppeln.**
Wer die Maus zusätzlich per Bluetooth mit Windows koppelt, bekommt Chaos: Sie springt direkt zu Windows, und Deskflow verliert sie. Also: Tastatur und Maus nur am Mac, Deskflow übernimmt den Rest.

**6. Nach dem Ändern der Konfiguration: Server neu starten.**
Klingt banal, hat mich aber eine halbe Stunde gekostet: Deskflow lief noch mit der alten, leeren Konfiguration. Kein Übergang, keine Hotkeys – bis zum Neustart.

## Sicherheit: SSH ja, aber mit angezogener Handbremse

Ein SSH-Schlüssel, mit dem das iPhone Befehle auf dem Mac ausführen darf, ist mächtig. Deshalb darf dieser Schlüssel **genau zwei Dinge** – nicht mehr. In der Datei `authorized_keys` bekommt der Schlüssel der Kurzbefehle einen Vorsatz:

```text
restrict,command="/Users/<benutzer>/.ssh/ddc-gate.sh"
```

Dahinter folgt – **in derselben Zeile**, durch ein Leerzeichen getrennt – wie gewohnt der Schlüssel selbst (`ssh-ed25519 AAAA… Kurzbefehle auf iPhone`).

Das Skript `ddc-gate.sh` prüft den angefragten Befehl gegen eine feste Liste und führt nur hinterlegte Aktionen aus:

```sh
#!/bin/sh
# ddc-gate.sh – nur diese zwei Stichwoerter sind erlaubt
DF="$HOME/Applications/DF-Umschalter.app"
case "$SSH_ORIGINAL_COMMAND" in
  "umschalten windows")
    /usr/local/bin/ddcctl -d 1 -i 17
    exec open -g "$DF" --args windows ;;
  "umschalten mac")
    /usr/local/bin/ddcctl -d 1 -i 56
    exec open -g "$DF" --args mac ;;
  *)
    echo "nicht erlaubt: $SSH_ORIGINAL_COMMAND" >&2
    exit 1 ;;
esac
```

Wer den Schlüssel stiehlt, kann damit den Monitor umschalten – sonst nichts. Dazu kommt: `restrict` verbietet Weiterleitungen und Terminal, Deskflow verschlüsselt per TLS, und nichts davon läuft über eine Cloud.

## Und wenn man das HDMI-Kabel nicht will?

Der S65TC hat **zwei** Thunderbolt-Anschlüsse – aber nur einer liefert die 90 Watt, die ein Notebook zum Laden braucht, und den belegt der Mac. Der zweite bringt 15 Watt: genug für Bild und USB (und damit für den eingebauten KVM-Switch), aber nicht zum Laden. Wer beide Notebooks mit **je einem einzigen Kabel** (Bild + Strom + USB) anschliessen möchte, hat drei Möglichkeiten:

- **Ein Monitor mit zwei USB-C-/Thunderbolt-Eingängen mit voller Ladeleistung.** Einige Business-Monitore bieten das.
- **Ein USB-C-KVM-Dock** zwischen Notebooks und Monitor, das beide Notebooks lädt und das Bild umschaltet.
- **Das Windows-Notebook an den zweiten Thunderbolt-Anschluss** und zusätzlich sein Netzteil – dann hat man Bild, USB und KVM über ein Kabel, nur das Laden läuft separat.

Für mich ist das HDMI-Kabel der pragmatische Weg, da das Kabel vorhanden war.

## Zum Nachbauen

Alles, was man braucht – kostenlos:

- **Deskflow** – [github.com/deskflow/deskflow](https://github.com/deskflow/deskflow) (macOS, Windows, Linux)
- **ddcctl** – kleines Kommandozeilen-Tool für DDC/CI am Mac
- **Kurzbefehle / Siri** – ist auf jedem Mac und iPhone dabei
- **DF-Umschalter** – das kleine Swift-Programm von oben, selbst gebaut in fünf Minuten
- ein Monitor mit **DDC/CI** (haben fast alle)
- optional: Aktivboxen am Kopfhörer-Ausgang des Monitors (Kabel 3,5-mm-Klinke auf Cinch) – dann wechselt auch der Ton mit

📄 **Die Kurzanleitung mit allen Tastenkürzeln zum Ausdrucken:** [Mac ↔ Windows umschalten (PDF)](/static/img/kvm-per-sprache-kurzanleitung.pdf)

## Fazit

Vier Gratis-Werkzeuge, Cursor & Claude eine Stunde tüfteln lassen – und der Arbeitsplatz fühlt sich an wie aus einem Guss. Beim Zero-Trust-Video springe ich jetzt dutzende Male pro Stunde zwischen Schnitt und PowerShell hin und her – ohne einen einzigen Knopf zu suchen. Ein Satz genügt, und ich arbeite einfach weiter.

## Mein nächstes Projekt: Einkaufen mit KI – bei Migros

<p style="text-align:center"><img src="/static/img/kvm-per-sprache-migros.svg" alt="Per Sprache: Kühlschrank prüfen, Lebensmittel vorschlagen, bei Migros liefern lassen"></p>

Der nächste Umbau betrifft nicht den Schreibtisch, sondern die Küche. Die Idee:

1. **Kühlschrank auf, Handy raus:** Fotos vom Kühlschrank, ein kurzes Video vom Vorratsregal.
2. **Die App erkennt, was da ist** – und was fehlt. Sie weiss, was wir gerne essen.
3. **Vorschläge für die nächste Woche:** asiatisch, polnisch, französisch, italienisch oder schweizer Küche – ganz egal, worauf wir Lust haben.
4. **Bestellen per Migros-App** – und die Sachen werden geliefert.

So macht Einkaufen wieder Spass. Und eine Erfahrung, die uns überrascht hat: Wir haben den Eindruck, dass Obst und Gemüse aus der Lieferung **frischer sind und nicht angedatscht** – sie sind eben nicht schon durch tausend Grabbelfinger gegangen wie in der Auslage im Laden.

**Was kostet die Lieferung?** Laut Migros-Hilfe kostet eine Lieferung ab CHF 99 Warenwert CHF 7.90, ab CHF 160 noch CHF 4.90, ab CHF 200 ist sie gratis – dazu kommen bei stark ausgelasteten Zeitfenstern CHF 1 bis 2 Zuschlag. Mit dem **Lieferpass** entfallen Lieferkosten und Zuschläge ab CHF 99 Bestellwert ganz:

| Lieferpass | Preis |
|---|---|
| 12 Monate | CHF 118.80 (rechnerisch CHF 9.90 pro Monat) |
| 6 Monate | CHF 65.40 |

Wer mehr als einmal im Monat für unter CHF 200 bestellt, fährt mit dem Jahrespass günstiger: Schon zwei Lieferungen à CHF 7.90 kosten mehr als die CHF 9.90 pro Monat.

Mehr dazu, wenn es läuft – hier im Blog.
