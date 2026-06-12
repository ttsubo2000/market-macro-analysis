import pytest
from market_macro_analysis.service import scenario_service
from market_macro_analysis.service.scenario_service import (
    SCENARIO_PRESETS,
    ScenarioPreset,
    evaluate_all_scenarios,
    format_scenario_comparison,
)


# --- SCENARIO_PRESETS 定義の確認 ---

def test_scenario_presets_has_4_entries():
    assert len(SCENARIO_PRESETS) == 4


def test_scenario_labels_are_unique():
    labels = [p.label for p in SCENARIO_PRESETS]
    assert len(set(labels)) == 4


def test_scenario_labels_contain_expected():
    labels = {p.label for p in SCENARIO_PRESETS}
    assert "baseline" in labels
    assert "optimistic" in labels
    assert "risk" in labels
    assert "stagflation" in labels


def test_scenario_names_contain_emoji():
    for preset in SCENARIO_PRESETS:
        assert any(c in preset.name for c in "🟢🔵🔴🟠")


def test_scenario_descriptions_are_non_empty():
    for preset in SCENARIO_PRESETS:
        assert len(preset.description) > 0


# --- ベースライン: 5/5 = 100% ---

def test_baseline_score_is_100():
    results = evaluate_all_scenarios()
    baseline = next(r for p, r in results if p.label == "baseline")
    assert baseline.score == 100.0
    assert baseline.met_count == 5


def test_baseline_all_conditions_met():
    results = evaluate_all_scenarios()
    baseline = next(r for p, r in results if p.label == "baseline")
    assert all(c.met for c in baseline.conditions)


# --- 楽観: 5/5 = 100% ---

def test_optimistic_score_is_100():
    results = evaluate_all_scenarios()
    optimistic = next(r for p, r in results if p.label == "optimistic")
    assert optimistic.score == 100.0


# --- リスク: 3/5 = 60% ---

def test_risk_score_is_60():
    results = evaluate_all_scenarios()
    risk = next(r for p, r in results if p.label == "risk")
    assert risk.score == 60.0
    assert risk.met_count == 3


def test_risk_gdp_gap_not_met():
    results = evaluate_all_scenarios()
    risk_result = next(r for p, r in results if p.label == "risk")
    gdp_cond = risk_result.conditions[0]
    assert not gdp_cond.met


def test_risk_wage_not_met():
    results = evaluate_all_scenarios()
    risk_result = next(r for p, r in results if p.label == "risk")
    wage_cond = risk_result.conditions[3]
    assert not wage_cond.met


# --- スタグフレーション: 3/5 = 60% ---

def test_stagflation_score_is_60():
    results = evaluate_all_scenarios()
    stagflation = next(r for p, r in results if p.label == "stagflation")
    assert stagflation.score == 60.0


def test_stagflation_gdp_gap_not_met():
    results = evaluate_all_scenarios()
    stagflation_result = next(r for p, r in results if p.label == "stagflation")
    assert not stagflation_result.conditions[0].met


def test_stagflation_wage_not_met():
    results = evaluate_all_scenarios()
    stagflation_result = next(r for p, r in results if p.label == "stagflation")
    assert not stagflation_result.conditions[3].met


# --- evaluate_all_scenarios の出力形式 ---

def test_evaluate_all_scenarios_returns_4_results():
    results = evaluate_all_scenarios()
    assert len(results) == 4


def test_evaluate_all_scenarios_returns_preset_result_pairs():
    results = evaluate_all_scenarios()
    for preset, result in results:
        assert isinstance(preset, ScenarioPreset)
        assert result.total_count == 5


def test_evaluate_all_scenarios_order_matches_presets():
    results = evaluate_all_scenarios()
    for (preset, _), expected_preset in zip(results, SCENARIO_PRESETS):
        assert preset.label == expected_preset.label


# --- format_scenario_comparison ---

def test_format_scenario_comparison_has_heading():
    results = evaluate_all_scenarios()
    md = format_scenario_comparison(results)
    assert "## シナリオ比較" in md


def test_format_scenario_comparison_has_all_scenario_names():
    results = evaluate_all_scenarios()
    md = format_scenario_comparison(results)
    assert "ベースライン" in md
    assert "楽観" in md
    assert "リスク" in md
    assert "スタグフレーション" in md


def test_format_scenario_comparison_has_scores():
    results = evaluate_all_scenarios()
    md = format_scenario_comparison(results)
    assert "100%" in md
    assert "60%" in md


def test_format_scenario_comparison_has_check_marks():
    results = evaluate_all_scenarios()
    md = format_scenario_comparison(results)
    assert "✅" in md
    assert "❌" in md


def test_format_scenario_comparison_has_prerequisite_table():
    results = evaluate_all_scenarios()
    md = format_scenario_comparison(results)
    assert "シナリオ前提条件" in md
    assert "GDPギャップ" in md


def test_format_scenario_comparison_has_evaluation_table():
    results = evaluate_all_scenarios()
    md = format_scenario_comparison(results)
    assert "利上げ確度評価" in md
