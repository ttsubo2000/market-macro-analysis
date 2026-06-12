from dataclasses import dataclass
from market_macro_analysis.service.policy_checker_service import (
    PolicyCheckResult,
    check_conditions_from_values,
)


@dataclass
class ScenarioPreset:
    name: str           # シナリオ名（絵文字付き表示名）
    label: str          # 識別子（baseline / optimistic / risk / stagflation）
    gdp_gap: float
    core_cpi: float
    expected_inflation: float
    wage: float
    policy_rate: float
    description: str    # キー仮定の説明


SCENARIO_PRESETS: list[ScenarioPreset] = [
    ScenarioPreset(
        name="🟢 ベースライン",
        label="baseline",
        gdp_gap=0.30,
        core_cpi=2.0,
        expected_inflation=2.0,
        wage=3.5,
        policy_rate=0.5,
        description="賃上げ継続（3.5%）・海外経済安定（+2%）・エネルギー横ばい・関税影響中程度",
    ),
    ScenarioPreset(
        name="🔵 楽観",
        label="optimistic",
        gdp_gap=1.00,
        core_cpi=2.5,
        expected_inflation=2.5,
        wage=5.0,
        policy_rate=1.0,
        description="賃上げ加速（5.0%）・海外経済好調（+3.5%）・エネルギー下落（-10%）・関税影響軽微",
    ),
    ScenarioPreset(
        name="🔴 リスク",
        label="risk",
        gdp_gap=-0.50,
        core_cpi=2.8,
        expected_inflation=1.8,
        wage=2.0,
        policy_rate=0.5,
        description="賃上げ停滞（2.0%）・海外経済悪化（-1.0%）・エネルギー上昇（+20%）・関税影響深刻",
    ),
    ScenarioPreset(
        name="🟠 スタグフレーション",
        label="stagflation",
        gdp_gap=-0.30,
        core_cpi=3.8,
        expected_inflation=3.0,
        wage=2.5,
        policy_rate=0.5,
        description="賃上げ停滞（2.5%）・海外経済横ばい（0%）・エネルギー急騰（+40%）・関税影響中程度",
    ),
]


def evaluate_all_scenarios() -> list[tuple[ScenarioPreset, PolicyCheckResult]]:
    """4シナリオ全てを評価し、(ScenarioPreset, PolicyCheckResult) のリストを返す。"""
    return [
        (preset, check_conditions_from_values(
            gdp_gap=preset.gdp_gap,
            core_cpi=preset.core_cpi,
            expected_inflation=preset.expected_inflation,
            wage=preset.wage,
            policy_rate=preset.policy_rate,
        ))
        for preset in SCENARIO_PRESETS
    ]


def format_scenario_comparison(results: list[tuple[ScenarioPreset, PolicyCheckResult]]) -> str:
    """シナリオ比較結果を Markdown セクション文字列に変換する。

    Returns:
        str: 前提条件表・利上げ確度比較表を含む Markdown テキスト
    """
    lines = [
        "## シナリオ比較（利上げ確度）",
        "",
        "### シナリオ前提条件",
        "",
        "| シナリオ | GDPギャップ | コアCPI | 予想インフレ | 賃金 | 政策金利 |",
        "|----------|------------|---------|------------|------|---------|",
    ]
    for preset, _ in results:
        lines.append(
            f"| {preset.name} | {preset.gdp_gap:+.2f}% | {preset.core_cpi:.1f}%"
            f" | {preset.expected_inflation:.1f}% | {preset.wage:.1f}%"
            f" | {preset.policy_rate:.2f}% |"
        )

    lines += [
        "",
        "### 利上げ確度評価",
        "",
        "| シナリオ | GDPギャップ | コアCPI | 予想インフレ | 賃金 | 実質金利<自然利子率 | スコア |",
        "|----------|------------|---------|------------|------|-------------------|--------|",
    ]
    for preset, result in results:
        marks = ["✅" if c.met else "❌" for c in result.conditions]
        lines.append(
            f"| {preset.name} | {marks[0]} | {marks[1]} | {marks[2]}"
            f" | {marks[3]} | {marks[4]} | **{result.score:.0f}%** |"
        )

    lines += [
        "",
        "---",
        "",
    ]
    return "\n".join(lines)
