import sqlite3
from market_macro_analysis.config import load_estat_api_key, ESTAT_API_CONFIG_PATH
from market_macro_analysis.service import estat_cpi_service


def fetch_price_data(conn: sqlite3.Connection) -> None:
    """物価ブロックのデータを取得してDBに保存する。"""
    app_id = load_estat_api_key(ESTAT_API_CONFIG_PATH)
    records = estat_cpi_service.fetch_core_cpi(app_id)
    count = estat_cpi_service.save_core_cpi(conn, records)
    print(f"[fetch_price_data] コアCPI: {count} 件保存")
