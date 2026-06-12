import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from market_macro_analysis.service import forecast_chart_service
from market_macro_analysis.service.forecast_chart_service import (
    RATE_HIKE_STEP,
    FORECAST_MONTHS,
    months_to_hike,
    format_forecast_summary,
)
from market_macro_analysis.service.policy_checker_service import (
    PolicyCheckResult,
    ConditionResult,
)
from market_macro_analysis.service.scenario_service import evaluate_all_scenarios


# --- months_to_hike ---

def test_months_to_hike_score_100():
    assert months_to_hike(100.0) == 6


def test_months_to_hike_score_80():
    assert months_to_hike(80.0) == 9


def test_months_to_hike_score_79():
    assert months_to_hike(79.9) == 12


def test_months_to_hike_score_60():
    assert months_to_hike(60.0) == 12


def test_months_to_hike_score_59():
    assert months_to_hike(59.9) == 18


def test_months_to_hike_score_40():
    assert months_to_hike(40.0) == 18


def test_months_to_hike_score_39():
    assert months_to_hike(39.9) == 24


def test_months_to_hike_score_20():
    assert months_to_hike(20.0) == 24


def test_months_to_hike_score_19():
    assert months_to_hike(19.9) is None


def test_months_to_hike_score_0():
    assert months_to_hike(0.0) is None


# --- _add_months ---

def test_add_months_normal():
    from datetime import datetime
    dt = datetime(2026, 1, 1)
    result = forecast_chart_service._add_months(dt, 3)
    assert result.year == 2026
    assert result.month == 4


def test_add_months_year_wrap():
    from datetime import datetime
    dt = datetime(2026, 11, 1)
    result = forecast_chart_service._add_months(dt, 3)
    assert result.year == 2027
    assert result.month == 2


def test_add_months_zero():
    from datetime import datetime
    dt = datetime(2026, 6, 1)
    result = forecast_chart_service._add_months(dt, 0)
    assert result == dt


# --- _build_path ---

def test_build_path_with_hike():
    dates, rates = forecast_chart_service._build_path(0.5, 6)
    assert len(dates) == FORECAST_MONTHS + 1
    assert rates[5] == 0.5
    assert rates[6] == pytest.approx(0.5 + RATE_HIKE_STEP)
    assert rates[-1] == pytest.approx(0.5 + RATE_HIKE_STEP)


def test_build_path_no_hike():
    dates, rates = forecast_chart_service._build_path(0.5, None)
    assert all(r == 0.5 for r in rates)


def test_build_path_length():
    dates, rates = forecast_chart_service._build_path(0.25, 12)
    assert len(dates) == len(rates) == FORECAST_MONTHS + 1


# --- format_forecast_summary ---

def _make_policy_result(score: float, met_count: int) -> PolicyCheckResult:
    conditions = [
        ConditionResult(name=f"cond{i}", met=(i < met_count),
                        value=None, threshold_desc="", value_text="")
        for i in range(5)
    ]
    return PolicyCheckResult(conditions=conditions, score=score,
                             met_count=met_count, total_count=5)


def test_format_forecast_summary_has_heading():
    policy_result = _make_policy_result(100.0, 5)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert "## 政策金利パス予測" in md


def test_format_forecast_summary_shows_current_rate():
    policy_result = _make_policy_result(60.0, 3)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert "0.50%" in md


def test_format_forecast_summary_shows_score():
    policy_result = _make_policy_result(60.0, 3)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert "60%" in md


def test_format_forecast_summary_shows_next_rate():
    policy_result = _make_policy_result(100.0, 5)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert f"{0.5 + RATE_HIKE_STEP:.2f}%" in md


def test_format_forecast_summary_has_timing_table():
    policy_result = _make_policy_result(100.0, 5)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert "次回利上げタイミング試算" in md
    assert "ヶ月以内" in md


def test_format_forecast_summary_no_hike_when_score_zero():
    policy_result = _make_policy_result(0.0, 0)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert "見込みなし" in md


def test_format_forecast_summary_all_scenarios_listed():
    policy_result = _make_policy_result(100.0, 5)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, 0.5)
    assert "ベースライン" in md
    assert "楽観" in md
    assert "リスク" in md
    assert "スタグフレーション" in md


def test_format_forecast_summary_none_current_rate():
    policy_result = _make_policy_result(60.0, 3)
    scenario_results = evaluate_all_scenarios()
    md = format_forecast_summary(policy_result, scenario_results, None)
    assert "不明" in md


# --- make_policy_rate_forecast_chart ---

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE financial_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
    """)
    conn.execute("""
        CREATE TABLE economic_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
    """)
    conn.execute("""
        CREATE TABLE price_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
    """)
    conn.execute("INSERT INTO financial_data VALUES ('2026-03', 'policy_rate', 0.5, '%')")
    conn.execute("INSERT INTO financial_data VALUES ('2026-Q1', 'expected_inflation_1y', 2.0, '%')")
    conn.execute("INSERT INTO economic_data VALUES ('2026-Q1', 'gdp_gap', 0.3, '%')")
    conn.execute("INSERT INTO economic_data VALUES ('2026-03', 'scheduled_wage_yoy', 3.5, '%')")
    conn.execute("INSERT INTO price_data VALUES ('2026-03', 'core_cpi_yoy', 2.0, '%')")
    yield conn
    conn.close()


def test_make_policy_rate_forecast_chart_returns_path(db_conn, tmp_path):
    path = forecast_chart_service.make_policy_rate_forecast_chart(
        db_conn, output_dir=str(tmp_path)
    )
    assert path.endswith("policy_rate_forecast.png")
    from pathlib import Path
    assert Path(path).exists()


def test_make_policy_rate_forecast_chart_raises_without_rate(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE financial_data (
            date TEXT NOT NULL, indicator TEXT NOT NULL,
            value REAL NOT NULL, unit TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
    """)
    from market_macro_analysis.exceptions import ChartError
    with pytest.raises(ChartError):
        forecast_chart_service.make_policy_rate_forecast_chart(conn, str(tmp_path))
    conn.close()
