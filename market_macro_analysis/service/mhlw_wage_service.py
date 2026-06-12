import time
import requests
import sqlite3
from market_macro_analysis.config import (
    ESTAT_API_BASE_URL,
    MHLW_WAGE_STATS_DATA_ID,
    MAX_RETRY_COUNT,
    RETRY_WAIT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from market_macro_analysis.exceptions import FetchError, DataStoreError


def fetch_scheduled_wage_yoy(app_id: str, limit: int = 120) -> list[dict]:
    """e-Stat API から所定内給与前年比（就業形態計・全産業・5人以上）を取得する。

    getMetaInfo でカテゴリコードを動的解決してから getStatsData を呼び出す 2 フェーズ方式。

    Returns:
        list of dict: [{"date": "2025-12", "value": 2.1}, ...]
    """
    codes = _resolve_filter_codes(app_id)
    url = f"{ESTAT_API_BASE_URL}/json/getStatsData"
    params = {
        "appId": app_id,
        "statsDataId": MHLW_WAGE_STATS_DATA_ID,
        "cdTab": codes["tab"],
        "cdCat01": codes["cat01"],
        "cdCat02": codes["cat02"],
        "cdCat03": codes["cat03"],
        "limit": limit,
        "metaGetFlg": "N",
    }

    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return _parse_data_response(response.json())
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"e-Stat API へのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)


def _resolve_filter_codes(app_id: str) -> dict:
    """getMetaInfo から所定内給与のフィルタコードを動的に解決する。"""
    url = f"{ESTAT_API_BASE_URL}/json/getMetaInfo"
    params = {"appId": app_id, "statsDataId": MHLW_WAGE_STATS_DATA_ID}

    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return _parse_meta_response(response.json())
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"e-Stat getMetaInfo へのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)


def _parse_meta_response(data: dict) -> dict:
    """getMetaInfo レスポンスから前年比・就業形態計・全産業・5人以上のコードを解決する。"""
    try:
        class_objs = data["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    except (KeyError, TypeError) as e:
        raise FetchError(f"getMetaInfo レスポンスのパースに失敗しました: {e}") from e

    if isinstance(class_objs, dict):
        class_objs = [class_objs]

    # CLASS_OBJ を {obj_id: {code: name}} 形式に変換
    class_map: dict[str, dict[str, str]] = {}
    for obj in class_objs:
        obj_id = obj.get("@id", "")
        classes = obj.get("CLASS", [])
        if isinstance(classes, dict):
            classes = [classes]
        class_map[obj_id] = {c.get("@code", ""): c.get("@name", "") for c in classes}

    tab_code = _find_code_by_keyword(class_map.get("tab", {}), "前年比")
    cat01_map = class_map.get("cat01", {})
    cat01_code = (
        _find_code_by_keyword(cat01_map, "就業形態計")
        or _find_code_by_keyword(cat01_map, "就業形態別計")
        or _find_code_by_keyword(cat01_map, "就業形態_計")
    )
    cat02_map = class_map.get("cat02", {})
    cat02_code = (
        _find_code_by_keyword(cat02_map, "産業計")
        or _find_code_by_keyword(cat02_map, "全産業")
        or next(iter(cat02_map), None)
    )
    cat03_map = class_map.get("cat03", {})
    cat03_code = _find_code_by_keyword(cat03_map, "5人以上") or next(iter(cat03_map), None)

    missing = [k for k, v in [("tab", tab_code), ("cat01", cat01_code), ("cat02", cat02_code), ("cat03", cat03_code)] if v is None]
    if missing:
        available = {k: list(v.values())[:5] for k, v in class_map.items()}
        raise FetchError(
            f"getMetaInfo から必要なコードが解決できませんでした: {missing}\n"
            f"利用可能なカテゴリ名称（先頭5件）: {available}"
        )

    return {"tab": tab_code, "cat01": cat01_code, "cat02": cat02_code, "cat03": cat03_code}


def _find_code_by_keyword(code_map: dict[str, str], keyword: str) -> str | None:
    """コード→名称の辞書からキーワードを含む名称に対応するコードを返す。"""
    for code, name in code_map.items():
        if keyword in name:
            return code
    return None


def _parse_data_response(data: dict) -> list[dict]:
    """getStatsData レスポンスから日付・値のリストを返す。"""
    try:
        values = data["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
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
    year = time_code[:4]
    month = time_code[6:8]
    return f"{year}-{month}"


def save_scheduled_wage(conn: sqlite3.Connection, records: list[dict]) -> int:
    """所定内給与前年比レコードを economic_data テーブルに保存する（重複は上書き）。

    Returns:
        int: 保存件数
    """
    _ensure_table(conn)
    try:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO economic_data (date, indicator, value, unit)
            VALUES (?, ?, ?, ?)
            """,
            [(r["date"], "scheduled_wage_yoy", r["value"], "%") for r in records],
        )
        return len(records)
    except sqlite3.Error as e:
        raise DataStoreError(f"economic_data への保存に失敗しました: {e}") from e


def _ensure_table(conn: sqlite3.Connection) -> None:
    """economic_data テーブルが存在しない場合は作成する。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS economic_data (
            date      TEXT NOT NULL,
            indicator TEXT NOT NULL,
            value     REAL NOT NULL,
            unit      TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
