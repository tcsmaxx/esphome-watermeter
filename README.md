# ESPHome Watermeter

Lokale Wasserzähler-Erkennung für den **Seeed Studio XIAO ESP32-S3 Sense mit OV3660 oder OV5640**. Die Kamera erfasst mechanische Ziffernrollen; TensorFlow Lite Micro erkennt die einzelnen Stellen direkt auf dem ESP32. Der bestätigte Zählerstand und Diagnosewerte werden über die verschlüsselte ESPHome-API an Home Assistant übertragen.

Die integrierte Weboberfläche ermöglicht Einrichtung, Kalibrierung und Betrieb ohne Ziffernkoordinaten in YAML. Bildverarbeitung, Referenzsuche und Erkennung laufen auf dem Gerät. Für den Betrieb sind weder ein externer KI-Server noch Cloud-Dienste erforderlich.

## Basis und Ergänzungen

Das Projekt verwendet [ESPHome](https://esphome.io/) und die externen Komponenten aus [nliaudat/esphome_ai_component](https://github.com/nliaudat/esphome_ai_component). Die KI-Basis ist auf Commit `048f6e932b9f90cb7a7a23a2e07f80fa65a987e7` festgelegt. Sie stellt die Modellverwaltung, TensorFlow-Lite-Micro-Inferenz und Bildvorverarbeitung bereit. Das verwendete Modell ist `digit_recognizer_v3_quantized_integer_quant_uint8.tflite` mit einem Eingabebild von **20 × 32 Pixeln und drei Farbkanälen** je Ziffer.

Die eigene Komponente **`meter_setup`** ergänzt diese Grundlage um eine abgestimmte Wasserzähler-Anwendung. Die Quellen der eingebundenen KI-Komponenten werden nicht verändert.

| Bereich | Grundlage | Ergänzung durch dieses Projekt |
| --- | --- | --- |
| Ziffernerkennung | `meter_reader_tflite` mit TensorFlow Lite Micro | Acht geordnete Ziffernrollen, Dezimalposition und bestätigter Wasserzählerstand in m³ |
| Bildausschnitte | Verarbeitung konfigurierter Ausschnitte | Rahmen direkt im Kamerabild zeichnen, verschieben und pixelgenau justieren |
| Einrichtung | ESPHome-Komponenten und YAML-Konfiguration | Vollständige Web-Einrichtung auf dem ESP mit Kamerabild, Ausschnittvorschau und Testfunktion |
| Speicherung | ESPHome-Präferenzen | Dauerhafte Speicherung von Rahmen, Stand, Intervall, Grenzwerten, Referenzen und Beleuchtung |
| Bildgeometrie | Bildverarbeitung und konfigurierbare Rotation | Optionale automatische Ausrichtung anhand zweier gespeicherter Referenzmuster |
| Plausibilitätsprüfung | Das Basisprojekt bietet unter anderem `value_validator` | Eigene Annahmelogik mit Ganzzahl-Rohwerten, Konfidenzprüfung, Rückwärts- und Sprungkontrolle |
| Beleuchtung | Das Basisprojekt bietet unter anderem `flash_light_controller` | SK6812-RGBW-Steuerung mit LED-Anzahl, Weiß-Helligkeit, Vorlauf und zeitlich begrenztem Lichttest im Setup |
| Home Assistant | ESPHome-API und Kamera | Bestätigter Stand, Änderung, Durchfluss, deutscher Zeitstempel, Status und Fehlermeldungen |

Der Schwerpunkt liegt auf komfortabler Einrichtung und kontrollierter Veröffentlichung der Messwerte. Das Erkennungsmodell bleibt das Modell der KI-Basis; die Erweiterung ist kein neu trainiertes oder grundsätzlich genaueres OCR-Modell.

## Hardware und Voraussetzungen

| Bestandteil | Konfiguration |
| --- | --- |
| Board | Seeed Studio XIAO ESP32-S3 Sense, Kamera-Kit 113991115 |
| Kamera | OV3660 |
| Flash / PSRAM | 8 MB / 8 MB, Octal-PSRAM |
| ESPHome-Board | `seeed_xiao_esp32s3` |
| Framework | ESP-IDF |
| Kamerabild | 640 × 480 Pixel, JPEG |
| Zähler | Acht mechanische Ziffernrollen; typischerweise fünf schwarze und drei rote Stellen |
| Beleuchtung, optional | SK6812 RGBW, 5 V, Datenleitung D1 / GPIO2 |
| Geprüfte Software | ESPHome 2026.9.1, ESP-IDF 5.5.5 |

Das analoge Zeigerrad wird nicht ausgewertet. Die Ziffern müssen scharf, vollständig und möglichst reflexionsfrei sichtbar sein. Eine feste Kameramontage und gleichmäßige Beleuchtung sind Voraussetzung für zuverlässige Erkennung.

## Installation

1. [wasserzaehler.yaml](wasserzaehler.yaml) in das ESPHome-Konfigurationsverzeichnis übernehmen. Gerätename und Kameraorientierung an die Installation anpassen.
2. Die Schlüssel aus [secrets.example.yaml](secrets.example.yaml) in `secrets.yaml` eintragen. WLAN-, Web-, OTA- und Fallback-Zugangsdaten sowie den API-Verschlüsselungsschlüssel setzen. Vorhandene Secrets beibehalten; Zugangsdaten nicht im Repository speichern. Der Fallback-WLAN-Schlüssel benötigt mindestens acht Zeichen. Ein API-Schlüssel lässt sich mit `openssl rand -base64 32` erzeugen.
3. Die Firmware mit ESPHome kompilieren und erstmals über USB installieren. Weitere Installationen können per OTA erfolgen.
4. `http://wasserzaehler.local/setup` oder `http://IP-DES-GERÄTS/setup` öffnen und mit den Web-Zugangsdaten anmelden. Auf der ESPHome-Startseite befinden sich Links zu Einrichtung und Status.
5. Das Gerät über die ESPHome-Integration in Home Assistant hinzufügen.

Die Beispielkonfiguration lädt `meter_setup` aus diesem Repository und die KI-Komponenten aus der festgelegten Basisversion. Sie begrenzt parallele Compilerprozesse auf einen Prozess, um den RAM-Bedarf auf dem Build-Rechner zu reduzieren.

## Web-Einrichtung

Auf großen Bildschirmen stehen die Einstellungen links und das Kamerabild rechts. Das Bild nutzt die volle Breite der rechten Spalte. Die Einstellungsleiste scrollt unabhängig. Auf kleinen Bildschirmen steht das Kamerabild oberhalb der Einstellungen.

### Ziffernrahmen und Kalibrierung

1. **Pausieren** und mit **Neues Bild** einen Kameraschnappschuss aufnehmen.
2. Unter **Ausgewählte Stelle** eine Ziffer wählen und einen Rahmen um die vollständige Ziffer ziehen. Acht Rahmen von links nach rechts einrichten.
3. Zum schnellen Verteilen zunächst für Stelle 1 die gesamte Ziffernreihe markieren und **8 Rahmen gleichmäßig verteilen** verwenden. Anschließend jede Stelle einzeln anpassen.
4. **Rahmen testen** und alle erkannten Stellen mit dem Bild vergleichen.
5. Den tatsächlichen Stand von Hand ablesen und als acht Ziffern ohne Komma eingeben: `00123,456 m³` entspricht `00123456`. Nachkommastellen, Ableseintervall und maximalen Sprung einstellen.
6. **Speichern & Automatik starten** sichert die Konfiguration und aktiviert die regelmäßige Ablesung.

Die Ausschnittvorschau zeigt jede Ziffer separat. Ein Klick auf einen Ausschnitt wählt den entsprechenden Rahmen aus. Unter **Bildansicht** lässt sich zwischen **Rohbild · Einrichtung** und **KI-Bild · Erkennung prüfen** umschalten. Im Werkzeug **Verschieben** lassen sich vorhandene Rahmen mit der Maus oder per Touch bewegen. X, Y, Breite und Höhe können direkt eingegeben oder in Schritten von 1, 5 oder 10 Pixeln angepasst werden. Pfeiltasten im fokussierten Kamerabild bewegen den Rahmen um einen Pixel; Umschalt + Pfeiltaste um zehn Pixel.

Koordinaten beziehen sich stets auf das 640 × 480 große Kamerabild und sind unabhängig von der Darstellungsgröße. Die Rahmenmitten müssen von links nach rechts geordnet sein. Überlappungen sind zulässig, jeder Ausschnitt sollte aber ausschließlich seine eigene Ziffer enthalten. Tests veröffentlichen keinen Zählerstand an Home Assistant.

### Speicherung und Zurücksetzen

Ziffernrahmen, Nachkommastellen, Ableseintervall, Sprunggrenze, Warnschwelle, Referenzen und letzter akzeptierter Rohwert werden auf dem Gerät gespeichert. Beim Speichern der Konfiguration erfolgt die Sicherung sofort. Während des Messbetriebs wird der aktuelle Stand spätestens nach fünf Minuten gesichert; bei Stromausfall können entsprechend die letzten Minuten fehlen. Nach einem Neustart wird der nächste erfolgreich erkannte Stand veröffentlicht.

**Zählerkonfiguration löschen** entfernt nach Bestätigung die Rahmen, Referenzen, Beleuchtungseinstellungen, den gespeicherten Stand und die Ableseeinstellungen. Die Automatik wird pausiert. WLAN, API, OTA und vorhandene Home-Assistant-Verlaufdaten bleiben erhalten. Während einer laufenden Ablesung ist das Zurücksetzen gesperrt.

### Konfiguration exportieren und importieren

**Exportieren** lädt eine JSON-Sicherung der gespeicherten Konfiguration herunter: alle Ziffernrahmen, Stand, Nachkommastellen, Ableseintervall, Sprunggrenze, Warnschwelle, Referenzpositionen und vollständige Referenzmuster sowie Beleuchtungseinstellungen. Ungespeicherte Änderungen im Browser gehören nicht zur Sicherung. WLAN-, API-, Web-, OTA- und MQTT-Zugangsdaten werden nicht exportiert; Hardwarepins und Kameraorientierung bleiben in YAML.

**Importieren** übernimmt eine solche JSON-Datei nach Bestätigung. Format, Version, Bildgröße, Zahlenbereiche, Rahmenfolge, Referenzmuster und LED-Kapazität werden geprüft. Ungültige Dateien verändern die Konfiguration nicht. Nach erfolgreicher Speicherung bleibt die Automatik pausiert: Kamerabild und Rahmen testen, tatsächlichen Stand prüfen und anschließend **Fortsetzen** oder mit korrigiertem Stand speichern. Eine andere Kameramontage kann trotz gültiger Sicherung neue Referenzen und Rahmen erfordern.

### Alter der letzten gültigen Ablesung

**Warnung nach · Sekunden** legt fest, wann eine fehlende aktuelle Ablesung gemeldet wird (Standard 300 Sekunden, Bereich 30–86400 Sekunden). Eine Warnschwelle größer als das Ableseintervall wählen. Der Sensor **Alter der letzten Ablesung** zeigt die vergangenen Sekunden seit einer akzeptierten automatischen Ablesung, **Ablesung veraltet** meldet eine Überschreitung. Auch der allgemeine Problemstatus berücksichtigt diese Warnung.

Tests und abgewiesene Ergebnisse setzen den Zeitpunkt nicht zurück. Nach Neustart kann der gespeicherte Zeitpunkt mit synchronisierter Systemzeit ausgewertet werden. Vor der ersten gültigen Ablesung ist das Alter unbekannt; die Warnung erfolgt nach Ablauf der Schwelle seit Start beziehungsweise manueller Neukalibrierung. Wie der Zählerstand wird der Zeitpunkt im laufenden Betrieb über ESPHome-Präferenzen gesichert. Das Setup zeigt den Zustand unter **Sicherung & Diagnose**.

## Schutz vor fehlerhaften Messwerten

Automatische Ablesungen werden nur übernommen, wenn alle folgenden Bedingungen erfüllt sind:

- Die KI meldet ein gültiges Ergebnis.
- Das Ergebnis enthält genau acht gültige Ziffern.
- Die mittlere Konfidenz erreicht mindestens 90 %.
- Der Stand ist mindestens so hoch wie der letzte akzeptierte Stand.
- Der Zuwachs überschreitet die eingestellte Sprunggrenze nicht.
- Bei aktivierter Ausrichtung sind beide Referenzen eindeutig und die Bildkorrektur zulässig.

Die Plausibilitätsprüfung und die Speicherung verwenden Ganzzahl-Rohwerte. Führende Nullen bleiben in der Zifferndarstellung erhalten. Bei drei Nachkommastellen entspricht eine Rohwerteinheit einem Liter; der Standardgrenzwert von 1000 entspricht damit 1000 Litern zwischen zwei akzeptierten Ablesungen. Bei anderen Nachkommastellen gilt die Grenze in Rohwerteinheiten.

Abgewiesene Ablesungen verändern den bestätigten Zählerstand nicht. Status und Fehlersensor geben den Ablehnungsgrund an. Nach längeren Unterbrechungen, einem Zählerwechsel oder einem tatsächlich größeren Verbrauch muss der aktuelle Stand gegebenenfalls manuell eingetragen werden.

Die Gesamtkonfidenz ist der Mittelwert der Stellen, keine Garantie für jede einzelne Ziffer. Zusätzlich werden acht Einzelkonfidenzen unter den Ziffernausschnitten und als Diagnose-Sensoren angezeigt. Werte unter 90 % werden im Setup hervorgehoben; dies ist ein Hinweis und keine zusätzliche Ablehnungsgrenze. Die Einzelwerte stammen aus der Ergebnislogzeile der festgelegten KI-Basis. Dafür muss das Logger-Level für `meter_reader_tflite` mindestens `INFO` sein. Fehlende oder nicht zum Ergebnis passende Einzelwerte werden als unbekannt angezeigt. Auch ein plausibler OCR-Fehler kann die Prüfungen passieren. Halb umgeschaltete Rollen, Reflexionen und unscharfe Ausschnitte erfordern besondere Aufmerksamkeit.

Bei ausbleibendem Kamerabild wird die Aufnahme beendet und die automatische Beleuchtung ausgeschaltet. Liegt nach 60 Sekunden kein KI-Ergebnis vor, wird der aktuelle Auftrag gesperrt. Die Fehlerdiagnose wird dauerhaft gespeichert, das Licht ausgeschaltet und nach fünf Sekunden ein kontrollierter automatischer Neustart ausgeführt. So wird kein weiterer Auftrag mit einer möglicherweise noch laufenden Inferenz überlappt. Nach wiederholten Zeitüberschreitungen verlängert sich die Wartezeit bis zur ersten Ablesung auf 1, 2, 4, 8, 16 und maximal 30 Minuten; eine erfolgreiche Ablesung setzt diese Staffelung zurück. Fehlende oder uneindeutige Referenzen verwerfen ausschließlich die betreffende Ablesung und lösen keinen Neustart aus. Ein vom Reader gemeldeter Kamera-Timeout wird abgeschlossen und im eingestellten Intervall erneut versucht.

## Optionale Referenzausrichtung

Die Bildausrichtung gleicht kleine Bewegungen zwischen Kamera und Zähler aus. Sie ist standardmäßig deaktiviert. Bei deaktivierter Ausrichtung geht das Kamerabild ohne Referenzkorrektur an die KI.

1. Ein neues Bild aufnehmen und die acht Ziffernrahmen einrichten.
2. **Ausrichtung mit Referenzen verwenden** aktivieren.
3. Unter **Ausgewählte Stelle** die Einträge **Referenz 1** und **Referenz 2** wählen und zwei feste, kontrastreiche Merkmale markieren, etwa unterschiedliche Schriftzeichen, Schrauben oder Gehäusedetails. Bewegliche Ziffern und Zeiger sowie wiederholte oder gleichförmige Flächen eignen sich nicht.
4. **Referenzen aus diesem Bild übernehmen** anklicken. Die Muster werden aus genau dem angezeigten Schnappschuss entnommen.
5. Rahmen testen und mit **Speichern & Automatik starten** Referenzmuster und Positionen dauerhaft sichern.

Die Referenzbereiche müssen jeweils 16–96 Pixel breit und hoch sein. Ihre Mittelpunkte benötigen mindestens 80 Pixel Abstand. Eine große Distanz und eine Position nahe der Ziffernreihe erleichtern die geometrische Korrektur.

Vor der Erkennung sucht das Gerät beide Referenzen im neuen Kamerabild und rechnet das Bild in die gespeicherten Rahmenkoordinaten zurück. Dieses korrigierte Bild wird für die Ziffernerkennung verwendet. Die Suche umfasst ±20 Pixel je Referenz. Treffer am äußeren Suchrand, uneindeutige Referenzen, Drehungen über 3°, Abstandsänderungen über 3 % oder ungültige korrigierte Ausschnitte führen zur Ablehnung.

Die Ausrichtung benötigt zeitweise etwa 2,1 MiB zusätzlichen PSRAM. Sie korrigiert begrenzte Montagebewegungen, verbessert aber weder Schärfe noch Beleuchtung und ersetzt keine korrekte Montage. Große Verschiebungen und Perspektivänderungen erfordern eine neue Kalibrierung.

Die Ansicht **Rohbild · Einrichtung** und das Home-Assistant-Kamerabild zeigen die Rohaufnahme. **KI-Bild · Erkennung prüfen** zeigt dagegen genau das zur Erkennung übergebene Bild einschließlich der Referenzkorrektur. Ziffernausschnitte und Rahmen beziehen sich dort auf diese Aufnahme und die bei ihrer Verarbeitung verwendete Konfiguration. Die KI-Ansicht ist schreibgeschützt; Rahmen und Referenzen werden im Rohbild eingerichtet. Ohne aktive Ausrichtung zeigt sie die unveränderte KI-Aufnahme.

Mit **Rahmen testen** lässt sich eine neue KI-Aufnahme erzeugen. Die KI-Ansicht aktualisiert sich bei neuen Aufnahmen automatisch. Scheitert eine Referenzsuche, ist keine gültige KI-Aufnahme verfügbar; eine vorherige korrigierte Aufnahme wird nicht als aktuelle angezeigt. Die angezeigte Bildnummer bezeichnet die verarbeitete Aufnahme, keine bestätigte Messwertübernahme. **Neues Bild** wechselt zur Rohbildansicht und erzeugt keine neue KI-Ablesung.

Für die Vorschau wird das korrigierte RGB-Bild im PSRAM gehalten (rund 0,9 MiB); es wird nicht erneut gedreht oder verlustbehaftet komprimiert. Ohne Ausrichtung wird eine Kopie des JPEG-Bilds gespeichert. `/meter/status` enthält die Laufzeit des Ausrichtungsschritts als `alignment_ms`. Der Sensor **Ablesedauer** umfasst bei aktiver Ausrichtung auch diesen Schritt; die beiden Zeiten dürfen nicht addiert werden.

## SK6812-RGBW-Beleuchtung

Die Beispielkonfiguration verwendet den weißen Kanal von SK6812-RGBW-LEDs. Sie reserviert mit `num_leds: 64` Platz für bis zu 64 LEDs. Die tatsächlich verwendete Anzahl wird unter **Beleuchtung** im Setup eingestellt; nur diese LEDs leuchten, alle übrigen Datenplätze bleiben ausgeschaltet.

| Einstellung | Bedeutung |
| --- | --- |
| Automatisch bei Aufnahmen einschalten | Beleuchtung für Schnappschüsse, Tests und regelmäßige Ablesungen verwenden |
| Anzahl LEDs | Anzahl der beleuchteten LEDs, 1 bis zur YAML-Kapazität, maximal 64 |
| Weiß-Helligkeit | Helligkeit des weißen Kanals, 1–100 % |
| Vorlauf | Zeit zur Anpassung von Belichtung und Weißabgleich, 0–5000 ms |
| Licht testen | Beleuchtung zum Einstellen einschalten; endet spätestens nach zwei Minuten |
| Licht aus | Laufenden Lichttest beenden |
| Beleuchtung speichern | LED-Einstellungen unabhängig von Zählerrahmen und Stand sichern |

Während des Lichttests wartet die automatische Ablesung. Der Helligkeitsregler wirkt im aktiven Test direkt. Mit **Neues Bild** lässt sich die Beleuchtung beurteilen. Bei automatischen Aufnahmen wird der Vorlauf abgewartet, ein gepuffertes Bild verworfen und ein neues Bild zur Verarbeitung angefordert. Nach Schnappschuss oder KI-Ergebnis wird das Licht ausgeschaltet. Ein aktiver Lichttest bleibt bis zum Ausschalten oder Ablauf bestehen.

Die Hardwareanbindung erfolgt in YAML:

```yaml
light:
  - platform: esp32_rmt_led_strip
    id: meter_illumination
    internal: true
    pin: GPIO2
    chipset: SK6812
    channel_colors: GRBW
    num_leds: 64
    gamma_correct: 1.0
    default_transition_length: 0s
    restore_mode: ALWAYS_OFF

meter_setup:
  illumination_id: meter_illumination
```

Der `meter_setup`-Ausschnitt zeigt nur die LED-Anbindung; die vollständige Konfiguration enthält weitere erforderliche Einträge. Ohne LED-Anbindung sind Erkennung und Referenzausrichtung weiterhin verwendbar.

`restore_mode: ALWAYS_OFF` setzt den LED-Ausgang nach einem Neustart zunächst auf aus. Gespeicherte Beleuchtungseinstellungen bleiben erhalten und werden bei der nächsten Aufnahme verwendet. Gewöhnliche Home-Assistant-Kameraanfragen aktivieren keine Beleuchtung; die Funktion ist keine Dauerbeleuchtung für einen Videostream.

### Anschluss

| LED-Anschluss | Verbindung |
| --- | --- |
| 5V | Geeignetes 5-V-Netzteil, Pluspol |
| GND | Netzteil-Minus und XIAO GND gemeinsam |
| DIN | XIAO D1 / GPIO2, vorzugsweise über etwa 330 Ω |

Die LEDs werden nicht aus einem GPIO oder dem 3,3-V-Ausgang versorgt. Eine kurze Datenleitung verwenden. Das direkte 3,3-V-Datensignal kann funktionieren, ist bei 5-V-LEDs jedoch nicht garantiert; für zuverlässige Pegel eignet sich ein mit 5 V versorgter 74AHCT125. Ein 500–1000-µF-Kondensator am LED-Eingang kann die Versorgung stabilisieren. Seitliche Beleuchtung und ein Diffusor reduzieren Reflexionen im Zählerglas.

Nach Änderungen an Beleuchtung oder Kameramontage Erkennung und Referenzen erneut prüfen.

## Home Assistant

Der bestätigte **Zählerstand** wird in m³ mit Geräteklasse `water` und Zustandsklasse `total_increasing` veröffentlicht. Er kann im Home-Assistant-Wasser-Dashboard verwendet werden.

| Entität | Inhalt |
| --- | --- |
| Kamerabild | Kameraschnappschuss ohne Referenzkorrektur |
| Zählerstand | Letzter akzeptierter automatischer Messwert in m³ |
| Änderung zu Vorwert | Differenz zum vorherigen akzeptierten Stand in m³ |
| Durchfluss | Aus Standänderung und Zeitabstand berechneter mittlerer Durchfluss in m³/h |
| Letzte Aktualisierung | Zeitpunkt der letzten akzeptierten Ablesung, `TT.MM.JJJJ HH:MM:SS` |
| Ablesestatus | Betriebszustand beziehungsweise Ergebnis der Ablesung |
| Ablesefehler | Fehler- oder Ablehnungsgrund |
| Ableseproblem | Binärer Problemstatus |
| Ablesedauer | Dauer einer Ablesung in Millisekunden |
| Alter der letzten Ablesung | Sekunden seit letzter akzeptierter Ablesung |
| Ablesung veraltet | Warnschwelle ohne neue gültige Ablesung überschritten |
| Erkennungskonfidenz | Mittlere Konfidenz des letzten Erkennungsergebnisses |
| Konfidenz Stelle 1–8 | Einzelkonfidenzen des letzten Erkennungsergebnisses |

Änderung und Durchfluss basieren ausschließlich auf akzeptierten automatischen Ablesungen. Der erste Durchfluss nach Start oder manueller Kalibrierung bleibt unbekannt, bis zwei akzeptierte Ablesungen vorliegen. Gleichbleibender Stand ergibt anschließend einen Durchfluss von null. Tests verändern keine Verbrauchswerte.

Die Beispielkonfiguration verwendet die Home-Assistant-Zeitquelle mit `Europe/Berlin`; Sommer- und Winterzeit werden berücksichtigt. Vor der Zeitsynchronisierung erscheint beim Zeitstempel „Zeit nicht synchronisiert“.

[home-assistant-card.yaml](home-assistant-card.yaml) enthält eine Dashboard-Karte mit Verbrauchsdiagramm, Status, Kamerabild und Zählerstand. Erforderlich sind `stack-in-card`, `mini-graph-card` und `card-mod`. Die optionale Darstellung in Seven-Segment-Schrift setzt eine entsprechende Frontend-Schrift voraus. Die Entitäts-IDs der Beispielkarte müssen an die eigene Installation angepasst werden.

## Fernwartung und automatische Erholung

Die Setupseite bietet **Gerät neu starten**. Der Neustart ist nach Bestätigung auch während einer Ablesesperre möglich; Rahmen, Referenzen und Stand bleiben erhalten. Die Beispiel-YAML erzeugt zusätzlich einen ESPHome-Neustartknopf für Home Assistant:

```yaml
button:
  - platform: restart
    name: Neustart
    entity_category: config
```

In einer eigenen YAML diesen Eintrag unter dem vorhandenen `button:`-Block ergänzen. Eine OTA-Installation startet das Gerät ebenfalls neu, sofern ESPHome-API und OTA erreichbar sind.

Der letzte Kamera- oder Inferenzfehler bleibt in der Setup-Diagnose und unter `/meter/status` nachvollziehbar. Erfasst werden Ursache, Zeitpunkt, Betriebsdauer, Reader-Phase, letzte Reader-Meldung, Ausrichtungsergebnis, Bildnummer sowie freier interner Heap und PSRAM. Automatische Neustarts und aufeinanderfolgende Zeitüberschreitungen werden gezählt. Die Diagnose wird vor einem automatischen Neustart im Flash gespeichert und nach dem Start im Log ausgegeben. Erfolgreiche Messungen löschen den letzten gespeicherten Fehler nicht.

Der automatische Neustart behandelt Fehler bei weiterhin laufendem Hauptloop. Bei komplett ausgefallenem Gerät, fehlender Versorgung oder nicht erreichbarem WLAN ist ein unabhängiger Fernschalter für die Stromversorgung nötig; OTA und Software-Neustart benötigen eine erreichbare Firmware.

## Debug-Livebild und Fortschritt

**Livebild starten** zeigt im Setup das Rohbild mit etwa einem neuen Bild pro Sekunde. Die automatische Ablesung pausiert währenddessen, Kamera und konfigurierte Beleuchtung bleiben an. Der Fokus wird beim Start entsprechend der gespeicherten Einstellung einmal gesetzt und während des Streams beibehalten. Zum Nachfokussieren das Livebild stoppen und **Neu fokussieren + Bild** wählen.

**Livebild stoppen** oder das Zeitlimit von zwei Minuten beenden den Stream und stellen den vorherigen Automatikzustand wieder her. Bleiben nach dem Streamstart zehn Sekunden lang neue Bilder aus, wird der Debugbetrieb beendet. Auch bei Verbindungsabbruch endet er spätestens am Zeitlimit. Native Home-Assistant-Streams sind davon unabhängig.

Die Statuszeile zeigt Aufwecken, Lichtvorlauf, Fokus, Pufferwechsel, Aufnahme und Erkennung. Klicks erhalten unmittelbar eine Rückmeldung; Statusabfragen verwenden einen getrennt geschützten Zwischenspeicher und warten nicht auf die Bildverarbeitung. `/meter/status` ergänzt `live` und `live_remaining` (Sekunden).


## Kamera-Standby und Wärme

Die OV5640 wird bei aktivierter Option **Sensor zwischen Aufnahmen in Standby** fünf Sekunden nach der letzten Aktivität über das Software-Power-down-Bit in Register `0x3008` schlafen gelegt. Das ist standardmäßig aktiv. Es werden ausschließlich die Power-down-Bits maskiert geschrieben und zurückgelesen; der Sensor wird nicht zurückgesetzt und seine Stromversorgung nicht physisch getrennt. Bei der OV3660 wird dieser Registerzugriff übersprungen.

Leerlaufbilder sind abgeschaltet (`idle_framerate: 0 fps`); die Komponente setzt dies auch für bestehende Geräte-Konfigurationen beim Generieren der Firmware durch. Normale Home-Assistant-Bildabfragen bekommen die letzte tatsächliche Aufnahme aus dem JPEG-Zwischenspeicher, einschließlich ihres ursprünglichen eingebrannten Aufnahmezeitpunkts. Ein ausdrücklich gestarteter **Livestream** hält die Kamera aktiv, bis er beendet wird. Die automatische Ablesung und **Neues Bild** im Setup wecken den Sensor auf, warten mindestens 300 ms und verwerfen vor der eigentlichen Aufnahme den alten Kamerapuffer. Beleuchtungsvorlauf, Autofokus, Ausrichtung und OCR laufen anschließend wie konfiguriert. Nach dem Aufwecken wird die Autofokus-Firmware beim nächsten Fokuslauf neu initialisiert, damit kein erhalten gebliebener AF-Zustand vorausgesetzt wird. Der Setup-Snapshot bleibt das zuletzt gespeicherte Rohbild; **Neues Bild** fordert eine neue Aufnahme an.

Im Setup zeigt **Kamera & Wärme** den aktuellen Zustand. **Schwächere Kamerasignale (optional)** setzt nur Bit 7:6 von Register `0x302c` auf 1×. Diese Option ist standardmäßig **aus**, insbesondere wegen möglicher Signalfehler mit langen Kameraflexkabeln. Beim Ausschalten wird die beim Start vorgefundene Treiber-Stärke wiederhergestellt. Bei Bildstörungen die Option deaktivieren. Einstellungen mit **Stromsparen speichern** sichern; Export/Import und Zurücksetzen berücksichtigen beide Optionen. Ältere Sicherungen behalten die vorhandenen Stromspareinstellungen bei.

`/meter/status` enthält `camera_standby_available`, `camera_standby_enabled`, `camera_sleeping`, `camera_weak_drive` und `camera_power_status`. Der Status bestätigt die Registereinstellung, misst aber keine Temperatur und keinen Stromverbrauch. Das Modul kann auch im Software-Standby warm bleiben; die tatsächlich erreichbare Temperaturreduzierung muss am eingebauten Gerät geprüft werden. Kühlkörper und dessen Belüftung bleiben erforderlich.

## OV5640 mit Autofokus

Unterstützt wird das Seeed-Modul **OV5640 Camera for XIAO ESP32S3 Sense (With Heat Sink), SKU 114993115**. Die Kamerapins und die Auflösung **640 × 480** bleiben bestehen. Die Komponente aktiviert die native Autofokus-Unterstützung des Kameratreibers beim Kompilieren; eine zusätzliche YAML-Option ist nicht erforderlich. Die OV3660 funktioniert ohne Fokusmotor weiter wie bisher.

Im Setup befindet sich der Abschnitt **Autofokus · OV5640**:

- **Neu fokussieren + Bild** pausiert die automatische Ablesung, verwendet den gespeicherten Beleuchtungsvorlauf, fokussiert einmal und nimmt anschließend ein neues Vorschaubild auf. Danach mit **Fortsetzen** die Automatik wieder starten.
- **Automatisch vor jeder neuen Aufnahme fokussieren** gilt für **Neues Bild**, Rahmentests und regelmäßige Ablesungen; beim Debug-Livebild wird einmal beim Start fokussiert. Die Option ist standardmäßig aktiv und lässt sich mit **Fokus speichern** dauerhaft ändern. Ausgeschaltet wird nur auf Knopfdruck fokussiert; die mechanische Position ist nicht als Konfigurationswert gespeichert. Eine unveränderte Linsenposition über Standby und Neustarts wird nicht vorausgesetzt. Bei aktiviertem Standby ist der Einzelfokus vor jeder Ablesung empfehlenswert.
- Der Fokusstatus wird im Setup und in `/meter/status` angezeigt (`autofocus_available`, `autofocus_before_reading`, `autofocus_status`, `autofocus_error`).

Der Ablauf ist **Lichtvorlauf → Einzelfokus → veralteten Kamerapuffer verwerfen → frisches Bild → Ausrichtung und OCR**. Es wird kein kontinuierlicher Autofokus aktiviert. Firmware-Initialisierung und Treiberaufrufe laufen in einer separaten Aufgabe mit 5 KiB Stack. Die eigentliche Scharfstellung wird höchstens vier Sekunden geprüft; die gesamte Fokusaufgabe hat ein Zeitlimit von 15 Sekunden. Ein normaler Fokusfehler verwirft die Aufnahme und plant den nächsten Ableseversuch, ohne einen Zählerstand zu übernehmen. Eine hängende Fokusaufgabe wird isoliert und löst nach fünf Sekunden einen protokollierten Neustart aus.

Die Option wird exportiert und importiert. Sicherungen ohne dieses Feld bleiben kompatibel und behalten die aktuelle Fokuseinstellung bei. Nach einem Kameratausch die Ziffernrahmen prüfen und Referenzen neu aufnehmen. Bei fehlendem Fokus Beleuchtung, Kamerabstand und freie Sicht auf die Ziffern kontrollieren.

## MQTT und zweite Home-Assistant-Instanz

MQTT ist optional und kann parallel zur ESPHome-API verwendet werden: beispielsweise ESPHome-API im Garten und MQTT in einer zweiten Home-Assistant-Instanz. Dazu in der vorhandenen Geräte-YAML ergänzen:

```yaml
packages:
  watermeter_mqtt: github://tcsmaxx/esphome-watermeter/packages/mqtt.yaml@main
```

Existiert bereits ein `packages:`-Block, nur den Eintrag ergänzen. Die Zugangsdaten werden in `secrets.yaml` hinterlegt:

```yaml
mqtt_broker: "DEIN-BROKER"
mqtt_port: 1883
mqtt_username: "DEIN-MQTT-BENUTZER"
mqtt_password: "DEIN-MQTT-PASSWORT"
```

Das Paket aktiviert MQTT-Discovery. Die Wasserzähler-Komponente veröffentlicht 18 Mess- und Diagnoseentitäten ausdrücklich: Zählerstand, Änderung, Durchfluss, letzte Aktualisierung, Status, Fehler, Alter, Veraltet-Warnung, Gesamt- und acht Einzelkonfidenzen sowie Ableseproblem. Die retained JSON-Nachricht unter `${device_name}/meter/state` wird alle fünf Sekunden aktualisiert; Discovery wird nach einer erneuten Broker-Verbindung wiederholt. Weitere öffentliche ESPHome-Entitäten wie der Neustart-Button verwenden die native MQTT-Anbindung. Home Assistant benötigt eine MQTT-Integration mit Zugang zu diesem Broker und aktivierter Discovery. Stabile Gerätekennungen auf Basis der MAC-Adresse ordnen die Entitäten dem Gerät zu. Entitäts-IDs anschließend in der Dashboard-Karte anpassen. Verwenden API und MQTT dieselbe Home-Assistant-Instanz, können dort zusätzliche MQTT-Entitäten neben den API-Entitäten erscheinen.

Das Kamerabild in Home Assistant über die ESPHome-API und das MQTT-Bild enthalten unten links den Aufnahmezeitpunkt als weiße Schrift auf schwarzem Hintergrund, im Format `12.10.2026 13:45:39`. Die Zeit folgt der konfigurierten Zeitzone (im Beispiel `Europe/Berlin`, einschließlich Sommer-/Winterzeit). Ohne synchronisierte Uhr steht dort `--.--.---- --:--:--`. Die Einblendung wird ausschließlich in einer separaten Bildkopie für die Übertragung gezeichnet; KI, Rahmen, Referenzen und die Setup-/KI-Ansicht verwenden die unveränderten Aufnahmen. Die JPEG-Kopie wird mit Qualität 85 kodiert. Bei fehlendem Speicher oder einem Codecfehler wird das Rohbild übertragen.

Für **Kamerabild** wird eine eigene MQTT-Camera-Discovery-Nachricht veröffentlicht. Nach jeder automatischen Ableserunde wird deren Aufnahme mit Zeitstempel als vollständige binäre JPEG-Nachricht an `${device_name}/camera/image` gesendet, auch bei einer wegen fehlender Referenzen abgewiesenen Aufnahme. Es wird kein zusätzlicher Kameraabruf und kein Livestream gestartet. Setup-Tests versenden keine Kamerabilder über MQTT. Das letzte Bild ist am Broker retained verfügbar; das kann auch eine abgewiesene Aufnahme sein und ist kein Nachweis eines übernommenen Zählerstands.

Die zweite Home-Assistant-Instanz benötigt für dieses Kamerabild keinen direkten HTTP-Zugang zum ESP. Die Referenzkorrektur ist in der lokalen KI-Ansicht sichtbar; MQTT überträgt die ursprüngliche Bildgeometrie als JPEG-Aufnahme mit Zeitstempel. Ein MQTT-Ausfall löst mit diesem Paket keinen zusätzlichen Broker-Watchdog-Neustart aus. Der Bildversand verwendet den asynchronen ESP-IDF-MQTT-Ausgang, damit die Netzwerkübertragung nicht die Bildverarbeitung blockiert. Die konkreten Zugänge und Brokerrechte müssen zur Installation passen.

## Architektur und Diagnose

| Datei / Verzeichnis | Aufgabe |
| --- | --- |
| `wasserzaehler.yaml` | Board, Kamerapins, KI-Modell, ESPHome-Integration und Beleuchtung |
| `components/meter_setup/web_ui.h` | Direkt auf dem Gerät ausgelieferte Setupoberfläche |
| `components/meter_setup/meter_setup.cpp` | Ablaufsteuerung, Speicherung, Beleuchtung und Veröffentlichung |
| `components/meter_setup/alignment.h` | Suche und geometrische Korrektur der Referenzmuster |
| `components/meter_setup/reading_guard.h` | Prüfung der Ziffern und Plausibilität |
| `components/meter_setup/navigation.js` | Links zur Einrichtung und Statusseite |
| `tests/` | Prüfungen für Annahmelogik, Speicherung, Ausrichtung, Beleuchtung und Browserbedienung |

| Adresse | Inhalt |
| --- | --- |
| `/` | ESPHome-Geräteübersicht |
| `/setup` | Einrichtung und Kalibrierung |
| `/meter/status` | JSON mit gespeicherter Konfiguration, Betriebszustand und Diagnosen |
| `/meter/snapshot` | Kameraschnappschuss |
| `/meter/export` | JSON-Sicherung ohne Zugangsdaten |
| `/meter/import` | Geprüfter Import über die Setupseite |
| `/meter/processed` | Letzte gültige KI-Aufnahme mit den verwendeten Rahmen als Antwortmetadaten |

Webaktionen werden im Hauptloop verarbeitet. Der Status wird dort vorbereitet, um den HTTP-Task zu entlasten. Schnappschüsse verwenden eine eigene Bildkopie und halten keinen Kamerapuffer dauerhaft fest. Stackdiagnosen stehen unter `/meter/status` bereit.

Die Setupoberfläche benötigt keine externen Schriftarten, Skripte oder CDN-Verbindungen. Der Webzugriff verwendet Digest-Anmeldung; ESPHome-API und OTA haben eigene Zugangsdaten. Das Gerät ist für den Betrieb im lokalen Netz vorgesehen.

## Grenzen und Laufzeit

Die Anwendung lokalisiert den Zähler nicht automatisch. Acht Ziffernrahmen werden manuell eingerichtet. Neue Kameraorientierung, Spiegelung, Auflösung oder ein anderer Blickwinkel erfordern eine erneute Kalibrierung. Kameraschnappschüsse sind keine archivierten Beweisbilder der letzten KI-Ablesung; Tests verwenden jeweils ein neues Bild.

Home Assistants numerische ESPHome-Sensorwerte verwenden Float32. Bei hohen Ständen kann die letzte Nachkommastelle gerundet werden. Plausibilitätsprüfung und gespeicherter Rohwert bleiben ganzzahlig; die Weboberfläche zeigt die erkannten Ziffern als Zeichenfolge.

Auf einem XIAO wurden ohne Referenzausrichtung rund 422–439 ms und mit Ausrichtung rund 768–773 ms pro Ablesung gemessen. Der Ausrichtungsschritt benötigte dabei etwa 509–512 ms. Beleuchtung mit Vorlauf verlängert die Aufnahme. Diese Messungen sind Beispiele; Modell, Ausschnitte, Referenzen und Einstellungen bestimmen die tatsächliche Laufzeit. Eine kurze Messreihe ersetzt keine Langzeitprüfung am jeweiligen Zähler.

## Entwicklung und Prüfungen

```sh
python -m pip install esphome==2026.9.1
python tests/build_check.py --config-only
python tests/build_check.py

g++ -std=c++17 tests/reading_guard.cpp -o /tmp/meter-guard
/tmp/meter-guard
python tests/result_flow.py
python tests/status_json.py
g++ -std=c++17 -O2 tests/alignment.cpp -o /tmp/meter-alignment
/tmp/meter-alignment
python tests/alignment_flow.py
python tests/persistence.py
python tests/illumination_flow.py
python tests/led_count_effect.py
python tests/recovery_flow.py
python tests/features_flow.py

npm ci
npx playwright install chromium --only-shell
node tests/ui_smoke.cjs
node tests/navigation_smoke.cjs
```

Der Build-Check verwendet lokale Komponenten und temporäre Test-Zugangsdaten. `navigation_smoke.cjs` benötigt die generierten Firmwarequellen. `features_flow.py` benötigt die durch den Firmware-Build bereitgestellten ArduinoJson-Header. Die MQTT-Prüfungen verwenden einen simulierten Broker-Client; die tatsächliche Brokerverbindung und Discovery in Home Assistant sind nach Installation zu prüfen. Browserprüfungen arbeiten mit einer simulierten Kamera/API; sie prüfen die Bedienung, nicht die Erkennung eines realen Zählers. Änderungen an der festgelegten KI-Basis erfordern eine erneute Integrationsprüfung.

## Abhängigkeiten

Die KI-Funktionen und das Ziffernmodell stammen aus [nliaudat/esphome_ai_component](https://github.com/nliaudat/esphome_ai_component). Für eingebundene Komponenten und Modelle gelten die jeweiligen Lizenzbedingungen der Ursprungsprojekte. ESPHome und TensorFlow Lite Micro bleiben eigenständige Abhängigkeiten; dieses Repository ergänzt sie um die Wasserzähler-Anwendung.
