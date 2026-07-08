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
        "hour_local": "07",
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
    assert route["latest"]["origin_lat"] == 48.7784
    assert route["latest"]["destination_lat"] == 48.1351
    assert route["by_weekday_hour"]["Monday"]["07"]["00"]["avg"] == 4500
    assert route["by_weekday_hour"]["Monday"]["07"]["00"]["min"] == 4500
    assert route["by_weekday_hour"]["Monday"]["07"]["00"]["max"] == 4500
    assert route["by_weekday_hour"]["Monday"]["07"]["00"]["count"] == 1


def test_build_aggregates_multiple_rows(tmp_path):
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
            "route_id": "r1", "timestamp_utc": "2025-01-20T07:00:00+00:00",
            "weekday_local": "Monday", "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 5000, "static_duration_seconds": 2800,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
    ])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    cell = result["routes"]["r1"]["by_weekday_hour"]["Monday"]["07"]["00"]
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


def test_build_multiple_routes(tmp_path):
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"
    write_csv(csv_path, [
        {
            "route_id": "route_a", "timestamp_utc": "2025-01-13T07:00:00+00:00",
            "weekday_local": "Monday", "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1000, "static_duration_seconds": 900,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
        {
            "route_id": "route_b", "timestamp_utc": "2025-01-13T07:00:00+00:00",
            "weekday_local": "Monday", "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0, "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 9000, "static_duration_seconds": 8000,
            "travel_mode": "DRIVE", "source": "google_routes_api",
        },
    ])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    assert set(result["routes"].keys()) == {"route_a", "route_b"}
    assert result["routes"]["route_a"]["latest"]["duration_seconds"] == 1000
    assert result["routes"]["route_b"]["latest"]["duration_seconds"] == 9000


def test_minute_level_aggregation(tmp_path):
    """Verify 3-level aggregation: weekday -> hour -> minute."""
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"

    write_csv(csv_path, [
        {
            "route_id": "test",
            "timestamp_utc": "2025-01-13T07:35:00+00:00",
            "weekday_local": "Monday",
            "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0,
            "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1800,
            "static_duration_seconds": 1700,
            "travel_mode": "DRIVE",
            "source": "google_routes_api",
        },
        {
            "route_id": "test",
            "timestamp_utc": "2025-01-13T07:40:00+00:00",
            "weekday_local": "Monday",
            "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0,
            "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1900,
            "static_duration_seconds": 1700,
            "travel_mode": "DRIVE",
            "source": "google_routes_api",
        },
    ])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    monday_07 = result["routes"]["test"]["by_weekday_hour"]["Monday"]["07"]

    # Should have two separate minute buckets
    assert "35" in monday_07
    assert "40" in monday_07
    assert monday_07["35"]["avg"] == 1800
    assert monday_07["35"]["count"] == 1
    assert monday_07["40"]["avg"] == 1900
    assert monday_07["40"]["count"] == 1


def test_malformed_timestamp_handling(tmp_path):
    """Verify that malformed timestamps are gracefully skipped."""
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"

    write_csv(csv_path, [
        {
            "route_id": "test",
            "timestamp_utc": "invalid-timestamp",
            "weekday_local": "Monday",
            "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0,
            "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1800,
            "static_duration_seconds": 1700,
            "travel_mode": "DRIVE",
            "source": "google_routes_api",
        },
        {
            "route_id": "test",
            "timestamp_utc": "2025-01-13T07:35:00+00:00",
            "weekday_local": "Monday",
            "hour_local": "07",
            "origin_lat": 0, "origin_lng": 0,
            "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1900,
            "static_duration_seconds": 1700,
            "travel_mode": "DRIVE",
            "source": "google_routes_api",
        },
    ])

    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)

    result = json.loads(json_path.read_text())
    # Should only have the valid row
    assert "test" in result["routes"]
    assert result["routes"]["test"]["latest"]["duration_seconds"] == 1900
    monday_07 = result["routes"]["test"]["by_weekday_hour"]["Monday"]["07"]
    assert "35" in monday_07
    assert monday_07["35"]["count"] == 1
