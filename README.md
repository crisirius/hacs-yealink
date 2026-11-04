# Yealink T5x Phone für Home Assistant

Lokale Home-Assistant-Integration für Yealink-T5x-Telefone (getestet mit
**T54W**, Firmware `96.87.0.15`). Sie spricht die inoffizielle Web-API des
Telefons direkt an – ohne Cloud, ohne MQTT-Broker und ohne zusätzlichen
Monitor-Prozess.

## Funktionen

- **Status:** online/offline, im Gespräch, Anrufstatus
- **Gerät:** Firmware, Hardware, MAC, IP-Adresse
- **WLAN:** SSID und Signalstärke
- **SIP-Leitungen:** Registrierungsstatus und Nummer je konfiguriertem Account
- **Anrufliste:** letzter Anruf inkl. Richtung, Nummer, Zeit und Dauer
- **Headset:** verbunden, Modell und MAC (per Syslog, optional)
- **Anrufsteuerung:** Auflegen-Button, Neustart-Button, Dial-Service
- **Automatischer Re-Login:** nach einem Telefon-Neustart meldet sich die
  Integration mit den gespeicherten Zugangsdaten selbst wieder an
- **Reauth-Flow:** bei falschem/geändertem Passwort fragt Home Assistant nach

## Voraussetzungen

- Home Assistant **2024.11** oder neuer
- Yealink T5x mit aktiviertem Webinterface (HTTPS)
- Ein Web-Benutzer mit Administratorrechten
- Telefon und Home Assistant im selben Netz (oder routingfähig)

## Installation über HACS

1. HACS öffnen → **Integrationen** → Drei-Punkte-Menü → **Benutzerdefinierte
   Repositories**.
2. `https://github.com/crisirius/hacs-yealink` eintragen, Kategorie
   **Integration**.
3. Die Integration installieren und Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen →
   Yealink T5x Phone**.

### Manuelle Installation

Den Ordner `custom_components/yealink_t54w/` nach
`<HA-Konfiguration>/custom_components/yealink_t54w/` kopieren und Home
Assistant neu starten.

## Einrichtung

| Feld | Bedeutung |
|---|---|
| Host oder IP-Adresse | z. B. `172.20.1.130` |
| Benutzername | meist `admin` |
| Passwort | Web-Passwort des Telefons |
| TLS-Zertifikat prüfen | standardmäßig aus (Yealink nutzt ein selbstsigniertes Zertifikat) |
| Abfrageintervall | Standard 30 s, erlaubt 10–600 s |
| Anrufsteuerung | Dial-/Hangup-Services und Buttons |
| Headset per Syslog | UDP-Listener für die Bluetooth-Erkennung |
| Syslog-UDP-Port | Standard `5514` |
| Telefon-Syslog umstellen | trägt die HA-IP automatisch im Telefon ein |

Nach dem Speichern wird das Gerät samt Entities angelegt. Die Zugangsdaten
liegen in der HA-Konfigurationsdatenbank (`.storage/core.config_entries`),
nicht in einer Klartextdatei im Repo.

### Optionen ändern

**Einstellungen → Geräte & Dienste → Yealink T5x Phone → Konfigurieren**.
Änderungen laden den Eintrag automatisch neu.

## Entities

Die Namen sind übersetzt (Deutsch/Englisch); die Entity-IDs werden aus dem
Gerätenamen abgeleitet, z. B. `sensor.yealink_t54w_firmware`.

| Entity | Typ | Beschreibung |
|---|---|---|
| Anrufstatus | Sensor | `Bereit` / `Im Gespräch` |
| Im Gespräch | Binary Sensor | aktuell aktiver Anruf |
| Online | Binary Sensor | letzter Poll erfolgreich |
| Firmware, IP-Adresse | Sensor (diagnostic) | Gerätedaten |
| WLAN-SSID, WLAN-Signal | Sensor | WLAN-Status |
| Letzter Anruf | Sensor | Name/Nummer, Details als Attribute |
| Letzte Abfrage | Sensor (timestamp, standardmäßig deaktiviert) | Poll-Zeitpunkt |
| Leitung *n* Status | Sensor | Registrierungsstatus |
| Leitung *n* Nummer | Sensor (diagnostic) | SIP-Benutzername |
| Leitung *n* registriert | Binary Sensor | Registrierung |
| Headset | Sensor | Modellname (nur mit Syslog) |
| Headset-MAC-Adresse | Sensor (diagnostic) | Bluetooth-MAC (nur mit Syslog) |
| Headset verbunden | Binary Sensor | Verbindungsstatus (nur mit Syslog) |
| Auflegen | Button | beendet das Gespräch |
| Neustart | Button | startet das Telefon neu (**standardmäßig deaktiviert**) |

Die Leitungs-Entities werden beim Einrichten aus den aktuell konfigurierten
Accounts erzeugt. Kommt später ein Account hinzu, hilft ein Neuladen des
Eintrags (Integration neu laden).

## Services

### `yealink_t54w.dial`

```yaml
service: yealink_t54w.dial
data:
  number: "+491701234567"
  account: Auto        # oder z. B. "1"
```

### `yealink_t54w.hangup`

```yaml
service: yealink_t54w.hangup
```

### `yealink_t54w.reboot`

```yaml
service: yealink_t54w.reboot
```

Bei mehreren Telefonen jeweils `entry_id` mitgeben. Die `entry_id` findet man
unter **Einstellungen → Geräte & Dienste → Integration → Gerät** oder über die
Entwicklerwerkzeuge.

## Headset-Erkennung

Die Web-API liefert den Bluetooth-Headset-Status **nicht** direkt. Die
Integration fragt deshalb regelmäßig `donglestatus?type=2` ab; das Telefon
schreibt daraufhin eine Syslog-Zeile:

```text
control bt dongle[1][Yealink T54W][...] dev[Jabra Evolve 65 SE][50:C2:75:12:7A:85] connect[1]
```

Der integrierte UDP-Listener wertet diese Zeile aus.

- Standardport **5514** (Ports < 1024 brauchen root).
- Mit **Telefon-Syslog umstellen** trägt die Integration die LAN-IP von Home
  Assistant und den Port unter **Diagnosis → Settings → Syslog** ein. Beim
  Entladen/Entfernen des Eintrags werden die vorherigen Werte
  wiederhergestellt.
- **Home Assistant Container/Docker:** UDP-Port `5514` veröffentlichen
  (`-p 5514:5514/udp`), sonst kommt kein Syslog an. Bei HA OS ist das nicht
  nötig.
- Nicht gleichzeitig den Syslog-Empfänger von `monitor.py` auf demselben Port
  betreiben.
- Ohne Syslog werden keine Headset-Entities angelegt; alles andere
  funktioniert weiter.

## Anrufsteuerung und Action-URI-Allowlist

Web-Wählen und Auflegen sind im Telefon **Action URIs**. Das Telefon führt sie
nur aus, wenn die IP des Aufrufers in
**Features → Remote Control → Action URI Allow IP List** steht. Ist die Liste
leer (Werkszustand), antwortet `/api/contacts/dial` mit `ret: failed`, obwohl
Session und CSRF-Token gültig sind.

Bei aktivierter Anrufsteuerung trägt die Integration die eigene LAN-IP
automatisch ein (sofern die Liste nicht bereits `any` enthält). Alternativ die
IP manuell im Telefon-Webinterface eintragen.

## Bekannte Einschränkungen

- Nur Polling, keine Push-Verbindung. Das Intervall bestimmt die Verzögerung.
- Getestet mit T54W / `96.87.0.15`; andere T5x-Modelle können abweichen.
- Headset-Erkennung benötigt Syslog (UDP, unverschlüsselt).
- Die Anrufliste wird nur als „letzter Anruf“ exportiert (v0.1).
- Das Telefon nutzt standardmäßig ein selbstsigniertes TLS-Zertifikat.
  Zertifikatsprüfung daher nur aktivieren, wenn das Zertifikat bekannt ist.
- Nach einem Werksreset oder Passwortwechsel meldet sich die Integration über
  den Reauth-Flow.

## Betrieb neben `monitor.py`

Die Integration ersetzt die MQTT-Anbindung des früheren Monitor-Toolsets.
Beides gleichzeitig ergibt doppelte Entities und konkurrierende
Syslog-Einstellungen:

- Vor der Einrichtung `pkill -f monitor.py` ausführen (sauberer SIGTERM, damit
  das Telefon-Syslog zurückgestellt wird).
- Die alten MQTT-Discovery-Entities in Home Assistant entfernen oder das
  MQTT-Gerät deaktivieren, sonst existieren sie parallel.
- Nur **ein** Syslog-Empfänger darf auf dem konfigurierten UDP-Port lauschen.
- Wer das LAN-Dashboard weiter nutzen will, kann `monitor.py --no-mqtt
  --no-syslog` starten. Dann bleiben aber die Headset-Karten im Dashboard leer,
  weil die Integration den Syslog-Empfang übernimmt.

## Fehlersuche

| Problem | Ursache / Lösung |
|---|---|
| `invalid_auth` | Benutzername/Passwort falsch oder Web-Login deaktiviert |
| `cannot_connect` | IP/Port prüfen, HTTPS am Telefon aktiv, LAN erreichbar |
| Dial endet mit `ret: failed` | Action-URI-Allowlist prüfen (siehe oben) |
| Headset-Entities fehlen | Syslog deaktiviert, Port belegt oder UDP blockiert |
| Headset bleibt „unbekannt“ | Telefon sendet kein Syslog an HA; Port/Firewall prüfen |
| Nach Telefon-Neustart kurz `offline` | normal; die Integration loggt sich selbst wieder ein |
| Log: `check passwd err` | darf nicht mehr auftreten; die Integration fragt nur `wui.device` und `wui.common.token` ab |

Debug-Logging:

```yaml
logger:
  logs:
    custom_components.yealink_t54w: debug
```

## Entwicklung

```text
custom_components/yealink_t54w/
├── __init__.py        Setup, Services, Syslog-Konfiguration
├── api.py             Web-API-Client (nur Standardbibliothek)
├── binary_sensor.py   Online, Im Gespräch, Leitung, Headset
├── button.py          Auflegen, Neustart
├── config_flow.py     Einrichtung, Reauth, Optionen
├── const.py           Konstanten
├── coordinator.py     Polling + automatischer Re-Login
├── entity.py          gemeinsame Gerätezuordnung
├── manifest.json
├── sensor.py          Status, Gerät, WLAN, Anrufliste, Headset
├── services.yaml
├── strings.json
├── syslog.py          UDP-Listener für die Headset-Erkennung
└── translations/      de.json, en.json
```

Syntaxprüfung:

```bash
python3 -m compileall custom_components/yealink_t54w
```

Die GitHub-Workflows prüfen bei jedem Push mit **hassfest** und der
**HACS Action**.

### Release

HACS erkennt Updates über GitHub-Releases. Vor dem Push die Version in
`custom_components/yealink_t54w/manifest.json` erhöhen, committen, Tag setzen
und ein Release anlegen:

```bash
git tag v0.1.0
git push origin main --tags
```

## Lizenz

MIT – siehe [LICENSE](LICENSE).

Dieses Projekt ist nicht mit Yealink verbunden. Die Web-API ist nicht
offiziell dokumentiert und kann sich mit Firmware-Updates ändern.
