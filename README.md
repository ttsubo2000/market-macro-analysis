# market-macro-analysis

日銀の「マクロ経済の見取り図」フレームワークに基づき、経済・物価・金融の現状をモニタリングするツール。
各種公開データを自動取得して SQLite に蓄積し、時系列チャートとサマリーレポートを生成する。

## クイックスタート

```bash
uv sync --extra dev
uv run python main.py fetch_data all
uv run python main.py make_chart all
uv run python main.py make_report all
```

## ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [利用方法ガイド](docs/guide/usage.md) | セットアップ・コマンド・出力ファイルの詳細 |
| [仕様書](docs/spec/macro_analysis_tool_spec.md) | システム設計・フレームワーク定義 |

## テスト

```bash
uv run pytest tests/unit/
```
