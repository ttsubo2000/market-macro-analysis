import sqlite3
from dataclasses import dataclass

NATURAL_RATE = 0.5


@dataclass
class ConditionResult:
    name: str
    met: bool
    value: float | None
    threshold_desc: str
    value_text: str


@dataclass
class PolicyCheckResult:
    conditions: list[ConditionResult]
    score: float
    met_count: int
    total_count: int


def _latest_value(conn: sqlite3.Connection, table: str, indicator: str) -> float | None:
    """指定テーブル・指標の最新値を返す。データなしは None。"""
    row = conn.execute(
        f"SELECT value FROM {table} WHERE indicator = ? ORDER BY date DESC LIMIT 1",
        (indicator,),
    ).fetchone()
    return row[0] if row else None


def check_rate_hike_conditions(conn: sqlite3.Connection) -> PolicyCheckResult:
    """日銀政策判断の5条件を評価し、利上げ確度スコアを算出する。

    5条件（§3.3）:
      1. GDPギャップ > 0%
      2. コアCPI（前年比） > 1.5%
      3. 予想インフレ率（1年後） > 1.5%
      4. 賃金上昇率（所定内給与前年比） > 3.0%
      5. 実質金利（政策金利 − 予想インフレ率） < 自然利子率（0.5% 定数）

    Returns:
        PolicyCheckResult: 各条件の評価結果とスコア（0〜100%）
    """
    gdp_gap = _latest_value(conn, "economic_data", "gdp_gap")
    core_cpi = _latest_value(conn, "price_data", "core_cpi_yoy")
    expected_inf = _latest_value(conn, "financial_data", "expected_inflation_1y")
    wage = _latest_value(conn, "economic_data", "scheduled_wage_yoy")
    policy_rate = _latest_value(conn, "financial_data", "policy_rate")

    real_rate = (policy_rate - expected_inf) if (policy_rate is not None and expected_inf is not None) else None

    conditions = [
        ConditionResult(
            name="GDPギャップ",
            met=(gdp_gap is not None and gdp_gap > 0),
            value=gdp_gap,
            threshold_desc="> 0%",
            value_text=f"{gdp_gap:.2f}%" if gdp_gap is not None else "データなし",
        ),
        ConditionResult(
            name="コアCPI（前年比）",
            met=(core_cpi is not None and core_cpi > 1.5),
            value=core_cpi,
            threshold_desc="> 1.5%",
            value_text=f"{core_cpi:.1f}%" if core_cpi is not None else "データなし",
        ),
        ConditionResult(
            name="予想インフレ率（1年後）",
            met=(expected_inf is not None and expected_inf > 1.5),
            value=expected_inf,
            threshold_desc="> 1.5%",
            value_text=f"{expected_inf:.1f}%" if expected_inf is not None else "データなし",
        ),
        ConditionResult(
            name="賃金上昇率（所定内給与前年比）",
            met=(wage is not None and wage > 3.0),
            value=wage,
            threshold_desc="> 3.0%",
            value_text=f"{wage:.1f}%" if wage is not None else "データなし",
        ),
        ConditionResult(
            name="実質金利 < 自然利子率",
            met=(real_rate is not None and real_rate < NATURAL_RATE),
            value=real_rate,
            threshold_desc=f"< {NATURAL_RATE}%（自然利子率・定数）",
            value_text=(
                f"{real_rate:.2f}%（政策金利{policy_rate:.2f}% − 予想インフレ率{expected_inf:.1f}%）"
                if real_rate is not None else "データなし"
            ),
        ),
    ]

    met_count = sum(1 for c in conditions if c.met)
    total_count = len(conditions)
    score = met_count / total_count * 100

    return PolicyCheckResult(
        conditions=conditions,
        score=score,
        met_count=met_count,
        total_count=total_count,
    )


def check_conditions_from_values(
    gdp_gap: float | None,
    core_cpi: float | None,
    expected_inflation: float | None,
    wage: float | None,
    policy_rate: float | None,
) -> PolicyCheckResult:
    """5指標を直接受け取り、DBを使わずに利上げ条件を評価する。

    シナリオ比較など仮定値での評価に使用する。
    条件評価ロジックは check_rate_hike_conditions() と共通。
    """
    real_rate = (
        (policy_rate - expected_inflation)
        if (policy_rate is not None and expected_inflation is not None)
        else None
    )

    conditions = [
        ConditionResult(
            name="GDPギャップ",
            met=(gdp_gap is not None and gdp_gap > 0),
            value=gdp_gap,
            threshold_desc="> 0%",
            value_text=f"{gdp_gap:.2f}%" if gdp_gap is not None else "データなし",
        ),
        ConditionResult(
            name="コアCPI（前年比）",
            met=(core_cpi is not None and core_cpi > 1.5),
            value=core_cpi,
            threshold_desc="> 1.5%",
            value_text=f"{core_cpi:.1f}%" if core_cpi is not None else "データなし",
        ),
        ConditionResult(
            name="予想インフレ率（1年後）",
            met=(expected_inflation is not None and expected_inflation > 1.5),
            value=expected_inflation,
            threshold_desc="> 1.5%",
            value_text=f"{expected_inflation:.1f}%" if expected_inflation is not None else "データなし",
        ),
        ConditionResult(
            name="賃金上昇率（所定内給与前年比）",
            met=(wage is not None and wage > 3.0),
            value=wage,
            threshold_desc="> 3.0%",
            value_text=f"{wage:.1f}%" if wage is not None else "データなし",
        ),
        ConditionResult(
            name="実質金利 < 自然利子率",
            met=(real_rate is not None and real_rate < NATURAL_RATE),
            value=real_rate,
            threshold_desc=f"< {NATURAL_RATE}%（自然利子率・定数）",
            value_text=(
                f"{real_rate:.2f}%（政策金利{policy_rate:.2f}% − 予想インフレ率{expected_inflation:.1f}%）"
                if real_rate is not None else "データなし"
            ),
        ),
    ]

    met_count = sum(1 for c in conditions if c.met)
    total_count = len(conditions)
    score = met_count / total_count * 100

    return PolicyCheckResult(
        conditions=conditions,
        score=score,
        met_count=met_count,
        total_count=total_count,
    )


def format_markdown_section(result: PolicyCheckResult) -> str:
    """PolicyCheckResult を Markdown セクション文字列に変換する。

    Returns:
        str: Markdown テキスト（見出し・スコア・条件テーブルを含む）
    """
    lines = [
        "## 日銀政策判断チェッカー（利上げ確度）",
        "",
        f"**利上げ確度スコア: {result.score:.0f}%**（{result.total_count}条件中{result.met_count}件充足）",
        "",
        "| 条件 | 最新値 | 閾値 | 判定 |",
        "|------|--------|------|------|",
    ]
    for cond in result.conditions:
        mark = "✅" if cond.met else "❌"
        lines.append(f"| {cond.name} | {cond.value_text} | {cond.threshold_desc} | {mark} |")

    lines += [
        "",
        "---",
        "",
    ]
    return "\n".join(lines)
