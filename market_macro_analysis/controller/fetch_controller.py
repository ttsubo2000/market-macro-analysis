import sqlite3
from market_macro_analysis.config import load_estat_api_key, ESTAT_API_CONFIG_PATH
from market_macro_analysis.service import estat_cpi_service, boj_rate_service, cao_gdp_service, boj_tankan_service


def fetch_price_data(conn: sqlite3.Connection) -> None:
    """物価ブロックのデータを取得してDBに保存する。"""
    app_id = load_estat_api_key(ESTAT_API_CONFIG_PATH)
    records = estat_cpi_service.fetch_core_cpi(app_id)
    count = estat_cpi_service.save_core_cpi(conn, records)
    print(f"[fetch_price_data] コアCPI: {count} 件保存")


def fetch_financial_data(conn: sqlite3.Connection) -> None:
    """金融ブロックのデータを取得してDBに保存する。"""
    records = boj_rate_service.fetch_policy_rate()
    count = boj_rate_service.save_policy_rate(conn, records)
    print(f"[fetch_financial_data] 政策金利: {count} 件保存")

    records = boj_tankan_service.fetch_price_outlook()
    count = boj_tankan_service.save_price_outlook(conn, records)
    print(f"[fetch_financial_data] 企業物価見通し（1年後）: {count} 件保存")


def fetch_economic_data(conn: sqlite3.Connection) -> None:
    """経済ブロックのデータを取得してDBに保存する。"""
    records = cao_gdp_service.fetch_gdp_gap()
    count = cao_gdp_service.save_gdp_gap(conn, records)
    print(f"[fetch_economic_data] GDPギャップ: {count} 件保存")

