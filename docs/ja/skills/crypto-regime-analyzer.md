---
layout: default
title: "Crypto Regime Analyzer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 15
lang_peer: /en/skills/crypto-regime-analyzer/
permalink: /ja/skills/crypto-regime-analyzer/
generated: false
---

# Crypto Regime Analyzer
{: .no_toc }

無料かつAPIキー不要の公開データ（CoinGeckoとBinance Funding）を使い、暗号資産市場のレジーム健全度を定量化します。BTCのトレンド、アルトコインの市場参加度、BTCドミナンス、無期限先物の資金調達率、ドローダウンとボラティリティ、モメンタムの6要素を0〜100点で合成し、市場環境に応じた姿勢を提示します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/crypto-regime-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/crypto-regime-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Crypto Regime Analyzerは、個別の暗号資産を分析する前に「現在の市場環境がどの程度リスクオンを支持しているか」を確認するためのスキルです。100点は広い市場参加、健全なトレンド、過熱していないレバレッジを伴う強いリスクオン環境を、0点は重大なリスクオフ環境を示します。

このスコアは市場環境の説明用です。個別銘柄の推奨、売買シグナル、価格目標、注文執行、ポートフォリオ変更は行いません。

---

## 2. 使用タイミング

- 「暗号資産市場はいまリスクオンか、リスクオフか」を確認したいとき
- 暗号資産市場全体の健全度を知りたいとき
- アルトシーズンか、BTCドミナンスがどちらへ向かっているかを確認したいとき
- 無期限先物の資金調達率が過熱していないかを調べたいとき
- 個別銘柄のスクリーニング前に、暗号資産枠の市場姿勢を整理したいとき
- 株式の`market-regime-daily`と並行して日次の暗号資産レジームを確認したいとき

---

## 3. 前提条件

- **Python 3.9以上**。ライブモードでは`requests`が必要です。オフラインモードは標準ライブラリのみで動作します。
- ライブモードでは`api.coingecko.com`と`fapi.binance.com`へのインターネット接続が必要です。
- APIキーは不要です。

---

## 4. クイックスタート

```bash
mkdir -p reports/<routine-or-date>
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --output-dir reports/<routine-or-date>
```

---

## 5. ワークフロー

### Phase 1：分析スクリプトを実行する

**ライブモード**ではCoinGeckoとBinanceの公開エンドポイントからデータを取得します。デフォルトの`--top-n 20`では、無料枠のレート制限に配慮するため初回実行に約2〜4分かかります。同日中の再実行ではキャッシュを利用します。

```bash
mkdir -p reports/<routine-or-date>
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --output-dir reports/<routine-or-date>
```

**オフラインモード**ではネットワークを使用せず、保存済みのスナップショットを読み込みます。入力JSONの仕様は`references/crypto_regime_methodology.md`を参照してください。

```bash
python3 skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py \
  --input-json snapshot.json \
  --output-dir reports/<routine-or-date>
```

主なオプションは、対象ユニバース数を指定する`--top-n <int>`（デフォルト20）、キャッシュ先を指定する`--cache-dir <path>`（デフォルト`.crypto_regime_cache`）、進捗表示を抑制する`--quiet`です。

### Phase 2：出力を解釈する

スクリプトは、後続スキルとの連携に使える`crypto_regime.json`と、1ページ形式の`crypto_regime.md`を出力し、次のような要約を標準出力へ表示します。

```text
CRYPTO REGIME: NEUTRAL (score 68.4/100) — Mixed conditions observed; no strong regime conclusion
```

結果を提示するときは、最初にゾーンと姿勢を示し、次にスコアへの寄与が大きかった1〜2要素を各`signal`の根拠とともに説明してください。`data_available: false`の要素がある場合は、その欠損と信頼度への影響も明示します。

### Phase 3：後続処理へ渡す（任意）

JSONの合成結果は、`exposure-coach`形式の姿勢サマリーにおける、暗号資産市場を説明する入力の一つとして利用できます。ただし、この結果だけで取引の許可・禁止、ポジションサイズ決定、注文執行を行ってはいけません。

---

## 6. 6つの構成要素

| # | 構成要素 | ウェイト | 確認する内容 |
|---|---|---:|---|
| 1 | BTCトレンド構造 | 25% | 終値、50日移動平均、200日移動平均、200日移動平均の傾き |
| 2 | アルトコイン市場参加度 | 20% | 上位ユニバースのうち50日・200日移動平均を上回る割合 |
| 3 | BTCドミナンス・レジーム | 15% | BTCトレンドと組み合わせた資金循環の方向 |
| 4 | 無期限先物Fundingレジーム | 15% | 主要銘柄の平均資金調達率とレバレッジの過熱度 |
| 5 | ドローダウンとボラティリティ | 15% | 過去1年高値からの下落率と実現ボラティリティ順位 |
| 6 | モメンタム・スラスト／ウォッシュアウト | 10% | 30日リターンがプラスの銘柄比率 |

データが欠けた要素のウェイトは、少なくとも4要素かつ元のモデルウェイトの65%以上が残る場合に限り、利用可能な要素へ比例配分されます。それ未満の場合、判定は`UNKNOWN`となります。

---

## 7. スコアの読み方

| スコア | ゾーン | 解釈 |
|---:|---|---|
| 80〜100 | RISK_ON | 広範なリスクオン環境が観測されています。判断前にリスク上限を確認します。 |
| 40〜79 | NEUTRAL | 条件が混在しており、強いレジーム結論はありません。 |
| 0〜39 | RISK_OFF | 防御的な市場環境が観測されています。既存のリスク管理を確認します。 |

これらは説明用のヒューリスティックな区分であり、検証済みの資産配分ルールではありません。現在の検証範囲と再現条件は`references/VALIDATION.md`を参照してください。

---

## 8. 出力

- `crypto_regime.json`：`metadata`、各構成要素の`score`・`signal`・`data_available`、合成結果の`score`・`zone`・`guidance`・`effective_weights`を含む機械可読レポート
- `crypto_regime.md`：合成スコア、ゾーンバー、姿勢、構成要素別のウェイト・スコア・シグナル、信頼度に関する注記をまとめた1ページレポート
- コンソール：`CRYPTO REGIME: <ZONE> (score <N>/100) — <posture>`形式の要約

---

## 9. 制約と注意事項

- CoinGecko無料枠はBTCドミナンスの履歴を提供しないため、ライブモードではキャッシュへ1日1観測を蓄積します。31観測未満ではこの要素を利用できません。
- Binance Fundingはベストエフォートです。地域制限や障害で取得できない場合、その要素を安全にスキップします。
- 対象は時価総額上位N銘柄からステーブルコイン、ラップド資産、ステーキング派生資産などを除いた動的ユニバースであり、固定指数ではありません。
- 閾値は解釈しやすさを優先した保守的なデフォルトで、最適化済みの売買エッジではありません。
- 入力は有限値・範囲・正数条件を検証し、計算結果に非有限値が生じた場合は非標準JSONとして出力しません。

---

## 10. リソース

**リファレンス：**

- `skills/crypto-regime-analyzer/references/VALIDATION.md`
- `skills/crypto-regime-analyzer/references/crypto_regime_methodology.md`

**スクリプト：**

- `skills/crypto-regime-analyzer/scripts/crypto_regime_analyzer.py`
- `skills/crypto-regime-analyzer/scripts/data_client.py`
- `skills/crypto-regime-analyzer/scripts/report_generator.py`
- `skills/crypto-regime-analyzer/scripts/scorer.py`

---

教育およびプロセス改善を目的としたスキルです。金融助言、売買シグナル、注文指示を提供するものではなく、最終的な判断は利用者自身が行います。

[English版ガイドを見る]({{ '/en/skills/crypto-regime-analyzer/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
