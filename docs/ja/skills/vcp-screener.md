---
layout: default
title: VCP Screener
grand_parent: 日本語
parent: スキルガイド
nav_order: 3
lang_peer: /en/skills/vcp-screener/
permalink: /ja/skills/vcp-screener/
---

# VCP Screener
{: .no_toc }

Mark MinerviniのVolatility Contraction Pattern (VCP) を自動検出するスキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/vcp-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/vcp-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

VCP Screenerは、Mark Minerviniが著書「Trade Like a Stock Market Wizard」で解説したVolatility Contraction Pattern (VCP) を自動検出するスキルです。Stage 2上昇トレンドにある銘柄の中から、ボラティリティが段階的に収縮しブレイクアウトに近づいている銘柄を識別します。

**主な特徴:**
- **3フェーズパイプライン:** プレフィルタ → トレンドテンプレート → VCP検出・スコアリング
- **Minerviniのトレンドテンプレート:** 7ポイントのStage 2フィルター
- **VCPパターン分析:** T1/T2/T3の収縮深度、収縮比率、出来高ドライアップ検出
- **トレードセットアップ生成:** ピボットポイント、ストップロス、リスク%を自動計算
- **2軸スコアリング:** パターンの品質（Quality）とエントリー可能性（Execution State）を分離。強いが延長済みの銘柄に誤って買いシグナルを出すことを防止
- **チューニング可能:** バックテストや研究用に全パラメータを調整可能

**解決する問題:**
- 数百銘柄からVCPパターンを手動で探す手間を自動化
- 定量的なパターン品質スコアリングで主観を排除
- 具体的なエントリーポイントとリスク管理値を提示

---

## 2. 前提条件

> FMP APIキーが必須です。無料ティア（250回/日）でデフォルトの上位100候補のスクリーニングに十分です。全S&P 500のスクリーニング（`--full-sp500`）にはPaidティアが推奨されます。
{: .api_required }

| 項目 | 要否 | 説明 |
|------|------|------|
| FMP APIキー | 必須 | 株価データ、コンポーネント情報の取得 |
| Python 3.7+ | 必須 | スクリプト実行用 |

**APIキー設定:**

```bash
export FMP_API_KEY=your_key_here
```

### APIコール予算

| フェーズ | 概算コール数 | 内容 |
|---------|------------|------|
| プレフィルタ | 約101回 | 株価、出来高、52週ポジション |
| トレンドテンプレート | 約100回 | 260日ヒストリカルデータ |
| VCP検出 | 0回 | 既存データで計算（追加APIコール不要） |
| **合計** | **約201回** | 無料ティア（250回/日）で対応可能 |

---

## 3. クイックスタート

### 最小限の実行

```bash
# デフォルト: S&P 500、上位100候補をスクリーニング
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/
```

### カスタムユニバース

```bash
# 特定銘柄のみ分析
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --universe AAPL NVDA MSFT AMZN META \
  --output-dir reports/
```

### Claudeへの自然言語

```
S&P 500からVCPパターンを探して。ブレイクアウト候補を教えて。
```

---

## 4. 仕組み

### 3フェーズパイプライン

```
Phase 1: プレフィルタ（Quote API）
  ↓ ~101 API calls
Phase 2: トレンドテンプレート（260日履歴）
  ↓ ~100 API calls
Phase 3: VCP検出・スコアリング・レポート生成
  ↓ 0 API calls（計算のみ）
```

**Phase 1: プレフィルタ**
- 株価、出来高、52週高値/安値ポジションで粗いフィルタリング
- 流動性、最低株価、基本的なトレンド条件を確認

**Phase 2: トレンドテンプレート**
- Minerviniの7ポイントStage 2基準を適用：
  1. 株価 > 150日SMA
  2. 150日SMA > 200日SMA
  3. 200日SMAが少なくとも1ヶ月上昇中
  4. 50日SMA > 150日SMA および 200日SMA
  5. 株価 > 50日SMA
  6. 株価が52週安値から25%以上上昇
  7. 株価が52週高値の75%以上
- スコア85以上（デフォルト）の銘柄のみ通過

**Phase 3: VCPパターン検出**
- ATRベースのZigZag分析で価格スイングを検出
- 連続する収縮（T1, T2, T3...）の深度と比率を計算
- 出来高のドライアップ（収縮中の出来高減少）を確認
- ピボットポイント（ブレイクアウト水準）を自動計算
- 複合スコアリングとレーティング付与

### VCPの核心: ボラティリティ収縮

典型的なVCPパターンは以下のように進行します：

```
T1（第1収縮）: 30%下落 → 回復
T2（第2収縮）: 15%下落 → 回復  ← T1の半分以下
T3（第3収縮）: 7%下落  → 回復  ← さらに縮小
                               ↑ ピボットポイント = ブレイクアウト水準
```

各収縮が前の収縮より浅くなることが、機関投資家の蓄積と売り圧力の消化を示しています。

---

## 5. 使用例

### 例1: デフォルトスキャン

**プロンプト:**
```
VCPスクリーニングを実行して
```

**Claudeの動作:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/
```

**期待される出力:** S&P 500からVCPスコア上位20銘柄のレポート（各銘柄にピボット価格、ストップロス、リスク%を含む）

---

### 例2: カスタムユニバース

**プロンプト:**
```
半導体銘柄でVCPパターンを探して。NVDA, AVGO, AMD, MRVL, AMAT, LRCX, KLAC, TXN を分析して。
```

**Claudeの動作:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --universe NVDA AVGO AMD MRVL AMAT LRCX KLAC TXN \
  --output-dir reports/
```

**なぜ有用か:** 特定セクター内のVCPブレイクアウト候補を効率的に発見できます。

---

### 例3: 厳格な品質フィルタ

**プロンプト:**
```
高品質なVCPのみ表示して。最低3回の収縮、T1深度12%以上、ブレイクアウト出来高2倍以上で。
```

**Claudeの動作:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --min-contractions 3 \
  --t1-depth-min 12.0 \
  --breakout-volume-ratio 2.0 \
  --output-dir reports/
```

**なぜ有用か:** より厳しい条件で、テキストブックVCPに近いパターンのみに絞り込めます。

---

### 例4: 収縮パターンの読み方

**プロンプト:**
```
VCPレポートの収縮データの見方を教えて
```

**Claudeの動作:**
- T1/T2/T3の深度と収縮比率の意味を解説
- 例: 「T1=25%, T2=12%, T3=5% の場合、収縮比率は0.48, 0.42。0.75以下なので健全な収縮パターンです」
- 出来高ドライアップ率の判読方法

**なぜ有用か:** VCPの品質を自分で判断するスキルが身につきます。

---

### 例5: エントリー準備 vs 拡張済み

**プロンプト:**
```
エントリー可能な銘柄だけ表示して。ピボットから3%以内のもの。
```

**Claudeの動作:**
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py \
  --mode prebreakout \
  --max-above-pivot 3.0 \
  --output-dir reports/
```

**なぜ有用か:** `prebreakout` モードで、すでにブレイクアウトして上昇しすぎた銘柄を除外し、まだエントリー可能な銘柄のみに集中できます。

---

### 例6: トレードセットアップの構築

**プロンプト:**
```
VCPの上位候補について、エントリー、ストップロス、リスク%を含むトレードプランを作って
```

**Claudeの動作:**
- VCPレポートからピボットポイント、ストップロス、リスク%を抽出
- Position Sizerスキルと連携して具体的な株数を計算
- エントリー条件: ピボットを出来高増加で上抜け

**なぜ有用か:** VCPスコアからそのまま実行可能なトレードプランを作成できます。

---

## 6. 出力の読み方

まず `evaluation_coverage` を確認します。評価済み件数 / 全件数と、`complete`・
`partial`・`not_evaluable` を表示します。評価が不完全な場合、候補0件は「機会なし」
ではなく **判定不能（undetermined）** です。有効なデータでの条件不一致は評価済み、
欠損データ・API/契約制限・候補数上限による除外は未評価として数えます。
候補の完全評価には銘柄とベンチマークの有効な履歴が各253行必要です。
表示上位件数や出力モードは評価件数を変更しません。対象は横断スクリーニングであり、
単一銘柄の履歴スキャンではありません。

### 2軸スコアリング

各銘柄は **品質レーティング**（パターンの強さ）と **Execution State**（エントリータイミング）の2軸で評価されます。最終レーティングは Execution State により上限が設定されます。

**Execution State（エントリー状態）:**

| 状態 | 意味 | 最大レーティング |
|------|------|----------------|
| Pre-breakout | ピボット以下（理想的なエントリーゾーン） | 制限なし |
| Breakout | ピボット上0-3% + 出来高確認 | 制限なし |
| Early-post-breakout | ピボット上3-5%、または0-3%で出来高未確認 | Strong VCP |
| Extended | ピボット上5-10% | Developing VCP |
| Overextended | ピボット上10%超 or SMA200上50%超 | Weak VCP |
| Damaged | SMA50以下 or ストップ割れ | No VCP |
| Invalid | 株価 < SMA50 < SMA200 | No VCP |

**品質レーティング（State Cap前）:**

| レーティング | スコア | 意味 | 推奨アクション |
|-------------|--------|------|---------------|
| **Textbook VCP** | 90+ | 教科書的な完璧パターン | ピボットで積極的買い |
| **Strong VCP** | 80-89 | 強力なパターン | ピボットで標準買い |
| **Good VCP** | 70-79 | 良好なパターン | 出来高確認後に買い |
| **Developing** | 60-69 | 発展途上 | ウォッチリスト、さらなる収縮を待つ |
| **Weak / No VCP** | <60 | パターン不完全 | 見送り |

### レポートの主要フィールド

| フィールド | 説明 |
|----------|------|
| Quality Score | 品質スコア（0-100） |
| Quality Rating | State Cap前のレーティング |
| Rating | State Cap後の最終レーティング |
| Execution State | エントリー状態（7段階） |
| Pattern Type | パターン分類（Textbook VCP / VCP-adjacent / Extended Leader 等） |
| Contractions | 検出された収縮の数（T1, T2, T3...） |
| Volume Dry-up | 収縮中の出来高減少率 |
| Pivot Price | ブレイクアウトのエントリーポイント |
| Stop Loss | 推奨ストップロス水準 |
| Risk % | ピボットからストップまでの距離（%） |

---

## 7. Tips & ベストプラクティス

### パラメータチューニング

| 目的 | 推奨設定 |
|------|---------|
| 高品質パターンのみ | `--min-contractions 3 --t1-depth-min 12.0` |
| より多くの候補 | `--min-contractions 2 --trend-min-score 80` |
| タイトなパターン | `--contraction-ratio 0.6` |
| 長期パターン | `--lookback-days 180 --min-contraction-days 10` |
| 短期パターン | `--lookback-days 60 --min-contraction-days 3` |

### エントリーのベストプラクティス

1. **ピボットを出来高で確認:** ブレイクアウト当日の出来高が50日平均の1.5倍以上を確認
2. **買いタイミング:** ピボットポイントを上抜けた日（または翌日寄付）
3. **ストップロス:** レポートの推奨ストップまたはVCPベースの底
4. **リスク管理:** 1トレードあたりのリスクをポートフォリオの1-2%に制限

### よくある間違い

- ピボットから5%以上離れた銘柄を追いかけない（拡張リスク）
- 出来高なしのブレイクアウトは偽シグナルの可能性が高い
- ベアマーケットでのVCPエントリーは成功率が大幅に低下

---

## 8. 他スキルとの連携

### CANSLIM → VCP パイプライン

ファンダメンタル（CANSLIM）とテクニカル（VCP）の両方で高評価の銘柄を特定：

```
1. CANSLIM: 成長ファンダメンタルが強い上位銘柄を特定
2. VCP: --universe で候補を渡し、テクニカルエントリータイミングを評価
```

### VCP → Position Sizer

VCPのピボットとストップから最適なポジションサイズを計算：

```
1. VCP: ピボット$155、ストップ$148のセットアップを発見
2. Position Sizer: --entry 155 --stop 148 --account-size 100000 --risk-pct 1.0
```

### VCP → Technical Analyst

VCP候補の週足チャートを視覚的に確認：

```
1. VCP: スコア80以上の候補を特定
2. Technical Analyst: チャートパターン、サポート/レジスタンスの視覚的確認
```

### FinViz → VCP（プレスクリーニング）

FinVizのトレンドテンプレート条件で粗い絞り込みを行い、VCPの分析対象を絞る：

```
1. FinViz: ta_sma20_pa,ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to25h
2. VCP: 候補銘柄のVCPパターン詳細分析
```

---

## 9. トラブルシューティング

### VCPパターンが検出されない

**原因:**
- マーケット全体がボラタイルで収縮パターンが少ない
- フィルター条件が厳しすぎる

**対処:**
1. `--min-contractions 2`（デフォルト）に戻す
2. `--trend-min-score` を80に下げる
3. `--lookback-days` を180に拡大
4. `--contraction-ratio` を0.80に緩和

### APIレートリミット

```
ERROR: 429 Too Many Requests
```

**対処:**
1. スクリプトは自動リトライ
2. `--max-candidates` を小さくしてAPIコールを削減
3. 全S&P 500（`--full-sp500`）は有料ティアが必要

### スコアが全体的に低い

**原因:** ベアマーケットまたは横ばい相場ではVCPパターンが形成されにくい

**対処:**
1. VCPはStage 2上昇トレンド銘柄のパターンなので、弱気相場では候補が少ないのは正常
2. Breadth Chart AnalystやMarket Top Detectorで市場環境を確認
3. 市場回復を待つか、個別の強いセクターに集中

### entry_ready銘柄がない

**原因:** 候補銘柄がピボットから離れすぎ、または既にブレイクアウト済み

**対処:**
1. `--max-above-pivot` を5.0%に拡大（ただしリスク増大に注意）
2. ウォッチリストとして保存し、プルバックを待つ
3. `--mode all` で全候補を確認し、Developing（60-69）を監視

---

## 10. リファレンス

### CLIオプション一覧

```bash
python3 skills/vcp-screener/scripts/screen_vcp.py [OPTIONS]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--api-key` | FMP APIキー | `$FMP_API_KEY` 環境変数 |
| `--max-candidates` | プレフィルタ後の最大候補数 | 100 |
| `--top` | レポート上位件数 | 20 |
| `--output-dir` | 出力ディレクトリ | カレントディレクトリ |
| `--universe` | カスタム銘柄リスト | S&P 500 |
| `--full-sp500` | 全S&P 500をスクリーニング | false |
| `--mode` | 出力モード: `all` / `prebreakout` | all |
| `--max-above-pivot` | entry_readyの最大ピボット超過% | 3.0 |
| `--max-risk` | entry_readyの最大リスク% | 15.0 |
| `--min-atr-pct` | 最低ATR%（低ボラ銘柄除外） | 1.0 |
| `--ext-threshold` | SMA50超過ペナルティ開始% | 8.0 |

### VCPチューニングパラメータ

| パラメータ | デフォルト | 範囲 | 効果 |
|-----------|-----------|------|------|
| `--min-contractions` | 2 | 2-4 | 高いほど厳格（少数の高品質パターン） |
| `--t1-depth-min` | 8.0% | 1-50 | 高いほど浅い第1収縮を除外 |
| `--breakout-volume-ratio` | 1.5x | 0.5-10 | 高いほど厳格な出来高確認 |
| `--trend-min-score` | 85 | 0-100 | 高いほど厳格なStage 2フィルター |
| `--atr-multiplier` | 1.5 | 0.5-5 | 低いほど敏感なスイング検出 |
| `--contraction-ratio` | 0.75 | 0.1-1 | 低いほど厳しい収縮要件 |
| `--min-contraction-days` | 5 | 1-30 | 高いほど長期の収縮を要求 |
| `--lookback-days` | 120 | 30-365 | 長いほど古いパターンも検出 |
| `--max-sma200-extension` | 50.0 | - | SMA200超過でOverextended判定の閾値% |
| `--wide-and-loose-threshold` | 15.0 | - | wide-and-loose判定の最終収縮深度% |
| `--strict` | false | - | 厳格モード（収縮3回以上、各7日以上、比率0.60） |

### 出力ファイル

| ファイル | 形式 | 用途 |
|----------|------|------|
| `vcp_screener_YYYY-MM-DD_HHMMSS.json` | JSON | プログラマティック利用 |
| `vcp_screener_YYYY-MM-DD_HHMMSS.md` | Markdown | 人間向けレポート |

### 関連ファイル

| ファイル | 説明 |
|----------|------|
| `skills/vcp-screener/SKILL.md` | スキル定義 |
| `skills/vcp-screener/references/vcp_methodology.md` | VCP理論とトレンドテンプレート解説 |
| `skills/vcp-screener/references/scoring_system.md` | スコアリング閾値とコンポーネントウェイト |
| `skills/vcp-screener/references/fmp_api_endpoints.md` | APIエンドポイントとレートリミット |
| `skills/vcp-screener/scripts/screen_vcp.py` | メインスクリプト |
| `skills/vcp-screener/scripts/calculators/` | パターン検出・スコアリングモジュール |
