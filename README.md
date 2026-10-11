# ESPHome Watermeter

Lokale Wasserzähler-Erkennung für den **Seeed Studio XIAO ESP32-S3 Sense mit OV3660**. Die Kamera erfasst mechanische Ziffernrollen; TensorFlow Lite Micro erkennt die einzelnen Stellen direkt auf dem ESP32. Der bestätigte Zählerstand und Diagnosewerte werden über die verschlüsselte ESPHome-API an Home Assistant übertragen.

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

Die Ausschnittvorschau zeigt jede Ziffer separat. Ein Klick auf einen Ausschnitt wählt den entsprechenden Rahmen aus. Im Werkzeug **Verschieben** lassen sich vorhandene Rahmen mit der Maus oder per Touch bewegen. X, Y, Breite und Höhe können direkt eingegeben oder in Schritten von 1, 5 oder 10 Pixeln angepasst werden. Pfeiltasten im fokussierten Kamerabild bewegen den Rahmen um einen Pixel; Umschalt + Pfeiltaste um zehn Pixel.

Koordinaten beziehen sich stets auf das 640 × 480 große Kamerabild und sind unabhängig von der Darstellungsgröße. Die Rahmenmitten müssen von links nach rechts geordnet sein. Überlappungen sind zulässig, jeder Ausschnitt sollte aber ausschließlich seine eigene Ziffer enthalten. Tests veröffentlichen keinen Zählerstand an Home Assistant.

### Speicherung und Zurücksetzen

Ziffernrahmen, Nachkommastellen, Intervall, Sprunggrenze, Referenzen und letzter akzeptierter Rohwert werden auf dem Gerät gespeichert. Beim Speichern der Konfiguration erfolgt die Sicherung sofort. Während des Messbetriebs wird der aktuelle Stand spätestens nach fünf Minuten gesichert; bei Stromausfall können entsprechend die letzten Minuten fehlen. Nach einem Neustart wird der nächste erfolgreich erkannte Stand veröffentlicht.

**Zählerkonfiguration löschen** entfernt nach Bestätigung die Rahmen, Referenzen, Beleuchtungseinstellungen, den gespeicherten Stand und die Ableseeinstellungen. Die Automatik wird pausiert. WLAN, API, OTA und vorhandene Home-Assistant-Verlaufdaten bleiben erhalten. Während einer laufenden Ablesung ist das Zurücksetzen gesperrt.

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

Die Konfidenz ist der Mittelwert der Stellen, keine Garantie für jede einzelne Ziffer. Auch ein plausibler OCR-Fehler kann die Prüfungen passieren. Halb umgeschaltete Rollen, Reflexionen und unscharfe Ausschnitte erfordern besondere Aufmerksamkeit.

Bei ausbleibendem Kamerabild wird die Aufnahme beendet und die automatische Beleuchtung ausgeschaltet. Liegt nach 60 Sekunden kein KI-Ergebnis vor, wird die Verarbeitung gesperrt und ein Neustart verlangt, damit kein weiterer Auftrag mit einer möglicherweise noch laufenden Inferenz überlappt.

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

Kameraansicht und Home-Assistant-Kamerabild zeigen die Rohaufnahme. `/meter/status` enthält die Laufzeit des Ausrichtungsschritts als `alignment_ms`. Der Sensor **Ablesedauer** umfasst bei aktiver Ausrichtung auch diesen Schritt; die beiden Zeiten dürfen nicht addiert werden.

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

Änderung und Durchfluss basieren ausschließlich auf akzeptierten automatischen Ablesungen. Der erste Durchfluss nach Start oder manueller Kalibrierung bleibt unbekannt, bis zwei akzeptierte Ablesungen vorliegen. Gleichbleibender Stand ergibt anschließend einen Durchfluss von null. Tests verändern keine Verbrauchswerte.

Die Beispielkonfiguration verwendet die Home-Assistant-Zeitquelle mit `Europe/Berlin`; Sommer- und Winterzeit werden berücksichtigt. Vor der Zeitsynchronisierung erscheint beim Zeitstempel „Zeit nicht synchronisiert“.

[home-assistant-card.yaml](home-assistant-card.yaml) enthält eine Dashboard-Karte mit Verbrauchsdiagramm, Status, Kamerabild und Zählerstand. Erforderlich sind `stack-in-card`, `mini-graph-card` und `card-mod`. Die optionale Darstellung in Seven-Segment-Schrift setzt eine entsprechende Frontend-Schrift voraus. Die Entitäts-IDs der Beispielkarte müssen an die eigene Installation angepasst werden.

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

npm ci
npx playwright install chromium --only-shell
node tests/ui_smoke.cjs
node tests/navigation_smoke.cjs
```

Der Build-Check verwendet lokale Komponenten und temporäre Test-Zugangsdaten. `navigation_smoke.cjs` benötigt die generierten Firmwarequellen. Browserprüfungen arbeiten mit einer simulierten Kamera/API; sie prüfen die Bedienung, nicht die Erkennung eines realen Zählers. Änderungen an der festgelegten KI-Basis erfordern eine erneute Integrationsprüfung.

## Abhängigkeiten

Die KI-Funktionen und das Ziffernmodell stammen aus [nliaudat/esphome_ai_component](https://github.com/nliaudat/esphome_ai_component). Für eingebundene Komponenten und Modelle gelten die jeweiligen Lizenzbedingungen der Ursprungsprojekte. ESPHome und TensorFlow Lite Micro bleiben eigenständige Abhängigkeiten; dieses Repository ergänzt sie um die Wasserzähler-Anwendung.
