"""
fetch_route.py — Google Routes API Call, Zeitfenster-Guard, Retry, CSV-Append

Berechnet pro Run beide Richtungen (outbound + return).

Umgebungsvariablen:
    GOOGLE_MAPS_API_KEY  (required)
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

FIELDNAMES = [
    "route_id", "timestamp_utc", "weekday_local", "hour_local",
    "origin_lat", "origin_lng", "destination_lat", "destination_lng",
    "duration_seconds", "static_duration_seconds", "travel_mode", "source",
]


def is_within_window(now_utc: dt.datetime, timezone: str = "Europe/Berlin") -> bool:
    """Gibt True zurück wenn now_utc in einem aktiven Abfrageintervall liegt.

    Aktive Zeitfenster (lokale Zeit, Werktage Mo–Fr):
      - Morgens: 06:00–08:59 Uhr
      - Abends:  16:00–18:59 Uhr

    Cron schedule controls the exact timing; this guard just prevents
    accidental runs far outside intended hours (e.g., manual triggers at night).
    """
    now_local = now_utc.astimezone(ZoneInfo(timezone))
    if now_local.weekday() >= 5:  # Samstag=5, Sonntag=6
        return False

    hour = now_local.hour

    # Morgens 06–08 Uhr (09:00 ist Endpunkt, also Stunden 6,7,8)
    if 6 <= hour < 9:
        return True

    # Abends 16–18 Uhr (19:00 ist Endpunkt, also Stunden 16,17,18)
    if 16 <= hour < 19:
        return True

    return False


def parse_duration(value) -> int:
    """Parst Googles duration-String '3600s' oder '3600' zu int."""
    return int(float(str(value).replace("s", "")))


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
    """Ruft die API auf, 1x Retry bei Netzwerkfehlern und 5xx/429. 4xx wird direkt geworfen."""
    for attempt in range(retries + 1):
        try:
            return _call_api(api_key, payload)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and status < 500 and status != 429:
                raise  # Deterministischer Fehler (4xx außer 429) — kein Retry
            if attempt < retries:
                print(f"API-Fehler HTTP {status} (Versuch {attempt + 1}) — Retry in {delay}s")
                time.sleep(delay)
            else:
                raise
        except requests.RequestException as exc:
            if attempt < retries:
                print(f"Netzwerkfehler (Versuch {attempt + 1}): {exc} — Retry in {delay}s")
                time.sleep(delay)
            else:
                raise


def fetch_one(
    api_key: str,
    route_id: str,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    now_utc: dt.datetime,
    timezone: str,
) -> dict:
    """Ruft eine Richtung ab und gibt eine CSV-Zeile zurück."""
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
        raise RuntimeError(f"Keine Route in der API-Antwort für route_id={route_id}")

    route = routes[0]
    now_local = now_utc.astimezone(ZoneInfo(timezone))

    return {
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


def main() -> None:
    now_utc = dt.datetime.now(dt.timezone.utc)
    timezone = os.environ.get("TIMEZONE") or "Europe/Berlin"

    if not is_within_window(now_utc, timezone=timezone):
        print(f"Außerhalb des Zeitfensters ({now_utc.isoformat()}), kein API-Call.")
        sys.exit(0)

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY Umgebungsvariable ist nicht gesetzt")

    origin_lat = float(os.environ.get("ORIGIN_LAT") or "48.7784")
    origin_lng = float(os.environ.get("ORIGIN_LNG") or "9.1800")
    dest_lat = float(os.environ.get("DEST_LAT") or "48.1351")
    dest_lng = float(os.environ.get("DEST_LNG") or "11.5820")

    # Zeitabhängige Richtungsauswahl:
    # Morgens (06-11 Uhr): nur outbound (zur Arbeit)
    # Abends (12-19 Uhr): nur return (nach Hause)
    now_local = now_utc.astimezone(ZoneInfo(timezone))
    hour_local = now_local.hour

    if hour_local < 12:
        # Morgens: nur Hinfahrt zur Arbeit
        directions = [("outbound", origin_lat, origin_lng, dest_lat, dest_lng)]
        print(f"Morgens {hour_local}:00 Uhr → fetche nur outbound (zur Arbeit)")
    else:
        # Abends: nur Rückfahrt nach Hause
        directions = [("return", dest_lat, dest_lng, origin_lat, origin_lng)]
        print(f"Abends {hour_local}:00 Uhr → fetche nur return (nach Hause)")

    rows = []
    for route_id, o_lat, o_lng, d_lat, d_lng in directions:
        row = fetch_one(api_key, route_id, o_lat, o_lng, d_lat, d_lng, now_utc, timezone)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    write_header = not _CSV_PATH.exists() or _CSV_PATH.stat().st_size == 0
    with _CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    build_stats()
    print("stats.json aktualisiert.")


if __name__ == "__main__":
    main()
