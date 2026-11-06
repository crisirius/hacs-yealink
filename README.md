# Yealink T5x Phone für Home Assistant

Lokale Home-Assistant-Integration für Yealink-T5x-Telefone (getestet mit
**T54W**, Firmware `96.87.0.15`). Sie spricht die inoffizielle Web-API des
Telefons direkt an – ohne Cloud, ohne MQTT-Broker und ohne zusätzlichen
Monitor-Prozess.

## Funktionen

- **Einrichtung:** IP-Adresse manuell eingeben oder das lokale Netzwerk
  automatisch durchsuchen; zusätzlich DHCP-Erkennung
- **Status:** online/offline, im Gespräch, Anrufstatus
- **Gerät:** Firmware, Hardware, MAC, IP-Adresse
- **WLAN:** SSID und Signalstärke
- **SIP-Leitungen:** Registrierungsstatus und Nummer je konfiguriertem Account
- **Anrufliste:** letzter Anruf inkl. Richtung, Nummer, Zeit und Dauer
- **Headset:** verbunden, Modell und MAC (per Syslog, optional)
- **Anrufsteuerung:** Auflegen-Button, Neustart-Button, Dial-Service, Anrufnummer-Entity
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

Beim Hinzufügen der Integration stehen zwei Wege zur Auswahl:

1. **IP-Adresse manuell eingeben** – Host, Benutzername und Passwort eintragen.
2. **Lokales Netzwerk durchsuchen** – die Integration sucht Yealink-Telefone
   im lokalen Netz, zeigt die Treffer zur Auswahl an und fragt danach nur noch
   die Zugangsdaten ab.

Zusätzlich erkennt Home Assistant ein Telefon automatisch per DHCP, sobald es
mit dem MAC-Präfix `80:5E:0C` im Netz erscheint. Dann erscheint das Gerät als
neuer Fund unter **Einstellungen → Geräte & Dienste** und muss nur noch
bestätigt werden.

| Feld | Bedeutung |
|---|---|
| Host oder IP-Adresse | nur bei manueller Einrichtung, z. B. `PHONE_HOST` |
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

### Automatische Netzwerksuche

Die Suche prüft HTTPS (Port 443) auf allen Hosts der privaten `/24`-Netze, die
Home Assistant an seinen physischen Netzwerkadaptern sieht (maximal vier
Netze). Ein Treffer wird über den Seitentitel des Webinterface erkannt
(`Yealink T54W Phone`), es werden keine Zugangsdaten benötigt.

- Virtuelle Adapter (Docker-Bridge, `veth`, `virbr`, `vmnet`, `utun`, …)
  werden übersprungen.
- Bei größeren Subnetzen (`/16`–`/23`) werden höchstens vier `/24`-Netze
  geprüft; bei sehr großen Netzen nur das `/24` der eigenen Adresse.
- **Home Assistant Container/Docker:** Die Suche funktioniert nur mit
  Host-Netzwerk (`network_mode: host`). Mit Bridge-Netzwerk ist das LAN des
  Telefons nicht erreichbar – dann die IP-Adresse manuell eintragen.
- Wird nichts gefunden, bricht der Dialog mit einem Hinweis ab; die manuelle
  Einrichtung bleibt verfügbar.

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
| Anrufnummer | Text | Rufnummer zum Anruf – **Setzen löst automatisch einen Anruf aus** (z. B. `+491701234567`, führende Nullen möglich) |

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

## Sicherheit

- **TLS-Prüfung:** standardmäßig aus, weil das Telefon ein selbstsigniertes
  Zertifikat nutzt. Wer dem Zertifikat vertraut, aktiviert die Prüfung bei der
  Einrichtung; ohne Prüfung ist ein LAN-MITM beim RSA-Schlüssel und damit beim
  Admin-Passwort möglich.
- **Passwort:** wird nur im Config-Entry gespeichert (HA-Standard,
  `.storage/core.config_entries`) und nie geloggt. Es ist das
  Telefon-**Admin**-Passwort, also voller Zugriff auf das Webinterface.
- **Syslog:** Der UDP-Listener akzeptiert nur Pakete der konfigurierten
  Telefon-IP, damit Fremde keinen Headset-Status vortäuschen können. Syslog ist
  unverschlüsselt (UDP).
- **Action-URI-Allowlist:** Die HA-IP wird beim Einrichten eingetragen und beim
  Entladen wieder entfernt. Eine vorhandene `any`-Regel bleibt unberührt.
- **Angriffsfläche:** Wer Home Assistant übernimmt, hat auch das
  Telefon-Passwort. HA sollte deshalb nicht ungeschützt aus dem Internet
  erreichbar sein (Cloudflared/Reverse Proxy nur mit Auth).
- Die Integration ändert Telefon-Einstellungen nur dort, wo es muss
  (Syslog-Ziel, Action-URI-Allowlist) und stellt das Syslog-Ziel beim Entladen
  zurück.

## Bekannte Einschränkungen

- Nur Polling, keine Push-Verbindung. Das Intervall bestimmt die Verzögerung.
- Getestet mit T54W / `96.87.0.15`; andere T5x-Modelle können abweichen.
- Headset-Erkennung benötigt Syslog (UDP, unverschlüsselt).
- Die Anrufliste wird nur als „letzter Anruf“ exportiert (v0.1).
- Die Netzwerksuche erreicht nur direkt angeschlossene private Netze; sie
  durchsucht keine fremden Subnetze und keine öffentlichen Adressen.
- Das Telefon nutzt standardmäßig ein selbstsigniertes TLS-Zertifikat.
  Zertifikatsprüfung daher nur aktivieren, wenn das Zertifikat bekannt ist.
- Nach einem Werksreset oder Passwortwechsel meldet sich die Integration über
  den Reauth-Flow.

## Das frühere Monitor-Toolset

Die Integration ersetzt das alte Standalone-Toolset (`monitor.py` mit
Dashboard, MQTT-Discovery und eigenem Syslog-Listener) vollständig. Der Monitor
wird **nicht mehr benötigt** und läuft nicht mehr.

- Alte MQTT-Discovery-Entities und das MQTT-Gerät „Yealink T54W" wurden entfernt;
  es existieren keine `yealink/t54w`-Topics mehr.
- Nur **ein** Syslog-Empfänger darf auf dem konfigurierten UDP-Port lauschen.
- Wer die alte API-Reimplementierung zum Debuggen braucht: siehe `legacy/` im
  Toolset-Ordner (`yealink.py`, `probe.py`).

## Fehlersuche

| Problem | Ursache / Lösung |
|---|---|
| `invalid_auth` | Benutzername/Passwort falsch oder Web-Login deaktiviert |
| `cannot_connect` | IP/Port prüfen, HTTPS am Telefon aktiv, LAN erreichbar |
| Netzwerksuche findet nichts | anderes Subnetz, Docker-Bridge oder Firewall; IP manuell eintragen |
| Telefon wird nicht per DHCP erkannt | MAC-Präfix prüfen oder Telefon manuell hinzufügen |
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
├── brand/             Icon für Home Assistant
├── button.py          Auflegen, Neustart
├── config_flow.py     Einrichtung, Reauth, Optionen
├── const.py           Konstanten
├── coordinator.py     Polling + automatischer Re-Login
├── discovery.py       Netzwerksuche nach Yealink-Telefonen
├── entity.py          gemeinsame Gerätezuordnung
├── manifest.json
├── number.py          Anrufnummer (wenn gesetzt: automatischer Anruf)
├── sensor.py          Status, Gerät, WLAN, Anrufliste, Headset
├── services.yaml
├── strings.json
├── syslog.py          UDP-Listener für die Headset-Erkennung
├── text.py            Anrufnummer (Setzen löst Anruf aus)
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
git tag v0.2.2
git push origin main --tags
```

## Lizenz

MIT – siehe [LICENSE](LICENSE).

Dieses Projekt ist nicht mit Yealink verbunden. Die Web-API ist nicht
offiziell dokumentiert und kann sich mit Firmware-Updates ändern.
