import time
import requests
import sqlite3
from market_macro_analysis.config import (
    BOJ_CALL_RATE_CSV_URL,
    MAX_RETRY_COUNT,
    RETRY_WAIT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from market_macro_analysis.exceptions import FetchError, DataStoreError


def fetch_policy_rate(limit: int = 120) -> list[dict]:
    """日銀時系列統計DBから政策金利（無担保コールレート翌日物・月次平均）を取得する。

    Returns:
        list of dict: [{"date": "2025-12", "value": 0.25}, ...]
    """
    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = requests.get(BOJ_CALL_RATE_CSV_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            records = _parse_csv(response.content)
            return records[-limit:] if len(records) > limit else records
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"日銀CSV へのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)


def _parse_csv(content: bytes) -> list[dict]:
    """日銀CSV（Shift-JIS）をパースして日付・値のリストを返す。

    CSV フォーマット（fm02_m_1.csv）:
      列0: YYYY/MM（日付）
      列1: 月末値
      列2: 月平均値  ← こちらを使用

    ヘッダー・メタデータ行は YYYY/MM 形式に一致しないためスキップされる。
    """
    try:
        text = content.decode("cp932")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")

    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 3:
            continue

        date_part = parts[0]
        value_part = parts[2]  # 月平均値（列2）

        # YYYY/MM 形式の日付のみ対象とする
        if "/" not in date_part:
            continue
        date_tokens = date_part.split("/")
        if len(date_tokens) != 2:
            continue
        year_str, month_str = date_tokens
        if not (year_str.isdigit() and month_str.isdigit()):
            continue

        date = f"{year_str}-{month_str.zfill(2)}"

        if value_part in ("", "-", "ND", "***"):
            continue
        try:
            value = float(value_part)
        except ValueError:
            continue

        result.append({"date": date, "value": value})

    return sorted(result, key=lambda x: x["date"])


def save_policy_rate(conn: sqlite3.Connection, records: list[dict]) -> int:
    """政策金利レコードを financial_data テーブルに保存する（重複は上書き）。

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
            [(r["date"], "policy_rate", r["value"], "%") for r in records],
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
