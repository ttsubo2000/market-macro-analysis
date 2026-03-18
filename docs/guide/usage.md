# 利用方法ガイド

日銀の「マクロ経済の見取り図」フレームワークに基づき、経済・物価・金融の現状をモニタリングするツール。
各種公開データを自動取得して SQLite に蓄積し、時系列チャートとサマリーレポートを生成する。

---

## 目次

1. [動作要件](#動作要件)
2. [セットアップ](#セットアップ)
3. [API キーの設定](#api-キーの設定)
4. [基本的な使い方](#基本的な使い方)
5. [ステップごとの詳細](#ステップごとの詳細)
6. [出力ファイル](#出力ファイル)
7. [サマリーレポートの見方](#サマリーレポートの見方)
8. [取得データ一覧](#取得データ一覧)
9. [テスト](#テスト)

---

## 動作要件

- Python 3.13 以上
- [uv](https://docs.astral.sh/uv/)（パッケージマネージャー）
- 総務省 e-Stat API キー（無料・要ユーザー登録）

---

## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/ttsubo2000/market-macro-analysis.git
cd market-macro-analysis

# 依存パッケージをインストール
uv sync --extra dev
```

---

## API キーの設定

e-Stat（総務省統計ポータル）の API キーが必要です。

1. [e-Stat ユーザー登録](https://www.e-stat.go.jp/mypage/user/preregister) でアカウント作成
2. マイページから「API 機能（アプリケーション ID）」を発行
3. プロジェクトルートに `estat-api.toml` を作成（**このファイルは git 管理外**）

```toml
# estat-api.toml
[estat-api]
app_id = "YOUR_APP_ID_HERE"
```

> **注意**: 日銀・内閣府のデータは公開 URL から直接ダウンロードするため、追加のキー設定は不要です。

---

## 基本的な使い方

```
uv run python main.py <stage_type> <block_type>
```

### stage_type（処理ステージ）

| 値 | 説明 |
|----|------|
| `fetch_data` | 外部ソースからデータを取得して DB に保存 |
| `make_chart` | DB のデータから時系列チャート（PNG）を生成 |
| `make_report` | DB のデータから現状サマリーレポート（Markdown）を生成 |

### block_type（対象ブロック）

| 値 | 対象指標 |
|----|---------|
| `all` | 全ブロック（金融・経済・物価） |
| `financial` | 金融ブロック（政策金利） |
| `economic` | 経済ブロック（GDPギャップ） |
| `price` | 物価ブロック（コアCPI） |

---

## ステップごとの詳細

### Step 1: データ取得

```bash
# 全指標を一括取得（推奨）
uv run python main.py fetch_data all

# 個別取得
uv run python main.py fetch_data price      # コアCPI（e-Stat API）
uv run python main.py fetch_data financial  # 政策金利（日銀CSV）
uv run python main.py fetch_data economic   # GDPギャップ（内閣府xlsx）
```

取得されたデータは `macro_analysis.db`（SQLite）に蓄積されます。

### Step 2: チャート生成

```bash
# 全指標のチャートを一括生成（推奨）
uv run python main.py make_chart all

# 個別生成
uv run python main.py make_chart price      # コアCPI チャート
uv run python main.py make_chart financial  # 政策金利 チャート
uv run python main.py make_chart economic   # GDPギャップ チャート
```

### Step 3: サマリーレポート生成

```bash
uv run python main.py make_report all
```

---

## 出力ファイル

### データベース

| ファイル | 内容 |
|---------|------|
| `macro_analysis.db` | 全指標の時系列データ（SQLite） |

**テーブル構成**

```
price_data     : date, indicator, value, unit  ← コアCPI
financial_data : date, indicator, value, unit  ← 政策金利
economic_data  : date, indicator, value, unit  ← GDPギャップ
```

### チャート（PNG）

| ファイル | 内容 |
|---------|------|
| `report/png/cpi_chart.png` | コアCPI 前年比の時系列グラフ |
| `report/png/policy_rate_chart.png` | 政策金利（月平均）の時系列グラフ |
| `report/png/gdp_gap_chart.png` | 需給ギャップの四半期棒グラフ（正:赤/負:青） |
| `report/png/combined_chart.png` | 3指標を縦に並べた統合チャート |

### レポート（Markdown）

| ファイル | 内容 |
|---------|------|
| `report/summary.md` | 最新値・前回比・信号機評価の一覧表 |

---

## サマリーレポートの見方

`report/summary.md` を開くと以下のような表が表示されます。

```
| 指標 | 最新値 | 前回比 | 評価 |
|------|--------|--------|------|
| コアCPI（前年比） [2025-01] | 3.2% | ▲ 0.20 | 🟡 |
| 政策金利（月平均） [2025-01] | 0.500% | ▲ 0.03 | 🟢 |
| 需給ギャップ [2024-Q4] | 0.1% | ▲ 0.40 | 🟢 |
```

### 信号機の判定基準

| 指標 | 🟢 緑（目標内） | 🟡 黄（やや外れ） | 🔴 赤（要注意） |
|------|--------------|----------------|--------------|
| コアCPI | 1.5〜2.5% | 2.5%超 | 1.5%未満 |
| 政策金利 | 0〜0.5% | 0.5%超 | 0%未満 |
| GDPギャップ | 0%超（需要超過） | −0.5〜0%（ゼロ近傍） | −0.5%未満（需要不足） |

### 前回比の記号

| 記号 | 意味 |
|------|------|
| `▲ 0.20` | 前回より 0.20 上昇 |
| `▼ 0.20` | 前回より 0.20 低下 |
| `→ 0.00` | 前回と変わらず |
| `―` | 前回データなし |

---

## 取得データ一覧

| ブロック | 指標 | データソース | 更新頻度 | 期間 |
|---------|------|------------|---------|------|
| 物価 | コアCPI（生鮮食品除く・前年比） | 総務省 e-Stat API | 月次 | 直近120件（約10年） |
| 金融 | 無担保コールレート翌日物・月平均 | 日銀時系列統計DB CSV | 月次 | 1985年〜現在 |
| 経済 | 需給ギャップ（GDPギャップ） | 内閣府月例経済報告 xlsx | 四半期 | 1994年〜現在 |

---

## テスト

```bash
# ユニットテスト（外部通信なし）
uv run pytest tests/unit/

# E2E テスト（実際の API・外部サイトに接続）
# 前提: estat-api.toml が存在すること
uv run pytest tests/e2e/ -m e2e -v -s --no-cov
```

---

## ログ

コマンド実行履歴は `logs/command_history.log` に記録されます。

```
2026-03-18 17:00:00 | fetch_data | all | SUCCESS | 12s
2026-03-18 17:01:00 | make_chart | all | SUCCESS | 3s
2026-03-18 17:01:05 | make_report | all | SUCCESS | 0s
```
