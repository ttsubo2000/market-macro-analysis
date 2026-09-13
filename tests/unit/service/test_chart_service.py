import math
import sqlite3
import pytest
from datetime import datetime, timedelta
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


# --- make_expected_inflation_chart（BEI チャート）---

@pytest.fixture
def db_with_bei(db_conn):
    """BEI データを投入した DB コネクション。"""
    db_conn.execute(
        "CREATE TABLE financial_data (date TEXT, indicator TEXT, value REAL, unit TEXT, PRIMARY KEY (date, indicator))"
    )
    db_conn.executemany(
        "INSERT INTO financial_data VALUES (?, 'bei', ?, '%')",
        [("2026-05-27", 2.245), ("2026-05-28", 2.208), ("2026-05-29", 2.172)],
    )
    return db_conn


def test_make_expected_inflation_chart_creates_file(db_with_bei, tmp_path):
    filepath = chart_service.make_expected_inflation_chart(db_with_bei, output_dir=str(tmp_path))
    assert Path(filepath).exists()
    assert filepath.endswith("expected_inflation_chart.png")


def test_make_expected_inflation_chart_raises_when_no_data(empty_tables, tmp_path):
    with pytest.raises(ChartError):
        chart_service.make_expected_inflation_chart(empty_tables, output_dir=str(tmp_path))


# --- REQ-21: BEI チャートの時間軸（目盛り刻み・欠測区間の分断）---

@pytest.fixture
def db_with_bei_gaps(db_with_all_data):
    """実データと同じ形（各月とも月後半10営業日のみ）の BEI を投入した DB。

    取得元が最新10営業日分しか掲載しないため、月前半が欠測する。
    2026-05〜08 の4クラスタ・欠測3箇所・全体で約3.5ヶ月分。
    """
    rows = []
    value = 2.25
    for year, month, first_day in [(2026, 5, 18), (2026, 6, 17), (2026, 7, 17), (2026, 8, 18)]:
        day = datetime(year, month, first_day)
        collected = 0
        while collected < 10:
            if day.weekday() < 5:
                rows.append((day.strftime("%Y-%m-%d"), round(value, 3)))
                collected += 1
                value -= 0.01
            day += timedelta(days=1)
    db_with_all_data.executemany(
        "INSERT INTO financial_data VALUES (?, 'bei', ?, '%')", rows
    )
    return db_with_all_data


@pytest.fixture
def keep_figure(monkeypatch):
    """生成関数に Figure を閉じさせず、描画済みの Figure を検証できるようにする。

    差し替えるのは後片付けの plt.close のみで、描画コードは本物を通す。
    """
    real_close = chart_service.plt.close
    monkeypatch.setattr(chart_service.plt, "close", lambda *args, **kwargs: None)
    yield lambda: chart_service.plt.gcf()
    real_close("all")


def _visible_tick_labels(ax) -> list:
    """描画範囲内に実際に表示される X 軸目盛りラベルを返す。"""
    ax.figure.canvas.draw()
    low, high = ax.get_xlim()
    return [
        label.get_text()
        for tick, label in zip(ax.get_xticks(), ax.get_xticklabels())
        if low <= tick <= high and label.get_text()
    ]


def _nan_break_count(ax) -> int:
    """折れ線に含まれる NaN（＝欠測による分断）の数を返す。"""
    return sum(1 for value in ax.get_lines()[0].get_ydata() if math.isnan(value))


def test_split_series_on_gaps_inserts_nan_for_bei_gap():
    """5日を超える間隔があく区間には NaN が1点挿入される。"""
    dates = [datetime(2026, 7, 30), datetime(2026, 7, 31), datetime(2026, 8, 18)]
    values = [1.963, 1.952, 2.014]

    plot_dates, plot_values = chart_service._split_series_on_gaps(dates, values)

    assert len(plot_values) == 4
    assert math.isnan(plot_values[2])
    assert plot_dates[2] == datetime(2026, 8, 1)
    assert [v for v in plot_values if not math.isnan(v)] == values


def test_split_series_on_gaps_keeps_bei_gap_boundary_continuous():
    """間隔がちょうど閾値（5日）なら分断しない（境界値）。"""
    dates = [datetime(2026, 7, 24), datetime(2026, 7, 29)]
    values = [1.976, 1.930]

    plot_dates, plot_values = chart_service._split_series_on_gaps(dates, values)

    assert plot_dates == dates
    assert plot_values == values


def test_split_series_on_gaps_returns_empty_for_empty_input():
    """空系列を渡しても例外にならず空を返す。"""
    assert chart_service._split_series_on_gaps([], []) == ([], [])


def test_make_expected_inflation_chart_bei_axis_shows_multiple_ticks(
    db_with_bei_gaps, keep_figure, tmp_path
):
    """約3.5ヶ月分のデータで X 軸目盛りが2本以上表示される。"""
    chart_service.make_expected_inflation_chart(db_with_bei_gaps, output_dir=str(tmp_path))

    labels = _visible_tick_labels(keep_figure().axes[0])

    assert len(labels) >= 2, f"目盛りが不足している: {labels}"
    assert all(label.startswith("2026-") for label in labels), labels


def test_make_expected_inflation_chart_bei_gap_breaks_line(
    db_with_bei_gaps, keep_figure, tmp_path
):
    """欠測3箇所で折れ線が分断される。"""
    chart_service.make_expected_inflation_chart(db_with_bei_gaps, output_dir=str(tmp_path))

    assert _nan_break_count(keep_figure().axes[0]) == 3


def test_combined_bei_panel_axis_shows_multiple_ticks(db_with_bei_gaps, keep_figure, tmp_path):
    """統合チャートの BEI パネルでも X 軸目盛りが2本以上表示される。"""
    chart_service.make_combined_chart(db_with_bei_gaps, output_dir=str(tmp_path))

    labels = _visible_tick_labels(keep_figure().axes[2])

    assert len(labels) >= 2, f"目盛りが不足している: {labels}"
    assert all(label.startswith("2026-") for label in labels), labels


def test_combined_bei_panel_gap_breaks_line(db_with_bei_gaps, keep_figure, tmp_path):
    """統合チャートの BEI パネルでも欠測で折れ線が分断される。"""
    chart_service.make_combined_chart(db_with_bei_gaps, output_dir=str(tmp_path))

    assert _nan_break_count(keep_figure().axes[2]) == 3
