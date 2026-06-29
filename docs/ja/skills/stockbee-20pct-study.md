---
layout: default
title: "Stockbee 20% Study"
grand_parent: 日本語
parent: スキルガイド
nav_order: 52
lang_peer: /en/skills/stockbee-20pct-study/
permalink: /ja/skills/stockbee-20pct-study/
generated: false
---

# Stockbee 20% Study
{: .no_toc }

米国株の +20% / -20% 級の大きな値動きを日次で蓄積し、カタリスト、チャート文脈、将来リターン、コホート傾向を整理する研究用スキルです。売買シグナルではなく、モデルブックと仮説作成のために使います。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span> <span class="badge badge-optional">ローカルJSON任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/stockbee-20pct-study.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/stockbee-20pct-study){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Stockbee 20% Study は、短期間で大きく上昇・下落した銘柄を体系的に研究するためのスキルです。日足 OHLCV から指定期間で 20% 以上動いた銘柄を検出し、イベントレコードを JSONL に保存し、後日 1日・3日・5日・10日・20日後の結果を更新します。

主な目的:

- どのカタリストが継続上昇につながりやすいかを調べる
- どの大陽線・大陰線がすぐに失敗しやすいかを調べる
- 強い終値、52週高値付近、出来高急増などの文脈を比較する
- 低品質な投機、分割・特殊要因らしきノイズを区別する
- 後続の edge research に渡す仮説候補を作る

このスキルは注文を出したり、ブローカー向けの発注指示を作ったり、コホートをそのまま売買ルールに昇格させたりしません。

---

## 2. 使う場面

- 引け後に +20% / -20% mover を確認したい
- 過去データから 20% mover のモデルブックを作りたい
- カタリスト JSON を使って価格イベントを分類したい
- 1日後、3日後、5日後、10日後、20日後の結果を更新したい
- direction、catalyst、chart pattern、close quality ごとにコホート集計したい
- edge-candidate-agent や月次レビューに渡す研究ヒントを作りたい

使わない場面:

- チャート確認なしに即時売買判断へ進む
- 少数サンプルだけで新しい売買ルールを採用する
- 出力を自動売買やシグナル配信として扱う

---

## 3. 前提条件

- Python 3.9+
- ライブのユニバース取得・OHLCV取得には FMP API キー
- API なしで使う場合は `--prices-json` にローカル OHLCV JSON
- 任意: カタリスト分類用の structured news / event JSON
- 推奨 state パス: `state/stockbee/20pct_study_events.jsonl`

FMP を使う場合:

```bash
export FMP_API_KEY=your_api_key_here
```

ローカル JSON を使う offline mode では FMP キーは不要です。

---

## 4. クイックスタート

FMP を使った日次スキャン:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py scan \
  --fmp-universe \
  --max-symbols 300 \
  --as-of 2026-06-28 \
  --lookback-days 5 \
  --min-abs-return-pct 20 \
  --min-price 5 \
  --min-dollar-volume 20000000 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

ローカル OHLCV JSON を使う場合:

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py scan \
  --prices-json data/us_daily_ohlcv.json \
  --as-of 2026-06-28 \
  --lookback-days 5 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

---

## 5. ワークフロー

### Step 1: 20% mover を検出する

`scan` は、対象日の終値と `--lookback-days` 前の終値を比較します。リターンが `--min-abs-return-pct` 以上なら `UP`、`--include-down-movers` を指定していてリターンが -20% 以下なら `DOWN` として記録します。

同時に、流動性、出来高倍率、終値位置、52週高値・安値からの距離、直前モメンタム、伸び切りリスク、データ品質フラグも保存します。

### Step 2: カタリストを補強する

structured news / catalyst JSON がある場合は、イベントを enrichment します。

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py enrich \
  --events-json reports/stockbee_20pct_events_YYYY-MM-DD_HHMMSS.json \
  --news-json data/catalysts_YYYY-MM-DD.json \
  --market-regime reports/market_regime_latest.json \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

一致するニュースがない場合は `NO_CLEAR_NEWS` のまま残します。後付けで理由を作るより、価格のみのイベントとして扱う方が安全です。

### Step 3: forward outcome を更新する

十分な将来バーが揃った後に outcome を更新します。

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py update-outcomes \
  --prices-json data/us_daily_ohlcv.json \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --horizons 1,3,5,10,20 \
  --output-dir reports/
```

各 horizon には、終値リターン、MFE、MAE、方向調整済みリターン、`STRONG_CONTINUATION`、`FAILED_FADE`、`BREAKDOWN_CONTINUED`、`REVERSAL_BOUNCE` などの outcome tag が入ります。

### Step 4: コホートを集計する

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py summarize \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --group-by direction,catalyst.label,technical_context.pattern_label,technical_context.close_quality \
  --min-sample 10 \
  --output-dir reports/
```

十分なサンプル数があるグループだけが `edge_hints` 候補になります。ただし、これは研究メモであり、実行ルールではありません。

### Step 5: 履歴バックフィルを行う

```bash
python3 skills/stockbee-20pct-study/scripts/run_20pct_study.py backfill \
  --from 2020-01-01 \
  --to 2026-06-28 \
  --prices-json data/us_daily_ohlcv.json \
  --min-abs-return-pct 20 \
  --include-down-movers \
  --state-file state/stockbee/20pct_study_events.jsonl \
  --output-dir reports/
```

現在のユニバースだけで過去検証する場合は、上場廃止銘柄が抜けるため survivorship bias があることを明示してください。
CLI はバックフィルした各レコードに `CURRENT_UNIVERSE_BACKFILL_SURVIVORSHIP_BIAS` を既定で付けます。`--survivorship-complete` は、OHLCV ファイルに上場廃止銘柄と当時のユニバースが含まれている場合だけ指定してください。

---

## 6. 出力の読み方

主な出力:

- `stockbee_20pct_events_*.json` / `stockbee_20pct_daily_report_*.md`
- `stockbee_20pct_enriched_*.json`
- `stockbee_20pct_outcome_update_*.json/md`
- `stockbee_20pct_cohort_summary_*.json/md`
- `stockbee_20pct_edge_hints_*.yaml`
- `state/stockbee/20pct_study_events.jsonl`

重要なフィールド:

- `direction`: `UP` または `DOWN`
- `price_snapshot.return_pct`: 指定期間のリターン
- `technical_context.pattern_label`: チャート文脈の分類
- `scores.continuation_quality_score`: 継続研究の品質スコア。買いシグナルではない
- `scores.reversal_risk_score`: 低品質・反落リスクの目安
- `data_quality.flags`: 短い履歴、分割疑い、流動性不足などの注意点
- `outcomes.<horizon>d`: 成熟済みまたは保留中の将来結果

---

## 7. ガードレール

- 少数サンプルだけでルールを採用しない
- 成功例と失敗例の代表チャートを必ず確認する
- 観察、仮説、実行可能な売買計画を分ける
- 低流動性、低 float、資本政策絡みのイベントは慎重に扱う
- current-universe-only のバックフィルは過大評価されやすいため、`data_quality.flags` で分けて扱う

---

## 8. リソース

- `skills/stockbee-20pct-study/references/methodology.md`
- `skills/stockbee-20pct-study/references/event_schema.md`
- `skills/stockbee-20pct-study/references/catalyst_taxonomy.md`
- `skills/stockbee-20pct-study/references/scoring_system.md`
- `skills/stockbee-20pct-study/references/cohort_mining_rules.md`
- `skills/stockbee-20pct-study/scripts/run_20pct_study.py`
