import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import estat_cpi_service
from market_macro_analysis.exceptions import FetchError, DataStoreError


# --- _parse_time_code ---

def test_parse_time_code_standard():
    assert estat_cpi_service._parse_time_code("2025001212") == "2025-12"


def test_parse_time_code_january():
    assert estat_cpi_service._parse_time_code("2026000101") == "2026-01"


# --- _parse_response ---

SAMPLE_RESPONSE = {
    "GET_STATS_DATA": {
        "STATISTICAL_DATA": {
            "DATA_INF": {
                "VALUE": [
                    {"@time": "2025001212", "$": "2.4"},
                    {"@time": "2025001111", "$": "3.0"},
                    {"@time": "2025001010", "$": "3.0"},
                ]
            }
        }
    }
}


def test_parse_response_returns_sorted_records():
    result = estat_cpi_service._parse_response(SAMPLE_RESPONSE)
    assert len(result) == 3
    assert result[0]["date"] == "2025-10"
    assert result[2]["date"] == "2025-12"
    assert result[2]["value"] == 2.4


def test_parse_response_skips_invalid_values():
    data = {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": [
                        {"@time": "2025001212", "$": "2.4"},
                        {"@time": "2025001111", "$": "-"},
                        {"@time": "2025001010", "$": "***"},
                        {"@time": "", "$": "3.0"},
                    ]
                }
            }
        }
    }
    result = estat_cpi_service._parse_response(data)
    assert len(result) == 1
    assert result[0]["value"] == 2.4


def test_parse_response_raises_on_invalid_structure():
    with pytest.raises(FetchError):
        estat_cpi_service._parse_response({"unexpected": "structure"})


def test_parse_response_handles_single_value_as_dict():
    data = {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": {"@time": "2025001212", "$": "2.4"}
                }
            }
        }
    }
    result = estat_cpi_service._parse_response(data)
    assert len(result) == 1
    assert result[0]["value"] == 2.4


# --- fetch_core_cpi ---

def test_fetch_core_cpi_success():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = estat_cpi_service.fetch_core_cpi("dummy_key")

    assert len(result) == 3
    assert result[-1]["date"] == "2025-12"
    assert result[-1]["value"] == 2.4


def test_fetch_core_cpi_retries_on_failure():
    import requests as req
    mock_ok = MagicMock()
    mock_ok.json.return_value = SAMPLE_RESPONSE
    mock_ok.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[req.RequestException("timeout"), mock_ok]) as mock_get:
        with patch("time.sleep"):
            result = estat_cpi_service.fetch_core_cpi("dummy_key")

    assert mock_get.call_count == 2
    assert len(result) == 3


def test_fetch_core_cpi_raises_after_max_retries():
    import requests as req
    with patch("requests.get", side_effect=req.RequestException("timeout")):
        with patch("time.sleep"):
            with pytest.raises(FetchError):
                estat_cpi_service.fetch_core_cpi("dummy_key")


# --- save_core_cpi ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_save_core_cpi_creates_table_and_saves(db_conn):
    records = [
        {"date": "2025-11", "value": 3.0},
        {"date": "2025-12", "value": 2.4},
    ]
    count = estat_cpi_service.save_core_cpi(db_conn, records)
    assert count == 2

    rows = db_conn.execute(
        "SELECT date, indicator, value, unit FROM price_data ORDER BY date"
    ).fetchall()
    assert rows[0] == ("2025-11", "core_cpi_yoy", 3.0, "%")
    assert rows[1] == ("2025-12", "core_cpi_yoy", 2.4, "%")


def test_save_core_cpi_overwrites_duplicate(db_conn):
    records = [{"date": "2025-12", "value": 2.4}]
    estat_cpi_service.save_core_cpi(db_conn, records)

    updated = [{"date": "2025-12", "value": 2.5}]
    estat_cpi_service.save_core_cpi(db_conn, updated)

    rows = db_conn.execute("SELECT value FROM price_data WHERE date='2025-12'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 2.5


def test_save_core_cpi_empty_records(db_conn):
    count = estat_cpi_service.save_core_cpi(db_conn, [])
    assert count == 0
