import sqlite3
from datetime import datetime
from pathlib import Path
from market_macro_analysis.config import REPORT_DIR
from market_macro_analysis.exceptions import ReportError
from market_macro_analysis.service import policy_checker_service


# --- 信号機評価ロジック ---

def evaluate_cpi(value: float) -> str:
    """コアCPI（前年比%）の信号機評価。

    🟢: 1.5〜2.5%（目標レンジ内）
    🟡: 2.5%超（目標超過）
    🔴: 1.5%未満（目標未達）
    """
    if value < 1.5:
        return "🔴"
    elif value <= 2.5:
        return "🟢"
    else:
        return "🟡"


def evaluate_policy_rate(value: float) -> str:
    """政策金利（%）の信号機評価。

    🟢: 0〜0.5%（緩和的）
    🟡: 0.5〜1.0%（中立方向）
    🔴: 0%未満（マイナス金利）
    """
    if value < 0:
        return "🔴"
    elif value <= 0.5:
        return "🟢"
    else:
        return "🟡"


def evaluate_gdp_gap(value: float) -> str:
    """GDPギャップ（%）の信号機評価。

    🟢: 0%超（需要超過）
    🟡: −0.5〜0%（ゼロ近傍）
    🔴: −0.5%未満（需要不足）
    """
    if value > 0:
        return "🟢"
    elif value >= -0.5:
        return "🟡"
    else:
        return "🔴"


def _direction(current: float, previous: float | None) -> str:
    """前回比の変化方向記号を返す。"""
    if previous is None:
        return "―"
    diff = current - previous
    if diff > 0:
        return f"▲ {abs(diff):.2f}"
    elif diff < 0:
        return f"▼ {abs(diff):.2f}"
    else:
        return "→ 0.00"


def _latest_two(conn: sqlite3.Connection, table: str, indicator: str) -> tuple[tuple | None, tuple | None]:
    """指定テーブル・指標の最新2件を (最新, 前回) で返す。"""
    rows = conn.execute(
        f"SELECT date, value FROM {table} WHERE indicator = ? ORDER BY date DESC LIMIT 2",
        (indicator,),
    ).fetchall()
    latest = rows[0] if len(rows) >= 1 else None
    previous = rows[1] if len(rows) >= 2 else None
    return latest, previous


# --- レポート本体 ---

def generate_summary(conn: sqlite3.Connection, output_dir: str = REPORT_DIR) -> str:
    """3指標の現状サマリーを Markdown として生成・保存する。

    Returns:
        str: 出力ファイルパス
    """
    cpi_latest, cpi_prev = _latest_two(conn, "price_data", "core_cpi_yoy")
    rate_latest, rate_prev = _latest_two(conn, "financial_data", "policy_rate")
    gap_latest, gap_prev = _latest_two(conn, "economic_data", "gdp_gap")

    if cpi_latest is None and rate_latest is None and gap_latest is None:
        raise ReportError("レポート生成に必要なデータが存在しません")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 日銀マクロ経済モニタリング サマリー",
        f"",
        f"生成日時: {now}",
        f"",
        f"---",
        f"",
        f"## 現状サマリー",
        f"",
        f"| 指標 | 最新値 | 前回比 | 評価 |",
        f"|------|--------|--------|------|",
    ]

    # コアCPI
    if cpi_latest:
        date, val = cpi_latest
        prev_val = cpi_prev[1] if cpi_prev else None
        signal = evaluate_cpi(val)
        lines.append(
            f"| コアCPI（前年比） [{date}] | {val:.1f}% | {_direction(val, prev_val)} | {signal} |"
        )
    else:
        lines.append("| コアCPI（前年比） | データなし | ― | ― |")

    # 政策金利
    if rate_latest:
        date, val = rate_latest
        prev_val = rate_prev[1] if rate_prev else None
        signal = evaluate_policy_rate(val)
        lines.append(
            f"| 政策金利（月平均） [{date}] | {val:.3f}% | {_direction(val, prev_val)} | {signal} |"
        )
    else:
        lines.append("| 政策金利（月平均） | データなし | ― | ― |")

    # GDPギャップ
    if gap_latest:
        date, val = gap_latest
        prev_val = gap_prev[1] if gap_prev else None
        signal = evaluate_gdp_gap(val)
        lines.append(
            f"| 需給ギャップ [{date}] | {val:.1f}% | {_direction(val, prev_val)} | {signal} |"
        )
    else:
        lines.append("| 需給ギャップ | データなし | ― | ― |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 信号機凡例",
        f"",
        f"| 信号 | 意味 |",
        f"|------|------|",
        f"| 🟢 | 目標レンジ内・緩和的・需要超過 |",
        f"| 🟡 | やや外れ・中立方向・ゼロ近傍 |",
        f"| 🔴 | 目標未達・マイナス金利・需要不足 |",
    ]

    # 政策判断チェッカーセクションを追記
    policy_result = policy_checker_service.check_rate_hike_conditions(conn)
    lines += [
        "",
        "---",
        "",
    ]
    lines.append(policy_checker_service.format_markdown_section(policy_result))

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    filepath = str(out / "summary.md")
    Path(filepath).write_text("\n".join(lines), encoding="utf-8")
    return filepath
