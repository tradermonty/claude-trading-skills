---
layout: default
title: Position Sizer
grand_parent: 日本語
parent: スキルガイド
nav_order: 6
lang_peer: /en/skills/position-sizer/
permalink: /ja/skills/position-sizer/
---

# Position Sizer
{: .no_toc }

リスク管理に基づくポジションサイズを3つの手法で計算するスキルです。整数株だけでなく、ブローカーが対応している場合の小数株サイジングにも対応します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/position-sizer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/position-sizer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Position Sizerは、「何株買うべきか？」という問いに対し、リスク管理の原則に基づいた最適なポジションサイズを計算するスキルです。

**主な特徴:**
- 3つのサイジング手法: Fixed Fractional、ATRベース、Kelly Criterion
- ポートフォリオ制約の自動適用（最大ポジション%、最大セクター%）
- 小口口座や高株価銘柄向けの小数株出力（`--fractional`）
- API不要、完全オフライン動作（標準ライブラリのみ）
- JSON + Markdownレポートの同時出力

**解決する問題:**
- 感覚的なポジションサイズ決定をルールベースに置き換える
- リスク許容度に基づく株数の自動計算
- 整数株ではリスク予算を使い切れない小口口座のサイジング
- セクター集中リスクの可視化と制限

**核心原則:**
1. **サバイバル最優先**: ポジションサイジングは連敗を生き延びるための技術
2. **1%ルール**: デフォルトは1トレードあたり資産の1%リスク。2%を超えるのは例外的な場合のみ
3. **切り捨て**: 株数は常に切り捨て（整数株は整数へ、小数株は指定桁数へ。切り上げは禁止）
4. **最も厳しい制約が勝つ**: 複数の制限がある場合、最も少ない株数が最終サイズ

---

## 2. 前提条件

| 項目 | 要否 | 説明 |
|------|------|------|
| Python 3.9+ | 必須 | スクリプト実行用 |
| APIキー | 不要 | 純粋な計算ツール |
| インターネット接続 | 不要 | 完全オフライン動作 |

追加のPythonパッケージのインストールは不要です（標準ライブラリのみ使用）。

---

## 3. クイックスタート

Claudeに自然言語で質問するだけで使えます：

```
AAPL $155で買いたい。ストップは$148.50、口座は10万ドル。何株買えばいい？
```

Claudeが以下の流れで処理します：
1. パラメータの確認（エントリー$155、ストップ$148.50、口座$100,000）
2. Fixed Fractional法（1%リスク）でポジションサイズを計算
3. 153株、ポジション価値$23,715、リスク$994.50と回答

CLIで直接実行する場合：

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --output-dir reports/
```

ブローカーが小数株に対応している場合は、以下のように小数株モードを使えます：

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 1000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --fractional \
  --share-precision 4 \
  --output-dir reports/
```

---

## 4. 仕組み

### 3つのサイジング手法

| 手法 | 計算式 | 最適な用途 |
|------|--------|-----------|
| **Fixed Fractional** | 株数 = floor(口座 x リスク% / (エントリー - ストップ)) | チャートで明確なストップがある裁量トレード |
| **ATRベース** | 株数 = floor(口座 x リスク% / (ATR x 乗数)) | ボラティリティの異なる銘柄の比較 |
| **Kelly Criterion** | Half Kelly% = (勝率 - (1-勝率)/R) / 2 | 100+トレードの統計がある戦略の資金配分 |
| **小数株出力** | `--fractional --share-precision N` | 小口口座、高株価銘柄、ブローカー対応済みの小数株取引 |

**ATR乗数の目安:** 1.0x（デイトレード）、2.0x（スイングのデフォルト）、3.0x（トレンドフォロー）

> Half Kellyは理論上の成長率の約75%を達成しつつ、ドローダウンを大幅に抑えます。実践では常にHalf Kellyを使用してください。Full Kellyは非推奨です。
{: .tip }

### ポートフォリオ制約

- **最大ポジション%**: 1銘柄が口座全体の何%を占めてよいかの上限
- **最大セクター%**: 同一セクターが口座全体の何%を占めてよいかの上限
- **バインディング制約**: 複数の制約がある場合、最も厳しい制約が最終株数を決定

---

## 5. 使用例

### 例1: 基本 -- ストップロスベースの1%リスクサイジング

**プロンプト:**
```
$155でエントリー、ストップは$148.50、口座10万ドルで何株買える？
```

**CLIコマンド:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --output-dir reports/
```

**結果:** 153株、ポジション価値$23,715、ドルリスク$994.50（口座の0.99%）

---

### 例2: ATRベースのボラティリティ調整サイジング

**プロンプト:** `ATRが$3.20の銘柄を$155で買いたい。ATR 2倍のストップで何株？`

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 --entry 155 --atr 3.20 \
  --atr-multiplier 2.0 --risk-pct 1.0 --output-dir reports/
```

**結果:** 156株、ストップ$148.60（ATR x 2.0 = $6.40のストップ距離）。明確なサポートがない銘柄でもボラティリティに基づくストップを設定できます。

---

### 例3: Kelly Criterion（バジェットモード）

**プロンプト:** `勝率55%、平均利益$2.50、平均損失$1.00の戦略。最適なリスク配分は？`

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 --win-rate 0.55 --avg-win 2.5 \
  --avg-loss 1.0 --output-dir reports/
```

**結果:** Half Kelly = 18.5%、リスクバジェット = $18,500。エントリーなしでも最適配分を事前に把握できます。

---

### 例4: ポートフォリオ制約付きサイジング

**プロンプト:**
```
$155で買い、ストップ$148.50。1銘柄最大10%、テクノロジーセクター最大30%で、
現在テクノロジーに22%のエクスポージャーがある。
```

**CLIコマンド:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --max-position-pct 10 \
  --max-sector-pct 30 \
  --sector Technology \
  --current-sector-exposure 22 \
  --output-dir reports/
```

**結果:** セクター制約により51株に制限（残り8% = $8,000 / $155 = 51株）

**なぜ有用か:** リスク計算上は153株買えるが、セクター集中を30%以下に抑えるために51株に制限される、という状況を自動判定できます。

---

### 例5: 複数シナリオ比較

**プロンプト:**
```
AAPLを$155で買いたい。ストップ$148.50で、0.5%、1.0%、1.5%のリスクを比較して
```

**Claudeの動作:**
- 3つのリスクレベルで計算を並列実行
- 比較表を生成:

| リスク% | 株数 | ポジション価値 | ドルリスク |
|---------|------|--------------|----------|
| 0.5% | 76 | $11,780 | $494 |
| 1.0% | 153 | $23,715 | $994 |
| 1.5% | 230 | $35,650 | $1,495 |

**なぜ有用か:** リスク許容度に応じた選択肢を一目で比較でき、口座サイズに対する影響を把握しやすくなります。

---

### 例6: 小口口座向けの小数株サイジング

**プロンプト:**
```
口座は$1,000。$155でエントリー、ストップ$148.50、1%リスク。
ブローカーは小数株に対応している。
```

**CLIコマンド:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 1000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --fractional \
  --share-precision 4 \
  --output-dir reports/
```

**結果:** 整数株モードでは1株ですが、小数株モードでは1.5384株です。予定リスク$10を超えずに、リスク予算をより有効に使えます。

**注意:** 小数株は計算上の出力です。実際に発注できるかは、ブローカーの対応銘柄、注文種別、最低注文金額、スプレッド、スリッページ、手数料に依存します。

---

### 例7: セクター集中チェック

**プロンプト:**
```
Technologyセクターに現在22%投資している。あと何%まで入れられる？
もう1銘柄追加する場合のサイジングを計算して
```

**CLIコマンド:**
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --account-size 100000 \
  --entry 155 \
  --stop 148.50 \
  --risk-pct 1.0 \
  --max-sector-pct 30 \
  --sector Technology \
  --current-sector-exposure 22 \
  --output-dir reports/
```

**結果:** セクター残枠8%（$8,000）、最大51株まで追加可能

**なぜ有用か:** 特定セクターへの偏りを数値で把握し、分散投資の原則を守りながらポジションを管理できます。

---

### 例8: 自然言語での依頼例

以下のような自然言語でもスキルが起動します：

- `NVDAのポジションサイズを計算して。口座は5万ドル、1%リスク`
- `ATR $5.80で2.5倍のストップ、口座20万ドル。何株買える？`
- `この戦略の勝率62%、平均利益$3.20、平均損失$1.50。Kelly Criterionは？`
- `ポートフォリオヒートが6%を超えないようにサイジングしたい`

---

## 6. 出力の読み方

### JSON出力の主要フィールド

| フィールド | 説明 |
|-----------|------|
| `mode` | `shares`（株数算出モード）または `budget`（Kelly予算モード） |
| `calculations.fixed_fractional` | Fixed Fractional法の結果 |
| `calculations.atr_based` | ATR法の結果（`--atr`指定時のみ） |
| `calculations.kelly` | Kelly Criterionの結果（`--win-rate`指定時のみ） |
| `constraints_applied` | 適用された制約の一覧 |
| `final_recommended_shares` | 最終推奨株数 |
| `binding_constraint` | 株数を制限している制約（`null`=リスクベースが最小） |
| `parameters.fractional_shares` | 小数株モードが有効な場合に表示 |
| `parameters.share_precision` | 小数株を切り捨てる桁数 |

### Markdownレポートの構成

1. **パラメータサマリー** - 入力値の確認
2. **計算詳細** - アクティブな手法ごとの計算過程
3. **制約分析** - 各制約による上限株数と、どの制約がバインディングか
4. **最終推奨** - 推奨株数、ポジション価値、ドルリスク

### 制約のバインディング判定

複数の制約がある場合、レポートは以下を明示します：
- リスクベースの株数（例: 153株）
- 最大ポジション制約の株数（例: 64株）
- セクター制約の株数（例: 51株）
- **バインディング制約**: 最も少ない株数を選択する制約（この例ではセクター制約）

---

## 7. Tips & ベストプラクティス

### 手法の選び方

| 状況 | 推奨手法 |
|------|----------|
| チャートで明確なストップ水準がある | Fixed Fractional |
| ストップ水準が不明確、異なるボラティリティの銘柄を比較 | ATRベース |
| 100トレード以上の統計がある | Kelly Criterion（上限チェックとして） |
| 初めてのトレード戦略 | Fixed Fractional 1%からスタート |

### リスク管理のガイドライン

- **ポートフォリオヒート**: 全ポジションの合計リスクが口座の6-8%を超えないようにする
- **連敗対応**: Minerviniのアドバイスに従い、連敗後はリスク%を0.5%に引き下げ
- **損失の非対称性**: 10%損失→11%回復、20%→25%、50%→100%が必要。小さく負けることが鍵
- **Kelly Criterionは上限チェック用**: Fixed FractionalやATRの結果がKelly推奨を超えていないか確認する用途。統計が100トレード未満ならKellyは信頼できない
- **小口取引の摩擦を確認**: 小数株や少額注文では、スプレッド、スリッページ、手数料、最低注文金額、為替コスト、決済/マージン制限がリスク予算に対して大きくなり得ます
- **日中取引の制約をブローカーで確認**: FINRAは旧来のpattern day traderの日数カウントと$25,000最低自己資本要件を、2026-06-04有効のintraday margin standardsに置き換えました。ブローカーには2027-10-20までのphase-inが認められているため、実際の制約は利用ブローカーで確認してください。Source: <https://www.finra.org/rules-guidance/notices/26-10>

---

## 8. 他スキルとの連携

### Position Sizer → Market Breadth Analyzer

ブレッドスのゾーンに応じてリスク%を動的に調整：

```
1. Market Breadth Analyzer: ゾーンを確認（例: Weakening）
2. Position Sizer: Weakening時はリスク%を0.5%に引き下げてサイジング
```

### Screener → Position Sizer → Portfolio Manager

スクリーニングからポジション管理までの一貫ワークフロー：

```
1. CANSLIM / VCP / Dividend Screener: 候補銘柄を特定
2. Position Sizer: エントリー/ストップに基づく適切な株数を計算
3. Portfolio Manager: Alpaca経由で発注・ポジション管理
```

### Backtest Expert → Position Sizer

バックテスト結果のトレード統計をKelly Criterionに活用：

```
1. Backtest Expert: 勝率62%、平均利益1.8%、平均損失1.2%を算出
2. Position Sizer: --win-rate 0.62 --avg-win 1.8 --avg-loss 1.2 で最適リスク配分を計算
```

---

## 9. トラブルシューティング

### 「entry and stop required」エラー

**原因:** Fixed FractionalまたはATRモードでエントリー価格やストップ価格が未指定

**対処:**
- `--entry` と `--stop`（Fixed Fractional）、または `--entry` と `--atr`（ATRベース）を指定
- Kelly Criterionのバジェットモードでは `--entry` 不要

### Kelly Criterionが0%と表示される

**原因:** 戦略が負の期待値を持つ（勝率とペイオフレシオの組み合わせが不利）

**対処:**
- Kelly Criterionがマイナス値の場合、自動で0%にフロアリングされます
- これは「このシステムではトレードすべきでない」というシグナルです
- 戦略の見直しが必要です

### 制約によって株数が大幅に減少する

**原因:** ポートフォリオ制約（最大ポジション%、最大セクター%）が厳しい

**対処:**
- レポートの「バインディング制約」を確認し、何が株数を制限しているか特定
- セクター制約の場合: 同セクターの既存ポジションを一部縮小するか、他セクターの銘柄を検討
- ポジション制約の場合: 制約設定が口座サイズに対して適切か確認

### ATR値がわからない

**対処:**
- TradingViewやFinVizで14日ATR（ATR(14)）を確認
- Claudeに「AAPLのATRを調べて」と依頼すれば、WebSearchで取得可能
- ATRが不明な場合はFixed Fractional法を使用

---

## 10. リファレンス

### CLIオプション一覧

```bash
python3 skills/position-sizer/scripts/position_sizer.py [OPTIONS]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--account-size` | 口座の総額（ドル）（必須） | - |
| `--entry` | エントリー価格 | - |
| `--stop` | ストップロス価格 | - |
| `--risk-pct` | 1トレードあたりのリスク%（例: 1.0） | - |
| `--atr` | Average True Range値 | - |
| `--atr-multiplier` | ATR乗数 | 2.0 |
| `--win-rate` | 勝率（0-1）、Kelly Criterion用 | - |
| `--avg-win` | 平均利益額、Kelly Criterion用 | - |
| `--avg-loss` | 平均損失額、Kelly Criterion用 | - |
| `--max-position-pct` | 1銘柄の最大ポジション比率（%） | - |
| `--max-sector-pct` | セクターの最大エクスポージャー（%） | - |
| `--sector` | セクター名（集中チェック用） | - |
| `--current-sector-exposure` | 現在のセクターエクスポージャー（%） | 0.0 |
| `--fractional` | 小数株出力を有効化 | false |
| `--share-precision` | 小数株を切り捨てる桁数（0-8） | 4 |
| `--output-dir` | レポート出力先ディレクトリ | `reports/` |

### 手法比較表

| 特徴 | Fixed Fractional | ATRベース | Kelly Criterion |
|------|-----------------|-----------|-----------------|
| 必要な入力 | エントリー、ストップ、リスク% | エントリー、ATR、乗数、リスク% | 勝率、平均損益 |
| ボラティリティ調整 | なし | あり | なし（履歴統計使用） |
| トラック記録が必要 | 不要 | 不要 | 必要（100トレード以上） |
| 最適な用途 | 裁量トレード | システマティック/メカニカル | 資金配分 |

### 関連ファイル

| ファイル | 説明 |
|----------|------|
| `skills/position-sizer/SKILL.md` | スキル定義（ワークフロー） |
| `skills/position-sizer/references/sizing_methodologies.md` | サイジング方法論の完全ガイド |
| `skills/position-sizer/scripts/position_sizer.py` | メイン計算スクリプト |
