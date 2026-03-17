# market-macro-analysis

日銀マクロ経済モニタリング＆予測ツール。

日本銀行の「マクロ経済の見取り図」フレームワーク（金融・経済・物価の3ブロック構造）に基づき、各種経済指標をリアルタイムで可視化し、将来の政策金利パスを予測する。

## セットアップ

```bash
uv sync --extra dev
```

## 使い方

```bash
uv run python main.py <stage_type> <block_type>
```

| stage_type | 説明 |
|-----------|------|
| `fetch_data` | 経済指標データを各APIから取得しDBへ保存 |
| `make_chart` | 時系列チャートを生成 |
| `make_report` | 現状サマリーレポートを生成 |

| block_type | 説明 |
|-----------|------|
| `all` | 全ブロック |
| `financial` | 金融ブロック（政策金利・実質金利） |
| `economic` | 経済ブロック（GDP・GDPギャップ） |
| `price` | 物価ブロック（CPI・賃金） |

## テスト

```bash
uv run pytest
```

## 仕様書

`docs/spec/macro_analysis_tool_spec.md` を参照。
