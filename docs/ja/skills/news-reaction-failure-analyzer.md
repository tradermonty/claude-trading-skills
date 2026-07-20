---
layout: default
title: "News Reaction Failure Analyzer"
grand_parent: 日本語
parent: スキルガイド
nav_order: 39
lang_peer: /en/skills/news-reaction-failure-analyzer/
permalink: /ja/skills/news-reaction-failure-analyzer/
generated: false
---

# News Reaction Failure Analyzer
{: .no_toc }

偏った投機的ポジションに有利なはずのニュースに対して市場が反応しなかったかどうかを判定する、ジェイソン・シャピロのCOT逆張りプロセスにおけるステップ2のスキルです。cot-contrarian-detectorのレポート、または明示的な方向指定を入力とし、Claudeが収集したイベントJSONを組み合わせます。フォールバックチェーンにより価格系列を取得し、ノイズだけで確信判定してしまうナイーブな失敗率方式ではなく、統計的に検証されたドリフト有意性検定を用いてCONFIRMED・NOT_CONFIRMED・INSUFFICIENT_EVIDENCEのいずれかを返すフェイルクローズドな判定を生成します。COT以外にも汎用的に使えるため、PEADやマクロの偏りに対するニュース失敗判定にも再利用できます。ニュース失敗の確認、偏った市場が好材料・悪材料を無視したかどうかの確認、CROWDED_LONGまたはCROWDED_SHORT市場でシャピロのステップ2を実行したい場合に使用してください。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/news-reaction-failure-analyzer.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/news-reaction-failure-analyzer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

ジェイソン・シャピロのCOT逆張りプロセスにおけるステップ2を実装します。市場がステップ1（cot-contrarian-detector）で偏っていると判定された後、その市場が本来クラウドを後押しするはずのニュースに反応しなかったかどうかを確認します。ネットロングに偏った市場が本当に強気な材料でも上昇しない場合、あるいはネットショートに偏った市場が本当に弱気な材料でも下落しない場合、それはクラウドの買い余力・売り余力が尽きたことを示す中心的な行動シグナルです。この確認が「偏っている」状態を逆張りセットアップ候補へと変える段階であり、続くステップ3〜5（価格アクションの確認、エントリー、エグジット）は引き続き手作業で行います。

**ナイーブな失敗率方式を採用しなかった理由:** 以前の設計では、関連イベントの半数未満しか「反応」しなかった場合に「ニュース失敗」と判定していました。しかし純粋なノイズの下でも個々のイベントが反応に至らない確率はおよそ69%あるため、このルールではサンプル数に応じて48〜83%の確率でランダムノイズだけを根拠にCONFIRMEDと判定してしまいます。このスキルでは代わりに、市場がクラウドに有利なニュースに対して統計的に有意に逆方向へ動いたことを要求するドリフト有意性検定を採用しています。この検定はモンテカルロ法で帰無仮説下の偽陽性率を検証済みで、単に「十分に反応しなかった」だけでは判定しません。統計的根拠の詳細は `references/news-failure-patterns.md` を参照してください。

---

## 2. 使用タイミング

**英語での質問例:**
- "Did the market shrug off [event] even though [asset] is crowded long/short?"
- "Run a news-failure check on [symbol]"
- "Is [symbol] confirmed for a Shapiro-style contrarian setup?"
- `cot-contrarian-detector` が市場をCROWDED_LONGまたはCROWDED_SHORTと判定した後、ステップ2に進みたいとき

**日本語での質問例:**
- 「この市場は好材料に反応しなかった？」
- 「COTで偏っているこの銘柄のニュース失敗を確認して」

**使用を避けるべき場面:**
- 市場が偏っていない場合、つまりNEUTRAL判定の場合です。このスキルは明示的な `--direction` の指定がない限りフェイルクローズドで拒否します。
- まだ収集済みのイベントJSONが存在しない場合です。先にWebSearchによるフェーズ2を実行してください。イベントやURLを捏造して判定を得ることは決してありません。

---

## 3. 前提条件

- **FMP APIキー:** 必須です。環境変数 `FMP_API_KEY` を設定するか、`--api-key` で渡してください。用途は価格データの取得のみで、`stable/historical-price-eod/light` を使用します。銘柄ごとにカバレッジが異なる点は `references/price-source-map.md` を参照してください。
- **Python 3.9以上** と `requests` ライブラリ。
- **WebSearchへのアクセス** — フェーズ2でイベントJSONを収集するために使用します。WebSearchが利用できない環境でも動作は継続しますが、その旨を明示し、イベントを捏造することはありません。
- **任意項目:** `cot-contrarian-detector` のJSONレポートを `--detector-json` で渡すと銘柄と方向を自動解決します。または `--direction` を直接指定することもできます。

> レポートの出力内容は英語で生成されます。これはグローバル市場の分析精度を保つための仕様です。プロンプトは日本語でも英語でも指示できます。
{: .tip }

---

## 4. クイックスタート

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json reports/cot_crowding_2026-07-12.json \
  --events-json reports/nrf_events_B6_2026-07-12.json \
  --output-dir reports/
```

---

## 5. ワークフロー

### Phase 1: 銘柄と方向の取得

`cot-contrarian-detector` のレポートを `--detector-json` で渡し、`markets[]` から該当銘柄を検索するか、ユーザーから直接 `--symbol` と `--direction` を受け取ります。NEUTRAL判定の場合、レポートに該当銘柄が存在しない場合、または `--max-detector-age-days`（デフォルト10日）より古いレポートの場合は、いずれも理由付きでフェイルクローズドに拒否します。明示的な `--direction` の指定のみが上書きを許可します。

### Phase 2: WebSearchによるイベントJSONの収集

評価ウィンドウ内でニュースを検索します。ウィンドウの長さは `--window-days` で指定し、デフォルトは10日です。ソースは4段階の階層に従い、発行体・一次情報源からSEC・公的統計、通信社、ポータルサイトの順に優先度を判断します。詳細は `references/news-failure-patterns.md` を参照してください。収集結果は同じく `references/news-failure-patterns.md` のテンプレートに従って記録します。各イベントには `event`、`event_time`、`source_url`、`source_tier`、`expected_impact` を記録してください。`event_time` は明示的なUTCオフセット付きのISO8601形式で、`expected_impact` はBULLISHまたはBEARISHのいずれかです。

**イベントやURLを捏造することは決してありません。** WebSearchが利用できない場合はその旨を明示してください。イベントJSONなしで進める場合は、ユーザーが `INSUFFICIENT_EVIDENCE` という結果を理由 `no_events_provided` とともに受け入れる場合のみです。CLIはイベントファイルが存在しなくても例外を発生させることはなく、常にexit 0で理由を明記して終了します。

### Phase 3: CLIの実行

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json reports/cot_crowding_2026-07-12.json \
  --events-json reports/nrf_events_B6_2026-07-12.json \
  --output-dir reports/
```

スクリプトは価格系列を取得します。取得方法は先物銘柄を優先し、402（アクセス制限）または `rows == 0` の場合はETFプロキシへフォールバックする、文書化されたチェーンに従います。詳細は `references/price-source-map.md` を参照してください。イベントごとに実効日・リターン・zスコアを算出し、3営業日ウィンドウが重なるイベントをクラスタリングして独立性を確保したうえで、判定を合成します。

### Phase 4: 判定結果の提示とハンドオフ

判定結果、集計統計量、証拠テーブルを提示してください。集計統計量には `drift_stat` と `responded_ratio` を含めます。証拠テーブルにはイベントごとのリターン、zスコア、反応ラベルを含めます。`dropped_events` の理由がある場合は必ず表示し、黙って隠すことはありません。`run_context.proxy_used` が示すようにプロキシが使用されている場合は、トラッキングエラーに関する注意点も添えてください。

`contrarian-setup-gate`（Issue #241、未実装）向けのハンドオフブロックを出力します。

```json
{"news_failure": {"verdict": "CONFIRMED", "confidence": "HIGH", "report_path": "reports/nrf_B6_2026-07-12.json"}}
```

---

## 6. リソース

**リファレンス:**

- `skills/news-reaction-failure-analyzer/references/news-failure-patterns.md`
- `skills/news-reaction-failure-analyzer/references/price-source-map.md`

**スクリプト:**

- `skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py`
- `skills/news-reaction-failure-analyzer/scripts/reaction_math.py`
