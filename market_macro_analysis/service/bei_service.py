import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from market_macro_analysis.config import (
    BEI_URL,
    MAX_RETRY_COUNT,
    RETRY_WAIT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)
from market_macro_analysis.exceptions import FetchError, DataStoreError


def fetch_bei() -> list[dict]:
    """stock-marketdata.com から BEI（ブレーク・イーブン・インフレ率）の最新値を取得する。

    取得先: https://stock-marketdata.com/bei.html
    データ: 日本相互証券（JBTS）データベースを出典とする日次 BEI（%）

    冪等性: 同じ日付のデータを何度取得しても upsert で1レコードに収束する。

    Returns:
        list of dict: [{"date": "2026-05-29", "value": 2.172}, ...]
    """
    for attempt in range(MAX_RETRY_COUNT):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; market-macro-analysis/1.0)"}
            response = requests.get(BEI_URL, timeout=REQUEST_TIMEOUT_SECONDS, headers=headers)
            response.raise_for_status()
            return _parse_html(response.content)
        except requests.RequestException as e:
            if attempt == MAX_RETRY_COUNT - 1:
                raise FetchError(f"BEI ページへのアクセスに失敗しました: {e}") from e
            time.sleep(RETRY_WAIT_SECONDS)
    return []


def _parse_html(content: bytes) -> list[dict]:
    """HTML から BEI の日付・値のリストを返す。

    stock-marketdata.com/bei.html のテーブル構造:
      列0: 日付（YYYY/MM/DD 形式）
      列1: BEI 値（%）
    直近12営業日分のデータが静的テーブルに含まれる。
    """
    try:
        soup = BeautifulSoup(content, "html.parser")
    except Exception as e:
        raise FetchError(f"BEI HTML のパースに失敗しました: {e}") from e

    result = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            date_text = cells[0].get_text(strip=True)
            value_text = cells[1].get_text(strip=True)

            date = _parse_date(date_text)
            if date is None:
                continue

            try:
                value = float(value_text)
            except ValueError:
                continue

            result.append({"date": date, "value": value})

    return sorted(result, key=lambda x: x["date"])


def _parse_date(date_text: str) -> str | None:
    """'YYYY/MM/DD' 形式を 'YYYY-MM-DD' に変換する。不正な場合は None を返す。"""
    parts = date_text.replace("-", "/").split("/")
    if len(parts) != 3:
        return None
    year, month, day = parts
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return None
    if len(year) != 4:
        return None
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def save_bei(conn: sqlite3.Connection, records: list[dict]) -> int:
    """BEI レコードを financial_data テーブルに保存する（重複は上書き・冪等）。

    同一 date・indicator の組み合わせは INSERT OR REPLACE により upsert される。
    records が空の場合は 0 を返して正常終了する。

    Returns:
        int: 保存件数
    """
    if not records:
        return 0
    _ensure_table(conn)
    try:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO financial_data (date, indicator, value, unit)
            VALUES (?, ?, ?, ?)
            """,
            [(r["date"], "bei", r["value"], "%") for r in records],
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
