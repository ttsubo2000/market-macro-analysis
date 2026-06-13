import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import bei_service
from market_macro_analysis.exceptions import FetchError, DataStoreError


# --- サンプル HTML ---

SAMPLE_HTML = """
<html><body>
<table>
  <tr><th>日付</th><th>BEI</th></tr>
  <tr><td>2026/05/29</td><td>2.172</td></tr>
  <tr><td>2026/05/28</td><td>2.208</td></tr>
  <tr><td>2026/05/27</td><td>2.245</td></tr>
</table>
</body></html>
""".encode("utf-8")

SAMPLE_HTML_SINGLE = """
<html><body>
<table>
  <tr><td>2026/05/29</td><td>2.172</td></tr>
</table>
</body></html>
""".encode("utf-8")

SAMPLE_HTML_NO_DATA = """
<html><body><p>データなし</p></body></html>
""".encode("utf-8")


# --- _parse_date ---

def test_parse_date_normal():
    assert bei_service._parse_date("2026/05/29") == "2026-05-29"


def test_parse_date_single_digit():
    assert bei_service._parse_date("2026/01/05") == "2026-01-05"


def test_parse_date_invalid_format():
    assert bei_service._parse_date("2026-05") is None


def test_parse_date_non_digit():
    assert bei_service._parse_date("YYYY/MM/DD") is None


def test_parse_date_wrong_year_length():
    assert bei_service._parse_date("26/05/29") is None


# --- _parse_html ---

def test_parse_html_extracts_all_rows():
    result = bei_service._parse_html(SAMPLE_HTML)
    assert len(result) == 3


def test_parse_html_sorted_by_date():
    result = bei_service._parse_html(SAMPLE_HTML)
    assert result[0]["date"] == "2026-05-27"
    assert result[-1]["date"] == "2026-05-29"


def test_parse_html_correct_values():
    result = bei_service._parse_html(SAMPLE_HTML)
    latest = [r for r in result if r["date"] == "2026-05-29"][0]
    assert latest["value"] == pytest.approx(2.172)


def test_parse_html_empty_returns_empty():
    result = bei_service._parse_html(SAMPLE_HTML_NO_DATA)
    assert result == []


def test_parse_html_single_row():
    result = bei_service._parse_html(SAMPLE_HTML_SINGLE)
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-29"
    assert result[0]["value"] == pytest.approx(2.172)


# --- fetch_bei ---

def test_fetch_bei_success():
    mock_response = MagicMock()
    mock_response.content = SAMPLE_HTML
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        result = bei_service.fetch_bei()

    assert len(result) == 3
    assert result[-1]["date"] == "2026-05-29"


def test_fetch_bei_retries_on_failure():
    import requests as req
    mock_ok = MagicMock()
    mock_ok.content = SAMPLE_HTML
    mock_ok.raise_for_status.return_value = None

    with patch("requests.get", side_effect=[req.RequestException("timeout"), mock_ok]) as mock_get:
        with patch("time.sleep"):
            result = bei_service.fetch_bei()

    assert mock_get.call_count == 2
    assert len(result) == 3


def test_fetch_bei_raises_after_max_retries():
    import requests as req
    with patch("requests.get", side_effect=req.RequestException("timeout")):
        with patch("time.sleep"):
            with pytest.raises(FetchError):
                bei_service.fetch_bei()


# --- save_bei ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_save_bei_creates_table_and_saves(db_conn):
    records = [
        {"date": "2026-05-28", "value": 2.208},
        {"date": "2026-05-29", "value": 2.172},
    ]
    count = bei_service.save_bei(db_conn, records)
    assert count == 2

    rows = db_conn.execute(
        "SELECT date, indicator, value, unit FROM financial_data ORDER BY date"
    ).fetchall()
    assert rows[0] == ("2026-05-28", "bei", 2.208, "%")
    assert rows[1] == ("2026-05-29", "bei", 2.172, "%")


def test_save_bei_idempotent_upsert(db_conn):
    """同一日付を2回保存しても1レコードにとどまる（冪等性）。"""
    records = [{"date": "2026-05-29", "value": 2.200}]
    bei_service.save_bei(db_conn, records)

    updated = [{"date": "2026-05-29", "value": 2.172}]
    bei_service.save_bei(db_conn, updated)

    rows = db_conn.execute(
        "SELECT value FROM financial_data WHERE date='2026-05-29' AND indicator='bei'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == pytest.approx(2.172)


def test_save_bei_empty_records_returns_zero(db_conn):
    """空リストを渡しても正常終了し 0 を返す（冪等性）。"""
    count = bei_service.save_bei(db_conn, [])
    assert count == 0


def test_save_bei_coexists_with_policy_rate(db_conn):
    """既存の policy_rate データと共存できる。"""
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
        "INSERT INTO financial_data VALUES ('2026-05', 'policy_rate', 0.5, '%')"
    )
    records = [{"date": "2026-05-29", "value": 2.172}]
    bei_service.save_bei(db_conn, records)

    rows = db_conn.execute("SELECT indicator FROM financial_data ORDER BY indicator").fetchall()
    indicators = [r[0] for r in rows]
    assert "policy_rate" in indicators
    assert "bei" in indicators
