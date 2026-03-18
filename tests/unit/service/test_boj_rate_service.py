import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import boj_rate_service
from market_macro_analysis.exceptions import FetchError, DataStoreError


# --- _parse_csv ---

# 日銀CSV の典型的なフォーマット（cp932, YYYY/MM 形式）
SAMPLE_CSV_BYTES = (
    "無担保コールレート（翌日物）（平均）（%）\n"
    "年/月,値\n"
    "2024/10,0.230\n"
    "2024/11,0.235\n"
    "2024/12,0.240\n"
).encode("cp932")

SAMPLE_CSV_WITH_MISSING = (
    "年/月,値\n"
    "2024/10,0.230\n"
    "2024/11,-\n"
    "2024/12,\n"
    "2025/01,0.500\n"
).encode("cp932")


def test_parse_csv_returns_sorted_records():
    result = boj_rate_service._parse_csv(SAMPLE_CSV_BYTES)
    assert len(result) == 3
    assert result[0]["date"] == "2024-10"
    assert result[2]["date"] == "2024-12"
    assert result[2]["value"] == 0.240


def test_parse_csv_skips_header_lines():
    result = boj_rate_service._parse_csv(SAMPLE_CSV_BYTES)
    # ヘッダー行（年/月,値）はパース結果に含まれない
    dates = [r["date"] for r in result]
    assert "年/月" not in dates


def test_parse_csv_skips_missing_values():
    result = boj_rate_service._parse_csv(SAMPLE_CSV_WITH_MISSING)
    assert len(result) == 2
    assert result[0]["date"] == "2024-10"
    assert result[1]["date"] == "2025-01"


def test_parse_csv_handles_utf8_fallback():
    # UTF-8 エンコードの CSV でもフォールバックで処理できる
    csv_utf8 = (
        "年/月,値\n"
        "2024/10,0.230\n"
    ).encode("utf-8")
    result = boj_rate_service._parse_csv(csv_utf8)
    assert len(result) == 1
    assert result[0]["date"] == "2024-10"


def test_parse_csv_pads_single_digit_month():
    csv_bytes = "年/月,値\n2024/1,0.230\n2024/9,0.210\n".encode("cp932")
    result = boj_rate_service._parse_csv(csv_bytes)
    assert result[0]["date"] == "2024-01"
    assert result[1]["date"] == "2024-09"


def test_parse_csv_skips_nd_and_asterisk_values():
    csv_bytes = (
        "年/月,値\n"
        "2024/10,ND\n"
        "2024/11,***\n"
        "2024/12,0.240\n"
    ).encode("cp932")
    result = boj_rate_service._parse_csv(csv_bytes)
    assert len(result) == 1
    assert result[0]["value"] == 0.240


def test_parse_csv_returns_empty_for_no_data():
    csv_bytes = b"No valid data here\n"
    result = boj_rate_service._parse_csv(csv_bytes)
    assert result == []


# --- fetch_policy_rate ---

def test_fetch_policy_rate_success():
    mock_response = MagicMock()
    mock_response.content = SAMPLE_CSV_BYTES
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = boj_rate_service.fetch_policy_rate()

    assert len(result) == 3
    assert result[-1]["date"] == "2024-12"
    assert result[-1]["value"] == 0.240


def test_fetch_policy_rate_respects_limit():
    mock_response = MagicMock()
    mock_response.content = SAMPLE_CSV_BYTES
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = boj_rate_service.fetch_policy_rate(limit=2)

    assert len(result) == 2
    # limit を超えた場合は末尾（最新）から取得
    assert result[-1]["date"] == "2024-12"


def test_fetch_policy_rate_retries_on_failure():
    import requests as req
    mock_ok = MagicMock()
    mock_ok.content = SAMPLE_CSV_BYTES
    mock_ok.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[req.RequestException("timeout"), mock_ok]) as mock_get:
        with patch("time.sleep"):
            result = boj_rate_service.fetch_policy_rate()

    assert mock_get.call_count == 2
    assert len(result) == 3


def test_fetch_policy_rate_raises_after_max_retries():
    import requests as req
    with patch("requests.get", side_effect=req.RequestException("timeout")):
        with patch("time.sleep"):
            with pytest.raises(FetchError):
                boj_rate_service.fetch_policy_rate()


# --- save_policy_rate ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_save_policy_rate_creates_table_and_saves(db_conn):
    records = [
        {"date": "2024-11", "value": 0.235},
        {"date": "2024-12", "value": 0.240},
    ]
    count = boj_rate_service.save_policy_rate(db_conn, records)
    assert count == 2

    rows = db_conn.execute(
        "SELECT date, indicator, value, unit FROM financial_data ORDER BY date"
    ).fetchall()
    assert rows[0] == ("2024-11", "policy_rate", 0.235, "%")
    assert rows[1] == ("2024-12", "policy_rate", 0.240, "%")


def test_save_policy_rate_overwrites_duplicate(db_conn):
    records = [{"date": "2024-12", "value": 0.240}]
    boj_rate_service.save_policy_rate(db_conn, records)

    updated = [{"date": "2024-12", "value": 0.500}]
    boj_rate_service.save_policy_rate(db_conn, updated)

    rows = db_conn.execute(
        "SELECT value FROM financial_data WHERE date='2024-12'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0.500


def test_save_policy_rate_empty_records(db_conn):
    count = boj_rate_service.save_policy_rate(db_conn, [])
    assert count == 0
