import sqlite3
from pathlib import Path
import matplotlib
matplotlib.use("Agg")  # GUI不要のバックエンド
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import japanize_matplotlib  # noqa: F401  日本語フォント有効化
from datetime import datetime
from market_macro_analysis.config import REPORT_PNG_DIR
from market_macro_analysis.exceptions import ChartError


def _load_monthly(conn: sqlite3.Connection, table: str, indicator: str) -> tuple[list, list]:
    """月次データ（YYYY-MM）を取得し (dates, values) を返す。"""
    rows = conn.execute(
        f"SELECT date, value FROM {table} WHERE indicator = ? ORDER BY date",
        (indicator,),
    ).fetchall()
    dates = [datetime.strptime(r[0], "%Y-%m") for r in rows]
    values = [r[1] for r in rows]
    return dates, values


def _load_quarterly(conn: sqlite3.Connection, table: str, indicator: str) -> tuple[list, list]:
    """四半期データ（YYYY-QN）を取得し (dates, values) を返す。"""
    rows = conn.execute(
        f"SELECT date, value FROM {table} WHERE indicator = ? ORDER BY date",
        (indicator,),
    ).fetchall()
    dates = []
    values = []
    for date_str, value in rows:
        year, q = date_str.split("-Q")
        month = (int(q) - 1) * 3 + 1
        dates.append(datetime(int(year), month, 1))
        values.append(value)
    return dates, values


def _ensure_output_dir(path: str) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def make_cpi_chart(conn: sqlite3.Connection, output_dir: str = REPORT_PNG_DIR) -> str:
    """コアCPI（前年比）の時系列チャートを生成する。

    Returns:
        str: 出力ファイルパス
    """
    dates, values = _load_monthly(conn, "price_data", "core_cpi_yoy")
    if not dates:
        raise ChartError("コアCPI のデータが存在しません")

    out = _ensure_output_dir(output_dir)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, values, color="#e63946", linewidth=1.5, label="コアCPI（前年比）")
    ax.axhline(2.0, color="gray", linestyle="--", linewidth=0.8, label="目標 2%")
    ax.set_title("コアCPI（生鮮食品を除く総合・前年比）", fontsize=13)
    ax.set_ylabel("前年比（%）")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    filepath = str(out / "cpi_chart.png")
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


def make_policy_rate_chart(conn: sqlite3.Connection, output_dir: str = REPORT_PNG_DIR) -> str:
    """政策金利の時系列チャートを生成する。

    Returns:
        str: 出力ファイルパス
    """
    dates, values = _load_monthly(conn, "financial_data", "policy_rate")
    if not dates:
        raise ChartError("政策金利のデータが存在しません")

    out = _ensure_output_dir(output_dir)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, values, color="#457b9d", linewidth=1.5, label="政策金利（無担保コールレート翌日物・月平均）")
    ax.set_title("政策金利（無担保コールレート翌日物・月平均）", fontsize=13)
    ax.set_ylabel("金利（%）")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(5))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    filepath = str(out / "policy_rate_chart.png")
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


def make_gdp_gap_chart(conn: sqlite3.Connection, output_dir: str = REPORT_PNG_DIR) -> str:
    """GDPギャップの時系列チャートを生成する。

    Returns:
        str: 出力ファイルパス
    """
    dates, values = _load_quarterly(conn, "economic_data", "gdp_gap")
    if not dates:
        raise ChartError("GDPギャップのデータが存在しません")

    out = _ensure_output_dir(output_dir)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(
        dates, values,
        width=60,
        color=["#e63946" if v >= 0 else "#457b9d" for v in values],
        alpha=0.7,
        label="GDPギャップ（四半期）",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("需給ギャップ（GDPギャップ）", fontsize=13)
    ax.set_ylabel("（%）")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(5))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()

    filepath = str(out / "gdp_gap_chart.png")
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


def make_expected_inflation_chart(conn: sqlite3.Connection, output_dir: str = REPORT_PNG_DIR) -> str:
    """BEI（ブレーク・イーブン・インフレ率）の時系列チャートを生成する。

    データソース: stock-marketdata.com（日本相互証券ベース）の日次 BEI。
    週次実行のたびに1点ずつ蓄積される。

    Returns:
        str: 出力ファイルパス
    """
    rows = conn.execute(
        "SELECT date, value FROM financial_data WHERE indicator = ? ORDER BY date",
        ("bei",),
    ).fetchall()
    if not rows:
        raise ChartError("BEI のデータが存在しません")

    dates = [datetime.strptime(r[0], "%Y-%m-%d") for r in rows]
    values = [r[1] for r in rows]

    out = _ensure_output_dir(output_dir)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, values, color="#2a9d8f", linewidth=1.5, marker="o", markersize=4,
            label="BEI（期待インフレ率・日次）")
    ax.axhline(2.0, color="gray", linestyle="--", linewidth=0.8, label="目標 2%")
    ax.axhline(1.5, color="#e9c46a", linestyle=":", linewidth=0.8, label="判定閾値 1.5%")
    ax.set_title("BEI（ブレーク・イーブン・インフレ率）", fontsize=13)
    ax.set_ylabel("（%）")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    filepath = str(out / "expected_inflation_chart.png")
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


INFLATION_TARGET = 2.0  # 日銀の物価安定目標（%）


def make_inflation_gap_chart(conn: sqlite3.Connection, output_dir: str = REPORT_PNG_DIR) -> str:
    """インフレギャップ（コアCPI − 物価安定目標2%）の時系列チャートを生成する。

    テイラールール定義: インフレギャップ = 実際のインフレ率 − 目標インフレ率（2%）

    Returns:
        str: 出力ファイルパス
    """
    dates, values = _load_monthly(conn, "price_data", "core_cpi_yoy")
    if not dates:
        raise ChartError("コアCPI のデータが存在しません")

    gaps = [v - INFLATION_TARGET for v in values]

    out = _ensure_output_dir(output_dir)
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["#e63946" if v >= 0 else "#457b9d" for v in gaps]
    ax.bar(dates, gaps, width=20, color=colors, alpha=0.8, label="インフレギャップ（コアCPI − 2%目標）")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("インフレギャップ（コアCPI − 物価安定目標 2%）", fontsize=13)
    ax.set_ylabel("（%ポイント）")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()

    filepath = str(out / "inflation_gap_chart.png")
    fig.savefig(filepath, dpi=150)
    plt.close(fig)
    return filepath


def make_combined_chart(conn: sqlite3.Connection, output_dir: str = REPORT_PNG_DIR) -> str:
    """5指標の統合チャートを生成する（見取り図の時計回り順）。

    順番: GDPギャップ（経済）→ コアCPI → BEI → インフレギャップ（物価）→ 政策金利（金融）

    Returns:
        str: 出力ファイルパス
    """
    gap_dates, gap_values = _load_quarterly(conn, "economic_data", "gdp_gap")
    cpi_dates, cpi_values = _load_monthly(conn, "price_data", "core_cpi_yoy")
    bei_rows = conn.execute(
        "SELECT date, value FROM financial_data WHERE indicator = 'bei' ORDER BY date"
    ).fetchall()
    bei_dates = [datetime.strptime(r[0], "%Y-%m-%d") for r in bei_rows]
    bei_values = [r[1] for r in bei_rows]
    gap_inf_dates = cpi_dates
    gap_inf_values = [v - INFLATION_TARGET for v in cpi_values]
    rate_dates, rate_values = _load_monthly(conn, "financial_data", "policy_rate")

    if not gap_dates and not cpi_dates and not bei_dates and not rate_dates:
        raise ChartError("チャート生成に必要なデータが存在しません")

    out = _ensure_output_dir(output_dir)
    fig, axes = plt.subplots(5, 1, figsize=(12, 16), sharex=False)
    fig.suptitle("日銀マクロ経済モニタリング（見取り図）", fontsize=15, y=1.01)

    # 1. GDPギャップ（経済）
    ax0 = axes[0]
    if gap_dates:
        ax0.bar(gap_dates, gap_values, width=60,
                color=["#e63946" if v >= 0 else "#457b9d" for v in gap_values], alpha=0.7)
        ax0.axhline(0, color="black", linewidth=0.8)
    ax0.set_title("① 需給ギャップ（経済）", fontsize=11)
    ax0.set_ylabel("（%）")
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax0.xaxis.set_major_locator(mdates.YearLocator(5))
    ax0.grid(True, alpha=0.3, axis="y")

    # 2. コアCPI（物価上昇率）
    ax1 = axes[1]
    if cpi_dates:
        ax1.plot(cpi_dates, cpi_values, color="#e63946", linewidth=1.5)
        ax1.axhline(2.0, color="gray", linestyle="--", linewidth=0.8)
    ax1.set_title("② コアCPI・物価上昇率（物価）", fontsize=11)
    ax1.set_ylabel("（%）")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.grid(True, alpha=0.3)

    # 3. BEI（予想インフレ率）
    ax2 = axes[2]
    if bei_dates:
        ax2.plot(bei_dates, bei_values, color="#2a9d8f", linewidth=1.5, marker="o", markersize=4)
        ax2.axhline(2.0, color="gray", linestyle="--", linewidth=0.8)
        ax2.axhline(1.5, color="#e9c46a", linestyle=":", linewidth=0.8)
    ax2.set_title("③ BEI・予想インフレ率（物価）", fontsize=11)
    ax2.set_ylabel("（%）")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax2.grid(True, alpha=0.3)

    # 4. インフレギャップ
    ax3 = axes[3]
    if gap_inf_dates:
        ax3.bar(gap_inf_dates, gap_inf_values, width=20,
                color=["#e63946" if v >= 0 else "#457b9d" for v in gap_inf_values], alpha=0.8)
        ax3.axhline(0, color="black", linewidth=0.8)
    ax3.set_title("④ インフレギャップ・コアCPI − 2%目標（物価）", fontsize=11)
    ax3.set_ylabel("（%pt）")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax3.xaxis.set_major_locator(mdates.YearLocator(2))
    ax3.grid(True, alpha=0.3, axis="y")

    # 5. 政策金利（金融）
    ax4 = axes[4]
    if rate_dates:
        ax4.plot(rate_dates, rate_values, color="#457b9d", linewidth=1.5)
    ax4.set_title("⑤ 政策金利（金融）", fontsize=11)
    ax4.set_ylabel("（%）")
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax4.xaxis.set_major_locator(mdates.YearLocator(5))
    ax4.grid(True, alpha=0.3)

    fig.tight_layout()

    filepath = str(out / "combined_chart.png")
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return filepath
