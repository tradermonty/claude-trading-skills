---
layout: default
title: ワークフローの選び方
parent: 日本語
nav_order: 6
lang_peer: /en/find-your-workflow/
permalink: /ja/find-your-workflow/
---

# ワークフローの選び方
{: .no_toc }

Solo Trader OS の静的な「どこから始めるか」ガイドです。[スキル一覧](skill-catalog.md)
や[ワークフロー](workflows.md)ページを見る前に、本ページで自分の状況に合った
入口ワークフローを一読で見つけられます。

下の表のどれにも該当しない場合は、
[**`trading-skills-navigator`**](skills/trading-skills-navigator.md)
に自然言語で目的を伝えてください。同じ推薦結果を機械的に返します。

---

## 毎日のリズムで選ぶ

| あなたの状況 | 始めるワークフロー |
|---|---|
| 寄り付き前の15分間で相場確認したい | [`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml) |
| 相場環境が許すときだけスイングトレードしたい | [`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml) → [`swing-opportunity-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/swing-opportunity-daily.yaml) |
| 長期ポートフォリオを週次で見直したい | [`core-portfolio-weekly`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/core-portfolio-weekly.yaml) |
| 約定したトレードから学びたい | [`trade-memory-loop`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/trade-memory-loop.yaml) |
| 月次でパフォーマンスを振り返ってルールを見直したい | [`monthly-performance-review`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/monthly-performance-review.yaml) |

> 迷う場合は [`trading-skills-navigator`](skills/trading-skills-navigator.md)
> に自然言語で日常のリズムを伝えてください。

---

## 目的で選ぶ

| あなたの目的 | スキルセット | 駆動ワークフロー |
|---|---|---|
| まず今日が risk-on か risk-off かを知りたい | [`market-regime`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/market-regime.yaml) | `market-regime-daily` |
| Core（配当・ETF・長期保有）の長期ポートフォリオを運用したい | [`core-portfolio`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/core-portfolio.yaml) | `core-portfolio-weekly` |
| 相場が許すときだけ規律あるサテライト・スイング候補を探したい | [`swing-opportunity`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/swing-opportunity.yaml) | `swing-opportunity-daily` |
| 全トレードを記録し、ポストモーテムを生成し、学びを journal に残したい | [`trade-memory`](https://github.com/tradermonty/claude-trading-skills/blob/main/skillsets/trade-memory.yaml) | `trade-memory-loop`, `monthly-performance-review` |

> 自分の目的がどれに合うか迷う場合は [`trading-skills-navigator`](skills/trading-skills-navigator.md)
> に自由記述の目的を伝えれば、スキルセットとワークフローに対応付けてくれます。

---

## 既存ワークフローに当てはまらない場合

### API キー不要の入口

FMP / FINVIZ / Alpaca の有料サブスクをまだ持っていない場合は、まずこの5つの
スキルを手動で回してください。同じ最小ループが
[`market-regime-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/market-regime-daily.yaml)
と
[`trade-memory-loop`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/trade-memory-loop.yaml)
を有料データなしで支えます。

1. [`market-breadth-analyzer`](skills/market-breadth-analyzer.md) — 公開 CSV による breadth スコア
2. [`uptrend-analyzer`](skills/uptrend-analyzer.md) — 公開 CSV の uptrend 参加比率
3. [`position-sizer`](skills/position-sizer.md) — 純粋計算
4. [`trader-memory-core`](skills/trader-memory-core.md) — ローカル YAML での journaling
5. [`signal-postmortem`](skills/signal-postmortem.md) — レビューフレームワーク

「API なし」は「外部データなし」ではありません。これらのスキルは公開 CSV・
チャート画像・ローカルファイルを必要とします。正確な入力要件は各スキルの
[`skills-index.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills-index.yaml)
の `integrations:` 欄を参照してください。

### 既知のギャップ

一部のユースケースには、まだパッケージ化されたワークフローがありません。これらは
[`PROJECT_VISION.md`](https://github.com/tradermonty/claude-trading-skills/blob/main/PROJECT_VISION.md)
で次の作業候補として明示的に追跡されています。

- **ショート専用 / risk-off 日中** — `parabolic-short-trade-planner` で部分的に
  カバーされていますが、エンドツーエンドのショートワークフローはまだありません
- **決算週の日中** — `earnings-trade-analyzer` と `pead-screener` で部分的に
  カバーされていますが、週次のオーケストレーションワークフローはまだありません
- **戦略リサーチパイプライン** — `edge-pipeline-orchestrator` はありますが、
  「新しいエッジを発見する」という canonical なワークフロー manifest は
  まだありません

あなたの状況がこれらのギャップに該当する場合は、探索的に扱ってください。
[スキル一覧](skill-catalog.md) から必要な個別スキルを選び、専用ワークフローが
出るまでアドホックに実行してください。

### 自由記述の自然言語による入口

上の表に該当しない状況には、
[`trading-skills-navigator`](skills/trading-skills-navigator.md)
スキルを使ってください。自由記述の目的を渡せば、最適なワークフロー、
スキルセット、API プロファイル、セットアップ手順を返します。
本ページと同じ
[`skills-index.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/skills-index.yaml)
の Single Source of Truth に基づいた推薦です。

---

## 関連ページ

- [はじめに](getting-started.md) — Claude Code / Claude ウェブアプリ / CLI 向けインストール手順
- [スキル一覧](skill-catalog.md) — 全スキルのアルファベット順カタログ
- [ワークフロー](workflows.md) — 全ワークフローの自動生成 manifest リファレンス
- [スキルセット](skillsets.md) — 目的別インストールバンドル
