import sqlite3
import pytest
from pathlib import Path
from market_macro_analysis.service import report_service
from market_macro_analysis.exceptions import ReportError


# --- フィクスチャ ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def db_with_all_data(db_conn):
    db_conn.execute(
        "CREATE TABLE price_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE financial_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE economic_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.executemany(
        "INSERT INTO price_data VALUES (?, 'core_cpi_yoy', ?, '%')",
        [("2024-11", 2.7), ("2024-12", 3.0)],
    )
    db_conn.executemany(
        "INSERT INTO financial_data VALUES (?, 'policy_rate', ?, '%')",
        [("2024-11", 0.25), ("2024-12", 0.50)],
    )
    db_conn.executemany(
        "INSERT INTO economic_data VALUES (?, 'gdp_gap', ?, '%')",
        [("2024-Q3", -0.3), ("2024-Q4", 0.1)],
    )
    return db_conn


@pytest.fixture
def empty_tables(db_conn):
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


# --- evaluate_cpi ---

def test_evaluate_cpi_green():
    assert report_service.evaluate_cpi(2.0) == "🟢"
    assert report_service.evaluate_cpi(1.5) == "🟢"
    assert report_service.evaluate_cpi(2.5) == "🟢"


def test_evaluate_cpi_yellow():
    assert report_service.evaluate_cpi(2.6) == "🟡"
    assert report_service.evaluate_cpi(4.0) == "🟡"


def test_evaluate_cpi_red():
    assert report_service.evaluate_cpi(1.4) == "🔴"
    assert report_service.evaluate_cpi(0.0) == "🔴"


# --- evaluate_policy_rate ---

def test_evaluate_policy_rate_green():
    assert report_service.evaluate_policy_rate(0.0) == "🟢"
    assert report_service.evaluate_policy_rate(0.25) == "🟢"
    assert report_service.evaluate_policy_rate(0.5) == "🟢"


def test_evaluate_policy_rate_yellow():
    assert report_service.evaluate_policy_rate(0.75) == "🟡"
    assert report_service.evaluate_policy_rate(1.0) == "🟡"


def test_evaluate_policy_rate_red():
    assert report_service.evaluate_policy_rate(-0.1) == "🔴"


# --- evaluate_gdp_gap ---

def test_evaluate_gdp_gap_green():
    assert report_service.evaluate_gdp_gap(0.1) == "🟢"
    assert report_service.evaluate_gdp_gap(1.0) == "🟢"


def test_evaluate_gdp_gap_yellow():
    assert report_service.evaluate_gdp_gap(0.0) == "🟡"
    assert report_service.evaluate_gdp_gap(-0.5) == "🟡"


def test_evaluate_gdp_gap_red():
    assert report_service.evaluate_gdp_gap(-0.6) == "🔴"
    assert report_service.evaluate_gdp_gap(-2.0) == "🔴"


# --- _direction ---

def test_direction_increase():
    result = report_service._direction(3.0, 2.7)
    assert result.startswith("▲")
    assert "0.30" in result


def test_direction_decrease():
    result = report_service._direction(2.4, 3.0)
    assert result.startswith("▼")
    assert "0.60" in result


def test_direction_no_change():
    result = report_service._direction(2.4, 2.4)
    assert result == "→ 0.00"


def test_direction_no_previous():
    result = report_service._direction(2.4, None)
    assert result == "―"


# --- generate_summary ---

def test_generate_summary_creates_file(db_with_all_data, tmp_path):
    filepath = report_service.generate_summary(db_with_all_data, output_dir=str(tmp_path))
    assert Path(filepath).exists()
    assert filepath.endswith("summary.md")


def test_generate_summary_content(db_with_all_data, tmp_path):
    filepath = report_service.generate_summary(db_with_all_data, output_dir=str(tmp_path))
    content = Path(filepath).read_text(encoding="utf-8")
    assert "コアCPI" in content
    assert "政策金利" in content
    assert "需給ギャップ" in content
    assert "🟡" in content or "🟢" in content or "🔴" in content


def test_generate_summary_shows_latest_date(db_with_all_data, tmp_path):
    filepath = report_service.generate_summary(db_with_all_data, output_dir=str(tmp_path))
    content = Path(filepath).read_text(encoding="utf-8")
    assert "2024-12" in content   # CPI最新
    assert "2024-Q4" in content   # GDPギャップ最新


def test_generate_summary_raises_when_all_empty(empty_tables, tmp_path):
    with pytest.raises(ReportError):
        report_service.generate_summary(empty_tables, output_dir=str(tmp_path))


def test_generate_summary_creates_output_dir(db_with_all_data, tmp_path):
    nested = str(tmp_path / "nested" / "report")
    filepath = report_service.generate_summary(db_with_all_data, output_dir=nested)
    assert Path(filepath).exists()


def test_generate_summary_partial_data(db_conn, tmp_path):
    """一部データのみでもレポートが生成できる。"""
    db_conn.execute(
        "CREATE TABLE price_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE financial_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute(
        "CREATE TABLE economic_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.execute("INSERT INTO price_data VALUES ('2024-12', 'core_cpi_yoy', 3.0, '%')")
    filepath = report_service.generate_summary(db_conn, output_dir=str(tmp_path))
    content = Path(filepath).read_text(encoding="utf-8")
    assert "3.0%" in content
    assert "データなし" in content
