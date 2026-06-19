"""
JSDA「公社債店頭売買参考統計値」CSVから期待インフレ率(簡易BEI)を算出するプロトタイプ

背景:
  - stock-marketdata.com由来のBEIは更新が不定期で時系列を継続的に積み上げられない
  - JSDAは毎営業日、公社債（国債含む）の売買参考統計値をCSVで公開しており、
    URLパターンが日付から機械的に決まるため、継続的な自動取得が可能
  - 物価連動国債の利回りと、同程度の残存年限を持つ名目国債の利回りの差分から
    簡易的なBEI（Break-Even Inflation）を算出する

注意:
  - 本スクリプトは列インデックスをJSDA公開PDF仕様書とサンプル行から推定して実装している。
    実データ取得後、`docs/csvheaderbaisan.xlsx`（JSDA公式ヘッダー定義）と突き合わせて
    列インデックスのズレがないか必ず検証すること。
  - 物価連動国債の「銘柄種別コード」が具体的に何の値かは未確定。
    本スクリプトでは銘柄名(漢字)に "物価連動" を含むかどうかでフィルタする
    フォールバック方式を採用している（文字コードはShift-JIS）。
  - 実行環境のネットワーク制限により、Claude側ではこのスクリプトの実行確認ができていない。
    ローカル環境(Mac mini等)で実行し、出力を確認すること。
"""

from __future__ import annotations

import csv
import io
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import requests

JSDA_BASE_URL = "https://market.jsda.or.jp/shijyo/saiken/baibai/baisanchi/files"

# CSVの列インデックス（0始まり）。PDF仕様書とサンプル行から推定。
# 実データで要検証。
COL_DATE = 0
COL_TYPE = 1          # 銘柄種別コード（01:国庫短期証券 等）
COL_CODE = 2          # 銘柄コード
COL_NAME = 3          # 銘柄名（漢字、Shift-JIS）
COL_MATURITY = 4      # 償還年月日 (YYYYMMDD)
COL_COUPON_RATE = 5   # 利率
COL_AVG_COMPOUND = 6  # 平均値複利（利回り、%）
COL_AVG_PRICE = 7     # 平均値単価
COL_AVG_PRICE_DIFF = 8

# 銘柄種別コード「05」= 物価連動国債（JSDAのCSVで実測済み・2026年6月確認）
INFLATION_BOND_TYPE_CODE = "05"

# 物価連動国債の表面利率（Nikkei JS Price 2024/6時点の情報等から確認。
# 新発債が出るたびに追加・更新が必要）
INFLATION_BOND_COUPONS = {
    "000220083": 0.1,    # 物価連動国債 22 (2027/3/10)
    "000230083": 0.1,    # 物価連動国債 23 (2028/3/10)
    "000240083": 0.1,    # 物価連動国債 24 (2029/3/10)
    "000250083": 0.2,    # 物価連動国債 25 (2030/3/10)
    "000260083": 0.005,  # 物価連動国債 26 (2031/3/10)
    "000270083": 0.005,  # 物価連動国債 27 (2032/3/10)
    "000280083": 0.005,  # 物価連動国債 28 (2033/3/10)
    "000290083": 0.005,  # 物価連動国債 29 (2034/3/10) ※推定。要確認
    "000300083": 0.005,  # 物価連動国債 30 (2035/3/10) ※推定。要確認
    "000310083": 0.005,  # 物価連動国債 31 (2036/3/10) ※推定。要確認
}

# stock-marketdata.com 掲載の参照値（2026/5/18-5/29、検証用）
REFERENCE_BEI = {
    "2026-05-29": 2.172,
    "2026-05-28": 2.208,
    "2026-05-27": 2.245,
    "2026-05-26": 2.277,
    "2026-05-25": 2.276,
    "2026-05-22": 2.276,
    "2026-05-21": 2.271,
    "2026-05-20": 2.268,
    "2026-05-19": 2.276,
    "2026-05-18": 2.258,
}


@dataclass
class BondQuote:
    trade_date: date
    bond_type: str
    code: str
    name: str
    maturity: Optional[date]
    coupon_rate: Optional[float]
    avg_compound_yield: Optional[float]  # 複利利回り(%)
    avg_price: Optional[float]

    @property
    def years_to_maturity(self) -> Optional[float]:
        if self.maturity is None:
            return None
        return (self.maturity - self.trade_date).days / 365.25

    @property
    def is_inflation_indexed(self) -> bool:
        # 銘柄種別コード「05」が物価連動国債（2026年6月にJSDA実データで確認済み）
        return self.bond_type == INFLATION_BOND_TYPE_CODE

    def real_yield_from_price(self) -> Optional[float]:
        """物価連動国債は利回り欄が報告対象外(999.999)で、単価のみ有効なため、
        単価からクーポン・残存年限を使って複利YTM(実質利回り)を逆算する。

        連動係数（CPIによる元本調整）は無視した近似値。
        """
        coupon = INFLATION_BOND_COUPONS.get(self.code)
        if coupon is None or self.avg_price is None or self.years_to_maturity is None:
            return None
        return _solve_ytm(
            price=self.avg_price,
            coupon_rate=coupon,
            years=self.years_to_maturity,
        )


def _solve_ytm(
    price: float, coupon_rate: float, years: float, face: float = 100.0
) -> Optional[float]:
    """半年複利の利付債について、単価からYTM(%)をニュートン法で逆算する。

    半年ごとのクーポン = face * coupon_rate / 100 / 2
    n = 半年期の数（残存年数 * 2、四捨五入せず連続値として扱う簡易近似）
    """
    n_periods = years * 2
    coupon_payment = face * coupon_rate / 100 / 2

    def price_given_yield(y_annual_pct: float) -> float:
        y = y_annual_pct / 100 / 2  # 半年複利のレート
        if y <= -1:
            return float("inf")
        # 残存期間を連続値として近似（割引係数を (1+y)^n_periods で計算）
        discount = (1 + y) ** n_periods
        if discount == 0:
            return float("inf")
        pv_coupons = coupon_payment * (1 - 1 / discount) / y if y != 0 else coupon_payment * n_periods
        pv_face = face / discount
        return pv_coupons + pv_face

    # ニュートン法（数値微分）で price_given_yield(y) = price となる y を求める
    y = coupon_rate if coupon_rate > 0 else 0.5  # 初期値
    for _ in range(100):
        f = price_given_yield(y) - price
        df = (price_given_yield(y + 1e-4) - price_given_yield(y - 1e-4)) / (2e-4)
        if df == 0:
            break
        y_new = y - f / df
        if abs(y_new - y) < 1e-6:
            y = y_new
            break
        y = y_new
    return round(y, 4)


def _parse_float(value: str) -> Optional[float]:
    value = value.strip()
    if not value or value in ("-----", "999.999", "999.99", "99.999"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    if not value or len(value) != 8:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def build_url(trade_date: date) -> str:
    """発表日付からJSDAのCSVダウンロードURLを組み立てる。

    ファイル名規則: S{YYMMDD}.csv（YYは西暦の下2桁）
    """
    yymmdd = trade_date.strftime("%y%m%d")
    year = trade_date.strftime("%Y")
    return f"{JSDA_BASE_URL}/{year}/S{yymmdd}.csv"


def fetch_csv_text(trade_date: date, timeout: int = 60, retries: int = 3) -> str:
    """指定日のCSVをダウンロードし、Shift-JISでデコードして返す。"""
    url = build_url(trade_date)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    last_exc = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
            # JSDAのCSVはShift-JIS(CP932)で配信される
            return resp.content.decode("cp932", errors="replace")
        except requests.exceptions.RequestException as e:
            last_exc = e
            print(
                f"  [RETRY {attempt + 1}/{retries}] {trade_date.isoformat()} 取得失敗: {e}",
                file=sys.stderr,
            )
            if attempt < retries - 1:
                time.sleep(3)
    raise last_exc


def parse_quotes(csv_text: str) -> list[BondQuote]:
    quotes: list[BondQuote] = []
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if len(row) <= COL_AVG_PRICE_DIFF:
            continue
        trade_date = _parse_date(row[COL_DATE])
        if trade_date is None:
            continue
        quotes.append(
            BondQuote(
                trade_date=trade_date,
                bond_type=row[COL_TYPE].strip(),
                code=row[COL_CODE].strip(),
                name=row[COL_NAME].strip(),
                maturity=_parse_date(row[COL_MATURITY]),
                coupon_rate=_parse_float(row[COL_COUPON_RATE]),
                avg_compound_yield=_parse_float(row[COL_AVG_COMPOUND]),
                avg_price=_parse_float(row[COL_AVG_PRICE]),
            )
        )
    return quotes


def nearest_nominal_bond(
    quotes: list[BondQuote], target_years: float
) -> Optional[BondQuote]:
    """物価連動国債と残存年限が最も近い名目国債(利付国庫債券)を探す。"""
    candidates = [
        q
        for q in quotes
        if not q.is_inflation_indexed
        and q.avg_compound_yield is not None
        and q.years_to_maturity is not None
        and q.years_to_maturity > 0
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda q: abs((q.years_to_maturity or 0) - target_years),
    )


def calc_simple_bei(quotes: list[BondQuote]) -> list[dict]:
    """物価連動国債ごとに、残存年限が近い名目国債との差分から簡易BEIを算出する。"""
    results = []
    inflation_bonds = [q for q in quotes if q.is_inflation_indexed]

    if not inflation_bonds:
        print(
            "[WARN] 物価連動国債（銘柄種別コード05）が見つかりませんでした。",
            file=sys.stderr,
        )

    for ib in inflation_bonds:
        if ib.years_to_maturity is None:
            continue
        real_yield = ib.real_yield_from_price()
        if real_yield is None:
            # 表面利率が未登録の銘柄。INFLATION_BOND_COUPONSへの追加が必要。
            continue
        nominal = nearest_nominal_bond(quotes, ib.years_to_maturity)
        if nominal is None or nominal.avg_compound_yield is None:
            continue
        bei = nominal.avg_compound_yield - real_yield
        results.append(
            {
                "trade_date": ib.trade_date.isoformat(),
                "inflation_bond_name": ib.name,
                "inflation_bond_price": ib.avg_price,
                "inflation_bond_real_yield": real_yield,
                "inflation_bond_maturity": ib.maturity.isoformat() if ib.maturity else None,
                "nominal_bond_name": nominal.name,
                "nominal_bond_yield": nominal.avg_compound_yield,
                "nominal_bond_maturity": nominal.maturity.isoformat() if nominal.maturity else None,
                "years_diff": round(
                    abs((nominal.years_to_maturity or 0) - ib.years_to_maturity), 2
                ),
                "simple_bei_pct": round(bei, 3),
            }
        )
    return results


def average_bei(results: list[dict]) -> Optional[float]:
    """非推奨: 複数銘柄の単純平均は残存年限の異なるBEIを混在させてしまうため、
    本来の「10年BEI」とは整合しない。後方互換のために残しているが、
    select_10y_bei() の利用を推奨する。"""
    values = [r["simple_bei_pct"] for r in results if r.get("simple_bei_pct") is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def select_10y_bei(results: list[dict], target_years: float = 10.0) -> Optional[dict]:
    """stock-marketdata.com等が公表する「10年BEI」相当の値を再現するため、
    物価連動国債の残存年限が10年に最も近い1銘柄のみを採用する。

    複数銘柄を平均すると、残存が短く流動性の低い銘柄のノイズが混入し、
    本来の指標とズレる（実証済み：平均方式では系統的に+0.6%程度のズレが発生）。
    """
    candidates = [r for r in results if r.get("years_diff") is not None]
    if not candidates:
        return None

    # results内には物価連動国債自体の残存年限情報を持たせていないため、
    # inflation_bond_maturity と trade_date から逆算する
    def years_to_mat(r: dict) -> float:
        maturity = datetime.strptime(r["inflation_bond_maturity"], "%Y-%m-%d").date()
        trade = datetime.strptime(r["trade_date"], "%Y-%m-%d").date()
        return (maturity - trade).days / 365.25

    best = min(candidates, key=lambda r: abs(years_to_mat(r) - target_years))
    return best


def run_for_date(target_date: date, verbose: bool = True) -> Optional[float]:
    """指定日のCSVを取得し、残存10年に最も近い物価連動国債1本から簡易BEIを返す。"""
    if verbose:
        print(f"\n対象日付: {target_date.isoformat()}")
        print(f"取得URL: {build_url(target_date)}")
    try:
        csv_text = fetch_csv_text(target_date)
    except requests.exceptions.RequestException as e:
        print(f"[SKIP] {target_date.isoformat()}: 取得エラー ({e})", file=sys.stderr)
        return None

    quotes = parse_quotes(csv_text)
    if verbose:
        print(f"取得行数: {len(quotes)}")

    results = calc_simple_bei(quotes)
    if not results:
        print(f"[WARN] {target_date.isoformat()}: 簡易BEIを算出できませんでした。")
        return None

    if verbose:
        print("--- 銘柄別 簡易BEI（参考：全銘柄） ---")
        for r in results:
            print(
                f"  {r['inflation_bond_name']} (残存差{r['years_diff']}年) vs "
                f"{r['nominal_bond_name']}: 簡易BEI = {r['simple_bei_pct']}% "
                f"(名目{r['nominal_bond_yield']}% - 実質{r['inflation_bond_real_yield']}%, "
                f"単価{r['inflation_bond_price']})"
            )

    best = select_10y_bei(results)
    if best is None:
        return None
    if verbose:
        print(f"--- 採用銘柄（残存10年に最も近い）: {best['inflation_bond_name']} ---")
    return best["simple_bei_pct"]


def run_verify():
    """stock-marketdata.com掲載の参照値(REFERENCE_BEI)と、JSDAベースの簡易BEIを
    日付ごとに比較し、乖離を表示する。"""
    print("=== 参照値(stock-marketdata.com)との比較検証 ===")
    print(f"{'日付':<12} {'参照値':>8} {'簡易BEI':>8} {'乖離':>8}")
    diffs = []
    for date_str, ref_value in sorted(REFERENCE_BEI.items()):
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        computed = run_for_date(target_date, verbose=False)
        time.sleep(1)  # サーバー負荷軽減のため軽く間隔を空ける
        if computed is None:
            print(f"{date_str:<12} {ref_value:>8.3f} {'N/A':>8} {'N/A':>8}")
            continue
        diff = round(computed - ref_value, 3)
        diffs.append(diff)
        print(f"{date_str:<12} {ref_value:>8.3f} {computed:>8.3f} {diff:>+8.3f}")

    if diffs:
        avg_abs_diff = round(sum(abs(d) for d in diffs) / len(diffs), 3)
        print(f"\n平均絶対誤差: {avg_abs_diff}%")
        if avg_abs_diff <= 0.1:
            print("→ 近似精度は良好です（±0.1%以内）。")
        else:
            print("→ 乖離が大きめです。連動係数の無視や残存年限マッチングの影響を確認してください。")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        run_verify()
        return

    target_date = date.today()
    if len(sys.argv) > 1:
        target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()

    bei = run_for_date(target_date)
    if bei is not None:
        print(f"\nその日の10年BEI（簡易推定）: {bei}%")


if __name__ == "__main__":
    main()
