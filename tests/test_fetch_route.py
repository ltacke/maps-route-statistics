import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import datetime as dt

import pytest
import requests as req_lib

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_route import is_within_window, parse_duration, fetch_with_retry
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Berlin")


def _local(year, month, day, hour, minute=0):
    """Erzeugt ein tz-aware datetime in Europe/Berlin und gibt UTC zurück."""
    return dt.datetime(year, month, day, hour, minute, tzinfo=_TZ).astimezone(dt.timezone.utc)


# ── Zeitfenster-Guard: Morgens 06–08:59 ──────────────────────────────────────

def test_morning_slot_on_time():
    # Mo 06:00 → aktiv
    assert is_within_window(_local(2025, 1, 13, 6, 0)) is True

def test_morning_slot_15():
    # Mo 07:15 → aktiv
    assert is_within_window(_local(2025, 1, 13, 7, 15)) is True

def test_morning_slot_30():
    # Mo 08:30 → aktiv
    assert is_within_window(_local(2025, 1, 13, 8, 30)) is True

def test_morning_slot_off_minute():
    # Mo 07:01 → aktiv (any minute within hour range is accepted)
    assert is_within_window(_local(2025, 1, 13, 7, 1)) is True

def test_morning_end_boundary():
    # Mo 09:00 → nicht aktiv (Endpunkt exklusiv: hour < 9)
    assert is_within_window(_local(2025, 1, 13, 9, 0)) is False

def test_morning_before_start():
    # Mo 05:45 → nicht aktiv
    assert is_within_window(_local(2025, 1, 13, 5, 45)) is False


# ── Zeitfenster-Guard: Abends 16–18:59 ────────────────────────────────────────

def test_evening_slot_on_time():
    # Mo 16:00 → aktiv
    assert is_within_window(_local(2025, 1, 13, 16, 0)) is True

def test_evening_slot_half():
    # Mo 17:30 → aktiv
    assert is_within_window(_local(2025, 1, 13, 17, 30)) is True

def test_evening_slot_off_minute():
    # Mo 16:15 → aktiv (any minute within hour range is accepted)
    assert is_within_window(_local(2025, 1, 13, 16, 15)) is True

def test_evening_end_boundary():
    # Mo 19:00 → nicht aktiv (Endpunkt exklusiv: hour < 19)
    assert is_within_window(_local(2025, 1, 13, 19, 0)) is False

def test_midday_inactive():
    # Mo 12:00 → nicht aktiv (zwischen den Fenstern)
    assert is_within_window(_local(2025, 1, 13, 12, 0)) is False


# ── Zeitfenster-Guard: Wochenende ────────────────────────────────────────────

def test_weekend_morning():
    # Sa 07:00 → nicht aktiv
    assert is_within_window(_local(2025, 1, 11, 7, 0)) is False

def test_weekend_evening():
    # So 17:00 → nicht aktiv
    assert is_within_window(_local(2025, 1, 12, 17, 0)) is False


# ── parse_duration ────────────────────────────────────────────────────────────

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
