---
layout: default
title: 用語集
parent: 日本語
nav_order: 7
lang_peer: /en/glossary/
permalink: /ja/glossary/
---

# 用語集
{: .no_toc }

Claude Trading Skills 全体で使うトレード用語を、初めての方向けに説明します。ここでの定義は語彙を理解するためのものであり、売買の推奨や将来成果の保証ではありません。
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 用語一覧

### ATR（Average True Range）
{: #atr }

ATR は、窓を開けた値動きも含め、指定した期間に価格が通常どの程度動くかを推定する指標です。方向ではなく値動きの大きさを測り、現在のボラティリティに応じてストップ幅やポジションリスクを調整するときに使います。

**関連スキル:** [Position Sizer]({{ '/ja/skills/position-sizer/' | relative_url }})

### ブレッドス（Breadth）
{: #breadth }

ブレッドスは、市場の値動きに構成銘柄がどの程度広く参加しているかを表します。多数の銘柄が上昇して支える指数高は、少数の大型株だけで上がる場合よりも裾野が広いと判断できます。

**関連スキル:** [Market Breadth Analyzer]({{ '/ja/skills/market-breadth-analyzer/' | relative_url }})

### ブレイクアウト（Breakout）
{: #breakout }

ブレイクアウトは、価格がレジスタンスや取引レンジ上限など、以前から重要だった境界を超えることです。境界を超えただけでは継続を保証しないため、通常は出来高、市場環境、失敗と判断する水準も併せて確認します。

**関連スキル:** [Breakout Trade Planner]({{ '/ja/skills/breakout-trade-planner/' | relative_url }})

### CANSLIM
{: #canslim }

CANSLIM は、Current quarterly earnings、Annual earnings growth、New、Supply and demand、Leader or laggard、Institutional sponsorship、Market direction の観点を組み合わせる成長株投資の枠組みです。企業業績だけでなく、価格・出来高・市場環境も評価します。

**関連スキル:** [CANSLIM Screener]({{ '/ja/skills/canslim-screener/' | relative_url }})

### カタリスト（Catalyst）
{: #catalyst }

カタリストは、決算、業績見通し、新製品、規制、経営陣の交代など、銘柄への期待を変え得る出来事や新情報です。値動きのきっかけにはなりますが、市場の反応が好意的か、長続きするかまでは決めません。

**関連スキル:** [Stockbee Episodic Pivot Analyzer]({{ '/ja/skills/stockbee-episodic-pivot-analyzer/' | relative_url }})

### コア・サテライト（Core + Satellite）
{: #core-satellite }

コア・サテライトは、長期・分散保有を担うコアと、より能動的または集中した機会に使う小さなサテライト枠を分けるポートフォリオ構成です。短期トレードが長期資産全体のリスク特性を知らないうちに変えることを防ぎやすくします。

**関連スキル:** [Kanchi Dividend SOP]({{ '/ja/skills/kanchi-dividend-sop/' | relative_url }})

### 相関（Correlation）
{: #correlation }

相関は、2つのリターン系列が過去にどの程度一緒に動いたかを、一般に -1 から +1 の範囲で要約します。相場環境によって変化し得る過去の関係であり、一方が他方を動かす因果関係を証明するものではありません。

**関連スキル:** [Pair Trade Screener]({{ '/ja/skills/pair-trade-screener/' | relative_url }})

### COT（Commitments of Traders）
{: #cot }

COT は、米国商品先物取引委員会（CFTC）が毎週公表する、商業ヘッジャーや運用業者などの区分別先物ポジション報告です。ポジションの偏りや混雑度を調べるために使い、通常は単独の売買タイミングではなく価格確認と組み合わせます。

**関連スキル:** [COT Contrarian Detector]({{ '/ja/skills/cot-contrarian-detector/' | relative_url }})

### ディストリビューション・デー（Distribution Day）
{: #distribution-day }

ディストリビューション・デーは一般に、主要指数が前日より多い出来高を伴って明確に下落した日を指します。直近で複数回重なると機関投資家の売り圧力を示す可能性がありますが、1日だけで市場全体を判断するものではありません。

**関連スキル:** [IBD Distribution Day Monitor]({{ '/ja/skills/ibd-distribution-day-monitor/' | relative_url }})

### ドローダウン（Drawdown）
{: #drawdown }

ドローダウンは、ポートフォリオや戦略がそれまでのピークからその後の安値まで下落した幅で、通常はパーセントで表します。損失局面の深さに加え、継続期間やピーク回復に必要な上昇率も併せて見る必要があります。

**関連スキル:** [Drawdown Circuit Breaker]({{ '/ja/skills/drawdown-circuit-breaker/' | relative_url }})

### エッジ（Edge）
{: #edge }

エッジは、同種の判断を多数繰り返したときに有利な結果が期待できる、情報・行動・分析・執行上の再現可能な優位性です。個々のトレードを確実に勝たせるものではなく、市場環境の変化で弱まる可能性がある検証対象の仮説です。

**関連スキル:** [Edge Concept Synthesizer]({{ '/ja/skills/edge-concept-synthesizer/' | relative_url }})

### エントリー（Entry）
{: #entry }

エントリーは、トレードを開始してよいと事前に定めた条件または価格帯です。実用的なルールでは、必要な証拠、許容するリスク、セットアップが無効になる条件も併せて定義します。

**関連スキル:** [Breakout Trade Planner]({{ '/ja/skills/breakout-trade-planner/' | relative_url }})

### エピソディック・ピボット（Episodic Pivot）
{: #episodic-pivot }

エピソディック・ピボットは、大幅な決算サプライズや業績見通し変更など、企業固有の重要イベントに伴う急激な価格・出来高変化です。期待の見直しから新しいトレンドが始まる可能性はありますが、流動性、フォロースルー、リスク上限は別途評価します。

**関連スキル:** [Stockbee Episodic Pivot Analyzer]({{ '/ja/skills/stockbee-episodic-pivot-analyzer/' | relative_url }})

### 期待値（Expectancy）
{: #expectancy }

期待値は、十分な件数のトレードを通じて、1回当たり平均でどの程度の利益または損失が見込まれるかを表します。代表的な計算は勝率と平均利益の積から敗率と平均損失の積を引きますが、次の1回の結果を予測するものではありません。

**関連スキル:** [Weekly Performance Digest]({{ '/ja/skills/weekly-performance-digest/' | relative_url }})

### エクスポージャー（Exposure）
{: #exposure }

エクスポージャーは、市場の値動きにさらされるポートフォリオ資本の量で、通常は純資産に対する割合としてロング、ショート、グロス、ネットに分けて表します。ポジション時価だけではレバレッジを隠すことがあるため、分母と符号の定義が重要です。

**関連スキル:** [Exposure Coach]({{ '/ja/skills/exposure-coach/' | relative_url }})

### フォロースルー・デー（Follow-Through Day / FTD）
{: #ftd }

フォロースルー・デーは、相場の安値候補の後に主要指数が出来高増を伴って大きく上昇した日で、一部の成長株投資法では上昇に機関投資家の支えが加わり始めた証拠として使います。確認条件の一つであり、上昇継続の保証ではありません。

**関連スキル:** [FTD Detector]({{ '/ja/skills/ftd-detector/' | relative_url }})

### ギャップ（Gap）
{: #gap }

ギャップは、前の取引セッションの価格帯と次のセッション開始時の価格帯との間に、ほとんど売買されていない空白が生じることです。新情報を反映する場合が多い一方、実務上の意味は大きさ、出来高、発生位置、その後の値動きで変わります。

**関連スキル:** [Earnings Trade Analyzer]({{ '/ja/skills/earnings-trade-analyzer/' | relative_url }})

### ヘッジ比率（Hedge Ratio）
{: #hedge-ratio }

ヘッジ比率は、市場リスクやスプレッドリスクなど、特定のリスクを減らすために一方の銘柄へもう一方をどれだけ組み合わせるかを示します。ペアトレードでは過去価格から推定することが多いものの、推定誤差や関係変化による残存リスクがあります。

**関連スキル:** [Pair Trade Screener]({{ '/ja/skills/pair-trade-screener/' | relative_url }})

### 流動性（Liquidity）
{: #liquidity }

流動性は、希望する数量を価格へ大きな影響を与えずに売買できる程度を表します。出来高、売買スプレッド、板の厚さが手掛かりになりますが、急変時や通常時間外には低下することがあります。

**関連スキル:** [Pair Trade Screener]({{ '/ja/skills/pair-trade-screener/' | relative_url }})

### 最大逆行幅（Maximum Adverse Excursion / MAE）
{: #mae }

MAE は、ポジション保有中にエントリーから最も不利な方向へ動いた未実現幅です。同種トレードの MAE を振り返ると、ストップが狭すぎるか、損失を拡大させているかを検討できますが、少数事例だけに最適化すべきではありません。

**関連スキル:** [Trader Memory Core]({{ '/ja/skills/trader-memory-core/' | relative_url }})

### 最大順行幅（Maximum Favorable Excursion / MFE）
{: #mfe }

MFE は、ポジション保有中にエントリーから最も有利な方向へ動いた未実現幅です。実現結果と比べることで出口執行を振り返れますが、保有中の最良価格で実際に約定できたと仮定してはいけません。

**関連スキル:** [Trader Memory Core]({{ '/ja/skills/trader-memory-core/' | relative_url }})

### 市場レジーム（Market Regime）
{: #market-regime }

市場レジームは、トレンド、ボラティリティ、ブレッドス、流動性、マクロ環境などで特徴付けられる広い相場環境です。安定した上昇局面と高ボラティリティの下落局面では、同じプロセスでもエクスポージャーやセットアップ規則を変えることがあります。

**関連スキル:** [Macro Regime Detector]({{ '/ja/skills/macro-regime-detector/' | relative_url }})

### モメンタム（Momentum）
{: #momentum }

モメンタムは、相対的に強いまたは弱い価格変化が一定期間続く傾向です。測定期間によって結果が変わるため、短期モメンタムが強い銘柄でも長期では弱い場合があります。

**関連スキル:** [Stockbee Momentum Burst Screener]({{ '/ja/skills/stockbee-momentum-burst-screener/' | relative_url }})

### 決算発表後ドリフト（Post-Earnings Announcement Drift / PEAD）
{: #pead }

PEAD は、決算サプライズ後に価格が最初の反応と同じ方向へ動き続ける傾向として研究されている現象です。すべての決算反応が継続するわけではないため、適格条件、エントリー、流動性、無効化ルールを明確にする必要があります。

**関連スキル:** [PEAD Screener]({{ '/ja/skills/pead-screener/' | relative_url }})

### ポジションサイジング（Position Sizing）
{: #position-sizing }

ポジションサイジングは、トレードに割り当てる株数、契約数、金額を決めることです。リスク基準の方法では、確信度だけで数量を決めず、ポートフォリオが許容できる損失額と無効化またはストップまでの距離から計算します。

**関連スキル:** [Position Sizer]({{ '/ja/skills/position-sizer/' | relative_url }})

### プルバック（Pullback）
{: #pullback }

プルバックは、上昇トレンド中の下落など、優勢なトレンドと一時的に反対方向へ動くことです。計画的なエントリー機会になり得ますが、反転の始まりである可能性もあるため、トレンドの質と無効化水準が重要です。

**関連スキル:** [Dividend Growth Pullback Screener]({{ '/ja/skills/dividend-growth-pullback-screener/' | relative_url }})

### R倍数（R-Multiple）
{: #r-multiple }

R倍数は、トレード結果を当初計画したリスクに対する比率で表し、+2R は初期リスクの2倍の利益、-1R は計画したリスク分の損失を意味します。初期リスクを一貫して記録すれば、異なるサイズのトレードを比較しやすくなります。

**関連スキル:** [Weekly Performance Digest]({{ '/ja/skills/weekly-performance-digest/' | relative_url }})

### 相対強度（Relative Strength）
{: #relative-strength }

相対強度は、選んだ期間における銘柄の成績をベンチマークや同業群と比較します。Relative Strength Index（RSI）とは別物で、相対強度は比較、RSI は一定範囲内のモメンタム・オシレーターです。

**関連スキル:** [CANSLIM Screener]({{ '/ja/skills/canslim-screener/' | relative_url }})

### リスクオン／リスクオフ（Risk-On / Risk-Off）
{: #risk-on-risk-off }

リスクオンは投資家が成長や市場リスクへの感応度が高い資産を広く選好する状態、リスクオフは資本保全や防御的資産へ傾く状態を表します。市場横断の動きを要約する呼び方であり、二者択一の予測ではありません。

**関連スキル:** [Market Environment Analysis]({{ '/ja/skills/market-environment-analysis/' | relative_url }})

### RSI（Relative Strength Index）
{: #rsi }

RSI は、直近の上昇幅と下落幅のバランスから計算し、通常は 0 から 100 で表すモメンタム・オシレーターです。70 や 30 といった水準は最近の計算上の極端さを示すもので、自動的な売買指示ではありません。

**関連スキル:** [Dividend Growth Pullback Screener]({{ '/ja/skills/dividend-growth-pullback-screener/' | relative_url }})

### ストップロス（Stop-Loss）
{: #stop-loss }

ストップロスは、トレードが計画に合わなくなったときに退出するため、事前に定める価格または条件です。意図したリスクを制限しますが、ギャップ、急変相場、流動性不足では想定価格での退出を保証できません。

**関連スキル:** [Breakout Trade Planner]({{ '/ja/skills/breakout-trade-planner/' | relative_url }})

### サポートとレジスタンス（Support and Resistance）
{: #support-resistance }

サポートは過去に買いが売りを吸収した価格帯、レジスタンスは売りが買いを吸収した価格帯です。市場行動から推定するゾーンであり、永久に価格を止める壁ではありません。

**関連スキル:** [Technical Analyst]({{ '/ja/skills/technical-analyst/' | relative_url }})

### 仮説と無効化（Thesis and Invalidation）
{: #thesis-invalidation }

トレード仮説は機会が機能すると考える理由と観察可能な根拠を示し、無効化条件はその理由を受け入れられなくなる証拠を示します。両方をエントリー前に書くことで、後知恵や説明のすり替えを減らせます。

**関連スキル:** [Trader Memory Core]({{ '/ja/skills/trader-memory-core/' | relative_url }})

### ボラティリティ（Volatility）
{: #volatility }

ボラティリティは、価格変化の大きさとばらつきを表し、方向は示しません。ボラティリティが高いほど結果の振れ幅が広がるため、ポートフォリオリスクを同程度に保つには数量を減らすか、リスク幅を広げる必要がある場合があります。

**関連スキル:** [Position Sizer]({{ '/ja/skills/position-sizer/' | relative_url }})

### VCP（Volatility Contraction Pattern）
{: #vcp }

VCP は、潜在的なピボット付近で供給が減るように見え、連続するプルバックが徐々に小さくなる価格構造です。Mark Minervini と関連するセットアップの枠組みであり、ブレイクアウト成功の証明ではありません。

**関連スキル:** [VCP Screener]({{ '/ja/skills/vcp-screener/' | relative_url }})

### Zスコア（Z-Score）
{: #z-score }

Zスコアは、現在値が過去平均から標準偏差何個分離れているかを表します。スプレッド分析では異常な乖離の大きさを示しますが、十分に安定した分布と適切な参照期間が前提です。

**関連スキル:** [Pair Trade Screener]({{ '/ja/skills/pair-trade-screener/' | relative_url }})
