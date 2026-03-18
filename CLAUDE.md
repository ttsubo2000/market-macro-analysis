# CLAUDE.md - market-macro-analysis

## プロジェクト概要

日銀の「マクロ経済の見取り図」フレームワークに基づき、経済・物価・金融の現状をモニタリングし、将来の政策金利パスを予測するツール。日銀統計DB・総務省e-Stat・内閣府GDPデータを取得し、SQLiteに蓄積。チャート生成とレポート作成を行う。

参考仕様書: `docs/spec/macro_analysis_tool_spec.md`

## 技術スタック

- **Python**: 3.13+
- **パッケージ管理**: uv
- **主要ライブラリ**: pandas, SQLAlchemy, matplotlib, japanize-matplotlib, requests, scikit-learn, statsmodels, yfinance
- **DB**: SQLite3 (`macro_analysis.db`)
- **テスト**: pytest, pytest-cov, pytest-mock

## コマンド

### 実行

```bash
uv run python main.py <stage_type> <block_type>
```

**stage_type**: `fetch_data` | `make_chart` | `make_report`

**block_type**: `all` | `financial` | `economic` | `price`

### テスト

```bash
uv run pytest                      # 全テスト実行（カバレッジ付き）
uv run pytest tests/unit/          # ユニットテストのみ
uv run pytest tests/integration/   # 統合テストのみ
uv run pytest -k "test_name"       # 特定テスト
```

### E2E テスト（手動実行）

**前提条件**: `estat-api.toml` がプロジェクトルートに存在すること

```bash
# E2E テスト全ステージ実行
uv run pytest tests/e2e/ -m e2e -v -s

# 特定ステージのみ実行（例: test_01 のみ）
uv run pytest tests/e2e/ -m e2e -v -s -k "test_01"

# カバレッジなしで実行
uv run pytest tests/e2e/ -m e2e -v -s --no-cov
```

**テストステージ一覧**

| ステージ | テスト名 | 内容 |
|---------|---------|------|
| 1 | test_01_fetch_price_data | e-Stat API からコアCPI取得・DB保存 |

## アーキテクチャ

```
market_macro_analysis/
├── config.py          # 設定・定数
├── exceptions.py      # 例外クラス
├── controller/        # ステージ処理の呼び出し層
└── service/           # データ取得・加工・DB操作の実装層
```

### ブロック構成（3ブロック構造）

| ブロック | 主要指標 | データソース |
|---------|---------|------------|
| 金融 (financial) | 政策金利・実質金利・自然利子率 | 日銀時系列統計DB |
| 経済 (economic) | GDP成長率・GDPギャップ・短観DI | 内閣府・日銀短観 |
| 物価 (price) | CPI・刈込平均・名目賃金 | 総務省e-Stat・厚労省 |

## 開発フェーズ

- **Phase 1 (MVP)**: データ取得・時系列チャート・現状サマリー
- **Phase 2**: シナリオ予測エンジン（VARモデル）
- **Phase 3**: 株式セクター連携・アラート機能

## 環境変数

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `MACRO_ANALYSIS_DB_NAME` | `macro_analysis.db` | DBファイルパス |
| `MACRO_ANALYSIS_REPORT_DIR` | `report/` | レポート出力先 |
| `MACRO_ANALYSIS_LOG_DIR` | `logs/` | ログ出力先 |
