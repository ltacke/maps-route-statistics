# Route Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stündliches Route-Monitoring via GitHub Actions + Google Routes API, CSV-Logging und statisches GitHub Pages Dashboard mit Zeitreihenchart und Heatmap.

**Architecture:** Ein GitHub Actions Workflow (Cron Werktage 3–21 UTC) ruft `fetch_route.py` auf, das nach einem Zeitfenster-Guard die Routes API aufruft, das Ergebnis an `data/route_history.csv` appended und dann `build_stats.py` aufruft, das eine aggregierte `data/stats.json` schreibt. Beide Dateien werden mit `[skip ci]` committed. `index.html` im Repo-Root lädt die JSON (Heatmap) und CSV (Zeitreihe) direkt im Browser via GitHub Pages.

**Tech Stack:** Python 3.12, `requests`, `zoneinfo` (stdlib), Chart.js (lokal), PapaParse (lokal), GitHub Actions, Google Routes API v2

---

## File Map

| Datei | Aktion | Verantwortlichkeit |
|-------|--------|--------------------|
| `requirements.txt` | Create | Python-Abhängigkeiten |
| `scripts/fetch_route.py` | Create | Zeitfenster-Guard, API-Call, Retry, CSV-Append, build_stats aufrufen |
| `scripts/build_stats.py` | Create | CSV → stats.json Aggregation |
| `tests/test_build_stats.py` | Create | Unit-Tests für Aggregationslogik |
| `tests/test_fetch_route.py` | Create | Unit-Tests für parse_duration, Zeitfenster-Guard |
| `data/route_history.csv` | Create | Master-Log mit CSV-Header |
| `data/stats.json` | Create | Initiale leere Aggregation |
| `vendor/chart.min.js` | Create | Chart.js lokal (Download) |
| `vendor/papaparse.min.js` | Create | PapaParse lokal (Download) |
| `index.html` | Create | Dashboard: aktueller Wert, Zeitreihenchart, Heatmap |
| `.github/workflows/route-monitor.yml` | Create | Cron-Workflow |
| `README.md` | Create | Setup-Anleitung |

---

## Task 1: Repo-Grundstruktur und Abhängigkeiten

**Files:**
- Create: `requirements.txt`
- Create: `data/route_history.csv`
- Create: `data/stats.json`

- [ ] **Schritt 1: Verzeichnisse anlegen**

```bash
mkdir -p scripts data tests vendor .github/workflows
```

- [ ] **Schritt 2: `requirements.txt` anlegen**

```txt
requests==2.32.3
```

(`zoneinfo` ist ab Python 3.9 stdlib, `statistics` ebenfalls — keine weiteren Deps nötig.)

- [ ] **Schritt 3: CSV-Header anlegen**

```bash
cat > data/route_history.csv <<'CSV'
route_id,timestamp_utc,weekday_local,hour_local,origin_lat,origin_lng,destination_lat,destination_lng,duration_seconds,static_duration_seconds,travel_mode,source
CSV
```

- [ ] **Schritt 4: Initiale leere `stats.json` anlegen**

```bash
echo '{"last_updated": null, "routes": {}}' > data/stats.json
```

- [ ] **Schritt 5: Commit**

```bash
git add requirements.txt data/route_history.csv data/stats.json
git commit -m "chore: initial repo structure and data files"
```

---

## Task 2: `build_stats.py` — Aggregation CSV → JSON

**Files:**
- Create: `scripts/build_stats.py`
- Test: `tests/test_build_stats.py`

- [ ] **Schritt 1: Failing-Test schreiben**

Datei `tests/test_build_stats.py` anlegen:

```python
import csv
import json
import tempfile
from pathlib import Path

import pytest

# Füge scripts/ zum Import-Pfad hinzu
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "route_id", "timestamp_utc", "weekday_local", "hour_local",
        "origin_lat", "origin_lng", "destination_lat", "destination_lng",
        "duration_seconds", "static_duration_seconds", "travel_mode", "source",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_build_empty_csv(tmp_path):
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"
    write_csv(csv_path, [])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    assert result["routes"] == {}
    assert result["last_updated"] is not None


def test_build_single_row(tmp_path):
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"
    write_csv(csv_path, [{
        "route_id": "test_route",
        "timestamp_utc": "2025-01-13T07:00:00+00:00",
        "weekday_local": "Monday",
        "hour_local": "08",
        "origin_lat": 48.7784,
        "origin_lng": 9.1800,
        "destination_lat": 48.1351,
        "destination_lng": 11.5820,
        "duration_seconds": 4500,
        "static_duration_seconds": 3600,
        "travel_mode": "DRIVE",
        "source": "google_routes_api",
    }])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    route = result["routes"]["test_route"]
    assert route["latest"]["duration_seconds"] == 4500
    assert route["by_weekday_hour"]["Monday"]["08"]["avg"] == 4500
    assert route["by_weekday_hour"]["Monday"]["08"]["min"] == 4500
    assert route["by_weekday_hour"]["Monday"]["08"]["max"] == 4500
    assert route["by_weekday_hour"]["Monday"]["08"]["count"] == 1


def test_build_aggregates_multiple_rows(tmp_path):
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"
    write_csv(csv_path, [
        {
            "route_id": "r1", "timestamp_utc": "2025-01-13T07:00:00+00:00",
            "weekday_local": "Monday", "hour_local": "08",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 3000, "static_duration_seconds": 2800,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
        {
            "route_id": "r1", "timestamp_utc": "2025-01-20T07:00:00+00:00",
            "weekday_local": "Monday", "hour_local": "08",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 5000, "static_duration_seconds": 2800,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
    ])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    cell = result["routes"]["r1"]["by_weekday_hour"]["Monday"]["08"]
    assert cell["avg"] == 4000
    assert cell["min"] == 3000
    assert cell["max"] == 5000
    assert cell["count"] == 2


def test_latest_is_most_recent(tmp_path):
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"
    write_csv(csv_path, [
        {
            "route_id": "r1", "timestamp_utc": "2025-01-13T07:00:00+00:00",
            "weekday_local": "Monday", "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 3000, "static_duration_seconds": 2800,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
        {
            "route_id": "r1", "timestamp_utc": "2025-01-14T08:00:00+00:00",
            "weekday_local": "Tuesday", "hour_local": "09",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 9999, "static_duration_seconds": 2800,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
    ])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    assert result["routes"]["r1"]["latest"]["duration_seconds"] == 9999
    assert result["routes"]["r1"]["latest"]["timestamp_utc"] == "2025-01-14T08:00:00+00:00"
```

- [ ] **Schritt 2: Test ausführen — muss fehlschlagen**

```bash
python -m pytest tests/test_build_stats.py -v
```

Erwartet: `ModuleNotFoundError: No module named 'build_stats'`

- [ ] **Schritt 3: `scripts/build_stats.py` implementieren**

```python
"""
build_stats.py — CSV → stats.json Aggregation

Kann standalone ausgeführt werden:
    python scripts/build_stats.py

Oder als Modul importiert:
    from build_stats import build
    build()
"""
import csv
import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from statistics import mean

_REPO_ROOT = Path(__file__).parent.parent
_DEFAULT_CSV = _REPO_ROOT / "data" / "route_history.csv"
_DEFAULT_JSON = _REPO_ROOT / "data" / "stats.json"


def build(
    csv_path: Path = _DEFAULT_CSV,
    json_path: Path = _DEFAULT_JSON,
) -> None:
    """Liest csv_path und schreibt aggregierte stats nach json_path (atomar)."""
    routes: dict = {}

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            route_id = row["route_id"]
            if route_id not in routes:
                routes[route_id] = {"_rows": []}
            routes[route_id]["_rows"].append(row)

    output: dict = {
        "last_updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "routes": {},
    }

    for route_id, data in routes.items():
        rows = data["_rows"]

        # Neuester Eintrag
        latest_row = max(rows, key=lambda r: r["timestamp_utc"])

        # Aggregation pro Wochentag × Stunde
        by_weekday_hour: dict = {}
        for row in rows:
            wd = row["weekday_local"]
            hr = row["hour_local"]
            val = int(row["duration_seconds"])
            by_weekday_hour.setdefault(wd, {}).setdefault(hr, []).append(val)

        aggregated: dict = {}
        for wd, hours in by_weekday_hour.items():
            aggregated[wd] = {}
            for hr, values in hours.items():
                aggregated[wd][hr] = {
                    "avg": round(mean(values)),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }

        output["routes"][route_id] = {
            "latest": {
                "timestamp_utc": latest_row["timestamp_utc"],
                "duration_seconds": int(latest_row["duration_seconds"]),
                "static_duration_seconds": int(latest_row["static_duration_seconds"]),
            },
            "by_weekday_hour": aggregated,
        }

    # Atomar schreiben: erst Temp-Datei, dann rename
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=json_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        Path(tmp_path).replace(json_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    build()
    print("stats.json aktualisiert.")
```

- [ ] **Schritt 4: Tests ausführen — müssen grün sein**

```bash
python -m pytest tests/test_build_stats.py -v
```

Erwartet: 4 Tests PASSED

- [ ] **Schritt 5: Commit**

```bash
git add scripts/build_stats.py tests/test_build_stats.py
git commit -m "feat: add build_stats.py with aggregation logic"
```

---

## Task 3: `fetch_route.py` — API-Call, Zeitfenster-Guard, Retry

**Files:**
- Create: `scripts/fetch_route.py`
- Test: `tests/test_fetch_route.py`

- [ ] **Schritt 1: Failing-Tests schreiben**

Datei `tests/test_fetch_route.py` anlegen:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import datetime as dt

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Zeitfenster-Guard ─────────────────────────────────────────────────────────

from fetch_route import is_within_window


def test_within_window_weekday_morning():
    # Montag 08:00 Uhr lokal → innerhalb
    ts = dt.datetime(2025, 1, 13, 8, 0, tzinfo=dt.timezone.utc)  # Montag
    assert is_within_window(ts) is True


def test_within_window_weekday_night():
    # Montag 23:00 Uhr lokal → außerhalb
    ts = dt.datetime(2025, 1, 13, 23, 0, tzinfo=dt.timezone.utc)  # Montag
    assert is_within_window(ts) is False


def test_within_window_weekend():
    # Samstag 10:00 Uhr → außerhalb
    ts = dt.datetime(2025, 1, 11, 10, 0, tzinfo=dt.timezone.utc)  # Samstag
    assert is_within_window(ts) is False


def test_within_window_boundary_start():
    # 05:00 Uhr lokal (MEZ = UTC+1, also UTC 04:00) → innerhalb
    # Wir testen mit einer naiven Uhrzeit in lokaler Zeit direkt
    # is_within_window erwartet ein tz-aware datetime in UTC,
    # konvertiert intern auf TIMEZONE
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Berlin")
    local_5am_monday = dt.datetime(2025, 1, 13, 5, 0, tzinfo=tz)
    utc_ts = local_5am_monday.astimezone(dt.timezone.utc)
    assert is_within_window(utc_ts) is True


def test_within_window_boundary_before_start():
    # 04:59 Uhr lokal → außerhalb
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Berlin")
    local_459am_monday = dt.datetime(2025, 1, 13, 4, 59, tzinfo=tz)
    utc_ts = local_459am_monday.astimezone(dt.timezone.utc)
    assert is_within_window(utc_ts) is False


# ── parse_duration ─────────────────────────────────────────────────────────────

from fetch_route import parse_duration


def test_parse_duration_with_s():
    assert parse_duration("3600s") == 3600


def test_parse_duration_without_s():
    assert parse_duration("4500") == 4500


def test_parse_duration_integer():
    assert parse_duration(1800) == 1800
```

- [ ] **Schritt 2: Tests ausführen — muss fehlschlagen**

```bash
python -m pytest tests/test_fetch_route.py -v
```

Erwartet: `ModuleNotFoundError: No module named 'fetch_route'`

- [ ] **Schritt 3: `scripts/fetch_route.py` implementieren**

```python
"""
fetch_route.py — Google Routes API Call, Zeitfenster-Guard, Retry, CSV-Append

Umgebungsvariablen:
    GOOGLE_MAPS_API_KEY  (required)
    ROUTE_ID             (default: "default")
    ORIGIN_LAT           (default: 48.7784)
    ORIGIN_LNG           (default: 9.1800)
    DEST_LAT             (default: 48.1351)
    DEST_LNG             (default: 11.5820)
    TIMEZONE             (default: "Europe/Berlin")
"""
import csv
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# Füge scripts/ zum Import-Pfad hinzu, damit build_stats importiert werden kann
sys.path.insert(0, str(Path(__file__).parent))
from build_stats import build as build_stats

_REPO_ROOT = Path(__file__).parent.parent
_CSV_PATH = _REPO_ROOT / "data" / "route_history.csv"
_TIMEZONE = os.environ.get("TIMEZONE", "Europe/Berlin")

FIELDNAMES = [
    "route_id", "timestamp_utc", "weekday_local", "hour_local",
    "origin_lat", "origin_lng", "destination_lat", "destination_lng",
    "duration_seconds", "static_duration_seconds", "travel_mode", "source",
]


def is_within_window(now_utc: dt.datetime, timezone: str = _TIMEZONE) -> bool:
    """Gibt True zurück wenn now_utc innerhalb Werktag 05–22 Uhr lokaler Zeit liegt."""
    now_local = now_utc.astimezone(ZoneInfo(timezone))
    if now_local.weekday() >= 5:  # Samstag=5, Sonntag=6
        return False
    return 5 <= now_local.hour < 22


def parse_duration(value) -> int:
    """Parst Googles duration-String '3600s' oder '3600' zu int."""
    return int(str(value).replace("s", ""))


def _call_api(api_key: str, payload: dict) -> dict:
    """Führt einen API-Call aus. Wirft bei HTTP-Fehler oder Timeout."""
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_with_retry(api_key: str, payload: dict, retries: int = 1, delay: int = 10) -> dict:
    """Ruft die API auf, 1x Retry bei Fehler nach `delay` Sekunden."""
    for attempt in range(retries + 1):
        try:
            return _call_api(api_key, payload)
        except (requests.RequestException, requests.HTTPError) as exc:
            if attempt < retries:
                print(f"API-Fehler (Versuch {attempt + 1}): {exc} — Retry in {delay}s")
                time.sleep(delay)
            else:
                raise


def main() -> None:
    now_utc = dt.datetime.now(dt.timezone.utc)

    if not is_within_window(now_utc):
        print(f"Außerhalb des Zeitfensters ({now_utc.isoformat()}), kein API-Call.")
        sys.exit(0)

    api_key = os.environ["GOOGLE_MAPS_API_KEY"]
    route_id = os.environ.get("ROUTE_ID", "default")
    origin_lat = float(os.environ.get("ORIGIN_LAT", "48.7784"))
    origin_lng = float(os.environ.get("ORIGIN_LNG", "9.1800"))
    dest_lat = float(os.environ.get("DEST_LAT", "48.1351"))
    dest_lng = float(os.environ.get("DEST_LNG", "11.5820"))
    timezone = os.environ.get("TIMEZONE", "Europe/Berlin")

    payload = {
        "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
        "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "languageCode": "de-DE",
        "units": "METRIC",
    }

    data = fetch_with_retry(api_key, payload)
    routes = data.get("routes", [])
    if not routes:
        raise RuntimeError("Keine Route in der API-Antwort gefunden")

    route = routes[0]
    now_local = now_utc.astimezone(ZoneInfo(timezone))

    row = {
        "route_id": route_id,
        "timestamp_utc": now_utc.replace(microsecond=0).isoformat(),
        "weekday_local": now_local.strftime("%A"),
        "hour_local": now_local.strftime("%H"),
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
        "destination_lat": dest_lat,
        "destination_lng": dest_lng,
        "duration_seconds": parse_duration(route["duration"]),
        "static_duration_seconds": parse_duration(route.get("staticDuration", route["duration"])),
        "travel_mode": "DRIVE",
        "source": "google_routes_api",
    }

    write_header = not _CSV_PATH.exists() or _CSV_PATH.stat().st_size == 0
    with _CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print(json.dumps(row, ensure_ascii=False))

    build_stats()
    print("stats.json aktualisiert.")


if __name__ == "__main__":
    main()
```

- [ ] **Schritt 4: Tests ausführen — müssen grün sein**

```bash
python -m pytest tests/test_fetch_route.py -v
```

Erwartet: 7 Tests PASSED

- [ ] **Schritt 5: Alle Tests ausführen**

```bash
python -m pytest tests/ -v
```

Erwartet: 11 Tests PASSED

- [ ] **Schritt 6: Commit**

```bash
git add scripts/fetch_route.py tests/test_fetch_route.py
git commit -m "feat: add fetch_route.py with time-window guard and retry logic"
```

---

## Task 4: JS-Bibliotheken lokal herunterladen

**Files:**
- Create: `vendor/chart.min.js`
- Create: `vendor/papaparse.min.js`

- [ ] **Schritt 1: Chart.js herunterladen**

```bash
curl -L "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js" \
  -o vendor/chart.min.js
```

- [ ] **Schritt 2: PapaParse herunterladen**

```bash
curl -L "https://cdn.jsdelivr.net/npm/papaparse@5.4.1/papaparse.min.js" \
  -o vendor/papaparse.min.js
```

- [ ] **Schritt 3: Größen prüfen**

```bash
ls -lh vendor/
```

Erwartet: `chart.min.js` ~200 KB, `papaparse.min.js` ~50 KB

- [ ] **Schritt 4: Commit**

```bash
git add vendor/
git commit -m "chore: add Chart.js and PapaParse as local vendor files"
```

---

## Task 5: `index.html` — Dashboard

**Files:**
- Create: `index.html`

- [ ] **Schritt 1: `index.html` anlegen**

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Route Monitor</title>
  <script src="vendor/papaparse.min.js"></script>
  <script src="vendor/chart.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: #1f2328;
      background: #ffffff;
      padding: 24px 16px;
    }
    .container { max-width: 760px; margin: 0 auto; }
    h1 { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
    .subtitle { color: #57606a; font-size: 13px; margin-bottom: 32px; }
    .card {
      background: #f7f8fa;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 20px;
      margin-bottom: 24px;
    }
    .card h2 { font-size: 15px; font-weight: 600; margin-bottom: 16px; }
    .stat-row { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 8px; }
    .stat { }
    .stat .label { font-size: 12px; color: #57606a; }
    .stat .value { font-size: 28px; font-weight: 700; color: #1f2328; }
    .stat .unit { font-size: 14px; color: #57606a; }
    .delay-positive { color: #d97706; }
    .delay-zero { color: #16a34a; }
    .toggle-group { display: flex; gap: 4px; margin-bottom: 16px; }
    .toggle-btn {
      padding: 4px 12px;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      background: #fff;
      cursor: pointer;
      font-size: 13px;
      color: #57606a;
    }
    .toggle-btn.active {
      background: #3b82d4;
      border-color: #3b82d4;
      color: #fff;
    }
    .chart-wrap { position: relative; height: 240px; }
    /* Heatmap */
    .heatmap-wrap { overflow-x: auto; }
    table.heatmap {
      border-collapse: collapse;
      font-size: 12px;
      min-width: 100%;
    }
    table.heatmap th, table.heatmap td {
      border: 1px solid #e5e7eb;
      padding: 5px 8px;
      text-align: center;
      white-space: nowrap;
    }
    table.heatmap th { background: #f7f8fa; font-weight: 600; }
    table.heatmap td { min-width: 52px; }
    .legend { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 12px; color: #57606a; }
    .legend-bar {
      width: 120px; height: 12px; border-radius: 2px;
      background: linear-gradient(to right, #bbf7d0, #fef08a, #fca5a5);
    }
    #loading { color: #57606a; font-size: 13px; }
    #error { color: #dc2626; font-size: 13px; display: none; }
  </style>
</head>
<body>
<div class="container">
  <h1>Route Monitor</h1>
  <p class="subtitle" id="route-label">Lade Daten…</p>
  <p id="loading">Daten werden geladen…</p>
  <p id="error"></p>

  <!-- Aktueller Wert -->
  <div class="card" id="card-current" style="display:none">
    <h2>Aktuell</h2>
    <div class="stat-row">
      <div class="stat">
        <div class="label">Fahrtdauer</div>
        <div class="value" id="val-duration">—</div>
        <span class="unit">min</span>
      </div>
      <div class="stat">
        <div class="label">Ohne Verkehr</div>
        <div class="value" id="val-static">—</div>
        <span class="unit">min</span>
      </div>
      <div class="stat">
        <div class="label">Verzögerung</div>
        <div class="value" id="val-delay">—</div>
        <span class="unit">min</span>
      </div>
    </div>
    <div style="font-size:12px;color:#57606a;margin-top:8px" id="val-timestamp"></div>
  </div>

  <!-- Zeitreihenchart -->
  <div class="card">
    <h2>Verlauf</h2>
    <div class="toggle-group">
      <button class="toggle-btn active" data-days="7">7 Tage</button>
      <button class="toggle-btn" data-days="30">30 Tage</button>
      <button class="toggle-btn" data-days="90">90 Tage</button>
    </div>
    <div class="chart-wrap">
      <canvas id="chart-timeseries"></canvas>
    </div>
  </div>

  <!-- Heatmap -->
  <div class="card">
    <h2>Durchschnitt nach Wochentag & Uhrzeit</h2>
    <div class="heatmap-wrap">
      <div id="heatmap-container"><p style="color:#57606a;font-size:13px">Noch keine Aggregationsdaten vorhanden.</p></div>
    </div>
    <div class="legend">
      <span>schnell</span>
      <div class="legend-bar"></div>
      <span>langsam</span>
    </div>
  </div>
</div>

<script>
const WEEKDAY_ORDER = ["Monday","Tuesday","Wednesday","Thursday","Friday"];
const WEEKDAY_DE = { Monday:"Mo", Tuesday:"Di", Wednesday:"Mi", Thursday:"Do", Friday:"Fr" };
const HOURS = Array.from({length: 17}, (_, i) => String(i + 5).padStart(2, "0")); // 05–21

let timeseriesChart = null;
let allRows = [];
let activeDays = 7;

// ── Hilfsfunktionen ────────────────────────────────────────────────────────────

function secToMin(s) { return Math.round(s / 60); }

function heatColor(value, minVal, maxVal) {
  if (value === null) return "#e5e7eb";
  if (minVal === maxVal) return "#fef08a";
  const t = (value - minVal) / (maxVal - minVal);
  // Grün → Gelb → Rot
  const r = Math.round(t < 0.5 ? 2 * t * 255 : 255);
  const g = Math.round(t < 0.5 ? 187 + (0.5 - t) * 2 * 68 : (1 - t) * 2 * 187);
  const b = Math.round(t < 0.5 ? 2 * t * 165 : (1 - t) * 2 * 165);
  return `rgb(${r},${g},${b})`;
}

function formatTs(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

// ── Zeitreihenchart ────────────────────────────────────────────────────────────

function buildTimeseries(rows, days) {
  const cutoff = new Date(Date.now() - days * 86400 * 1000);
  const filtered = rows.filter(r => new Date(r.timestamp_utc) >= cutoff);
  const labels = filtered.map(r => formatTs(r.timestamp_utc));
  const duration = filtered.map(r => secToMin(parseInt(r.duration_seconds)));
  const staticDur = filtered.map(r => secToMin(parseInt(r.static_duration_seconds)));
  return { labels, duration, staticDur };
}

function renderTimeseries(rows, days) {
  const ctx = document.getElementById("chart-timeseries").getContext("2d");
  const { labels, duration, staticDur } = buildTimeseries(rows, days);
  if (timeseriesChart) timeseriesChart.destroy();
  timeseriesChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Mit Verkehr",
          data: duration,
          borderColor: "#3b82d4",
          backgroundColor: "rgba(59,130,212,0.08)",
          borderWidth: 2,
          pointRadius: labels.length > 100 ? 0 : 3,
          tension: 0.3,
        },
        {
          label: "Ohne Verkehr",
          data: staticDur,
          borderColor: "#9ca3af",
          borderDash: [4, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
        y: { title: { display: true, text: "Minuten" }, beginAtZero: false },
      },
    },
  });
}

// ── Heatmap ────────────────────────────────────────────────────────────────────

function renderHeatmap(byWeekdayHour) {
  const days = WEEKDAY_ORDER.filter(d => byWeekdayHour[d]);
  if (days.length === 0) return;

  // Alle Werte für Farbskala sammeln
  const allVals = [];
  for (const d of days) {
    for (const h of HOURS) {
      const cell = byWeekdayHour[d]?.[h];
      if (cell) allVals.push(cell.avg);
    }
  }
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);

  let html = '<table class="heatmap"><thead><tr><th>Uhr</th>';
  for (const d of days) html += `<th>${WEEKDAY_DE[d]}</th>`;
  html += "</tr></thead><tbody>";

  for (const h of HOURS) {
    html += `<tr><td><strong>${h}:00</strong></td>`;
    for (const d of days) {
      const cell = byWeekdayHour[d]?.[h];
      if (cell) {
        const color = heatColor(cell.avg, minVal, maxVal);
        const min = secToMin(cell.avg);
        html += `<td style="background:${color}" title="${min} min (n=${cell.count})">${min}</td>`;
      } else {
        html += `<td style="background:#e5e7eb;color:#9ca3af">—</td>`;
      }
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  document.getElementById("heatmap-container").innerHTML = html;
}

// ── Hauptlogik ─────────────────────────────────────────────────────────────────

async function init() {
  try {
    // stats.json laden
    const statsRes = await fetch("data/stats.json");
    if (!statsRes.ok) throw new Error("stats.json nicht gefunden");
    const stats = await statsRes.json();

    const routeKeys = Object.keys(stats.routes || {});
    if (routeKeys.length === 0) {
      document.getElementById("loading").textContent = "Noch keine Daten vorhanden.";
      return;
    }

    const routeId = routeKeys[0];
    const routeData = stats.routes[routeId];

    // Label
    document.getElementById("route-label").textContent =
      `Route: ${routeId} · Stand: ${formatTs(stats.last_updated)}`;

    // Aktueller Wert
    if (routeData.latest) {
      const dur = secToMin(routeData.latest.duration_seconds);
      const sta = secToMin(routeData.latest.static_duration_seconds);
      const delay = dur - sta;
      document.getElementById("val-duration").textContent = dur;
      document.getElementById("val-static").textContent = sta;
      const delayEl = document.getElementById("val-delay");
      delayEl.textContent = delay > 0 ? `+${delay}` : delay;
      delayEl.className = `value ${delay > 0 ? "delay-positive" : "delay-zero"}`;
      document.getElementById("val-timestamp").textContent =
        `Gemessen: ${formatTs(routeData.latest.timestamp_utc)}`;
      document.getElementById("card-current").style.display = "";
    }

    // Heatmap
    if (routeData.by_weekday_hour) {
      renderHeatmap(routeData.by_weekday_hour);
    }

    // CSV für Zeitreihe laden
    const csvRes = await fetch("data/route_history.csv");
    if (!csvRes.ok) throw new Error("route_history.csv nicht gefunden");
    const csvText = await csvRes.text();
    const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });
    allRows = parsed.data.filter(r => r.route_id === routeId);
    allRows.sort((a, b) => a.timestamp_utc.localeCompare(b.timestamp_utc));

    renderTimeseries(allRows, activeDays);

    // Toggle-Buttons
    document.querySelectorAll(".toggle-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeDays = parseInt(btn.dataset.days);
        renderTimeseries(allRows, activeDays);
      });
    });

    document.getElementById("loading").style.display = "none";

  } catch (err) {
    document.getElementById("loading").style.display = "none";
    const errEl = document.getElementById("error");
    errEl.textContent = `Fehler: ${err.message}`;
    errEl.style.display = "";
  }
}

init();
</script>
</body>
</html>
```

- [ ] **Schritt 2: Dashboard lokal prüfen**

```bash
python -m http.server 8080
```

Browser öffnen: `http://localhost:8080` — Seite sollte laden, "Noch keine Daten vorhanden" anzeigen (leere CSV/stats.json).

- [ ] **Schritt 3: Commit**

```bash
git add index.html
git commit -m "feat: add static dashboard with timeseries chart and heatmap"
```

---

## Task 6: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/route-monitor.yml`

- [ ] **Schritt 1: Workflow-Datei anlegen**

```yaml
name: Route Monitor

on:
  schedule:
    - cron: '0 3-21 * * 1-5'
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
          ROUTE_ID: ${{ vars.ROUTE_ID }}
          ORIGIN_LAT: ${{ vars.ORIGIN_LAT }}
          ORIGIN_LNG: ${{ vars.ORIGIN_LNG }}
          DEST_LAT: ${{ vars.DEST_LAT }}
          DEST_LNG: ${{ vars.DEST_LNG }}
          TIMEZONE: ${{ vars.TIMEZONE }}
        run: python scripts/fetch_route.py

      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/route_history.csv data/stats.json
          git diff --staged --quiet || git commit -m "chore: update route history [skip ci]"
          git push
```

- [ ] **Schritt 2: Commit**

```bash
git add .github/workflows/route-monitor.yml
git commit -m "ci: add route-monitor workflow with cron schedule"
```

---

## Task 7: README

**Files:**
- Create: `README.md`

- [ ] **Schritt 1: README anlegen**

```markdown
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
pip install -r requirements.txt
# stats.json manuell neu generieren:
python scripts/build_stats.py
# Dashboard lokal testen:
python -m http.server 8080
```
```

- [ ] **Schritt 2: Commit und Push**

```bash
git add README.md
git commit -m "docs: add setup README"
git push
```

---

## Task 8: Erster Testlauf und Verifikation

*Dieser Task erfordert manuelle Schritte in der GitHub UI.*

- [ ] **Schritt 1: Google Cloud Setup verifizieren**
  - Cloud-Projekt erstellt ✓
  - Billing aktiviert ✓
  - Routes API aktiviert ✓
  - API-Key erstellt, auf Routes API beschränkt ✓
  - Budget-Alert gesetzt ✓

- [ ] **Schritt 2: GitHub Setup verifizieren**
  - Repo ist öffentlich ✓
  - Secret `GOOGLE_MAPS_API_KEY` gesetzt ✓
  - Repository Variables für Koordinaten, TIMEZONE, ROUTE_ID gesetzt ✓

- [ ] **Schritt 3: Manuellen Workflow-Run starten**

  GitHub UI: `Actions → Route Monitor → Run workflow → Run workflow`

- [ ] **Schritt 4: Workflow-Output prüfen**

  Im Workflow-Log unter "Fetch route duration" sollte eine JSON-Zeile erscheinen:
  ```json
  {"route_id": "...", "duration_seconds": 4320, ...}
  ```
  Gefolgt von: `stats.json aktualisiert.`

- [ ] **Schritt 5: Daten im Repo prüfen**

  Nach dem Workflow-Run:
  - `data/route_history.csv` sollte eine Datenzeile enthalten
  - `data/stats.json` sollte einen `routes`-Eintrag enthalten

- [ ] **Schritt 6: GitHub Pages aktivieren**

  `Settings → Pages → Branch: main, Folder: / (root) → Save`

  Nach 1–2 Minuten: Dashboard-URL im Browser öffnen und prüfen, dass Daten angezeigt werden.

- [ ] **Schritt 7: Häufige Fehlerursachen**

  | Symptom | Ursache | Fix |
  |---------|---------|-----|
  | Workflow schlägt fehl: `403 Forbidden` | Billing nicht aktiv oder Routes API nicht aktiviert | Google Cloud Console prüfen |
  | Workflow schlägt fehl: `GOOGLE_MAPS_API_KEY not set` | Secret fehlt | Secret in GitHub anlegen |
  | CSV bleibt leer, kein Commit | Zeitfenster-Guard greift (außerhalb Werktag 5–22 Uhr) | `workflow_dispatch` nutzen für manuellen Test |
  | Dashboard zeigt "Fehler" | GitHub Pages noch nicht aktiv oder Route zu stats.json falsch | Pages-Einstellungen prüfen, 2 min warten |
