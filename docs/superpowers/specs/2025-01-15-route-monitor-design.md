# Design: Route Monitor mit GitHub Pages Dashboard

**Datum:** 2025-01-15  
**Status:** Approved  
**Repo:** öffentlich, `maps-route-statistics`

---

## Ziel

Eine feste Fahrtroute stündlich (Werktage, 5–22 Uhr Berliner Zeit) per Google Routes API überwachen. Die Daten werden als CSV im Repo gespeichert und über ein statisches GitHub Pages Dashboard als Zeitreihenchart und Heatmap visualisiert.

---

## Architektur

```
GitHub Actions (Cron: Werktage, 3–21 Uhr UTC)
    └── fetch_route.py
            ├── Zeitfenster-Guard (skip wenn außerhalb 5–22 Uhr lokal)
            ├── Google Routes API POST (1x Retry bei Fehler)
            ├── Append → data/route_history.csv
            └── build_stats.py aufrufen → data/stats.json
    └── git commit [skip ci]: route_history.csv + stats.json

GitHub Pages (main / root)
    └── index.html
            ├── fetch("data/stats.json")  → Heatmap
            └── fetch("data/route_history.csv")  → Zeitreihenchart
```

---

## Dateistruktur

```
maps-route-statistics/
├── .github/
│   └── workflows/
│       └── route-monitor.yml
├── scripts/
│   ├── fetch_route.py
│   └── build_stats.py
├── data/
│   ├── route_history.csv
│   └── stats.json
├── index.html
├── requirements.txt
└── README.md
```

---

## Datenmodell

### `data/route_history.csv`

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `route_id` | string | Frei wählbarer Bezeichner, z.B. `"stuttgart_munich"`. Default: `"default"`. Via Repo Variable `ROUTE_ID`. |
| `timestamp_utc` | ISO 8601 | Zeitpunkt des API-Calls in UTC |
| `weekday_local` | string | Wochentag in lokaler Zeit, z.B. `"Monday"` |
| `hour_local` | string | Stunde in lokaler Zeit, z.B. `"07"` |
| `origin_lat` | float | Breitengrad Startpunkt |
| `origin_lng` | float | Längengrad Startpunkt |
| `destination_lat` | float | Breitengrad Zielpunkt |
| `destination_lng` | float | Längengrad Zielpunkt |
| `duration_seconds` | int | Fahrtdauer mit aktuellem Verkehr |
| `static_duration_seconds` | int | Fahrtdauer ohne Verkehr (Baseline) |
| `travel_mode` | string | Immer `"DRIVE"` |
| `source` | string | Immer `"google_routes_api"` |

Das Schema ist von Anfang an mehrfähig (`route_id`), auch wenn das Dashboard zunächst nur eine Route anzeigt.

### `data/stats.json`

```json
{
  "last_updated": "2025-01-15T08:00:00Z",
  "routes": {
    "stuttgart_munich": {
      "latest": {
        "timestamp_utc": "2025-01-15T08:00:00Z",
        "duration_seconds": 4320
      },
      "by_weekday_hour": {
        "Monday": {
          "07": { "avg": 4500, "min": 3900, "max": 5100, "count": 12 },
          "08": { "avg": 5100, "min": 4200, "max": 6300, "count": 12 }
        }
      }
    }
  }
}
```

Wird bei jedem erfolgreichen API-Call neu generiert. Primäre Datenquelle für das Dashboard.

---

## Python-Skripte

### `scripts/fetch_route.py`

**Verantwortlichkeiten:**
1. Zeitfenster-Guard: Prüft ob aktuelle lokale Zeit Werktag 5–22 Uhr ist. Falls nicht: Exit 0, kein API-Call.
2. HTTP POST an `https://routes.googleapis.com/directions/v2:computeRoutes`
3. Bei Fehler (HTTP-Fehler oder Timeout): 1x Retry nach 10 Sekunden. Bei zweitem Fehler: `raise` (Workflow schlägt fehl, GitHub sendet Benachrichtigung).
4. Parsed `duration` und `staticDuration` aus der Antwort.
5. Appended eine Zeile an `data/route_history.csv`.
6. Importiert und ruft `build_stats.build()` auf.

**Environment Variables:**

| Variable | Typ | Quelle | Default |
|----------|-----|--------|---------|
| `GOOGLE_MAPS_API_KEY` | Secret | GitHub Secret | — (required) |
| `ROUTE_ID` | string | Repo Variable | `"default"` |
| `ORIGIN_LAT` | float | Repo Variable | `48.7784` |
| `ORIGIN_LNG` | float | Repo Variable | `9.1800` |
| `DEST_LAT` | float | Repo Variable | `48.1351` |
| `DEST_LNG` | float | Repo Variable | `11.5820` |
| `TIMEZONE` | string | Repo Variable | `"Europe/Berlin"` |

**API-Parameter:**
- `travelMode: DRIVE`
- `routingPreference: TRAFFIC_AWARE_OPTIMAL`
- `X-Goog-FieldMask: routes.duration,routes.staticDuration`

### `scripts/build_stats.py`

**Verantwortlichkeiten:**
1. Liest `data/route_history.csv` vollständig ein.
2. Berechnet pro `route_id` × `weekday_local` × `hour_local`: `avg`, `min`, `max`, `count` für `duration_seconds`.
3. Ermittelt den neuesten Datenpunkt pro Route für `latest`.
4. Schreibt `data/stats.json` atomar (Temp-Datei → rename).
5. Ist standalone ausführbar: `python scripts/build_stats.py` (für manuelle Regenerierung).

**Dependencies:** nur stdlib (`csv`, `json`, `pathlib`, `statistics`, `os`, `tempfile`)

---

## GitHub Actions Workflow

### Cron

```yaml
on:
  schedule:
    - cron: '0 3-21 * * 1-5'
  workflow_dispatch:
```

`0 3-21 * * 1-5` = Werktage Mo–Fr, jeweils zur vollen Stunde zwischen 3 und 21 Uhr UTC. Das entspricht 4–22 Uhr MEZ (Winter) bzw. 5–23 Uhr MESZ (Sommer). Der skript-seitige Zeitfenster-Guard (`5–22 Uhr lokal`) stellt sicher, dass außerhalb relevanter Zeiten kein API-Call erfolgt — unabhängig von Sommer-/Winterzeit.

### Commit-Schritt

```bash
git add data/route_history.csv data/stats.json
git diff --staged --quiet || git commit -m "chore: update route history [skip ci]"
git push
```

`[skip ci]` verhindert, dass der Commit einen neuen Workflow-Run triggert.

### Permissions

```yaml
permissions:
  contents: write
```

---

## Dashboard (`index.html`)

### Technologie

- Reines HTML + CSS + Vanilla JS
- **Chart.js** und **PapaParse** werden als Skript-Dateien ins Repo committed (kein CDN, funktioniert offline)
- Kein Build-Schritt, kein Framework

### Sektionen

**1. Aktueller Wert**
- Letzte gemessene Fahrtdauer in Minuten
- Timestamp des letzten Calls
- Differenz zu `static_duration` als Stau-Indikator

**2. Zeitreihenchart**
- X-Achse: Datum + Uhrzeit
- Y-Achse: Fahrtdauer in Minuten
- Zwei Linien: `duration` (mit Verkehr, blau) und `static_duration` (ohne Verkehr, grau)
- Toggle: letzte 7 / 30 / 90 Tage
- Datenquelle: `data/route_history.csv` (gefiltert auf letzten N Tage)

**3. Heatmap**
- Grid: X-Achse Wochentag (Mo–Fr), Y-Achse Stunde (5–22)
- Farbe = Durchschnittsdauer (grün = kurz, rot = lang)
- Leere Felder (keine Daten vorhanden) grau
- Datenquelle: `data/stats.json` → `by_weekday_hour`

### Datenladen

```
index.html lädt:
├── data/stats.json   → Heatmap + aktueller Wert (klein, schnell)
└── data/route_history.csv  → Zeitreihenchart (nur bei Bedarf, gefiltert)
```

### Route-Selector

Kein Dropdown in V1. Die Route wird als erster Key aus `stats.json.routes` genommen. Erweiterbar.

### GitHub Pages Setup

- Repo: öffentlich
- Settings → Pages → Branch `main`, Folder `/` (root)
- URL: `https://<username>.github.io/maps-route-statistics/`

---

## Kosten & Limits

- Bei Werktagen 5–22 Uhr: max. 17 Calls/Tag × 5 Tage × 4,3 Wochen ≈ **~365 Calls/Monat**
- Google Routes API Free Tier: 10.000 Calls/Monat (Stand 2024)
- Budget-Alert in Google Cloud setzen, Quota bewusst niedrig halten
- Pro Workflow-Lauf genau **ein** API-Request

---

## GitHub Konfiguration

### Secrets

| Name | Beschreibung |
|------|--------------|
| `GOOGLE_MAPS_API_KEY` | Google API Key, eingeschränkt auf Routes API |

### Repository Variables

| Name | Beispielwert |
|------|--------------|
| `ROUTE_ID` | `stuttgart_munich` |
| `ORIGIN_LAT` | `48.7784` |
| `ORIGIN_LNG` | `9.1800` |
| `DEST_LAT` | `48.1351` |
| `DEST_LNG` | `11.5820` |
| `TIMEZONE` | `Europe/Berlin` |

---

## Offene Entscheidungen / Nicht in Scope

- **Benachrichtigungen** (Telegram/Slack bei Stau-Schwellwert): bewusst nicht in V1
- **Mehrere Routen im Dashboard** anzeigen: Datenmodell ist bereit, UI-Erweiterung für später
- **Rückwärts-Geocoding** der Koordinaten für Labels im Dashboard: optional, nicht V1
- **Historische Daten** vor dem Setup: nicht vorhanden, kein Backfill nötig

---

## Checkliste Umsetzung

- [ ] Google Cloud Projekt erstellen, Billing aktivieren
- [ ] Routes API aktivieren
- [ ] API Key erstellen, auf Routes API beschränken
- [ ] Budget-Alert in Google Cloud setzen
- [ ] GitHub Repo auf öffentlich stellen
- [ ] GitHub Secret `GOOGLE_MAPS_API_KEY` setzen
- [ ] Repository Variables für Koordinaten, TIMEZONE, ROUTE_ID setzen
- [ ] `requirements.txt` anlegen
- [ ] `scripts/fetch_route.py` implementieren
- [ ] `scripts/build_stats.py` implementieren
- [ ] `data/route_history.csv` mit Header anlegen
- [ ] `.github/workflows/route-monitor.yml` anlegen
- [ ] Chart.js und PapaParse als lokale Dateien committen
- [ ] `index.html` implementieren
- [ ] GitHub Pages aktivieren
- [ ] Manuellen Testlauf ausführen
- [ ] CSV und stats.json nach Testlauf prüfen
- [ ] Dashboard im Browser prüfen
