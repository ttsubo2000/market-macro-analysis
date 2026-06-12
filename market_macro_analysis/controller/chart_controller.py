import sqlite3
from market_macro_analysis.service import chart_service


def make_chart(conn: sqlite3.Connection, block_type: str) -> None:
    """チャートを生成する。

    Args:
        block_type: "all" | "financial" | "economic" | "price"
    """
    if block_type in ("all", "price"):
        path = chart_service.make_cpi_chart(conn)
        print(f"[make_chart] コアCPI チャート: {path}")

    if block_type in ("all", "financial"):
        path = chart_service.make_policy_rate_chart(conn)
        print(f"[make_chart] 政策金利 チャート: {path}")

        path = chart_service.make_expected_inflation_chart(conn)
        print(f"[make_chart] 企業物価見通し チャート: {path}")

    if block_type in ("all", "economic"):
        path = chart_service.make_gdp_gap_chart(conn)
        print(f"[make_chart] GDPギャップ チャート: {path}")

    if block_type == "all":
        path = chart_service.make_combined_chart(conn)
        print(f"[make_chart] 統合チャート: {path}")
