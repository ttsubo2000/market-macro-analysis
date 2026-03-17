"""
E2E テスト: 物価ブロック データ取得（コアCPI）

実際の e-Stat API を使い、コアCPIの取得・DB保存の一連フローを検証する。

実行方法:
  uv run pytest tests/e2e/ -m e2e -v -s          # 全 E2E テスト実行
  uv run pytest tests/e2e/ -m e2e -v -s -k 01    # このファイルのみ実行
"""
import pytest
from market_macro_analysis.controller import fetch_controller


@pytest.mark.e2e
def test_01_fetch_core_cpi(e2e_db):
    """e-Stat API からコアCPIを取得して DB に保存できること"""
    fetch_controller.fetch_price_data(e2e_db)

    rows = e2e_db.execute(
        "SELECT date, indicator, value, unit FROM price_data ORDER BY date DESC LIMIT 5"
    ).fetchall()

    print("\n[E2E] 取得データ（直近5件）:")
    for row in rows:
        print(f"  {row[0]}  {row[1]}  {row[2]}{row[3]}")

    # 1件以上保存されていること
    assert len(rows) > 0, "price_data テーブルにデータが保存されていない"

    # 指標名が正しいこと
    assert all(row[1] == "core_cpi_yoy" for row in rows)

    # 単位が % であること
    assert all(row[3] == "%" for row in rows)

    # 直近の値が妥当な範囲内であること（-5% 〜 +10% の範囲）
    latest_value = rows[0][2]
    assert -5.0 <= latest_value <= 10.0, f"コアCPI の値が想定外: {latest_value}%"
