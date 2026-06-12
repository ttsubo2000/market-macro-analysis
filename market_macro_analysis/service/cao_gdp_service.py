import io
import re
import time
import requests
import sqlite3
import openpyxl
from market_macro_analysis.config import (
    CAO_GDP_INDEX_URL,
    MAX_RETRY_COUNT,
    RETRY_WAIT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from market_macro_analysis.exceptions import FetchError, DataStoreError

# ローマ数字四半期 → 数字マッピング
_QUARTER_MAP = {"Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4}

# データ開始行（0始まり）: 先頭6行はヘッダー・メタデータ
_DATA_START_ROW = 6


def _resolve_latest_gap_url() -> str:
    """インデックスページから最新の gap.xlsx URL を取得する。"""
    try:
        response = requests.get(CAO_GDP_INDEX_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as e:
        raise FetchError(f"内閣府インデックスページへのアクセスに失敗しました: {e}") from e

    matches = re.findall(r'href=["\']([^"\']*[0-9]{4}gap\.xlsx)["\']', response.text)
    if not matches:
        raise FetchError("内閣府インデックスページで gap.xlsx のリンクが見つかりませんでした")

    href = matches[-1]
    if href.startswith("http"):
        return href
    return "https://www.cao.go.jp" + (href if href.startswith("/") else "/" + href)


def fetch_gdp_gap(limit: int = 120) -> list[dict]:
    """内閣府月例経済報告から需給ギャップ（四半期）を取得する。

    Returns:
        list of dict: [{"date": "2024-Q4", "value": 0.1}, ...]
    """
    xlsx_url = _resolve_latest_gap_url()
    for attempt in range(MAX_RETRY_COUNT):
        try:
            response = requests.get(xlsx_url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            records = _parse_xlsx(response.content)
            return records[-limit:] if len(records) > limit else records
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"内閣府 GDP ギャップ xlsx へのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)


def _parse_xlsx(content: bytes) -> list[dict]:
    """内閣府GDPギャップ xlsx をパースして日付・値のリストを返す。

    フォーマット（シート「四半期」）:
      列0: 年（Q1のみ値あり、Q2-Q4は空）
      列1: 四半期（Ⅰ / Ⅱ / Ⅲ / Ⅳ）
      列2: GDPギャップ（%）
      行1-6: ヘッダー・メタデータ（スキップ）
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb["四半期"]
    except Exception as e:
        raise FetchError(f"内閣府 GDP ギャップ xlsx のオープンに失敗しました: {e}") from e

    result = []
    current_year = None

    for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
        if row_idx < _DATA_START_ROW:
            continue

        year_cell = row[0]
        quarter_cell = row[1]
        value_cell = row[2]

        # 年の引き継ぎ（Q2-Q4 は年列が空）
        if isinstance(year_cell, int):
            current_year = year_cell

        if current_year is None:
            continue

        quarter_num = _QUARTER_MAP.get(quarter_cell)
        if quarter_num is None:
            continue

        if value_cell is None or value_cell == "" or value_cell == "-":
            continue
        try:
            value = float(value_cell)
        except (ValueError, TypeError):
            continue

        date = f"{current_year}-Q{quarter_num}"
        result.append({"date": date, "value": value})

    wb.close()
    return sorted(result, key=lambda x: x["date"])


def save_gdp_gap(conn: sqlite3.Connection, records: list[dict]) -> int:
    """GDPギャップレコードを economic_data テーブルに保存する（重複は上書き）。

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
            [(r["date"], "gdp_gap", r["value"], "%") for r in records],
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
