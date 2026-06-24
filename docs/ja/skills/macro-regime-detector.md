---
layout: default
title: "Macro Regime Detector"
grand_parent: 日本語
parent: スキルガイド
nav_order: 29
lang_peer: /en/skills/macro-regime-detector/
permalink: /ja/skills/macro-regime-detector/
---

# Macro Regime Detector
{: .no_toc }

クロスアセット比率分析を用いて、構造的なマクロレジーム転換（1〜2年の期間）を検出します。RSP/SPY集中度、イールドカーブ、信用環境、サイズファクター、株式-債券関係、セクターローテーションを分析し、Concentration、Broadening、Contraction、Inflationary、Transitionalの各状態間のレジームシフトを特定します。マクロレジーム、市場レジーム変化、構造的ローテーション、長期的な市場ポジショニングについて聞かれた際に実行します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/macro-regime-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/macro-regime-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

クロスアセット比率分析を用いて構造的なマクロレジーム転換を検出するスキルです。

---

## 2. 使用タイミング

- ユーザーが現在のマクロレジームやレジーム転換について質問した場合
- ユーザーが構造的な市場ローテーション（集中 vs 分散）を理解したい場合
- ユーザーがイールドカーブ、信用環境、クロスアセットシグナルに基づく長期ポジショニングについて質問した場合
- ユーザーがRSP/SPY比率、IWM/SPY、HYG/LQDなどのクロスアセット比率に言及した場合
- ユーザーがレジーム変化が進行中かどうかを評価したい場合

---

## 3. 前提条件

- **FMP APIキー**（必須）: 環境変数 `FMP_API_KEY` を設定するか `--api-key` を渡す
- 無料枠（250コール/日）で十分（スクリプトは約10コールを使用）

---

## 4. クイックスタート

```bash
python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
```

---

## 5. ワークフロー

1. 方法論のコンテキストとしてリファレンスドキュメントを読み込む:
   - `references/regime_detection_methodology.md`
   - `references/indicator_interpretation_guide.md`

2. メイン分析スクリプトを実行:
   ```bash
   python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
   ```
   9つのETF + 国債金利の600日分のデータを取得します（合計10 APIコール）。

3. 生成されたMarkdownレポートを読み、ユーザーに結果を提示。

4. ユーザーが歴史的な類似事例について質問した場合、`references/historical_regimes.md` を使用して追加コンテキストを提供。

---

## 6. コンポーネント

| # | コンポーネント | 比率/データ | ウェイト | 検出対象 |
|---|--------------|------------|---------|---------|
| 1 | 市場集中度 | RSP/SPY | 25% | メガキャップ集中 vs 市場の広がり |
| 2 | イールドカーブ | 10Y-2Yスプレッド | 20% | 金利サイクルの転換 |
| 3 | クレジット状況 | HYG/LQD | 15% | クレジットサイクルのリスク選好 |
| 4 | サイズファクター | IWM/SPY | 15% | 小型株 vs 大型株ローテーション |
| 5 | 株式-債券関係 | SPY/TLT + 相関 | 15% | 株式・債券の関係レジーム |
| 6 | セクターローテーション | XLY/XLP | 10% | 景気敏感 vs ディフェンシブ |

---

## 7. レジーム分類

- **Concentration（集中）**: メガキャップ主導、狭い相場。大型テック・グロース集中。
- **Broadening（分散）**: 市場参加拡大、小型・バリューローテーション。均等加重・景気敏感への配分を増加。
- **Contraction（収縮）**: 信用引き締め、ディフェンシブローテーション。キャッシュ増加、生活必需品・ヘルスケア優先。
- **Inflationary（インフレ）**: 株式・債券の正相関、伝統的ヘッジが機能しない。実物資産、TIPS、短期債券。
- **Transitional（移行）**: 複数シグナルが点灯するが明確なパターンなし。分散を高め、集中したポジションを避ける。

---

## 8. 出力

`--output-dir`（デフォルト: カレントディレクトリ）に2ファイルを保存:

- `macro_regime_YYYY-MM-DD_HHMMSS.json` — プログラム処理向け構造化データ
- `macro_regime_YYYY-MM-DD_HHMMSS.md` — 可読レポート（以下を含む）:
  1. 現在のレジーム評価
  2. 転換シグナルダッシュボード
  3. コンポーネント詳細
  4. レジーム分類の根拠
  5. ポートフォリオポスチャー推奨

---

## 9. 他スキルとの関係

| 観点 | Macro Regime Detector | Market Top Detector | Market Breadth Analyzer |
|------|----------------------|--------------------|-----------------------|
| 時間軸 | 1〜2年（構造的） | 2〜8週（戦術的） | 現在のスナップショット |
| データ粒度 | 月次（6M/12M SMA） | 日次（25営業日） | 日次CSV |
| 検出対象 | レジーム転換 | 10〜20%の調整 | ブレッドスヘルス |
| APIコール数 | 約10回 | 約33回 | 0回（無料CSV） |

---

## 10. スクリプト引数

```bash
python3 macro_regime_detector.py [options]

オプション:
  --api-key KEY       FMP APIキー（デフォルト: $FMP_API_KEY）
  --output-dir DIR    出力ディレクトリ（デフォルト: カレントディレクトリ）
  --days N            取得する履歴日数（デフォルト: 600）
```

---

## 11. リソース

**リファレンス:**

- `skills/macro-regime-detector/references/historical_regimes.md`
- `skills/macro-regime-detector/references/indicator_interpretation_guide.md`
- `skills/macro-regime-detector/references/regime_detection_methodology.md`

**スクリプト:**

- `skills/macro-regime-detector/scripts/fmp_client.py`
- `skills/macro-regime-detector/scripts/macro_regime_detector.py`
- `skills/macro-regime-detector/scripts/report_generator.py`
- `skills/macro-regime-detector/scripts/scorer.py`
