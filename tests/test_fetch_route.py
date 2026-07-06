import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import datetime as dt

import pytest
import requests as req_lib

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
from fetch_route import fetch_with_retry


def test_parse_duration_with_s():
    assert parse_duration("3600s") == 3600


def test_parse_duration_without_s():
    assert parse_duration("4500") == 4500


def test_parse_duration_integer():
    assert parse_duration(1800) == 1800


# ── fetch_with_retry ──────────────────────────────────────────────────────────

def test_fetch_with_retry_succeeds_on_first_attempt():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"routes": [{"duration": "3600s"}]}
    mock_response.raise_for_status.return_value = None

    with patch("fetch_route.requests.post", return_value=mock_response) as mock_post:
        result = fetch_with_retry("key", {}, delay=0)
    assert result == {"routes": [{"duration": "3600s"}]}
    assert mock_post.call_count == 1


def test_fetch_with_retry_retries_on_network_error():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"routes": []}
    mock_response.raise_for_status.return_value = None

    with patch("fetch_route.requests.post", side_effect=[
        req_lib.ConnectionError("Network down"),
        mock_response,
    ]) as mock_post:
        result = fetch_with_retry("key", {}, delay=0)
    assert mock_post.call_count == 2
    assert result == {"routes": []}


def test_fetch_with_retry_does_not_retry_4xx():
    error_response = MagicMock()
    error_response.status_code = 401
    http_error = req_lib.HTTPError(response=error_response)

    call_count = 0
    def mock_call_api(api_key, payload):
        nonlocal call_count
        call_count += 1
        raise http_error

    with patch("fetch_route._call_api", side_effect=mock_call_api):
        with pytest.raises(req_lib.HTTPError):
            fetch_with_retry("key", {}, delay=0)
    assert call_count == 1, "4xx should not be retried"


def test_within_window_boundary_end():
    # 22:00 Uhr lokal → außerhalb (hour < 22 required)
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Berlin")
    local_22_monday = dt.datetime(2025, 1, 13, 22, 0, tzinfo=tz)
    utc_ts = local_22_monday.astimezone(dt.timezone.utc)
    assert is_within_window(utc_ts) is False


def test_within_window_boundary_before_end():
    # 21:59 Uhr lokal → innerhalb
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Berlin")
    local_2159_monday = dt.datetime(2025, 1, 13, 21, 59, tzinfo=tz)
    utc_ts = local_2159_monday.astimezone(dt.timezone.utc)
    assert is_within_window(utc_ts) is True
