import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from market_macro_analysis.exceptions import ReportError


DOCS_REPORT_DIR = "docs/report"

_USDJPY_TICKER = "USDJPY=X"
_N225_TICKER = "^N225"

_PERIOD_DAYS = 30


def _fetch_yf_latest(ticker: str, days: int = _PERIOD_DAYS) -> dict | None:
    """yfinance で直近 `days` 日の終値を取得し、現在値・変化率を返す。

    Returns:
        {"current": float, "prev": float, "change_pct": float} or None（取得失敗時）
    """
    try:
        end = datetime.now()
        start = end - timedelta(days=days)
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if df.empty or len(df) < 2:
            return None
        close = df["Close"].dropna()
        current = float(close.iloc[-1])
        prev = float(close.iloc[0])
        change_pct = (current - prev) / prev * 100
        return {"current": current, "prev": prev, "change_pct": change_pct}
    except Exception:
        return None


def _latest_val(conn: sqlite3.Connection, table: str, indicator: str) -> float | None:
    row = conn.execute(
        f"SELECT value FROM {table} WHERE indicator = ? ORDER BY date DESC LIMIT 1",
        (indicator,),
    ).fetchone()
    return row[0] if row else None


def _latest_bei(conn: sqlite3.Connection) -> float | None:
    row = conn.execute(
        "SELECT value FROM financial_data WHERE indicator = 'bei' ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


# --- 考察テキスト生成 ---

def _comment_usdjpy(data: dict) -> str:
    val = data["current"]
    chg = data["change_pct"]
    direction = "上昇（円安）" if chg >= 0 else "下落（円高）"
    pct_str = f"{chg:+.1f}%"
    if val > 155:
        stance = "大幅な円安水準。輸入物価を押し上げており、コアCPIへの上昇圧力として働いている。日銀の利上げペースが市場の期待に届いていない可能性がある。"
    elif val > 145:
        stance = "円安傾向が続いており、輸入コスト増加を通じて物価を下支えしている。"
    elif val > 135:
        stance = "やや円安の水準。輸入物価への影響は限定的。"
    else:
        stance = "円高方向にあり、輸入物価の低下を通じて物価抑制方向に働く可能性がある。"
    return (
        f"直近{_PERIOD_DAYS}日間で **{direction}（{pct_str}）**。"
        f"現在 **{val:.2f} 円/ドル**。{stance}"
    )


def _comment_n225(data: dict) -> str:
    val = data["current"]
    chg = data["change_pct"]
    direction = "上昇" if chg >= 0 else "下落"
    pct_str = f"{chg:+.1f}%"
    if chg >= 5:
        stance = "力強い上昇トレンド（リスクオン）。企業業績改善期待が強く、株式市場は利上げへの耐性を示している。"
    elif chg >= 0:
        stance = "緩やかな上昇。景況感は安定しており、金融政策の正常化を妨げる要因は少ない。"
    elif chg >= -5:
        stance = "やや軟調。グローバルリスクや国内需要の不透明感が漂っている。"
    else:
        stance = "大幅下落（リスクオフ）。市場の警戒感が高まっており、利上げの急進は難しい局面。"
    return (
        f"直近{_PERIOD_DAYS}日間で **{direction}（{pct_str}）**。"
        f"現在 **{val:,.0f} 円**。{stance}"
    )


def _comment_overall(
    cpi: float | None,
    rate: float | None,
    gdp_gap: float | None,
    bei: float | None,
    usdjpy: dict | None,
) -> str:
    lines = []

    # インフレギャップ
    if cpi is not None:
        inf_gap = cpi - 2.0
        if inf_gap > 0:
            lines.append(
                f"コアCPI（{cpi:.1f}%）は物価安定目標（2%）を上回っており、"
                f"インフレギャップはプラス（{inf_gap:+.1f}%pt）。引き締め方向の圧力が存在する。"
            )
        else:
            lines.append(
                f"コアCPI（{cpi:.1f}%）は物価安定目標（2%）に未達で、"
                f"インフレギャップはマイナス（{inf_gap:+.1f}%pt）。緩和継続の余地がある。"
            )

    # 需給ギャップ
    if gdp_gap is not None:
        if gdp_gap > 0.5:
            lines.append(f"需給ギャップ（{gdp_gap:+.1f}%）は需要超過で、物価上昇圧力が続いている。")
        elif gdp_gap > 0:
            lines.append(f"需給ギャップ（{gdp_gap:+.1f}%）は小幅なプラスで、需要は供給をわずかに上回っている。")
        else:
            lines.append(f"需給ギャップ（{gdp_gap:+.1f}%）はマイナスで、需要不足の状態。")

    # 実質金利
    if rate is not None and bei is not None:
        real_rate = rate - bei
        if real_rate < 0.5:
            lines.append(
                f"実質金利（政策金利{rate:.2f}% − BEI{bei:.2f}% ＝ {real_rate:.2f}%）は"
                f"自然利子率（0.5%）を下回っており、金融環境は**緩和的**。"
            )
        else:
            lines.append(
                f"実質金利（政策金利{rate:.2f}% − BEI{bei:.2f}% ＝ {real_rate:.2f}%）は"
                f"自然利子率（0.5%）を上回っており、金融環境は**引き締め的**。"
            )

    # 為替の追加コメント
    if usdjpy is not None and usdjpy["current"] > 150:
        lines.append(
            "円安が続く中で輸入物価が上昇しており、エネルギー・食料品を通じた"
            "物価押し上げが国内消費を圧迫するリスクに注意が必要。"
        )

    if not lines:
        return "現時点では総合考察に必要なデータが不足しています。"

    return "\n\n".join(lines)


def generate_macro_analysis_report(
    conn: sqlite3.Connection,
    output_dir: str = DOCS_REPORT_DIR,
) -> str:
    """外部要因（為替・株価）を加えたマクロ経済考察レポートを生成する。

    Returns:
        str: 出力ファイルパス
    """
    # 国内指標
    cpi = _latest_val(conn, "price_data", "core_cpi_yoy")
    rate = _latest_val(conn, "financial_data", "policy_rate")
    gdp_gap = _latest_val(conn, "economic_data", "gdp_gap")
    bei = _latest_bei(conn)

    if cpi is None and rate is None and gdp_gap is None:
        raise ReportError("考察レポート生成に必要なデータが存在しません")

    # 外部マーケットデータ
    usdjpy = _fetch_yf_latest(_USDJPY_TICKER)
    n225 = _fetch_yf_latest(_N225_TICKER)

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# マクロ経済考察レポート（{today}）",
        "",
        f"> 生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 1. 国内経済・物価指標の現状",
        "",
        "| 指標 | 最新値 | 備考 |",
        "|------|--------|------|",
    ]

    lines.append(f"| コアCPI（前年比） | {f'{cpi:.1f}%' if cpi is not None else 'データなし'} | 物価安定目標: 2% |")
    lines.append(f"| 政策金利 | {f'{rate:.2f}%' if rate is not None else 'データなし'} | 無担保コールレート翌日物・月平均 |")
    lines.append(f"| 需給ギャップ | {f'{gdp_gap:+.1f}%' if gdp_gap is not None else 'データなし'} | プラス = 需要超過 |")
    lines.append(f"| BEI（期待インフレ率） | {f'{bei:.2f}%' if bei is not None else 'データなし'} | 市場参加者の期待インフレ |")
    if rate is not None and bei is not None:
        real_rate = rate - bei
        lines.append(f"| 実質金利（政策金利 − BEI） | {real_rate:+.2f}% | 自然利子率 0.5% が中立基準 |")

    lines += [
        "",
        "---",
        "",
        "## 2. 外部要因・市場動向",
        "",
        "### 2-1. 為替（USDJPY）",
        "",
    ]
    if usdjpy:
        lines.append(_comment_usdjpy(usdjpy))
    else:
        lines.append("※ 為替データの取得に失敗しました（ネットワーク等を確認してください）。")

    lines += [
        "",
        "### 2-2. 株式市場（日経225）",
        "",
    ]
    if n225:
        lines.append(_comment_n225(n225))
    else:
        lines.append("※ 日経225データの取得に失敗しました（ネットワーク等を確認してください）。")

    lines += [
        "",
        "---",
        "",
        "## 3. 総合考察（金融政策への含意）",
        "",
        _comment_overall(cpi, rate, gdp_gap, bei, usdjpy),
        "",
        "---",
        "",
        "> ※ このレポートは自動生成です。考察テキストは指標の値に応じた定型文を組み合わせたものです。",
        "> 社会情勢・地政学リスク等の定性情報は含まれていません。",
    ]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    filepath = str(out / f"macro_analysis_{today}.md")
    Path(filepath).write_text("\n".join(lines), encoding="utf-8")
    return filepath
