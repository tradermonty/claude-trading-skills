---
layout: default
title: "Contrarian Setup Gate"
grand_parent: 日本語
parent: スキルガイド
nav_order: 13
lang_peer: /en/skills/contrarian-setup-gate/
permalink: /ja/skills/contrarian-setup-gate/
generated: false
---

# Contrarian Setup Gate
{: .no_toc }

ジェイソン・シャピロの逆張りパイプラインが生成する3つの判定、COTの偏りポジション検出、ニュースフェイリュア検証、週足の価格アクション確認を1つのアクション可能な状態に統合するスキルです。フェイルクローズドな優先順位付き状態遷移マシンによって統合を行います。ネットワークアクセスもAPIキーも使わず、検証と優先順位付け以外の計算は一切行わない、純粋でオフラインな統合ゲートです。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/contrarian-setup-gate.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/contrarian-setup-gate){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

ジェイソン・シャピロの3ステップ逆張りプロセスの出力を1つのアクション可能な状態にまとめるスキルです。ステップ1のcot-contrarian-detectorが偏ったポジションを検出し、ステップ2のnews-reaction-failure-analyzerが偏りに有利なニュースへの反応失敗を検証し、ステップ3のtechnical-analyst逆張り確認モードが週足の反転を裏付けます。このゲートは3つのレポートJSONを読み込み、網羅的にテストされた明示的な優先順位ルールを適用して1つの`setup_status`を生成します。確認に至らなかった入力にはすべて、フェイルクローズドな理由が付与されます。

このゲートはデータ取得もAPI呼び出しも行いません。3つの入力を検証し組み合わせる以外の計算もしません。パイプラインの統合の中心であり、データソースではありません。

---

## 2. 使用タイミング

- cot-contrarian-detectorの実行後。このスキルは常に必須で、パイプラインの起点となります
- 検出器レポートのみが揃っている段階で、CROWDED状態と残りのステップを確認したいとき
- news-reaction-failure-analyzerの実行後、セットアップがWATCHING_PRICEに進むかREJECTEDになるかを確認したいとき
- technical-analystの逆張り確認モード実行後、セットアップがREADY_FOR_PLANに到達したかを確認したいとき
- 銘柄の方向性とストップ水準をポジションサイジングのスキルに引き継ぐ前

---

## 3. 前提条件

- **Python 3.9以上**
- **APIキーは不要です。** このスキルは完全にオフラインで動作します
- 評価対象銘柄のcot-contrarian-detector JSONレポート。必須です
- 同一銘柄のnews-reaction-failure-analyzer JSONレポート。ステップ2に相当し、任意です
- 同一銘柄のtechnical-analyst逆張り確認JSONレポート。ステップ3に相当し、任意です

---

## 4. クイックスタート

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json reports/cot_crowding_2026-07-12.json \
  --news-json reports/nrf_B6_2026-07-12.json \
  --price-action-json reports/ta_confirmation_B6_2026-07-12.json \
  --as-of 2026-07-15 \
  --output-dir reports/
```

---

## 5. ワークフロー

### Phase 1: ゲートの実行

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json reports/cot_crowding_2026-07-12.json \
  --news-json reports/nrf_B6_2026-07-12.json \
  --price-action-json reports/ta_confirmation_B6_2026-07-12.json \
  --as-of 2026-07-15 \
  --output-dir reports/
```

`--symbol`と`--detector-json`は必須です。`--news-json`と`--price-action-json`は任意で、どちらかを省略するとそのパイプライン段階での状態を確認できます。`--as-of`は必須で、「今日」の暗黙的な補完は行いません。鮮度の判定は常に明示的な基準日に対して行われるため、再実行の結果は決定論的になります。

終了コードの扱いは意図的に非対称です。`--as-of`が欠落・不正な形式である場合、あるいはその他のCLI使用エラーはオペレーターの設定ミスとみなし、CLIは使用方法を表示して終了コード`2`で終了し、レポートは書き出しません。一方、3つの信頼できないレポートファイルのいずれかに問題がある場合、つまり読み取り不能・不正な形式・鮮度切れ・不整合のいずれかは、常にフェイルクローズドに処理します。このパイプラインの他のすべてのスキルと同様、CLIは終了コード`0`で終了し、理由を明記したレポートを書き出します。

### Phase 2: setup_statusの読み取り

| ステータス | 意味 | 次のステップ |
|---|---|---|
| `READY_FOR_PLAN` | 3ステップすべてが確認済み。direction、entry_trigger、invalidation_levelが populated されます | `direction`と`invalidation_level`をポジションサイジングのスキルに引き継ぎます |
| `WATCHING_PRICE` | 偏りとニュースは確認済みで、価格アクションが保留中です | technical-analystの逆張り確認モードを実行します |
| `CROWDED` | 偏りは確認済みで、ニュースと価格アクションの一方または両方が保留中です | news-reaction-failure-analyzerを実行します |
| `REJECTED` | 偏りがNOT_CONFIRMED（分類NEUTRAL）、またはニュースか価格アクションがNOT_CONFIRMEDでした | 停止します。この銘柄・方向性についてはこれ以上ステップを進めません |
| `INSUFFICIENT_EVIDENCE` | 必須入力が欠落・読み取り不能・鮮度切れ・不整合のいずれか、または判定自体に至れませんでした | 停止します。名指しされた入力を修正または再生成してから再実行してください |

`missing_confirmations`には、まだブロックしている各ステップの`state`と`reason`が列挙されます。`warnings`はステータスを変更しません。信頼度MEDIUMの確認シグナルや鮮度切れ間近の入力など、監査上注意すべき条件のみを示します。

### Phase 3: READY_FOR_PLANでのみ行動する

`READY_FOR_PLAN`に到達すると、3つの出力フィールドが埋まります。`direction`は群集ポジションに逆張りする方向をSHORTまたはLONGで示し、`entry_trigger`は確認された週足シグナルを事実として要約し、`invalidation_level`は価格アクションレポートのストップ参照値を引き継ぎます。`gate_confidence`にはニュースと価格アクションそれぞれの信頼度のうち弱い方をHIGH・MEDIUM・LOWのいずれかで設定します。LOWは両上流スキルが予約済みトークンとして文書化しているものの実際には出力しない値です。このゲートは値を受理し、最弱のランクとして扱います。ポジションサイジングはパイプラインの次段階にあたりますが、本スキルのリリース時点ではまだ実装されていません。このゲートは発注や発注推奨を一切行いません。

---

## 6. リソース

**リファレンス:**

- `skills/contrarian-setup-gate/references/gate-decision-table.md`

**スクリプト:**

- `skills/contrarian-setup-gate/scripts/gate_logic.py`
- `skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py`
