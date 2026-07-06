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
