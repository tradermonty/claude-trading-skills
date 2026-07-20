---
layout: default
title: "COT Contrarian Detector"
grand_parent: 日本語
parent: スキルガイド
nav_order: 13
lang_peer: /en/skills/cot-contrarian-detector/
permalink: /ja/skills/cot-contrarian-detector/
generated: false
---

# COT Contrarian Detector
{: .no_toc }

CFTC先物市場のCOTレポートから投機筋の偏ったポジションを検出し、ジェイソン・シャピロの手法に基づく逆張りセットアップを見つけるスキルです。指数・金利・為替・貴金属・エネルギー・暗号資産を含む65市場を対象に、FMPのCommitment of Traders APIを通じて大口投機筋（非商業部門）の建玉を取得します。市場ごとに3年間と26週間のCOT Indexを算出し、極端な水準をCROWDED_LONGまたはCROWDED_SHORTとして分類します。COTレポート分析、偏ったポジション、「誰が踏み上げられているか」、投機的ポジションの極端な水準、先物の逆張りセットアップ、ジェイソン・シャピロ式の分析についてユーザーから質問された際に使用してください。このスキルが自動化するのは5ステップのうち最初の混雑検出のみで、それ単体で売買シグナルを生成するものではありません。
{: .fs-6 .fw-300 }

<span class="badge badge-api">FMP必須</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/cot-contrarian-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/cot-contrarian-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

ジェイソン・シャピロのCOT（Commitment of Traders）逆張りプロセスにおける最初のステップを実装します。大口投機筋が先物市場の片側に偏って集中しているタイミングを検出するものです。偏ったポジションは逆張りトレードの前提条件であり、それ自体は売買シグナルではありません。市場が実際にトレード可能になるのは、ニュースフェイリュアと価格アクションの反転によって偏りが裏付けられてからです。ステップ2〜3にあたるこの確認作業は、このスキルがユーザーとともに手作業で進める領域です。

**シャピロのコアテーゼ:** ヘッジファンドやCTA、モメンタムトレーダーといった大口投機筋は、トレンドの始まりではなくトレンドの終焉で最大のポジションを持つ傾向があります。すでに片側に偏りきっている場合、次の大きな値動きは投機筋にさらなる利益をもたらすよりも、彼らを踏み上げる方向に働く可能性が統計的に高くなります。フェードすべきは投機筋であって、コマーシャル（実需筋）ではありません。実需筋は事業上の構造的な理由でヘッジを行っており、群集心理のシグナルにはなりません。

---

## 2. 使用タイミング

**英語での質問例:**
- "What markets are the speculators crowded into right now?"
- "Run a COT report analysis" / "Show me COT positioning extremes"
- "Is anyone 'trapped' in gold / the dollar / bonds right now?"
- 逆張りの先物セットアップを探したいとき
- ジェイソン・シャピロ式のCOTスクリーニングを求められたとき

**日本語での質問例:**
- 「COTレポートで買われすぎ・売られすぎのポジションを調べて」
- 「投機筋が偏っている市場は？」
- 「ジェイソン・シャピロ式の逆張り分析をして」

**使用を避けるべき場面:**
- ユーザーがすぐに売買シグナルを求めている場合。偏ったポジションだけでは行動には移せません。詳細は後述のガードレールに関する記述を参照してください。
- 個別株について聞かれた場合。COTレポートが対象とするのはCFTC先物市場、つまり指数・金利・為替・貴金属・エネルギー・農産物・暗号資産であり、個別株は含まれません。

---

## 3. 前提条件

- **FMP APIキー:** 必須です。環境変数 `FMP_API_KEY` を設定するか、`--api-key` で渡してください。**COTエンドポイントの利用にはFMP Premium+プランが必要**で、無料枠のキーではアクセスできません。
- **Python 3.9以上** と `requests` ライブラリ。
- **API使用量:** 市場ごとに1コールです。`--core` オプションでは23コール、全市場対象では最大65コール程度になります。`--symbols` と `--core` のどちらも指定しない場合は、市場一覧取得のために追加で1コール発生します。

> レポートの出力内容は英語で生成されます。これはグローバル市場の分析精度を保つための仕様です。プロンプトは日本語でも英語でも指示できます。
{: .tip }

---

## 4. クイックスタート

```bash
# 主要な先物市場23銘柄に絞ったコアユニバース
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --core --output-dir reports/

# 銘柄を明示的に指定
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --symbols "ES,GC,CL" --output-dir reports/

# FMPのCOT一覧がカバーする全市場（約65銘柄）
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --output-dir reports/
```

---

## 5. ワークフロー

### Phase 1: 混雑検出スクリーンの実行

```bash
# 主要な先物市場23銘柄に絞ったコアユニバース
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --core --output-dir reports/

# 銘柄を明示的に指定
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --symbols "ES,GC,CL" --output-dir reports/

# FMPのCOT一覧がカバーする全市場（約65銘柄）
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py --output-dir reports/
```

このスクリプトは市場ごとに週次のレガシーCOTレポートを取得します。大口投機筋のロング・ショートポジションから156週間（3年）と26週間のCOT Indexを算出し、極端な水準を次のように分類します。

- `CROWDED_LONG` — COT Indexが90以上。3年間の中でネットロングが最も積み上がった水準に近い状態です。
- `CROWDED_SHORT` — COT Indexが10以下。3年間の中でネットショートが最も積み上がった水準に近い状態です。
- `NEUTRAL` — 上記以外のすべての水準です。

インデックスの算出に十分な履歴がない市場も、黙って除外されることはありません。理由付きで `skipped` リストに含まれます。表示例は「insufficient history: 40/156 weeks」のようになります。

### Phase 2: 混雑レポートの提示

生成されたMarkdownレポートを提示する際は、次の点を強調してください。

- どの市場が `CROWDED_LONG` または `CROWDED_SHORT` で、どの程度偏っているか
- 26週間のインデックスの文脈。偏りが直近で生まれたものか、すでに古くなりつつあるものか
- 週次ベースのネットポジション変動。急速に動いている偏りほど脆いと考えられます
- 手法に関する注記と免責事項。偏ったポジションはそれ単体では売買シグナルではありません

### Phase 3: ステップ2〜5の手作業ガイド（シャピロプロセス）

ユーザーが `CROWDED_LONG` または `CROWDED_SHORT` の市場を掘り下げたい場合は、`references/shapiro-methodology.md` を読み込み、残りのステップを一緒に進めます。以下は自動化されていません。

1. ~~偏ったポジションの検出~~ — 完了。このスキルが担当します。
2. **ニュースフェイリュア** — WebSearchを使い、偏りの方向に有利なはずのニュースが出たにもかかわらず価格が期待通りに動かなかったかどうかを確認します。例えば、ネットロングに偏った市場が強気材料でも上昇しない場合です。これがシャピロ手法の核心であり、最も重要な手作業での確認事項です。
3. **価格アクションの確認** — 週足チャートで反転パターンや、新高値・新安値での失敗を確認します。
4. **エントリー** — 偏りに逆らう方向で、直近のスイング極値に損切りを置き、小さく固定したリスクでサイズを決めます。サイジングには `position-sizer` スキルを使ってください。
5. **エグジット** — ポジションが正常化してニュートラル方向、つまりCOT Indexが50に戻る方向に動いたとき、または損切りに達したときに手仕舞います。

偏ったポジションだけを根拠にエントリーを勧めることはありません。ステップ2とステップ3の両方が裏付けられて初めてエントリー検討に進みます。

---

## 6. リソース

**リファレンス:**

- `skills/cot-contrarian-detector/references/cot-index-calculation.md`
- `skills/cot-contrarian-detector/references/shapiro-methodology.md`

**スクリプト:**

- `skills/cot-contrarian-detector/scripts/cot_index.py`
- `skills/cot-contrarian-detector/scripts/screen_cot_crowding.py`
