import io
import sqlite3
import pytest
import openpyxl
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import cao_gdp_service
from market_macro_analysis.exceptions import FetchError, DataStoreError


# --- テスト用 xlsx バイト生成ヘルパー ---

def _make_xlsx_bytes(data_rows: list[tuple]) -> bytes:
    """内閣府GDPギャップ xlsx のフォーマットに合わせたバイト列を生成する。

    先頭6行にヘッダーを付け、7行目以降にデータを配置する。
    """
    wb = openpyxl.Workbook()
    wb.active.title = "四半期"
    ws = wb["四半期"]

    # 6行のダミーヘッダー（実際のフォーマットに合わせる）
    for _ in range(6):
        ws.append([None])

    for row in data_rows:
        ws.append(list(row))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# 標準的なデータ（年がQ1にのみ記載）
SAMPLE_XLSX_BYTES = _make_xlsx_bytes([
    (2024, "Ⅰ", -0.9, "", 0.4),
    ("",   "Ⅱ", -0.8, "", 0.4),
    ("",   "Ⅲ", -0.3, "", 0.4),
    ("",   "Ⅳ",  0.1, "", 0.4),
    (2025, "Ⅰ",  0.3, "", 0.4),
    ("",   "Ⅱ",  0.8, "", 0.4),
])

SAMPLE_XLSX_WITH_MISSING = _make_xlsx_bytes([
    (2024, "Ⅰ", -0.9, "", 0.4),
    ("",   "Ⅱ", None, "", 0.4),   # 欠損
    ("",   "Ⅲ", "-",  "", 0.4),   # 欠損（文字列）
    ("",   "Ⅳ",  0.1, "", 0.4),
])


# --- _parse_xlsx ---

def test_parse_xlsx_returns_sorted_records():
    result = cao_gdp_service._parse_xlsx(SAMPLE_XLSX_BYTES)
    assert len(result) == 6
    assert result[0]["date"] == "2024-Q1"
    assert result[5]["date"] == "2025-Q2"


def test_parse_xlsx_uses_correct_values():
    result = cao_gdp_service._parse_xlsx(SAMPLE_XLSX_BYTES)
    assert result[0]["value"] == -0.9   # 2024-Q1
    assert result[3]["value"] ==  0.1   # 2024-Q4


def test_parse_xlsx_carries_forward_year():
    result = cao_gdp_service._parse_xlsx(SAMPLE_XLSX_BYTES)
    # Q2-Q4 も正しく年が設定されている
    dates = [r["date"] for r in result]
    assert "2024-Q2" in dates
    assert "2024-Q3" in dates
    assert "2024-Q4" in dates


def test_parse_xlsx_skips_missing_values():
    result = cao_gdp_service._parse_xlsx(SAMPLE_XLSX_WITH_MISSING)
    assert len(result) == 2
    assert result[0]["date"] == "2024-Q1"
    assert result[1]["date"] == "2024-Q4"


def test_parse_xlsx_raises_on_invalid_content():
    with pytest.raises(FetchError):
        cao_gdp_service._parse_xlsx(b"this is not xlsx content")


def test_parse_xlsx_handles_none_year_in_first_q1():
    # 年が None の場合はスキップ
    xlsx_bytes = _make_xlsx_bytes([
        (None, "Ⅰ", -0.9, "", 0.4),
        (2025, "Ⅱ",  0.8, "", 0.4),
    ])
    result = cao_gdp_service._parse_xlsx(xlsx_bytes)
    assert len(result) == 1
    assert result[0]["date"] == "2025-Q2"


_MOCK_GAP_URL = "https://www.cao.go.jp/keizai3/getsurei/2612gap.xlsx"
_MOCK_INDEX_HTML = '<a href="/keizai3/getsurei/2612gap.xlsx">GDPギャップ</a>'


# --- _resolve_latest_gap_url ---

def test_resolve_latest_gap_url_success():
    mock_response = MagicMock()
    mock_response.text = _MOCK_INDEX_HTML
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        url = cao_gdp_service._resolve_latest_gap_url()

    assert url == _MOCK_GAP_URL


def test_resolve_latest_gap_url_raises_when_no_link():
    mock_response = MagicMock()
    mock_response.text = "<html>no gap link here</html>"
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(FetchError):
            cao_gdp_service._resolve_latest_gap_url()


def test_resolve_latest_gap_url_raises_on_http_error():
    import requests as req
    with patch("requests.get", side_effect=req.RequestException("connection error")):
        with pytest.raises(FetchError):
            cao_gdp_service._resolve_latest_gap_url()


# --- fetch_gdp_gap ---

def test_fetch_gdp_gap_success():
    mock_response = MagicMock()
    mock_response.content = SAMPLE_XLSX_BYTES
    mock_response.raise_for_status.return_value = None

    with patch("market_macro_analysis.service.cao_gdp_service._resolve_latest_gap_url", return_value=_MOCK_GAP_URL):
        with patch("requests.get", return_value=mock_response):
            result = cao_gdp_service.fetch_gdp_gap()

    assert len(result) == 6
    assert result[-1]["date"] == "2025-Q2"
    assert result[-1]["value"] == 0.8


def test_fetch_gdp_gap_respects_limit():
    mock_response = MagicMock()
    mock_response.content = SAMPLE_XLSX_BYTES
    mock_response.raise_for_status.return_value = None

    with patch("market_macro_analysis.service.cao_gdp_service._resolve_latest_gap_url", return_value=_MOCK_GAP_URL):
        with patch("requests.get", return_value=mock_response):
            result = cao_gdp_service.fetch_gdp_gap(limit=3)

    assert len(result) == 3
    assert result[-1]["date"] == "2025-Q2"


def test_fetch_gdp_gap_retries_on_failure():
    import requests as req
    mock_ok = MagicMock()
    mock_ok.content = SAMPLE_XLSX_BYTES
    mock_ok.raise_for_status.return_value = None

    with patch("market_macro_analysis.service.cao_gdp_service._resolve_latest_gap_url", return_value=_MOCK_GAP_URL):
        with patch("requests.get", side_effect=[req.RequestException("timeout"), mock_ok]) as mock_get:
            with patch("time.sleep"):
                result = cao_gdp_service.fetch_gdp_gap()

    assert mock_get.call_count == 2
    assert len(result) == 6


def test_fetch_gdp_gap_raises_after_max_retries():
    import requests as req
    with patch("market_macro_analysis.service.cao_gdp_service._resolve_latest_gap_url", return_value=_MOCK_GAP_URL):
        with patch("requests.get", side_effect=req.RequestException("timeout")):
            with patch("time.sleep"):
                with pytest.raises(FetchError):
                    cao_gdp_service.fetch_gdp_gap()


# --- save_gdp_gap ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_save_gdp_gap_creates_table_and_saves(db_conn):
    records = [
        {"date": "2024-Q3", "value": -0.3},
        {"date": "2024-Q4", "value":  0.1},
    ]
    count = cao_gdp_service.save_gdp_gap(db_conn, records)
    assert count == 2

    rows = db_conn.execute(
        "SELECT date, indicator, value, unit FROM economic_data ORDER BY date"
    ).fetchall()
    assert rows[0] == ("2024-Q3", "gdp_gap", -0.3, "%")
    assert rows[1] == ("2024-Q4", "gdp_gap",  0.1, "%")


def test_save_gdp_gap_overwrites_duplicate(db_conn):
    records = [{"date": "2024-Q4", "value": 0.1}]
    cao_gdp_service.save_gdp_gap(db_conn, records)

    updated = [{"date": "2024-Q4", "value": 0.2}]
    cao_gdp_service.save_gdp_gap(db_conn, updated)

    rows = db_conn.execute(
        "SELECT value FROM economic_data WHERE date='2024-Q4'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0.2


def test_save_gdp_gap_empty_records(db_conn):
    count = cao_gdp_service.save_gdp_gap(db_conn, [])
    assert count == 0
