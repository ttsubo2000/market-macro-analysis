import time
import requests
import sqlite3
from market_macro_analysis.config import (
    ESTAT_API_BASE_URL,
    ESTAT_CPI_STATS_DATA_ID,
    ESTAT_CPI_CAT01_CORE,
    ESTAT_CPI_TAB_YOY,
    ESTAT_CPI_AREA_NATIONAL,
    MAX_RETRY_COUNT,
    RETRY_WAIT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from market_macro_analysis.exceptions import FetchError, DataStoreError


def fetch_core_cpi(app_id: str, limit: int = 120) -> list[dict]:
    """e-Stat API からコアCPI（生鮮食品を除く総合・前年同月比・全国）を取得する。

    Returns:
        list of dict: [{"date": "2025-12", "value": 2.4}, ...]
    """
    url = f"{ESTAT_API_BASE_URL}/json/getStatsData"
    params = {
        "appId": app_id,
        "statsDataId": ESTAT_CPI_STATS_DATA_ID,
        "cdTab": ESTAT_CPI_TAB_YOY,
        "cdCat01": ESTAT_CPI_CAT01_CORE,
        "cdArea": ESTAT_CPI_AREA_NATIONAL,
        "limit": limit,
        "metaGetFlg": "N",
    }

    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return _parse_response(response.json())
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"e-Stat API へのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)


def _parse_response(data: dict) -> list[dict]:
    """API レスポンスから日付・値のリストを返す。"""
    try:
        values = (
            data["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
        )
    except (KeyError, TypeError) as e:
        raise FetchError(f"e-Stat API レスポンスのパースに失敗しました: {e}") from e

    if isinstance(values, dict):
        values = [values]

    result = []
    for v in values:
        time_code = v.get("@time", "")
        raw_value = v.get("$", "")
        if not time_code or raw_value in ("", "-", "***"):
            continue
        result.append({
            "date": _parse_time_code(time_code),
            "value": float(raw_value),
        })

    return sorted(result, key=lambda x: x["date"])


def _parse_time_code(time_code: str) -> str:
    """e-Stat の時刻コード（例: 2025001212）を YYYY-MM 形式に変換する。"""
    # フォーマット: YYYY00MMDD → YYYY-MM
    year = time_code[:4]
    month = time_code[6:8]
    return f"{year}-{month}"


def save_core_cpi(conn: sqlite3.Connection, records: list[dict]) -> int:
    """コアCPIレコードを price_data テーブルに保存する（重複は上書き）。

    Returns:
        int: 保存件数
    """
    _ensure_table(conn)
    try:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO price_data (date, indicator, value, unit)
            VALUES (?, ?, ?, ?)
            """,
            [(r["date"], "core_cpi_yoy", r["value"], "%") for r in records],
        )
        return len(records)
    except sqlite3.Error as e:
        raise DataStoreError(f"price_data への保存に失敗しました: {e}") from e


def _ensure_table(conn: sqlite3.Connection) -> None:
    """price_data テーブルが存在しない場合は作成する。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_data (
            date      TEXT NOT NULL,
            indicator TEXT NOT NULL,
            value     REAL NOT NULL,
            unit      TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
