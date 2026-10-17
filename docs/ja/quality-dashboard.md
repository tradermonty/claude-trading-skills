---
layout: page
parent: 日本語
title: 品質ダッシュボード
nav_order: 3
permalink: /ja/quality-dashboard/
lang_peer: /en/quality-dashboard/
generated: true
---


# 品質ダッシュボード

> 本セクションは `scripts/generate_quality_dashboard.py` により自動生成されます。手動編集しないでください。

スナップショット基準日: `2026-10-17T07:11:43Z`

## ライフサイクル

| 合計 | 本番 | ベータ | 知識のみ | 実行可能 | テストあり | テストなし |
|---:|---:|---:|---:|---:|---:|---:|
| 74 | 62 | 12 | 3 | 71 | 71 | 0 |

## テストカバレッジ

- 全体カバレッジ目標: 75.0%
- 全体カバレッジ下限: 75.0%
- 許容失敗: 0 (目標 0)

## E2E リプレイ

- リプレイ一覧のワークフロー数（実行結果の測定ではありません）: 12 / 12

## 依存関係

| プロバイダ | 件数 |
|---|---:|
| FMP | 29 |
| FINVIZ | 4 |
| ALPACA | 2 |
| その他の外部プロバイダ | 8 |
| オフライン（外部データなし） | 35 |

## ベータパイプライン

| スキル | ベータ経過日数 |
|---|---:|
| `crypto-regime-analyzer` | not yet measured |
| `fxmacrodata-calendar` | not yet measured |
| `manifoldbt-backtester` | not yet measured |
| `mt5-robot-tester` | not yet measured |
| `residual-edge-analyzer` | not yet measured |
| `stockbee-20pct-study` | not yet measured |
| `stockbee-episodic-pivot-analyzer` | not yet measured |
| `stockbee-exhaustion-hammer-screener` | not yet measured |
| `stockbee-momentum-burst-screener` | not yet measured |
| `stockbee-setup-fluency-trainer` | not yet measured |
| `trade-performance-coach` | not yet measured |
| `us-undervalued-growth-screener` | not yet measured |

## スキル別ステータス

| スキル | ステータス | 実行可能 | テスト | カバレッジ |
|---|---|---|---|---|
| **Backtest Expert** (`backtest-expert`) | 本番 | はい | はい | 87.4% |
| **Breadth Chart Analyst** (`breadth-chart-analyst`) | 本番 | はい | はい | 99.2% |
| **Breakout Trade Planner** (`breakout-trade-planner`) | 本番 | はい | はい | 78.8% |
| **CANSLIM Screener** (`canslim-screener`) | 本番 | はい | はい | 98.9% |
| **Contrarian Setup Gate** (`contrarian-setup-gate`) | 本番 | はい | はい | 98.3% |
| **COT Contrarian Detector** (`cot-contrarian-detector`) | 本番 | はい | はい | 77.9% |
| **Crypto Regime Analyzer** (`crypto-regime-analyzer`) | ベータ | はい | はい | 82.4% |
| **Data Quality Checker** (`data-quality-checker`) | 本番 | はい | はい | 78.5% |
| **Dividend Growth Pullback Screener** (`dividend-growth-pullback-screener`) | 本番 | はい | はい | 98.9% |
| **Downtrend Duration Analyzer** (`downtrend-duration-analyzer`) | 本番 | はい | はい | 85.3% |
| **Drawdown Circuit Breaker** (`drawdown-circuit-breaker`) | 本番 | はい | はい | 89.4% |
| **Dual Axis Skill Reviewer** (`dual-axis-skill-reviewer`) | 本番 | はい | はい | 73.2% |
| **Earnings Calendar** (`earnings-calendar`) | 本番 | はい | はい | 75.7% |
| **Earnings Trade Analyzer** (`earnings-trade-analyzer`) | 本番 | はい | はい | 84.6% |
| **Economic Calendar Fetcher** (`economic-calendar-fetcher`) | 本番 | はい | はい | 83.6% |
| **Edge Candidate Agent** (`edge-candidate-agent`) | 本番 | はい | はい | 99.3% |
| **Edge Concept Synthesizer** (`edge-concept-synthesizer`) | 本番 | はい | はい | 91.9% |
| **Edge Hint Extractor** (`edge-hint-extractor`) | 本番 | はい | はい | 74.2% |
| **Edge Pipeline Orchestrator** (`edge-pipeline-orchestrator`) | 本番 | はい | はい | 91.8% |
| **Edge Signal Aggregator** (`edge-signal-aggregator`) | 本番 | はい | はい | 79.5% |
| **Edge Strategy Designer** (`edge-strategy-designer`) | 本番 | はい | はい | 99.3% |
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | 本番 | はい | はい | 92.0% |
| **Exposure Coach** (`exposure-coach`) | 本番 | はい | はい | 84.8% |
| **Finviz Screener** (`finviz-screener`) | 本番 | はい | はい | 97.7% |
| **FTD Detector** (`ftd-detector`) | 本番 | はい | はい | 89.8% |
| **Futures Position Sizer** (`futures-position-sizer`) | 本番 | はい | はい | 93.5% |
| **FXMacroData Calendar** (`fxmacrodata-calendar`) | ベータ | はい | はい | 96.0% |
| **IBD Distribution Day Monitor** (`ibd-distribution-day-monitor`) | 本番 | はい | はい | 98.7% |
| **Institutional Flow Tracker** (`institutional-flow-tracker`) | 本番 | はい | はい | 75.7% |
| **Kanchi Dividend Review Monitor** (`kanchi-dividend-review-monitor`) | 本番 | はい | はい | 82.2% |
| **Kanchi Dividend SOP** (`kanchi-dividend-sop`) | 本番 | はい | はい | 76.2% |
| **Kanchi Dividend US Tax Accounting** (`kanchi-dividend-us-tax-accounting`) | 本番 | はい | はい | 70.5% |
| **Macro Regime Detector** (`macro-regime-detector`) | 本番 | はい | はい | 86.1% |
| **manifoldbt Backtester** (`manifoldbt-backtester`) | ベータ | はい | はい | 82.2% |
| **Market Breadth Analyzer** (`market-breadth-analyzer`) | 本番 | はい | はい | 80.8% |
| **Market Environment Analysis** (`market-environment-analysis`) | 本番 | はい | はい | 89.6% |
| **Market News Analyst** (`market-news-analyst`) | 本番 | いいえ | いいえ | not yet measured |
| **Market Top Detector** (`market-top-detector`) | 本番 | はい | はい | 86.2% |
| **MT5 Robot Tester** (`mt5-robot-tester`) | ベータ | はい | はい | 79.0% |
| **News Reaction Failure Analyzer** (`news-reaction-failure-analyzer`) | 本番 | はい | はい | 82.7% |
| **Options Strategy Advisor** (`options-strategy-advisor`) | 本番 | はい | はい | 80.1% |
| **Pair Trade Screener** (`pair-trade-screener`) | 本番 | はい | はい | 100.0% |
| **Parabolic Short Trade Planner** (`parabolic-short-trade-planner`) | 本番 | はい | はい | 76.6% |
| **PEAD Screener** (`pead-screener`) | 本番 | はい | はい | 89.3% |
| **Portfolio Manager** (`portfolio-manager`) | 本番 | はい | はい | 95.9% |
| **Position Sizer** (`position-sizer`) | 本番 | はい | はい | 89.3% |
| **Pre-Trade Discipline Gate** (`pre-trade-discipline-gate`) | 本番 | はい | はい | 85.3% |
| **Residual Edge Analyzer** (`residual-edge-analyzer`) | ベータ | はい | はい | 82.4% |
| **Scenario Analyzer** (`scenario-analyzer`) | 本番 | いいえ | いいえ | not yet measured |
| **Sector Analyst** (`sector-analyst`) | 本番 | はい | はい | 81.6% |
| **Signal Postmortem** (`signal-postmortem`) | 本番 | はい | はい | 90.3% |
| **Skill Designer** (`skill-designer`) | 本番 | はい | はい | 100.0% |
| **Skill Idea Miner** (`skill-idea-miner`) | 本番 | はい | はい | 85.5% |
| **Skill Integration Tester** (`skill-integration-tester`) | 本番 | はい | はい | 70.5% |
| **Stanley Druckenmiller Investment** (`stanley-druckenmiller-investment`) | 本番 | はい | はい | 82.6% |
| **Stockbee 20% Study** (`stockbee-20pct-study`) | ベータ | はい | はい | 74.3% |
| **Stockbee Episodic Pivot Analyzer** (`stockbee-episodic-pivot-analyzer`) | ベータ | はい | はい | 99.5% |
| **Stockbee Exhaustion Hammer Screener** (`stockbee-exhaustion-hammer-screener`) | ベータ | はい | はい | 98.9% |
| **Stockbee Momentum Burst Screener** (`stockbee-momentum-burst-screener`) | ベータ | はい | はい | 99.7% |
| **Stockbee Setup Fluency Trainer** (`stockbee-setup-fluency-trainer`) | ベータ | はい | はい | 100.0% |
| **Strategy Pivot Designer** (`strategy-pivot-designer`) | 本番 | はい | はい | 95.9% |
| **Technical Analyst** (`technical-analyst`) | 本番 | はい | はい | 90.9% |
| **Theme Detector** (`theme-detector`) | 本番 | はい | はい | 86.4% |
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | 本番 | はい | はい | 73.6% |
| **Trade Performance Coach** (`trade-performance-coach`) | ベータ | はい | はい | 96.2% |
| **Trader Memory Core** (`trader-memory-core`) | 本番 | はい | はい | 88.5% |
| **Trading Skills Navigator** (`trading-skills-navigator`) | 本番 | はい | はい | 85.3% |
| **Uptrend Analyzer** (`uptrend-analyzer`) | 本番 | はい | はい | 89.8% |
| **US Market Bubble Detector** (`us-market-bubble-detector`) | 本番 | はい | はい | 96.1% |
| **US Stock Analysis** (`us-stock-analysis`) | 本番 | いいえ | いいえ | not yet measured |
| **US Undervalued Growth Screener** (`us-undervalued-growth-screener`) | ベータ | はい | はい | 79.3% |
| **Value Dividend Screener** (`value-dividend-screener`) | 本番 | はい | はい | 98.9% |
| **VCP Screener** (`vcp-screener`) | 本番 | はい | はい | 76.1% |
| **Weekly Performance Digest** (`weekly-performance-digest`) | 本番 | はい | はい | 94.2% |

## 入力証跡

上記の収集日時は各入力の測定日時とは異なります。生成ページの一致は再現性の確認であり、証跡の鮮度を保証しません。

| 入力 | 測定コミット | 測定 / 実行更新日時 | 出典 |
|---|---|---|---|
| catalog | b29c6dfc2d4dc82bdfcfc13891e490863283405f | 2026-10-17T07:11:43Z | skills-index.yaml; config/ci-test-policy.yaml; examples/workflows/replay-coverage.yaml |
| per\_skill\_coverage\_pct | b29c6dfc2d4dc82bdfcfc13891e490863283405f | 2026-10-16T11:46:22Z | https://github.com/tradermonty/claude-trading-skills/actions/runs/38895293520/artifacts/12043243687 |
| beta\_since | not-yet-measured | not-yet-measured | not-yet-measured |
| dual\_axis\_score\_distribution | not-yet-measured | not-yet-measured | not-yet-measured |
| open\_high\_severity\_issues | not applicable (live issue state) | 2026-10-17T07:11:43Z | https://github.com/tradermonty/claude-trading-skills/issues |
| last\_successful\_ci\_timestamp | b29c6dfc2d4dc82bdfcfc13891e490863283405f | 2026-10-16T11:46:22Z | https://github.com/tradermonty/claude-trading-skills/actions/runs/38895293520 |
| drift\_status | not-yet-measured | not-yet-measured | not-yet-measured |
| production\_verification\_declarations | b29c6dfc2d4dc82bdfcfc13891e490863283405f | 2026-10-17T07:11:43Z | skills-index.yaml; config/ci-test-policy.yaml; examples/workflows/replay-coverage.yaml |
| executed\_smoke\_count | not-yet-measured | not-yet-measured | not-yet-measured |
| latest\_successful\_live\_sample | not-yet-measured | not-yet-measured | not-yet-measured |

## 本番スキルの検証宣言

カタログ上の宣言です。この収集処理は元の監査を再実行しません。

| Axis | passed | not_verified | not_applicable |
|---|---:|---:|---:|
| data\_provenance | 0 | 61 | 1 |
| empirical\_validation | 0 | 54 | 8 |
| end\_to\_end\_replay | 5 | 32 | 25 |
| financial\_logic\_review | 0 | 61 | 1 |
| instruction\_contract | 0 | 62 | 0 |
| security\_review | 0 | 62 | 0 |
| unit\_tests | 0 | 59 | 3 |
| workflow\_contract | 5 | 32 | 25 |

## ランタイム指標（スナップショット）

高深刻度件数はリポジトリ全体の P0/P1 タイトル・ラベルによる集計であり、各スキルのリリース承認ではありません。

| 指標 | 値 |
|---|---|
| スナップショット基準日: | 2026-10-17T07:11:43Z |
| Dual-axis スコア分布 | not-yet-measured |
| 高深刻度の未解決 Issue | 5 |
| 直近の成功 CI | 2026-10-16T11:46:22Z |
| パッケージ差分 | not-yet-measured |
| ドキュメント差分 | not-yet-measured |
| ナビゲータ差分 | not-yet-measured |
| スモーク実行件数 | not-yet-measured |
| 直近の成功ライブデータサンプル | not-yet-measured |
