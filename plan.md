# Anleitung: Feste Google-Maps-Route stündlich überwachen mit GitHub Actions und Google Routes API

Diese Anleitung zeigt Schritt für Schritt, wie eine feste Fahrtroute stündlich überwacht wird, sodass die aktuelle Fahrtdauer unter der jeweiligen Verkehrslage gespeichert wird. Für dieses Setup werden ein privates GitHub-Repository, GitHub Actions, Python und die offizielle Google Maps Platform Routes API verwendet. Google verlangt dafür ein billing-fähiges Cloud-Projekt und einen API-Key; die Nutzung kann bei einem kleinen privaten Setup trotzdem innerhalb der freien monatlichen Kontingente bleiben.[1][2][3]

## Zielbild

Das fertige Setup macht bei jeder Ausführung genau einen API-Aufruf an Googles Endpoint `directions/v2:computeRoutes`, speichert die aktuelle Dauer mit Zeitstempel in einer CSV-Datei und committed die Datei zurück ins private Repository.[4][5]

Am Ende liegt im Repository ein kleines Historien-Log, aus dem sich später Trends wie „Montag 8 Uhr ist regelmäßig 25 Minuten langsamer als Mittwoch 11 Uhr“ ableiten lassen. Die Secrets liegen dabei nicht im Code, sondern als verschlüsselte Repository-Secrets in GitHub Actions.[6]

## Voraussetzungen

Vor dem Start werden benötigt:

- Ein privates GitHub-Repository.
- Ein Google-Konto.
- Eine Kreditkarte oder anderes gültiges Zahlungsmittel für das Google-Cloud-Billing-Setup; Google Maps Platform verlangt ein billing-fähiges Projekt.[1][7]
- Grundkenntnisse in Git und GitHub.
- Zwei feste Punkte für die Route, idealerweise als Latitude/Longitude statt als Adresse, damit nicht bei jedem Lauf zusätzlich Geocoding nötig wird.[1]

## Architektur

Die einfachste Architektur besteht aus vier Bausteinen:

1. GitHub Actions startet jede Stunde per `schedule` einen Workflow.
2. Der Workflow liest den Google-API-Key aus GitHub Secrets.
3. Ein Python-Skript ruft die Routes API auf und extrahiert `duration` und optional `staticDuration`.
4. Die Ergebnisse werden in `data/route_history.csv` gespeichert und automatisch ins Repo committed.[6][4]

Dieses Design ist absichtlich minimal. Es ist für einen privaten Monitor robuster und billiger als Browser-Automation gegen die normale Google-Maps-Webseite.[2][1]

## Schritt 1: Privates GitHub-Repository anlegen

Ein neues privates Repository anlegen, zum Beispiel `route-monitor`. Danach lokal klonen und eine einfache Ordnerstruktur anlegen:

```text
route-monitor/
├─ .github/
│  └─ workflows/
├─ scripts/
├─ data/
├─ requirements.txt
└─ README.md
```

Die CSV-Datei kann bereits vorbereitet werden:

```bash
mkdir -p .github/workflows scripts data
cat > data/route_history.csv <<'CSV'
timestamp_utc,weekday_local,hour_local,origin_lat,origin_lng,destination_lat,destination_lng,duration_seconds,static_duration_seconds,travel_mode,source
CSV
```

## Schritt 2: Google Cloud Projekt erstellen

Google beschreibt als Startpunkt ein billing-fähiges Cloud-Projekt, in dem die benötigte API aktiviert und anschließend ein API-Key erstellt wird.[1]

Vorgehen:

1. [Google Cloud Console](https://console.cloud.google.com/) öffnen.
2. Neues Projekt erstellen.
3. Billing für dieses Projekt aktivieren.[1]
4. In **APIs & Services > Library** die **Routes API** suchen und aktivieren.[1]
5. Danach in **APIs & Services > Credentials** einen neuen API-Key anlegen.[1]

## Schritt 3: API-Key absichern

Der API-Key sollte direkt nach der Erstellung eingeschränkt werden. Google empfiehlt generell, API-Keys zu verwalten und zu beschränken, statt sie offen nutzbar zu lassen.[1][7]

Empfohlene Einschränkungen:

- **API restrictions**: nur die **Routes API** erlauben.[1]
- **Application restrictions**: für einen GitHub-Action-Use-Case ist IP-Restriktion schwierig, weil GitHub-hosted Runner keine feste einzelne IP garantieren; daher ist hier die API-Beschränkung besonders wichtig.
- In Google Cloud zusätzlich **Quotas** und **Budgets/Alerts** konfigurieren, um versehentliche Mehrkosten zu vermeiden.[2][3]

## Schritt 4: GitHub Secret anlegen

Der Google-API-Key gehört nicht in den Quellcode. GitHub empfiehlt dafür Repository-Secrets.[6]

Vorgehen im Repository:

1. **Settings** öffnen.
2. Zu **Secrets and variables > Actions** gehen.
3. **New repository secret** wählen.[6]
4. Als Namen zum Beispiel `GOOGLE_MAPS_API_KEY` eintragen.
5. Den API-Key als Wert speichern.[6]

Optional können auch diese Werte als Secrets oder Variables abgelegt werden:

- `ORIGIN_LAT`
- `ORIGIN_LNG`
- `DEST_LAT`
- `DEST_LNG`
- `TIMEZONE` (zum Beispiel `Europe/Berlin`)

Für ein privates Einzelprojekt reicht es oft, die Koordinaten direkt im Skript oder als Repository Variables zu pflegen.

## Schritt 5: Python-Abhängigkeiten definieren

In `requirements.txt` genügt für den Start:

```txt
requests==2.32.3
python-dateutil==2.9.0.post0
```

Das Kernstück ist ein normaler HTTP-POST gegen Googles `computeRoutes`-Endpoint.[4]

## Schritt 6: Python-Skript erstellen

Die Datei `scripts/fetch_route.py` anlegen:

```python
import csv
import datetime as dt
import json
import os
from pathlib import Path

import requests
from zoneinfo import ZoneInfo

API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
ORIGIN_LAT = float(os.environ.get("ORIGIN_LAT", "48.7784"))
ORIGIN_LNG = float(os.environ.get("ORIGIN_LNG", "9.1800"))
DEST_LAT = float(os.environ.get("DEST_LAT", "48.1351"))
DEST_LNG = float(os.environ.get("DEST_LNG", "11.5820"))
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Berlin")

url = "https://routes.googleapis.com/directions/v2:computeRoutes"
headers = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": "routes.duration,routes.staticDuration"
}
payload = {
    "origin": {
        "location": {
            "latLng": {
                "latitude": ORIGIN_LAT,
                "longitude": ORIGIN_LNG,
            }
        }
    },
    "destination": {
        "location": {
            "latLng": {
                "latitude": DEST_LAT,
                "longitude": DEST_LNG,
            }
        }
    },
    "travelMode": "DRIVE",
    "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
    "languageCode": "de-DE",
    "units": "METRIC"
}

response = requests.post(url, headers=headers, json=payload, timeout=30)
response.raise_for_status()
data = response.json()

routes = data.get("routes", [])
if not routes:
    raise RuntimeError("Keine Route in der API-Antwort gefunden")

route = routes[0]

def parse_duration(value: str) -> int:
    return int(str(value).replace("s", ""))

now_utc = dt.datetime.now(dt.timezone.utc)
now_local = now_utc.astimezone(ZoneInfo(TIMEZONE))

row = {
    "timestamp_utc": now_utc.replace(microsecond=0).isoformat(),
    "weekday_local": now_local.strftime("%A"),
    "hour_local": now_local.strftime("%H"),
    "origin_lat": ORIGIN_LAT,
    "origin_lng": ORIGIN_LNG,
    "destination_lat": DEST_LAT,
    "destination_lng": DEST_LNG,
    "duration_seconds": parse_duration(route["duration"]),
    "static_duration_seconds": parse_duration(route.get("staticDuration", route["duration"])),
    "travel_mode": "DRIVE",
    "source": "google_routes_api"
}

csv_path = Path("data/route_history.csv")
write_header = not csv_path.exists() or csv_path.stat().st_size == 0

with csv_path.open("a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=row.keys())
    if write_header:
        writer.writeheader()
    writer.writerow(row)

print(json.dumps(row, ensure_ascii=False))
```

Der Endpoint und das Grundprinzip des POST-Requests entsprechen der offiziellen Google-Routes-Nutzung rund um `computeRoutes`.[4][5]

### Warum diese Parameter?

- `travelMode: DRIVE` überwacht die Autofahrt.[4]
- `routingPreference: TRAFFIC_AWARE_OPTIMAL` nutzt laut Google verkehrsoptimierte Berechnung, die dem Verhalten von maps.google.com bzw. der Google-Maps-App entspricht.[2]
- `X-Goog-FieldMask` reduziert die Antwort auf die tatsächlich benötigten Felder und hält Requests sauber und effizient.[2]

## Schritt 7: GitHub-Workflow erstellen

Die Datei `.github/workflows/route-monitor.yml` anlegen:

```yaml
name: Route Monitor

on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  fetch-route:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Fetch route duration
        env:
          GOOGLE_MAPS_API_KEY: ${{ secrets.GOOGLE_MAPS_API_KEY }}
          ORIGIN_LAT: ${{ vars.ORIGIN_LAT }}
          ORIGIN_LNG: ${{ vars.ORIGIN_LNG }}
          DEST_LAT: ${{ vars.DEST_LAT }}
          DEST_LNG: ${{ vars.DEST_LNG }}
          TIMEZONE: ${{ vars.TIMEZONE }}
        run: python scripts/fetch_route.py

      - name: Commit updated CSV
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/route_history.csv
          git diff --staged --quiet || git commit -m "Update route history"
          git push
```

Die GitHub-Secrets-Dokumentation beschreibt genau den Mechanismus, über den der Secret-Wert im Workflow als Environment-Variable verfügbar gemacht wird.[6]

### Hinweis zum Cron

Der Ausdruck `0 * * * *` bedeutet: immer zur vollen Stunde. GitHub Actions verarbeitet `schedule` ereignisbasiert, daher können Jobs in der Praxis leicht verzögert anlaufen; für ein stündliches Monitoring ist das normalerweise unkritisch.

## Schritt 8: Repository Variables setzen

Neben Secrets sind für nicht-sensitive Konfigurationswerte Repository Variables praktisch. In GitHub können sie unter **Settings > Secrets and variables > Actions** verwaltet werden, parallel zu den Secrets.[6]

Sinnvolle Variablen:

- `ORIGIN_LAT`
- `ORIGIN_LNG`
- `DEST_LAT`
- `DEST_LNG`
- `TIMEZONE`

Beispiel:

- `ORIGIN_LAT=48.7784`
- `ORIGIN_LNG=9.1800`
- `DEST_LAT=48.1351`
- `DEST_LNG=11.5820`
- `TIMEZONE=Europe/Berlin`

## Schritt 9: Ersten Testlauf ausführen

Nach dem Commit des Workflows kann der erste Lauf manuell über **Actions > Route Monitor > Run workflow** gestartet werden. Wenn alles korrekt konfiguriert ist, erzeugt das Skript eine neue Zeile in `data/route_history.csv`.[6]

Wenn ein Fehler auftritt, sind die häufigsten Ursachen:

- Billing nicht aktiviert.[1]
- Routes API nicht aktiviert.[1]
- Falscher oder gesperrter API-Key.[1]
- `GOOGLE_MAPS_API_KEY` nicht als Secret gesetzt.[6]
- Leere oder fehlerhafte Koordinaten in Repository Variables.

## Schritt 10: Kosten absichern

Auch wenn das Setup klein ist, sollte die Kostenkontrolle von Anfang an gesetzt werden. Google beschreibt das Preismodell als nutzungsabhängig mit freien Nutzungskontingenten pro SKU und verweist auf Preisübersichten und Billing-Kontrolle.[2][3]

Empfehlungen:

- In Google Cloud ein **Budget** mit Warnung anlegen.[2]
- Quotas für die betroffene API prüfen und bewusst niedrig halten.[2]
- Pro Workflow-Lauf genau **einen** Request senden.
- Keine unnötigen Zusatzcalls wie Geocoding bei jedem Lauf ausführen.[1]

Bei einem stündlichen Lauf mit genau einem Request entstehen grob rund 720 bis 744 Requests pro Monat. Das ist für einen kleinen privaten Use Case normalerweise weit unter den freien monatlichen Nutzungskontingenten, die Google auf der Pricing-Seite ausweist; trotzdem bleibt Billing Pflicht.[2][3]

## Schritt 11: Daten auswerten

Sobald einige Tage Daten vorhanden sind, lassen sich einfache Auswertungen erzeugen. Zum Beispiel können Durchschnittswerte nach Wochentag und Stunde gebildet werden:

- Wie lange dauert die Strecke montags um 7 Uhr im Mittel?
- Wie groß ist die Differenz zwischen `duration_seconds` und `static_duration_seconds`?
- Welche Tageszeiten sind besonders volatil?

Dafür genügt später ein kleines Python-Notebook, ein zweiter GitHub-Action-Workflow oder ein lokales pandas-Skript.

## Schritt 12: Sinnvolle Erweiterungen

Nach dem Minimal-Setup bieten sich diese Erweiterungen an:

- **Zweite CSV oder JSON-Snapshot** mit Rohantwort für Debugging.
- **Benachrichtigung**, wenn `duration_seconds` über einem Schwellwert liegt, zum Beispiel via Telegram, Slack oder E-Mail.
- **Visualisierung** per GitHub Pages oder kleinem statischen Dashboard.
- **Mehrere Routen** in derselben Struktur, etwa Heimweg und Arbeitsweg.
- **Abfahrt zu festen Uhrzeiten in der Zukunft**, falls eher Prognosen für 17:00 Uhr statt „jetzt sofort“ relevant sind; Google beschreibt dafür die Nutzung mit `departureTime` und Traffic-Modellen.[2]

## Wichtige Grenzen des Setups

Die API überwacht standardmäßig die aktuell beste Route zwischen Origin und Destination. Das bedeutet: Wenn Google wegen Verkehr eine andere Straßenführung für schneller hält, kann sich die beobachtete Route ändern, obwohl Start und Ziel identisch bleiben.[2]

Wenn wirklich exakt dieselbe Straßenführung über Monate hinweg beobachtet werden soll, ist das komplizierter. Dann müssten zusätzliche Wegpunkte oder eine bewusst stärker fixierte Routenlogik geprüft werden.[2]

## Checkliste

Zum Abschluss sollte alles Folgende erfüllt sein:

- Google-Cloud-Projekt erstellt.[1]
- Billing aktiviert.[1]
- Routes API aktiviert.[1]
- API-Key erstellt.[1]
- API-Key auf Routes API beschränkt.[1]
- GitHub Secret `GOOGLE_MAPS_API_KEY` gesetzt.[6]
- Repository Variables für Koordinaten gesetzt.[6]
- Python-Skript eingecheckt.
- Workflow-Datei eingecheckt.
- Manueller Testlauf erfolgreich.
- CSV wird nach jedem Lauf erweitert.
- Budget-Alert und Quota gesetzt.[2][3]

## Dateien im Überblick

### `requirements.txt`

```txt
requests==2.32.3
python-dateutil==2.9.0.post0
```

### `data/route_history.csv`

```csv
timestamp_utc,weekday_local,hour_local,origin_lat,origin_lng,destination_lat,destination_lng,duration_seconds,static_duration_seconds,travel_mode,source
```

### `scripts/fetch_route.py`

Siehe vollständigen Code in Schritt 6.

### `.github/workflows/route-monitor.yml`

Siehe vollständigen Code in Schritt 7.

## Nächster sinnvoller Schritt

Nach Umsetzung dieser Anleitung sollte zuerst 24 bis 72 Stunden lang nur Daten gesammelt werden. Danach lohnt es sich, eine kleine Auswertung zu bauen, die Durchschnittsdauer, Streuung und Tagesmuster sichtbar macht; erst dann zeigt der Monitor wirklich seinen Nutzen.