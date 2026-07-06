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
