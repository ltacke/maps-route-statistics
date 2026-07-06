# Route Monitor

Stündliches Monitoring einer festen Fahrtroute via Google Routes API.
Daten werden als CSV geloggt und über ein GitHub Pages Dashboard visualisiert.

## Setup

### 1. Google Cloud
1. Cloud-Projekt erstellen, Billing aktivieren
2. **Routes API** aktivieren
3. API-Key erstellen, auf Routes API beschränken
4. Budget-Alert setzen (empfohlen: 5 €/Monat als Warnschwelle)

### 2. GitHub Repository
Repo auf **öffentlich** stellen (Voraussetzung für GitHub Pages mit Free-Plan).

#### Secret anlegen
`Settings → Secrets and variables → Actions → New repository secret`

| Name | Wert |
|------|------|
| `GOOGLE_MAPS_API_KEY` | Google API Key |

#### Repository Variables anlegen
`Settings → Secrets and variables → Actions → Variables`

| Name | Beispiel |
|------|---------|
| `ROUTE_ID` | `stuttgart_munich` |
| `ORIGIN_LAT` | `48.7784` |
| `ORIGIN_LNG` | `9.1800` |
| `DEST_LAT` | `48.1351` |
| `DEST_LNG` | `11.5820` |
| `TIMEZONE` | `Europe/Berlin` |

### 3. GitHub Pages aktivieren
`Settings → Pages → Branch: main, Folder: / (root)`

Dashboard-URL: `https://<username>.github.io/maps-route-statistics/`

### 4. Ersten Testlauf ausführen
`Actions → Route Monitor → Run workflow`

## Kosten

~365 API-Calls/Monat (Werktage 5–22 Uhr).
Google Routes API Free Tier: 10.000 Calls/Monat.

## Lokale Entwicklung

```bash
pip install -r requirements-dev.txt
# stats.json manuell neu generieren:
python scripts/build_stats.py
# Dashboard lokal testen:
python -m http.server 8080
```
