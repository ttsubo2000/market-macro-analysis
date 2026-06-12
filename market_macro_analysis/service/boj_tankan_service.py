import io
import time
import zipfile
import requests
import sqlite3
from market_macro_analysis.config import (
    BOJ_TANKAN_ZIP_URL,
    BOJ_TANKAN_PRICE_OUTLOOK_CODE,
    MAX_RETRY_COUNT,
    RETRY_WAIT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from market_macro_analysis.exceptions import FetchError, DataStoreError


def fetch_price_outlook(limit: int = 40) -> list[dict]:
    """日銀短観 co.zip から企業物価見通し（大企業・全産業計・1年後）を取得する。

    **算出方法**: 日銀短観「企業物価見通し（大企業・全産業計・1年後の消費者物価変化率・中央値）」
    系列コード TK99F0000201HCQ00000 の値を使用。
    大企業が1年後の消費者物価上昇率を何%と見込んでいるかの回答中央値。

    **時系列構築**: co.zip は最新四半期のみを収録する。
    fetch_data を毎四半期実行するたびにDBに追記・upsert され、時系列が蓄積される。

    Returns:
        list of dict: [{"date": "2026-Q1", "value": 3.1}, ...]
    """
    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = requests.get(BOJ_TANKAN_ZIP_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return _parse_zip(response.content)
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"日銀短観 co.zip へのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)


def _parse_zip(content: bytes) -> list[dict]:
    """co.zip から co.csv を展開し、物価見通し系列を抽出する。"""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            with zf.open("co.csv") as f:
                csv_bytes = f.read()
    except (zipfile.BadZipFile, KeyError) as e:
        raise FetchError(f"co.zip の展開に失敗しました: {e}") from e

    return _parse_csv(csv_bytes)


def _parse_csv(content: bytes) -> list[dict]:
    """co.csv をパースして物価見通し系列の [date, value] リストを返す。

    CSV フォーマット:
      列0: 系列コード
      列1: 頻度（Q=四半期）
      列2: 年または年Q（例: 202601 = 2026年第1四半期）
      列3: 値
    """
    try:
        text = content.decode("cp932", errors="replace")
    except Exception as e:
        raise FetchError(f"co.csv のデコードに失敗しました: {e}") from e

    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue

        code, freq, date_str, value_str = parts[0], parts[1], parts[2], parts[3]

        if code != BOJ_TANKAN_PRICE_OUTLOOK_CODE:
            continue
        if freq != "Q":
            continue

        date = _parse_quarter(date_str)
        if date is None:
            continue

        if value_str in ("", "-", "ND", "***"):
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue

        result.append({"date": date, "value": value})

    return sorted(result, key=lambda x: x["date"])


def _parse_quarter(date_str: str) -> str | None:
    """日銀短観の日付コード（例: 202601）を YYYY-QN 形式に変換する。

    日銀短観の四半期コード:
      末尾2桁: 01=Q1（3月調査）, 04=Q2（6月調査）,
               07=Q3（9月調査）, 10=Q4（12月調査）
    """
    if len(date_str) != 6 or not date_str.isdigit():
        return None
    year = date_str[:4]
    month_code = date_str[4:6]
    quarter_map = {"01": "Q1", "04": "Q2", "07": "Q3", "10": "Q4"}
    quarter = quarter_map.get(month_code)
    if quarter is None:
        return None
    return f"{year}-{quarter}"


def save_price_outlook(conn: sqlite3.Connection, records: list[dict]) -> int:
    """企業物価見通しレコードを financial_data テーブルに保存する（重複は上書き）。

    Returns:
        int: 保存件数
    """
    _ensure_table(conn)
    try:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO financial_data (date, indicator, value, unit)
            VALUES (?, ?, ?, ?)
            """,
            [(r["date"], "expected_inflation_1y", r["value"], "%") for r in records],
        )
        return len(records)
    except sqlite3.Error as e:
        raise DataStoreError(f"financial_data への保存に失敗しました: {e}") from e


def _ensure_table(conn: sqlite3.Connection) -> None:
    """financial_data テーブルが存在しない場合は作成する。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_data (
            date      TEXT NOT NULL,
            indicator TEXT NOT NULL,
            value     REAL NOT NULL,
            unit      TEXT NOT NULL,
            PRIMARY KEY (date, indicator)
        )
        """
    )
