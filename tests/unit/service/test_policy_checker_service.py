import sqlite3
import pytest
from market_macro_analysis.service import policy_checker_service
from market_macro_analysis.service.policy_checker_service import (
    ConditionResult,
    PolicyCheckResult,
    check_rate_hike_conditions,
    format_markdown_section,
    NATURAL_RATE,
)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE economic_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE price_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE financial_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
    yield conn
    conn.close()


def _insert(conn, table, date, indicator, value, unit="%"):
    conn.execute(
        f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?)",
        (date, indicator, value, unit),
    )


# --- _latest_value ---

def test_latest_value_returns_most_recent(db_conn):
    _insert(db_conn, "price_data", "2024-01", "core_cpi_yoy", 2.0)
    _insert(db_conn, "price_data", "2024-02", "core_cpi_yoy", 2.5)
    result = policy_checker_service._latest_value(db_conn, "price_data", "core_cpi_yoy")
    assert result == 2.5


def test_latest_value_returns_none_when_no_data(db_conn):
    result = policy_checker_service._latest_value(db_conn, "price_data", "core_cpi_yoy")
    assert result is None


# --- check_rate_hike_conditions: スコア計算 ---

def _insert_all_conditions(conn, gdp_gap, core_cpi, expected_inf, wage, policy_rate):
    _insert(conn, "economic_data", "2026-Q1", "gdp_gap", gdp_gap)
    _insert(conn, "price_data", "2026-03", "core_cpi_yoy", core_cpi)
    _insert(conn, "financial_data", "2026-Q1", "expected_inflation_1y", expected_inf)
    _insert(conn, "economic_data", "2026-03", "scheduled_wage_yoy", wage)
    _insert(conn, "financial_data", "2026-03", "policy_rate", policy_rate)


def test_all_conditions_met_score_100(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.score == 100.0
    assert result.met_count == 5
    assert result.total_count == 5


def test_no_conditions_met_score_0(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=-1.0, core_cpi=1.0, expected_inf=1.0, wage=2.0, policy_rate=3.0
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.score == 0.0
    assert result.met_count == 0


def test_three_conditions_met_score_60(db_conn):
    # GDP: ✅, CPI: ✅, 予想インフレ: ✅, 賃金: ❌, 実質金利: ❌
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=2.0, policy_rate=3.0
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.score == 60.0
    assert result.met_count == 3


# --- 個別条件の境界値 ---

def test_gdp_gap_exactly_zero_not_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.0, core_cpi=2.0, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    gdp_cond = result.conditions[0]
    assert not gdp_cond.met


def test_gdp_gap_positive_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.01, core_cpi=2.0, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.conditions[0].met


def test_core_cpi_exactly_1_5_not_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=1.5, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert not result.conditions[1].met


def test_core_cpi_above_1_5_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=1.51, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.conditions[1].met


def test_expected_inflation_exactly_1_5_not_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=1.5, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert not result.conditions[2].met


def test_wage_exactly_3_not_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=3.0, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert not result.conditions[3].met


def test_wage_above_3_met(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=3.01, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.conditions[3].met


def test_real_rate_equals_natural_rate_not_met(db_conn):
    # 実質金利 = 0.5 - 0.0 = 0.5 = NATURAL_RATE → 充足せず（< でないと）
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=0.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    real_rate_cond = result.conditions[4]
    assert not real_rate_cond.met


def test_real_rate_below_natural_rate_met(db_conn):
    # 実質金利 = 0.5 - 2.0 = -1.5 < 0.5 → 充足
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    assert result.conditions[4].met


# --- データなし時の挙動 ---

def test_missing_data_condition_not_met(db_conn):
    # データが一切ない状態 → すべての条件が met=False
    result = check_rate_hike_conditions(db_conn)
    assert result.score == 0.0
    assert all(not c.met for c in result.conditions)


def test_missing_data_value_text_is_no_data(db_conn):
    result = check_rate_hike_conditions(db_conn)
    assert all(c.value_text == "データなし" for c in result.conditions)


def test_partial_missing_data_real_rate_not_met(db_conn):
    # 政策金利のみある（予想インフレなし）→ 実質金利算出不可 → met=False
    _insert(db_conn, "financial_data", "2026-03", "policy_rate", 0.5)
    result = check_rate_hike_conditions(db_conn)
    real_rate_cond = result.conditions[4]
    assert not real_rate_cond.met
    assert real_rate_cond.value is None


# --- format_markdown_section ---

def test_format_markdown_section_contains_score(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=3.5, policy_rate=0.5
    )
    result = check_rate_hike_conditions(db_conn)
    md = format_markdown_section(result)
    assert "100%" in md
    assert "5条件中5件充足" in md


def test_format_markdown_section_has_check_marks(db_conn):
    _insert_all_conditions(db_conn,
        gdp_gap=0.5, core_cpi=2.0, expected_inf=2.0, wage=2.0, policy_rate=3.0
    )
    result = check_rate_hike_conditions(db_conn)
    md = format_markdown_section(result)
    assert "✅" in md
    assert "❌" in md


def test_format_markdown_section_has_table_header(db_conn):
    result = check_rate_hike_conditions(db_conn)
    md = format_markdown_section(result)
    assert "| 条件 | 最新値 | 閾値 | 判定 |" in md


def test_format_markdown_section_has_heading(db_conn):
    result = check_rate_hike_conditions(db_conn)
    md = format_markdown_section(result)
    assert "## 日銀政策判断チェッカー" in md


def test_format_markdown_section_all_5_conditions_listed(db_conn):
    result = check_rate_hike_conditions(db_conn)
    md = format_markdown_section(result)
    assert "GDPギャップ" in md
    assert "コアCPI" in md
    assert "予想インフレ率" in md
    assert "賃金上昇率" in md
    assert "実質金利" in md
