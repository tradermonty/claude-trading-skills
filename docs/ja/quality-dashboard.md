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

スナップショット基準日: `2026-09-12T00:00:00Z`

## ライフサイクル

| 合計 | 本番 | ベータ | 知識のみ | 実行可能 | テストあり | テストなし |
|---:|---:|---:|---:|---:|---:|---:|
| 74 | 58 | 16 | 3 | 71 | 71 | 0 |

## テストカバレッジ

- 全体カバレッジ目標: 75.0%
- 全体カバレッジ下限: 72.0%
- 許容失敗: 0 (目標 0)

## E2E リプレイ

- E2E リプレイでカバーされたワークフロー: 7 / 11

## 依存関係

| プロバイダ | 件数 |
|---|---:|
| FMP | 29 |
| FINVIZ | 4 |
| ALPACA | 2 |
| なし（オフライン / 純粋計算） | 43 |

## ベータパイプライン

| スキル | ベータ経過日数 |
|---|---:|
| `contrarian-setup-gate` | not yet measured |
| `crypto-regime-analyzer` | not yet measured |
| `drawdown-circuit-breaker` | not yet measured |
| `futures-position-sizer` | not yet measured |
| `fxmacrodata-calendar` | not yet measured |
| `manifoldbt-backtester` | not yet measured |
| `mt5-robot-tester` | not yet measured |
| `pre-trade-discipline-gate` | not yet measured |
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
| **Backtest Expert** (`backtest-expert`) | 本番 | はい | はい | not yet measured |
| **Breadth Chart Analyst** (`breadth-chart-analyst`) | 本番 | はい | はい | not yet measured |
| **Breakout Trade Planner** (`breakout-trade-planner`) | 本番 | はい | はい | not yet measured |
| **CANSLIM Screener** (`canslim-screener`) | 本番 | はい | はい | not yet measured |
| **Contrarian Setup Gate** (`contrarian-setup-gate`) | ベータ | はい | はい | not yet measured |
| **COT Contrarian Detector** (`cot-contrarian-detector`) | 本番 | はい | はい | not yet measured |
| **Crypto Regime Analyzer** (`crypto-regime-analyzer`) | ベータ | はい | はい | not yet measured |
| **Data Quality Checker** (`data-quality-checker`) | 本番 | はい | はい | not yet measured |
| **Dividend Growth Pullback Screener** (`dividend-growth-pullback-screener`) | 本番 | はい | はい | not yet measured |
| **Downtrend Duration Analyzer** (`downtrend-duration-analyzer`) | 本番 | はい | はい | not yet measured |
| **Drawdown Circuit Breaker** (`drawdown-circuit-breaker`) | ベータ | はい | はい | not yet measured |
| **Dual Axis Skill Reviewer** (`dual-axis-skill-reviewer`) | 本番 | はい | はい | not yet measured |
| **Earnings Calendar** (`earnings-calendar`) | 本番 | はい | はい | not yet measured |
| **Earnings Trade Analyzer** (`earnings-trade-analyzer`) | 本番 | はい | はい | not yet measured |
| **Economic Calendar Fetcher** (`economic-calendar-fetcher`) | 本番 | はい | はい | not yet measured |
| **Edge Candidate Agent** (`edge-candidate-agent`) | 本番 | はい | はい | not yet measured |
| **Edge Concept Synthesizer** (`edge-concept-synthesizer`) | 本番 | はい | はい | not yet measured |
| **Edge Hint Extractor** (`edge-hint-extractor`) | 本番 | はい | はい | not yet measured |
| **Edge Pipeline Orchestrator** (`edge-pipeline-orchestrator`) | 本番 | はい | はい | not yet measured |
| **Edge Signal Aggregator** (`edge-signal-aggregator`) | 本番 | はい | はい | not yet measured |
| **Edge Strategy Designer** (`edge-strategy-designer`) | 本番 | はい | はい | not yet measured |
| **Edge Strategy Reviewer** (`edge-strategy-reviewer`) | 本番 | はい | はい | not yet measured |
| **Exposure Coach** (`exposure-coach`) | 本番 | はい | はい | not yet measured |
| **Finviz Screener** (`finviz-screener`) | 本番 | はい | はい | not yet measured |
| **FTD Detector** (`ftd-detector`) | 本番 | はい | はい | not yet measured |
| **Futures Position Sizer** (`futures-position-sizer`) | ベータ | はい | はい | not yet measured |
| **FXMacroData Calendar** (`fxmacrodata-calendar`) | ベータ | はい | はい | not yet measured |
| **IBD Distribution Day Monitor** (`ibd-distribution-day-monitor`) | 本番 | はい | はい | not yet measured |
| **Institutional Flow Tracker** (`institutional-flow-tracker`) | 本番 | はい | はい | not yet measured |
| **Kanchi Dividend Review Monitor** (`kanchi-dividend-review-monitor`) | 本番 | はい | はい | not yet measured |
| **Kanchi Dividend SOP** (`kanchi-dividend-sop`) | 本番 | はい | はい | not yet measured |
| **Kanchi Dividend US Tax Accounting** (`kanchi-dividend-us-tax-accounting`) | 本番 | はい | はい | not yet measured |
| **Macro Regime Detector** (`macro-regime-detector`) | 本番 | はい | はい | not yet measured |
| **manifoldbt Backtester** (`manifoldbt-backtester`) | ベータ | はい | はい | not yet measured |
| **Market Breadth Analyzer** (`market-breadth-analyzer`) | 本番 | はい | はい | not yet measured |
| **Market Environment Analysis** (`market-environment-analysis`) | 本番 | はい | はい | not yet measured |
| **Market News Analyst** (`market-news-analyst`) | 本番 | いいえ | いいえ | not yet measured |
| **Market Top Detector** (`market-top-detector`) | 本番 | はい | はい | not yet measured |
| **MT5 Robot Tester** (`mt5-robot-tester`) | ベータ | はい | はい | not yet measured |
| **News Reaction Failure Analyzer** (`news-reaction-failure-analyzer`) | 本番 | はい | はい | not yet measured |
| **Options Strategy Advisor** (`options-strategy-advisor`) | 本番 | はい | はい | not yet measured |
| **Pair Trade Screener** (`pair-trade-screener`) | 本番 | はい | はい | not yet measured |
| **Parabolic Short Trade Planner** (`parabolic-short-trade-planner`) | 本番 | はい | はい | not yet measured |
| **PEAD Screener** (`pead-screener`) | 本番 | はい | はい | not yet measured |
| **Portfolio Manager** (`portfolio-manager`) | 本番 | はい | はい | not yet measured |
| **Position Sizer** (`position-sizer`) | 本番 | はい | はい | not yet measured |
| **Pre-Trade Discipline Gate** (`pre-trade-discipline-gate`) | ベータ | はい | はい | not yet measured |
| **Residual Edge Analyzer** (`residual-edge-analyzer`) | ベータ | はい | はい | not yet measured |
| **Scenario Analyzer** (`scenario-analyzer`) | 本番 | いいえ | いいえ | not yet measured |
| **Sector Analyst** (`sector-analyst`) | 本番 | はい | はい | not yet measured |
| **Signal Postmortem** (`signal-postmortem`) | 本番 | はい | はい | not yet measured |
| **Skill Designer** (`skill-designer`) | 本番 | はい | はい | not yet measured |
| **Skill Idea Miner** (`skill-idea-miner`) | 本番 | はい | はい | not yet measured |
| **Skill Integration Tester** (`skill-integration-tester`) | 本番 | はい | はい | not yet measured |
| **Stanley Druckenmiller Investment** (`stanley-druckenmiller-investment`) | 本番 | はい | はい | not yet measured |
| **Stockbee 20% Study** (`stockbee-20pct-study`) | ベータ | はい | はい | not yet measured |
| **Stockbee Episodic Pivot Analyzer** (`stockbee-episodic-pivot-analyzer`) | ベータ | はい | はい | not yet measured |
| **Stockbee Exhaustion Hammer Screener** (`stockbee-exhaustion-hammer-screener`) | ベータ | はい | はい | not yet measured |
| **Stockbee Momentum Burst Screener** (`stockbee-momentum-burst-screener`) | ベータ | はい | はい | not yet measured |
| **Stockbee Setup Fluency Trainer** (`stockbee-setup-fluency-trainer`) | ベータ | はい | はい | not yet measured |
| **Strategy Pivot Designer** (`strategy-pivot-designer`) | 本番 | はい | はい | not yet measured |
| **Technical Analyst** (`technical-analyst`) | 本番 | はい | はい | not yet measured |
| **Theme Detector** (`theme-detector`) | 本番 | はい | はい | not yet measured |
| **Trade Hypothesis Ideator** (`trade-hypothesis-ideator`) | 本番 | はい | はい | not yet measured |
| **Trade Performance Coach** (`trade-performance-coach`) | ベータ | はい | はい | not yet measured |
| **Trader Memory Core** (`trader-memory-core`) | 本番 | はい | はい | not yet measured |
| **Trading Skills Navigator** (`trading-skills-navigator`) | 本番 | はい | はい | not yet measured |
| **Uptrend Analyzer** (`uptrend-analyzer`) | 本番 | はい | はい | not yet measured |
| **US Market Bubble Detector** (`us-market-bubble-detector`) | 本番 | はい | はい | not yet measured |
| **US Stock Analysis** (`us-stock-analysis`) | 本番 | いいえ | いいえ | not yet measured |
| **US Undervalued Growth Screener** (`us-undervalued-growth-screener`) | ベータ | はい | はい | not yet measured |
| **Value Dividend Screener** (`value-dividend-screener`) | 本番 | はい | はい | not yet measured |
| **VCP Screener** (`vcp-screener`) | 本番 | はい | はい | not yet measured |
| **Weekly Performance Digest** (`weekly-performance-digest`) | 本番 | はい | はい | not yet measured |

## ランタイム指標（スナップショット）

| 指標 | 値 |
|---|---|
| スナップショット基準日: | 2026-09-12T00:00:00Z |
| Dual-axis スコア分布 | not-yet-measured |
| 高深刻度の未解決 Issue | not-yet-measured |
| 直近の成功 CI | not-yet-measured |
| パッケージ差分 | not-yet-measured |
| ドキュメント差分 | not-yet-measured |
| ナビゲータ差分 | not-yet-measured |
