# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Route monitoring system that tracks traffic patterns on a fixed route using Google Routes API. The system:
- Fetches route durations bidirectionally (outbound + return) at scheduled intervals
- Logs data to CSV with bidirectional tracking per run
- Aggregates statistics by weekday and hour
- Visualizes data on a GitHub Pages dashboard with Leaflet map and Chart.js

**Key architectural decision**: Each run fetches BOTH directions (outbound A→B, return B→A) to capture asymmetric traffic patterns.

## Development Commands

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run specific test file
pytest tests/test_fetch_route.py

# Regenerate statistics manually (reads CSV, writes stats.json)
python scripts/build_stats.py

# Test dashboard locally
python -m http.server 8080
# Then open: http://localhost:8080
```

## Architecture

### Data Pipeline

1. **External Scheduling via cron-job.org**
   - Triggers GitHub Actions workflow via `workflow_dispatch` API
   - Schedule: weekdays only (Mo-Fr)
     - Morning: 06:00-09:00 Berlin time, 15-minute intervals
     - Evening: 16:00-19:00 Berlin time, 30-minute intervals
   - Timezone-aware: `Europe/Berlin` (handles DST automatically)
   - Can also be triggered manually via workflow_dispatch

2. **fetch_route.py** — API fetch + CSV append + stats rebuild
   - `is_within_window()`: Guards against off-schedule runs (e.g., manual triggers)
   - Fetches BOTH directions per run: `directions = [("outbound", ...), ("return", ...)]`
   - Writes two rows per run to `data/route_history.csv`
   - Calls `build_stats()` to regenerate `data/stats.json` after every successful fetch
   - **Retry logic**: 1 retry for network errors and 5xx/429, no retry for 4xx (except 429)

3. **build_stats.py** — CSV → JSON aggregation
   - Reads entire CSV
   - Aggregates by `route_id` (outbound/return) → weekday → hour
   - Outputs min/max/avg/count per bucket
   - Atomic write pattern (temp file → rename)
   - Can be run standalone OR imported by fetch_route.py

4. **index.html** — Static GitHub Pages dashboard
   - Fetches `data/stats.json` and `data/route_history.csv` (via Papa Parse)
   - Displays Leaflet map with route visualization
   - Chart.js for time-series and aggregated views
   - Pure client-side, no build step

### CSV Schema

```
route_id,timestamp_utc,weekday_local,hour_local,origin_lat,origin_lng,destination_lat,destination_lng,duration_seconds,static_duration_seconds,travel_mode,source
```

- `route_id`: "outbound" or "return"
- Each run creates TWO rows (one per direction)
- `static_duration_seconds`: Google's no-traffic baseline

### Configuration (GitHub Secrets + Variables)

**Secret** (encrypted):
- `GOOGLE_MAPS_API_KEY`

**Repository Variables**:
- `ROUTE_ID`: Legacy (not used; route_id hardcoded as outbound/return)
- `ORIGIN_LAT`, `ORIGIN_LNG`: Start point
- `DEST_LAT`, `DEST_LNG`: End point
- `TIMEZONE`: Default "Europe/Berlin"

## Critical Implementation Details

### Time Window Logic

The `is_within_window()` function enforces:
- Weekdays only (Mo-Fr, `weekday < 5`)
- Morning: 06:00-08:59 (hour < 9), minute % 15 == 0
- Evening: 16:00-18:59 (hour < 19), minute % 30 == 0

**Why**: Prevents accidental API costs from manual workflow runs outside intended schedule.

**Note**: cron-job.org schedules extend to 09:00 and 19:00, but `is_within_window()` rejects hour 9 and 19 (stricter guard). This is intentional for cost control.

### Time-Based Direction Selection

**Smart routing logic**: Only fetches the relevant direction based on local time:
- **Morgens (06-11 Uhr)**: Nur `outbound` (zur Arbeit)
- **Abends (12-19 Uhr)**: Nur `return` (nach Hause)

```python
if hour_local < 12:
    directions = [("outbound", origin_lat, origin_lng, dest_lat, dest_lng)]
else:
    directions = [("return", dest_lat, dest_lng, origin_lat, origin_lng)]
```

**Why**: Mornings are for commuting TO work, evenings are for commuting HOME. This:
- Saves 50% API calls
- Makes logical sense (no need to measure return route at 7am)
- Creates cleaner, more relevant data

### Stats Rebuild Trigger

`fetch_route.py` calls `build_stats()` after every successful fetch. This keeps `stats.json` always in sync with the CSV, avoiding manual rebuild steps.

## Testing

- **Unit tests** in `tests/` for time window logic, parsing, and retry behavior
- Tests use `sys.path.insert(0, ...)` to import from `scripts/` (no package structure)
- Mock HTTP responses to avoid real API calls
- Timezone-aware datetime fixtures using `ZoneInfo("Europe/Berlin")`

## Frontend

- **No build step**: Static HTML + vendored libraries
- **Vendor dependencies**: Chart.js, Leaflet, Papa Parse (all minified)
- **Data loading**: Client fetches `stats.json` for live metrics, `route_history.csv` for historical charts
- **Route visualization**: Leaflet map with route polyline between origin and destination

### Analytics Features (index.html)

The dashboard includes 8 comprehensive analytics sections:

1. **Empfehlungs-Widget**: Best departure time per weekday for each route direction
2. **Best/Worst Times Ranking**: Top 5 fastest and slowest time slots
3. **Heute vs. Durchschnitt**: Compares current measurement to historical average
4. **Wochentag-Vergleich**: Bar chart comparing average duration by weekday
5. **Monatlicher Trend**: Line chart showing monthly averages (appears when ≥2 months of data)
6. **Zeitersparnis-Rechner**: Interactive calculator comparing any time slot vs. optimal time
7. **Zuverlässigkeits-Indikator**: Standard deviation per hour (shows predictability)
8. **Verzögerungs-Verteilung**: Histogram of traffic delay buckets

All charts are conditionally rendered based on data availability and use consistent color coding:
- Blue (#3b82d4) for outbound
- Green (#16a34a) for return

## Cost Management

- Free tier: 10,000 Google Routes API calls/month
- Expected usage: ~365 calls/month (2 directions × ~182 runs)
- Budget alert recommended at €5/month
