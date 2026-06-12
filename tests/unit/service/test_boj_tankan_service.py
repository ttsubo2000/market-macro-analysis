import io
import sqlite3
import zipfile
import pytest
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import boj_tankan_service
from market_macro_analysis.exceptions import FetchError, DataStoreError


# --- サンプルCSV データ ---

SAMPLE_CSV_ROWS = "\n".join([
    "TK99F0000201HCQ00000,Q,202601,3.1",
    "TK99F0000201HCQ01000,Q,202601,2.5",
    "TK99F0000201HCQ02000,Q,202601,2.7",
    "TK99F9999999AAA00000,Q,202601,99.9",   # 別系列（スキップされる）
    "TK99F0000201HCQ00000,FY,2025,148.0",  # FY は非四半期（スキップ）
])

SAMPLE_CSV_MULTI = "\n".join([
    "TK99F0000201HCQ00000,Q,202510,2.8",
    "TK99F0000201HCQ00000,Q,202601,3.1",
])


def _make_zip(csv_text: str) -> bytes:
    """テスト用 co.zip バイト列を生成する。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("co.csv", csv_text.encode("cp932"))
    return buf.getvalue()


# --- _parse_quarter ---

def test_parse_quarter_q1():
    assert boj_tankan_service._parse_quarter("202601") == "2026-Q1"


def test_parse_quarter_q2():
    assert boj_tankan_service._parse_quarter("202504") == "2025-Q2"


def test_parse_quarter_q3():
    assert boj_tankan_service._parse_quarter("202507") == "2025-Q3"


def test_parse_quarter_q4():
    assert boj_tankan_service._parse_quarter("202510") == "2025-Q4"


def test_parse_quarter_invalid_length():
    assert boj_tankan_service._parse_quarter("2025") is None


def test_parse_quarter_unknown_month():
    assert boj_tankan_service._parse_quarter("202603") is None


def test_parse_quarter_non_digit():
    assert boj_tankan_service._parse_quarter("20XX01") is None


# --- _parse_csv ---

def test_parse_csv_extracts_target_series():
    result = boj_tankan_service._parse_csv(SAMPLE_CSV_ROWS.encode("cp932"))
    assert len(result) == 1
    assert result[0]["date"] == "2026-Q1"
    assert result[0]["value"] == 3.1


def test_parse_csv_skips_non_quarterly():
    result = boj_tankan_service._parse_csv(SAMPLE_CSV_ROWS.encode("cp932"))
    # FY 行は含まれない
    assert all(r["date"].startswith("20") for r in result)
    assert len(result) == 1


def test_parse_csv_skips_other_series():
    result = boj_tankan_service._parse_csv(SAMPLE_CSV_ROWS.encode("cp932"))
    assert all(r["value"] != 99.9 for r in result)


def test_parse_csv_sorted_by_date():
    result = boj_tankan_service._parse_csv(SAMPLE_CSV_MULTI.encode("cp932"))
    assert len(result) == 2
    assert result[0]["date"] == "2025-Q4"
    assert result[1]["date"] == "2026-Q1"


def test_parse_csv_empty_value_skipped():
    csv_text = "TK99F0000201HCQ00000,Q,202601,"
    result = boj_tankan_service._parse_csv(csv_text.encode("cp932"))
    assert len(result) == 0


def test_parse_csv_dash_value_skipped():
    csv_text = "TK99F0000201HCQ00000,Q,202601,-"
    result = boj_tankan_service._parse_csv(csv_text.encode("cp932"))
    assert len(result) == 0


# --- _parse_zip ---

def test_parse_zip_success():
    zip_bytes = _make_zip(SAMPLE_CSV_ROWS)
    result = boj_tankan_service._parse_zip(zip_bytes)
    assert len(result) == 1
    assert result[0]["value"] == 3.1


def test_parse_zip_raises_on_bad_zip():
    with pytest.raises(FetchError):
        boj_tankan_service._parse_zip(b"not a zip file")


def test_parse_zip_raises_on_missing_csv():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.csv", "data")
    with pytest.raises(FetchError):
        boj_tankan_service._parse_zip(buf.getvalue())


# --- fetch_price_outlook ---

def test_fetch_price_outlook_success():
    zip_bytes = _make_zip(SAMPLE_CSV_ROWS)
    mock_response = MagicMock()
    mock_response.content = zip_bytes
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = boj_tankan_service.fetch_price_outlook()

    assert len(result) == 1
    assert result[0]["date"] == "2026-Q1"
    assert result[0]["value"] == 3.1


def test_fetch_price_outlook_retries_on_failure():
    import requests as req
    zip_bytes = _make_zip(SAMPLE_CSV_ROWS)
    mock_ok = MagicMock()
    mock_ok.content = zip_bytes
    mock_ok.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[req.RequestException("timeout"), mock_ok]) as mock_get:
        with patch("time.sleep"):
            result = boj_tankan_service.fetch_price_outlook()

    assert mock_get.call_count == 2
    assert len(result) == 1


def test_fetch_price_outlook_raises_after_max_retries():
    import requests as req
    with patch("requests.get", side_effect=req.RequestException("timeout")):
        with patch("time.sleep"):
            with pytest.raises(FetchError):
                boj_tankan_service.fetch_price_outlook()


# --- save_price_outlook ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_save_price_outlook_creates_table_and_saves(db_conn):
    records = [
        {"date": "2025-Q4", "value": 2.8},
        {"date": "2026-Q1", "value": 3.1},
    ]
    count = boj_tankan_service.save_price_outlook(db_conn, records)
    assert count == 2

    rows = db_conn.execute(
        "SELECT date, indicator, value, unit FROM financial_data ORDER BY date"
    ).fetchall()
    assert rows[0] == ("2025-Q4", "expected_inflation_1y", 2.8, "%")
    assert rows[1] == ("2026-Q1", "expected_inflation_1y", 3.1, "%")


def test_save_price_outlook_overwrites_duplicate(db_conn):
    records = [{"date": "2026-Q1", "value": 3.0}]
    boj_tankan_service.save_price_outlook(db_conn, records)

    updated = [{"date": "2026-Q1", "value": 3.1}]
    boj_tankan_service.save_price_outlook(db_conn, updated)

    rows = db_conn.execute(
        "SELECT value FROM financial_data WHERE date='2026-Q1' AND indicator='expected_inflation_1y'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3.1


def test_save_price_outlook_coexists_with_policy_rate(db_conn):
    db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
    db_conn.execute(
        "INSERT INTO financial_data VALUES ('2026-01', 'policy_rate', 0.5, '%')"
    )

    records = [{"date": "2026-Q1", "value": 3.1}]
    boj_tankan_service.save_price_outlook(db_conn, records)

    rows = db_conn.execute("SELECT indicator FROM financial_data ORDER BY indicator").fetchall()
    indicators = [r[0] for r in rows]
    assert "policy_rate" in indicators
    assert "expected_inflation_1y" in indicators


def test_save_price_outlook_empty_records(db_conn):
    count = boj_tankan_service.save_price_outlook(db_conn, [])
    assert count == 0
