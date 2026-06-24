---
layout: default
title: "Edge Candidate Agent"
grand_parent: 日本語
parent: スキルガイド
nav_order: 18
lang_peer: /en/skills/edge-candidate-agent/
permalink: /ja/skills/edge-candidate-agent/
---

# Edge Candidate Agent
{: .no_toc }

EOD観測から米国株式ロングサイドのエッジリサーチチケットを生成・優先順位付けし、trade-strategy-pipeline Phase I 向けのパイプライン対応候補スペックをエクスポートします。仮説/アノマリーを再現可能なリサーチチケットに変換する場合、検証済みアイデアを `strategy.yaml` + `metadata.json` に変換する場合、またはパイプラインバックテスト実行前にインターフェース互換性（`edge-finder-candidate/v1`）をプリフライトチェックする場合に使用します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/edge-candidate-agent.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/edge-candidate-agent){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

日々の市場観測を再現可能なリサーチチケットおよびPhase I互換の候補スペックに変換します。
積極的な戦略の大量生産よりも、シグナル品質とインターフェース互換性を優先します。
このスキルはスタンドアロンでエンドツーエンドの実行が可能ですが、分割ワークフローでは主に最終的なエクスポート/検証ステージとして機能します。

---

## 2. 使用タイミング

- 市場観測、アノマリー、仮説を構造化されたリサーチチケットに変換する場合
- EOD OHLCVとオプションのヒントから新しいエッジ候補を発見する日次自動検出を実行する場合
- 検証済みチケットを `trade-strategy-pipeline` Phase I 向けの `strategy.yaml` + `metadata.json` としてエクスポートする場合
- パイプライン実行前に `edge-finder-candidate/v1` のプリフライト互換性チェックを実行する場合

---

## 3. 前提条件

- Python 3.9+ と `PyYAML` がインストール済み
- スキーマ/ステージ検証のためにターゲットの `trade-strategy-pipeline` リポジトリへのアクセス
- `--pipeline-root` を通じたパイプライン管理検証の実行時に `uv` が利用可能

---

## 4. クイックスタート

推奨される分割ワークフロー：

1. `skills/edge-hint-extractor`: 観測/ニュース -> `hints.yaml`
2. `skills/edge-concept-synthesizer`: チケット/ヒント -> `edge_concepts.yaml`
3. `skills/edge-strategy-designer`: コンセプト -> `strategy_drafts` + エクスポート可能なチケットYAML
4. `skills/edge-candidate-agent`（本スキル）: パイプラインハンドオフ向けのエクスポート + 検証

---

## 5. ワークフロー

推奨される分割ワークフロー：

1. `skills/edge-hint-extractor`: 観測/ニュース -> `hints.yaml`
2. `skills/edge-concept-synthesizer`: チケット/ヒント -> `edge_concepts.yaml`
3. `skills/edge-strategy-designer`: コンセプト -> `strategy_drafts` + エクスポート可能なチケットYAML
4. `skills/edge-candidate-agent`（本スキル）: パイプラインハンドオフ向けのエクスポート + 検証

---

## 6. リソース

**リファレンス:**

- `skills/edge-candidate-agent/references/ideation_loop.md`
- `skills/edge-candidate-agent/references/pipeline_if_v1.md`
- `skills/edge-candidate-agent/references/research_ticket_schema.md`
- `skills/edge-candidate-agent/references/signal_mapping.md`

**スクリプト:**

- `skills/edge-candidate-agent/scripts/auto_detect_candidates.py`
- `skills/edge-candidate-agent/scripts/candidate_contract.py`
- `skills/edge-candidate-agent/scripts/export_candidate.py`
- `skills/edge-candidate-agent/scripts/validate_candidate.py`
