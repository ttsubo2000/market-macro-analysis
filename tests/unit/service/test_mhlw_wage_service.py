import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import mhlw_wage_service
from market_macro_analysis.exceptions import FetchError, DataStoreError


# --- サンプルデータ ---

SAMPLE_META_RESPONSE = {
    "GET_META_INFO": {
        "METADATA_INF": {
            "CLASS_INF": {
                "CLASS_OBJ": [
                    {
                        "@id": "tab",
                        "CLASS": [
                            {"@code": "01", "@name": "指数(平成22年平均＝100)"},
                            {"@code": "02", "@name": "前年比【％】"},
                        ],
                    },
                    {
                        "@id": "cat01",
                        "CLASS": [
                            {"@code": "01", "@name": "就業形態計"},
                            {"@code": "02", "@name": "一般労働者"},
                            {"@code": "03", "@name": "パートタイム労働者"},
                        ],
                    },
                    {
                        "@id": "cat02",
                        "CLASS": [
                            {"@code": "00", "@name": "産業計"},
                            {"@code": "01", "@name": "製造業"},
                        ],
                    },
                    {
                        "@id": "cat03",
                        "CLASS": [
                            {"@code": "01", "@name": "5人以上"},
                            {"@code": "02", "@name": "30人以上"},
                        ],
                    },
                ]
            }
        }
    }
}

SAMPLE_DATA_RESPONSE = {
    "GET_STATS_DATA": {
        "STATISTICAL_DATA": {
            "DATA_INF": {
                "VALUE": [
                    {"@time": "2025001212", "$": "2.1"},
                    {"@time": "2025001111", "$": "2.5"},
                    {"@time": "2025001010", "$": "2.8"},
                ]
            }
        }
    }
}


# --- _find_code_by_keyword ---

def test_find_code_by_keyword_matches():
    code_map = {"01": "前年比【％】", "02": "指数"}
    assert mhlw_wage_service._find_code_by_keyword(code_map, "前年比") == "01"


def test_find_code_by_keyword_no_match():
    code_map = {"01": "指数", "02": "前年比"}
    assert mhlw_wage_service._find_code_by_keyword(code_map, "存在しない") is None


def test_find_code_by_keyword_empty():
    assert mhlw_wage_service._find_code_by_keyword({}, "前年比") is None


# --- _parse_meta_response ---

def test_parse_meta_response_returns_correct_codes():
    result = mhlw_wage_service._parse_meta_response(SAMPLE_META_RESPONSE)
    assert result["tab"] == "02"
    assert result["cat01"] == "01"
    assert result["cat02"] == "00"
    assert result["cat03"] == "01"


def test_parse_meta_response_raises_on_invalid_structure():
    with pytest.raises(FetchError):
        mhlw_wage_service._parse_meta_response({"unexpected": "structure"})


def test_parse_meta_response_raises_when_code_not_found():
    meta = {
        "GET_META_INFO": {
            "METADATA_INF": {
                "CLASS_INF": {
                    "CLASS_OBJ": [
                        {
                            "@id": "tab",
                            "CLASS": [{"@code": "01", "@name": "指数のみ"}],
                        },
                        {"@id": "cat01", "CLASS": [{"@code": "01", "@name": "就業形態計"}]},
                        {"@id": "cat02", "CLASS": [{"@code": "00", "@name": "産業計"}]},
                        {"@id": "cat03", "CLASS": [{"@code": "01", "@name": "5人以上"}]},
                    ]
                }
            }
        }
    }
    with pytest.raises(FetchError, match="tab"):
        mhlw_wage_service._parse_meta_response(meta)


def test_parse_meta_response_handles_single_class_obj_as_dict():
    meta = {
        "GET_META_INFO": {
            "METADATA_INF": {
                "CLASS_INF": {
                    "CLASS_OBJ": {
                        "@id": "tab",
                        "CLASS": [
                            {"@code": "01", "@name": "指数"},
                            {"@code": "02", "@name": "前年比【％】"},
                        ],
                    }
                }
            }
        }
    }
    # cat01/cat02/cat03 がない場合 FetchError になる（missing codes）
    with pytest.raises(FetchError):
        mhlw_wage_service._parse_meta_response(meta)


# --- _parse_time_code ---

def test_parse_time_code_standard():
    assert mhlw_wage_service._parse_time_code("2025001212") == "2025-12"


def test_parse_time_code_january():
    assert mhlw_wage_service._parse_time_code("2026000101") == "2026-01"


# --- _parse_data_response ---

def test_parse_data_response_returns_sorted_records():
    result = mhlw_wage_service._parse_data_response(SAMPLE_DATA_RESPONSE)
    assert len(result) == 3
    assert result[0]["date"] == "2025-10"
    assert result[2]["date"] == "2025-12"
    assert result[2]["value"] == 2.1


def test_parse_data_response_skips_invalid_values():
    data = {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": [
                        {"@time": "2025001212", "$": "2.1"},
                        {"@time": "2025001111", "$": "-"},
                        {"@time": "2025001010", "$": "***"},
                        {"@time": "", "$": "3.0"},
                    ]
                }
            }
        }
    }
    result = mhlw_wage_service._parse_data_response(data)
    assert len(result) == 1
    assert result[0]["value"] == 2.1


def test_parse_data_response_handles_single_value_as_dict():
    data = {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": {"@time": "2025001212", "$": "2.1"}
                }
            }
        }
    }
    result = mhlw_wage_service._parse_data_response(data)
    assert len(result) == 1
    assert result[0]["value"] == 2.1


def test_parse_data_response_raises_on_invalid_structure():
    with pytest.raises(FetchError):
        mhlw_wage_service._parse_data_response({"unexpected": "structure"})


# --- fetch_scheduled_wage_yoy ---

def test_fetch_scheduled_wage_yoy_success():
    mock_meta = MagicMock()
    mock_meta.json.return_value = SAMPLE_META_RESPONSE
    mock_meta.raise_for_status.return_value = None

    mock_data = MagicMock()
    mock_data.json.return_value = SAMPLE_DATA_RESPONSE
    mock_data.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[mock_meta, mock_data]):
        result = mhlw_wage_service.fetch_scheduled_wage_yoy("dummy_key")

    assert len(result) == 3
    assert result[-1]["date"] == "2025-12"
    assert result[-1]["value"] == 2.1


def test_fetch_scheduled_wage_yoy_retries_on_meta_failure():
    import requests as req

    mock_meta = MagicMock()
    mock_meta.json.return_value = SAMPLE_META_RESPONSE
    mock_meta.raise_for_status.return_value = None

    mock_data = MagicMock()
    mock_data.json.return_value = SAMPLE_DATA_RESPONSE
    mock_data.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[req.RequestException("timeout"), mock_meta, mock_data]) as mock_get:
        with patch("time.sleep"):
            result = mhlw_wage_service.fetch_scheduled_wage_yoy("dummy_key")

    assert mock_get.call_count == 3
    assert len(result) == 3


def test_fetch_scheduled_wage_yoy_raises_after_max_retries():
    import requests as req
    with patch("requests.get", side_effect=req.RequestException("timeout")):
        with patch("time.sleep"):
            with pytest.raises(FetchError):
                mhlw_wage_service.fetch_scheduled_wage_yoy("dummy_key")


# --- save_scheduled_wage ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_save_scheduled_wage_creates_table_and_saves(db_conn):
    records = [
        {"date": "2025-11", "value": 2.5},
        {"date": "2025-12", "value": 2.1},
    ]
    count = mhlw_wage_service.save_scheduled_wage(db_conn, records)
    assert count == 2

    rows = db_conn.execute(
        "SELECT date, indicator, value, unit FROM economic_data ORDER BY date"
    ).fetchall()
    assert rows[0] == ("2025-11", "scheduled_wage_yoy", 2.5, "%")
    assert rows[1] == ("2025-12", "scheduled_wage_yoy", 2.1, "%")


def test_save_scheduled_wage_overwrites_duplicate(db_conn):
    records = [{"date": "2025-12", "value": 2.1}]
    mhlw_wage_service.save_scheduled_wage(db_conn, records)

    updated = [{"date": "2025-12", "value": 2.3}]
    mhlw_wage_service.save_scheduled_wage(db_conn, updated)

    rows = db_conn.execute(
        "SELECT value FROM economic_data WHERE date='2025-12' AND indicator='scheduled_wage_yoy'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 2.3


def test_save_scheduled_wage_coexists_with_gdp_gap(db_conn):
    db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS economic_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
    db_conn.execute(
        "INSERT INTO economic_data VALUES ('2025-Q4', 'gdp_gap', 0.1, '%')"
    )

    records = [{"date": "2025-12", "value": 2.1}]
    mhlw_wage_service.save_scheduled_wage(db_conn, records)

    rows = db_conn.execute("SELECT indicator FROM economic_data ORDER BY indicator").fetchall()
    indicators = [r[0] for r in rows]
    assert "gdp_gap" in indicators
    assert "scheduled_wage_yoy" in indicators


def test_save_scheduled_wage_empty_records(db_conn):
    count = mhlw_wage_service.save_scheduled_wage(db_conn, [])
    assert count == 0
