import sqlite3
import pytest
from pathlib import Path
from market_macro_analysis.service import chart_service
from market_macro_analysis.exceptions import ChartError


# --- フィクスチャ ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def db_with_all_data(db_conn):
    """3指標すべてのデータを投入した DB コネクション。"""
    db_conn.execute(
        "CREATE TABLE price_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE financial_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE economic_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    # コアCPI（月次）
    db_conn.executemany(
        "INSERT INTO price_data VALUES (?, 'core_cpi_yoy', ?, '%')",
        [("2023-01", 4.2), ("2023-06", 3.3), ("2024-01", 2.5), ("2024-12", 3.5)],
    )
    # 政策金利（月次）
    db_conn.executemany(
        "INSERT INTO financial_data VALUES (?, 'policy_rate', ?, '%')",
        [("2023-01", 0.0), ("2023-06", 0.0), ("2024-01", 0.1), ("2024-12", 0.25)],
    )
    # GDPギャップ（四半期）
    db_conn.executemany(
        "INSERT INTO economic_data VALUES (?, 'gdp_gap', ?, '%')",
        [("2023-Q1", -1.5), ("2023-Q3", -0.5), ("2024-Q1", -0.9), ("2024-Q4", 0.1)],
    )
    return db_conn


@pytest.fixture
def empty_tables(db_conn):
    """テーブルはあるがデータが空の DB。"""
    db_conn.execute(
        "CREATE TABLE price_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE financial_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE economic_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    return db_conn


# --- _load_monthly ---

def test_load_monthly_returns_dates_and_values(db_with_all_data):
    dates, values = chart_service._load_monthly(db_with_all_data, "price_data", "core_cpi_yoy")
    assert len(dates) == 4
    assert values[0] == 4.2
    assert values[-1] == 3.5


def test_load_monthly_returns_empty_for_no_data(empty_tables):
    dates, values = chart_service._load_monthly(empty_tables, "price_data", "core_cpi_yoy")
    assert dates == []
    assert values == []


# --- _load_quarterly ---

def test_load_quarterly_returns_dates_and_values(db_with_all_data):
    dates, values = chart_service._load_quarterly(db_with_all_data, "economic_data", "gdp_gap")
    assert len(dates) == 4
    assert values[0] == -1.5
    assert values[-1] == 0.1


def test_load_quarterly_converts_q_to_month(db_with_all_data):
    dates, values = chart_service._load_quarterly(db_with_all_data, "economic_data", "gdp_gap")
    # Q1 → 1月, Q3 → 7月
    assert dates[0].month == 1
    assert dates[1].month == 7


# --- make_cpi_chart ---

def test_make_cpi_chart_creates_file(db_with_all_data, tmp_path):
    filepath = chart_service.make_cpi_chart(db_with_all_data, output_dir=str(tmp_path))
    assert Path(filepath).exists()
    assert filepath.endswith("cpi_chart.png")


def test_make_cpi_chart_raises_when_no_data(empty_tables, tmp_path):
    with pytest.raises(ChartError):
        chart_service.make_cpi_chart(empty_tables, output_dir=str(tmp_path))


# --- make_policy_rate_chart ---

def test_make_policy_rate_chart_creates_file(db_with_all_data, tmp_path):
    filepath = chart_service.make_policy_rate_chart(db_with_all_data, output_dir=str(tmp_path))
    assert Path(filepath).exists()
    assert filepath.endswith("policy_rate_chart.png")


def test_make_policy_rate_chart_raises_when_no_data(empty_tables, tmp_path):
    with pytest.raises(ChartError):
        chart_service.make_policy_rate_chart(empty_tables, output_dir=str(tmp_path))


# --- make_gdp_gap_chart ---

def test_make_gdp_gap_chart_creates_file(db_with_all_data, tmp_path):
    filepath = chart_service.make_gdp_gap_chart(db_with_all_data, output_dir=str(tmp_path))
    assert Path(filepath).exists()
    assert filepath.endswith("gdp_gap_chart.png")


def test_make_gdp_gap_chart_raises_when_no_data(empty_tables, tmp_path):
    with pytest.raises(ChartError):
        chart_service.make_gdp_gap_chart(empty_tables, output_dir=str(tmp_path))


# --- make_combined_chart ---

def test_make_combined_chart_creates_file(db_with_all_data, tmp_path):
    filepath = chart_service.make_combined_chart(db_with_all_data, output_dir=str(tmp_path))
    assert Path(filepath).exists()
    assert filepath.endswith("combined_chart.png")


def test_make_combined_chart_raises_when_all_empty(empty_tables, tmp_path):
    with pytest.raises(ChartError):
        chart_service.make_combined_chart(empty_tables, output_dir=str(tmp_path))


def test_make_combined_chart_partial_data(db_conn, tmp_path):
    """一部指標だけでも統合チャートが生成できる。"""
    db_conn.execute(
        "CREATE TABLE price_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE financial_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE economic_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute("INSERT INTO price_data VALUES ('2024-01', 'core_cpi_yoy', 2.5, '%')")
    filepath = chart_service.make_combined_chart(db_conn, output_dir=str(tmp_path))
    assert Path(filepath).exists()


def test_make_combined_chart_creates_output_dir(db_with_all_data, tmp_path):
    """出力ディレクトリが存在しない場合でも自動作成される。"""
    nested = str(tmp_path / "nested" / "dir")
    filepath = chart_service.make_combined_chart(db_with_all_data, output_dir=nested)
    assert Path(filepath).exists()
