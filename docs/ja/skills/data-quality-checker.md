---
layout: default
title: "Data Quality Checker"
grand_parent: 日本語
parent: スキルガイド
nav_order: 12
lang_peer: /en/skills/data-quality-checker/
permalink: /ja/skills/data-quality-checker/
---

# Data Quality Checker
{: .no_toc }

市場分析ドキュメントやブログ記事の公開前にデータ品質を検証します。価格スケールの不整合（ETF vs 先物）、金融商品の表記エラー、日付/曜日の不一致、配分合計のエラー、単位の不一致をチェックする際に使用します。英語・日本語のコンテンツに対応。アドバイザリーモード -- 問題をブロッカーとしてではなく、人間のレビュー用の警告としてフラグします。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/data-quality-checker.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/data-quality-checker){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

市場分析ドキュメントの公開前に一般的なデータ品質の問題を検出します。チェッカーは5つのカテゴリを検証します：価格スケールの一貫性、金融商品の表記、日付/曜日の正確性、配分合計、単位の使用法。すべての検出結果はアドバイザリーであり、公開をブロックするのではなく、人間のレビュー用に潜在的な問題をフラグします。

---

## 2. 使用タイミング

- 週次戦略ブログや市場分析レポートの公開前
- 自動生成された市場サマリーの確認後
- 翻訳されたドキュメント（英語/日本語）のデータ正確性をレビューする場合
- 複数のデータソース（FRED、FMP、FINVIZ）からのデータを1つのレポートに統合する場合
- 金融データを含むドキュメントの事前チェックとして

---

## 3. 前提条件

- Python 3.9+
- 外部APIキー不要
- サードパーティのPythonパッケージ不要（標準ライブラリのみ使用）

---

## 4. クイックスタート

```bash
# マークダウンファイルのチェック
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file reports/weekly_strategy.md

# 特定のチェックのみ実行
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --checks price_scale,dates,allocations

# 年推定のための基準日指定
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file report.md --as-of 2026-02-28 --output-dir reports/
```

---

## 5. ワークフロー

### ステップ1: 入力ドキュメントの受領

対象のマークダウンファイルパスとオプションパラメータを受け取ります：
- `--file`: 検証対象のマークダウンドキュメントへのパス（必須）
- `--checks`: 実行するチェックのカンマ区切りリスト（任意、デフォルト: 全チェック）
- `--as-of`: 年推定のための基準日（YYYY-MM-DD形式、任意）
- `--output-dir`: レポート出力ディレクトリ（任意、デフォルト: `reports/`）

### ステップ2: 検証スクリプトの実行

データ品質チェッカースクリプトを実行します：

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --output-dir reports/
```

特定のチェックのみ実行する場合：

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --checks price_scale,dates,allocations
```

年推定のための基準日を指定する場合（日付に明示的な年がないドキュメントに有用）：

```bash
python3 skills/data-quality-checker/scripts/check_data_quality.py \
  --file path/to/document.md \
  --as-of 2026-02-28
```

### ステップ3: リファレンス基準の読み込み

検出結果を文脈化するために関連するリファレンスドキュメントを読み込みます：

- `references/instrument_notation_standard.md` -- 各金融商品クラスの標準ティッカー表記、桁数ヒント、命名規則
- `references/common_data_errors.md` -- FREDデータの遅延、ETF/先物スケールの混同、祝日の見落とし、配分合計の落とし穴、単位混同パターンなど、頻繁に観察されるエラーのカタログ

### ステップ4: 検出結果のレビュー

出力の各検出結果を確認します：

- **ERROR** -- 高信頼度の問題（例：カレンダー計算で検証された日付/曜日の不一致）。修正を強く推奨。
- **WARNING** -- 人間の判断が必要な可能性の高い問題（例：価格スケールの異常、表記の不整合、0.5%以上ずれた配分合計）。
- **INFO** -- 情報提供的な注記（例：意図的かもしれないbp/%の混在使用）。

### ステップ5: 品質レポートの生成

スクリプトは2つの出力ファイルを生成します：

1. **JSONレポート** (`data_quality_YYYY-MM-DD_HHMMSS.json`): 重大度、カテゴリ、メッセージ、行番号、コンテキストを含む機械可読な検出結果リスト。
2. **マークダウンレポート** (`data_quality_YYYY-MM-DD_HHMMSS.md`): 重大度レベル別にグループ化された人間可読なレポート。

検出結果をナレッジベースからの説明とともにユーザーに提示し、各問題に対する具体的な修正案を提案します。

---

## 6. リソース

**リファレンス:**

- `skills/data-quality-checker/references/common_data_errors.md`
- `skills/data-quality-checker/references/instrument_notation_standard.md`

**スクリプト:**

- `skills/data-quality-checker/scripts/check_data_quality.py`

## 日付と曜日の対応形式

`YYYY-MM-DD`・`YYYY/MM/DD`・`M/D`・`M月D日`の後の曜日を検証します。
数値形式では英語の3文字略称・正式名（大小文字不問）と日本語の「火」「火曜日」に対応し、
半角`(Tue)`・全角`（火）`の同種の括弧と、その前の空白・タブを受け付けます。
日本語の曜日は従来どおり半角・全角が混在した括弧も受け付けます。日付は全角数字を含む
Unicodeの十進数字に対応し、`11/10(火)-11/12(水)`や`12/9-12/10(金)`のように連結した範囲も、
曜日の付いた日付をすべて検証します。`2025-11/10(水)`のような年の書き方はどちらの年とも読めるため、
その年と推定した年のどちらで見ても曜日が誤っているときだけ報告します。
無効な暦日や認識できない曜日は、この曜日検査では読み飛ばします。有効な日付という判定ではありません。
明示された数値年を最優先し、年省略時は従来の`--as-of`と6か月超の年越し推定、文書の年、
ファイル名の年、現在年の順に補います。再現可能な検証には`--as-of`を指定してください。
日本語の不一致もWARNINGから**ERROR**に統一しますが、指摘は助言であり、CLIは従来どおり終了0です。
