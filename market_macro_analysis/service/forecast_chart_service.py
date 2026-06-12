import sqlite3
from datetime import datetime, date
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import japanize_matplotlib  # noqa: F401

from market_macro_analysis.config import REPORT_PNG_DIR
from market_macro_analysis.exceptions import ChartError
from market_macro_analysis.service.policy_checker_service import (
    PolicyCheckResult,
    check_rate_hike_conditions,
)
from market_macro_analysis.service.scenario_service import (
    ScenarioPreset,
    SCENARIO_PRESETS,
    evaluate_all_scenarios,
)

RATE_HIKE_STEP = 0.25   # 1回あたりの利上げ幅（%）
FORECAST_MONTHS = 24    # 予測期間（ヶ月）


def _add_months(dt: datetime, months: int) -> datetime:
    """datetime に月数を加算する（標準ライブラリのみ使用）。"""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month)


def months_to_hike(score: float) -> int | None:
    """利上げ確度スコアから次回利上げまでの目安月数を返す。

    ルールベース試算:
      100%  →  6 ヶ月以内
       80%〜 →  9 ヶ月以内
       60%〜 → 12 ヶ月以内
       40%〜 → 18 ヶ月以内
       20%〜 → 24 ヶ月以内
        0%  → None（利上げ見込みなし）
    """
    if score >= 100:
        return 6
    elif score >= 80:
        return 9
    elif score >= 60:
        return 12
    elif score >= 40:
        return 18
    elif score >= 20:
        return 24
    else:
        return None


def _get_current_policy_rate(conn: sqlite3.Connection) -> float | None:
    """DBから最新の政策金利を取得する。"""
    row = conn.execute(
        "SELECT value FROM financial_data WHERE indicator = 'policy_rate' ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _build_path(current_rate: float, hike_months: int | None) -> tuple[list[datetime], list[float]]:
    """ステップ関数の (dates, rates) を生成する。

    current_rate から開始し、hike_months ヶ月後に RATE_HIKE_STEP 分上昇。
    None の場合はフラット（利上げなし）。
    """
    now = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    dates = [_add_months(now, i) for i in range(FORECAST_MONTHS + 1)]
    rates = []
    for i in range(FORECAST_MONTHS + 1):
        if hike_months is not None and i >= hike_months:
            rates.append(current_rate + RATE_HIKE_STEP)
        else:
            rates.append(current_rate)
    return dates, rates


def make_policy_rate_forecast_chart(
    conn: sqlite3.Connection,
    output_dir: str = REPORT_PNG_DIR,
) -> str:
    """政策金利パス予測チャート（PNG）を生成する。

    現状評価（実績DBデータ）と4シナリオの予測パスを描画する。
    各パスはステップ関数: 現在金利 → months_to_hike ヶ月後に +0.25%。

    Returns:
        str: 出力ファイルパス
    """
    current_rate = _get_current_policy_rate(conn)
    if current_rate is None:
        raise ChartError("政策金利データが存在しません")

    policy_result = check_rate_hike_conditions(conn)
    scenario_results = evaluate_all_scenarios()

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5))

    # 現状評価パス
    current_hike = months_to_hike(policy_result.score)
    dates, rates = _build_path(current_rate, current_hike)
    ax.step(dates, rates, where="post", color="gray", linestyle="--",
            linewidth=1.5, label=f"現状評価（{policy_result.score:.0f}%）")

    # シナリオパス
    colors = {
        "baseline": "#2a9d8f",
        "optimistic": "#457b9d",
        "risk": "#e63946",
        "stagflation": "#f4a261",
    }
    for preset, result in scenario_results:
        hike_m = months_to_hike(result.score)
        dates, rates = _build_path(current_rate, hike_m)
        name_text = preset.name.split(" ", 1)[-1] if " " in preset.name else preset.name
        ax.step(dates, rates, where="post",
                color=colors.get(preset.label, "black"),
                linewidth=1.5, label=f"{name_text}（{result.score:.0f}%）")

    ax.set_title("政策金利パス予測（ルールベース・今後24ヶ月）", fontsize=13)
    ax.set_ylabel("政策金利（%）")
    ax.set_xlabel("予測期間")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    filepath = str(out / "policy_rate_forecast.png")
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


def format_forecast_summary(
    policy_result: PolicyCheckResult,
    scenario_results: list[tuple[ScenarioPreset, PolicyCheckResult]],
    current_rate: float | None,
) -> str:
    """政策金利パス予測サマリーを Markdown セクション文字列に変換する。

    Returns:
        str: 予測サマリー Markdown テキスト
    """
    rate_str = f"{current_rate:.2f}%" if current_rate is not None else "不明"
    next_rate_str = (
        f"{current_rate + RATE_HIKE_STEP:.2f}%"
        if current_rate is not None else "不明"
    )

    current_hike = months_to_hike(policy_result.score)
    current_timing = f"{current_hike} ヶ月以内" if current_hike is not None else "見込みなし"

    lines = [
        "## 政策金利パス予測（ルールベース）",
        "",
        f"現在の政策金利: **{rate_str}**　現状評価スコア: **{policy_result.score:.0f}%**"
        f"（{policy_result.total_count}条件中{policy_result.met_count}件充足）",
        "",
        "### 次回利上げタイミング試算",
        "",
        "| シナリオ | 利上げ確度 | 次回利上げ目安 | 予測政策金利（+1回） |",
        "|----------|-----------|--------------|---------------------|",
        f"| 現状評価 | {policy_result.score:.0f}% | {current_timing} | {next_rate_str} |",
    ]

    for preset, result in scenario_results:
        hike_m = months_to_hike(result.score)
        timing = f"{hike_m} ヶ月以内" if hike_m is not None else "見込みなし"
        lines.append(
            f"| {preset.name} | {result.score:.0f}% | {timing} | {next_rate_str} |"
        )

    lines += [
        "",
        "> ルールベース予測。統計的信頼区間は含まない。利上げ幅は 0.25% を仮定。",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)
