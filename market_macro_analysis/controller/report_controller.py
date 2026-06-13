import sqlite3
from market_macro_analysis.service import report_service, macro_report_service


def make_report(conn: sqlite3.Connection, block_type: str) -> None:
    """サマリーレポートを生成する。

    Args:
        block_type: "all" | "financial" | "economic" | "price"
                    現状は block_type によらず統合サマリーを生成する。
    """
    path = report_service.generate_summary(conn)
    print(f"[make_report] サマリーレポート: {path}")

    if block_type in ("all", "financial"):
        path = macro_report_service.generate_macro_analysis_report(conn)
        print(f"[make_report] マクロ経済考察レポート: {path}")
