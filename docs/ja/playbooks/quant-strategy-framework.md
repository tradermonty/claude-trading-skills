---
layout: default
title: Quant Strategy Framework
grand_parent: 日本語
parent: プレイブック
nav_order: 10
lang_peer: /en/playbooks/quant-strategy-framework/
permalink: /ja/playbooks/quant-strategy-framework/
---

# クロスアセット Quant 戦略フレームワーク — Pre / During / Post
{: .no_toc }

株式、為替（リサーチ専用）、コモディティ、オプション、テーマ投資という各アセットクラスを横断して、このプロジェクトのスキルと API クライアントを1つのプロセスに結びつけるプレイブックです。
{: .fs-6 .fw-300 }

**このフレームワークはリサーチと意思決定支援に徹しており、発注は行いません。** 発注はすべて手動です。生成されるすべての成果物には `manual_review_required: true` と `data_gaps[]` 配列が付きます。実際に注文を出すのは常に人間です。

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 背骨 — すべてのアセットクラスに共通

3つのループが常時回っています。

| ループ | 頻度 | 出力 |
|---|---|---|
| マクロレジーム | 週次 | リスクオン／リスクオフ／移行中のポスチャー |
| アイデア生成 | 日次 | 仮説カード付きの候補ランキング |
| ポジションのライフサイクル | トレードごと | Pre → During → Post |

### 7層シグナルスタック

トレードが資金を投じるに値するのは**レイヤー1〜5が揃ったとき**だけです。

```
1. マクロレジーム         → BISClient, BLSClient, BEAClient, EIAClient
2. テーマ・セクター       → theme-detector, sector-analyst
3. アセットクラス別スクリーナー → VCP / CANSLIM / PEAD / Dividend / Parabolic
4. セットアップ確認        → technical-analyst（チャート）, breakout-trade-planner
5. 織り込み状況の確認      → PolymarketClient, NewsClient, FMP コンセンサス
                          （references/what-is-priced-in-framework.md 参照）
6. サイジング             → position-sizer（Rマルチプル）, exposure-coach
7. 事後検証               → signal-postmortem, trader-memory-core
```

### キルルール

すべてのトレードは、エントリー前に**書面の thesis**、「何が起きたら間違いと判断するか」を定めた**キル基準**、そしてエグジット後の**ジャーナル記入**を必須とします。例外はありません。これがそのままマニュアルレビューのゲートです。

---

## 1. 株式 — 業種・個別銘柄・セクター

**対象:** 米国上場株 + セクター／テーマ ETF。保有期間は3〜30日のスイング、または1〜6ヶ月のポジションです。

### PRE

| ステップ | ツール | 出力 |
|---|---|---|
| 1. アイデアソース | `vcp-screener`（強気スイング）, `canslim-screener`（成長株）, `pead-screener`（決算ドリフト）, `parabolic-short-trade-planner`（平均回帰ショート）, `dividend-growth-pullback-screener`（クオリティ押し目） | 候補ランキング |
| 2. テーマ文脈 | `theme-detector` | 加速中の上位3テーマに絞り込み |
| 3. チャート確認 | `technical-analyst`（チャート画像） | 視覚的パターンの可否判定 |
| 4. トリガー水準 | `breakout-trade-planner` | 5分足 ORL、ブレイクアウトの延長、無効化水準 |
| 5. 決算反応の履歴 | `earnings-trade-analyzer` | 「噂で買われ材料出尽くしで売られる」パターンに逆らわない |
| 6. 織り込み状況 | `PolymarketClient`, `NewsClient`, FMP コンセンサス vs 自分の見立て | ギャップ = （自分の見立て − コンセンサス）× 反応関数 |
| 7. 仮説カード | `trade-hypothesis-ideator` → `trader-memory-core` IDEA → ENTRY_READY | Thesis + キル基準 + Rターゲット + タイムストップ |
| 8. サイジング | `position-sizer`（ストップロス基準または Kelly） | 株数 + ドルリスク |
| 9. ポートフォリオ確認 | `exposure-coach` | セクター上限、市場の幅のポスチャー、エクスポージャー上限% |

### DURING

- **毎朝:** `market-regime-daily` ワークフロー（市場の幅 + アップトレンド + エクスポージャー）を実行。総合スコアが1段階下がったら、ストップを詰めて新規エントリーは見送る。
- **ニュース監視:** `NewsClient.get_market_news(tickers=[...], days=1)` — thesis を壊すヘッドラインが無いか確認。
- **PEAD 銘柄:** SIGNAL_READY → BREAKOUT の遷移を監視。
- **保有中の決算跨ぎ:** 決算が thesis そのものでない限り、発表前にポジションを1/3に減らすかクローズする。

### POST

- `trader-memory-core` → CLOSED として実現 R と MAE/MFE を記録。
- `signal-postmortem`: 何がうまくいき何がうまくいかなかったか、キル基準は守られたか、サイジングは適切だったか。
- 教訓を `monthly-performance-review` に反映する。

---

## 2. 為替 — リサーチ専用

**対象:** USD/JPY、EUR/USD、GBP/USD、AUD/USD、USD/CAD の方向性バイアス。**出力はリサーチ成果物であり、注文ではありません。** 執行は別プロジェクトで扱い、本プロジェクトがそちらから import することは決してありません。

### PRE（リサーチ）

| ステップ | ツール | シグナル |
|---|---|---|
| 1. 金利差 | `BISClient.rate_differential("US", "JP")` | キャリーの追い風／向かい風（pp） |
| 2. 米国マクロ | `BLSClient.get_named("unemployment_rate")`, `BLSClient.get_named("cpi_core")`, `BEAClient.real_gdp_growth()` | Fed のタカ派／ハト派バイアス |
| 3. 相手国マクロ | JPY は `EStatClient.cpi_national()`、AUD/CAD はコモディティ | 国別サプライズの可能性 |
| 4. コモディティベータ | `EIAClient.natural_gas_spot()`, `CommodityClient.latest(["WTI", "GOLD"])` | AUD = 鉄鉱石 + 銅、CAD = WTI、金 = USD 逆相関 |
| 5. カタリストの織り込み | `PolymarketClient.search_markets("Fed cut")` | 政策変更の予測確率 |
| 6. リサーチ成果物 | `manual_review_required: true` + `data_gaps[]` を付した Markdown レポート | 方向性バイアススコア（−5 … +5）。発注チケットではない |

### DURING（監視というよりリサーチの継続）

- BLS の雇用統計、CPI 発表を確認（Finnhub の経済カレンダー）
- BIS の金利改定を月次で確認
- `NewsClient` でニュースを追う

### POST（リサーチの検証）

- 金利差の thesis は実際に機能したか
- どの BIS 国・BLS 系列が方向性予測の的中率が高いか、キャリブレーションする
- `trader-memory-core` に `research_only: true` で記録

### 明確にスコープ外

発注、ストップ、ブローカー連携コードは別の為替プロジェクトで扱います。リリースゲートがこれを強制します。

---

## 3. コモディティ

**対象:** エネルギー（WTI、ブレント、天然ガス）、貴金属（金、銀）、産業用金属（銅）。**株式プロキシの ETF・個別株**（XLE、USO、GLD、GDX、FCX）経由で取引し、先物そのものはスコープ外です。

### PRE

| ステップ | ツール | シグナル |
|---|---|---|
| 1. ファンダメンタルの牽引要因 | `EIAClient.electricity_demand("PJM")`（AI 電力需要）, `EIAClient.natural_gas_spot()`（ガス）, `EIAClient.power_demand_yoy()` | 前年比の転換点はあるか |
| 2. スポット価格 | `CommodityClient.latest(["BRENT", "GOLD", "COPPER"])` | 直近30日レンジに対する現在位置 |
| 3. 系列トレンド | `CommodityClient.time_series("BRENT", start, end)` | 直近30日の方向性 |
| 4. テーマ文脈 | `theme-detector` — Oil & Gas、Gold & Precious Metals、Power Infrastructure | テーマの熱量 ≥ 60、ライフサイクル = Accelerating を確認 |
| 5. スパークスプレッド（IPP向け） | EIA データを使った `(電力価格) − (ガス価格 × ヒートレート)` | 拡大は VST/NRG/TLN に強気、縮小は弱気 |
| 6. 株式での表現方法 | プロキシを選定 — エネルギーロングなら XLE/XOP/OIH または VST/CEG/EQT、金なら GDX/GLD/NEM、銅なら FCX | Thesis ごとに1銘柄 |
| 7. 織り込み状況 | Polymarket の OPEC・Fed 利下げ関連市場、コモディティ ETF のインプライドボラティリティ | サプライズの可能性 |

### DURING

- スパークスプレッドを週次でウォッチ — 拡大は IPP 銘柄の thesis を裏付ける
- 地政学（中東、ロシア、OPEC）のニュースを `NewsClient` で追う
- EIA の在庫統計（週次）を確認

### POST

- EIA の統計は需要 thesis を裏付けたか
- 自分の電力需要モデルを実績と突き合わせてキャリブレーションする
- `trader-memory-core` に記録

---

## 4. オプション

**対象:** 流動性の高い米国銘柄でのディファインドリスク戦略。**ネイキッドオプション（無制限リスク）は扱いません。**

### PRE

**1. 原資産はすでに§1の高確信度な株式セットアップである必要があります。** オプションは thesis の発生源ではなく、その**表現方法**です。

**2. 戦略選定の決定木:**

| 方向性 | IV レジーム | 戦略 |
|---|---|---|
| 強気 | High IV | **Bull put spread**（プレミアム売り、ディファインドリスク） |
| 強気 | Low IV | **Bull call spread** または **long call**（安いディレクショナル買い） |
| 強気 + 現物保有 | 問わず | **Covered call**（インカム上乗せ） |
| レンジ相場 | High IV | **Iron condor** |
| 弱気 | High IV | **Bear call spread** |
| 弱気 | Low IV | **Bear put spread** または **long put** |

**3. 検証:** `options-strategy-advisor` で Black-Scholes 価格付け + Greeks + シナリオ分析を行う。**利益確率 60% 以上**を下限とする。

**4. サイジング:** トレードあたりの最大損失 = `position-sizer` の R 相当額。ネットデビット、またはクレジットスプレッドの最大損失を R 以下に収める。

**5. 織り込み状況:** IV パーセンタイルを過去1年レンジと比較（プレミアムが割高か割安か）。決算前は、ストラドル価格が市場の期待変動幅を示すので、自分の見立てと比較する。

### DURING

- **デルタ**（方向性リスク）と**シータ**（時間価値の減衰による利益）を監視
- **最大利益の50%でウィナーをクローズ**する（最後の25%まで欲張らない）
- **テストされたショートストライク**への対応: ロールアウト + 上下にロール
- **保有中の決算跨ぎ:** クローズするかロールする。バイナリイベントを跨いでショートボラを持ち続けない。

### POST

- 理論上の最大利益に対する実現損益
- **Greeks 別のアトリビューション**: 損益のうちデルタ由来・シータ由来・ベガ由来はそれぞれどれだけか
- IV レジームの文脈を添えて `signal-postmortem`

---

## 5. テーマ・セクターローテーション

**対象:** ETF または上位構成銘柄バスケットによる複数週にまたがるテーマ投資。

### PRE

| ステップ | ツール | 出力 |
|---|---|---|
| 1. テーマスキャン | `theme-detector --dynamic-stocks` | 熱量とライフサイクルでランク付けされたテーマ |
| 2. ライフサイクルフィルタ | **Exhausting** は避け、**Emerging / Accelerating** を優先 | 末期は混雑トレードのリスクが高い |
| 3. 構成銘柄選定 | テーマごとに相対力の上位3〜5銘柄 | 等ウェイトのバスケット |
| 4. ETF での表現 | `skills/theme-detector/references/cross_sector_themes.md` のプロキシ ETF | 1行で表現できる形にする |
| 5. 業種確認 | FINVIZ で業種ランクが上位クオータイル | theme-detector の出力とのクロスチェック |
| 6. 出来高確認 | `PolygonClient.get_grouped_daily()` | 実際の機関投資家の資金フローか確認 |

### DURING

- 日次の市場の幅チェック（`market-breadth-analyzer`）— 市場の幅が縮小し始めると真っ先に崩れるのがテーマ株
- テーマライフサイクルのドリフト監視: **Exhausting に入ってから** ではなく、**入る前に**手仕舞う

### POST

- 保有期間中、プロキシ ETF は SPY を5%以上アウトパフォームしたか
- 実現した成否をテーマモデルに反映して更新する

---

## 頻度 — 各ルーティンをいつ回すか

| タイミング | ルーティン | スキル／ワークフロー |
|---|---|---|
| **米国市場オープン15分前** | 日次レジームチェック | `market-regime-daily` ワークフロー |
| **日次、引け後** | ニューススキャン、ポジション監視 | `NewsClient.get_market_news(tickers=open_positions)` |
| **日次（レジーム確認後）** | マルチアセットの機会スキャン | `multi-asset-opportunity-daily` ワークフロー（本プレイブックをフロー化したもの） |
| **週次（日曜）** | 新規候補とマクロの更新 | `swing-opportunity-daily`、`theme-detector`、BIS/BLS/BEA の更新 |
| **月次** | パフォーマンスとキャリブレーション | `monthly-performance-review`、`signal-postmortem` の集計 |
| **トレードごと — Pre** | 仮説カードとサイジング | `trade-hypothesis-ideator`、`position-sizer`、`exposure-coach`、`trader-memory-core` IDEA → ENTRY_READY |
| **トレードごと — During** | 日次のキルチェック、ニュース監視 | `trader-memory-core` の review-due、`NewsClient` |
| **トレードごと — Post** | クローズ、MAE/MFE、教訓 | `trader-memory-core` CLOSED、`signal-postmortem` |

---

## ツールチェーンマップ — 各ステップに対応するツールは1つだけ

| 必要なもの | ツール |
|---|---|
| OHLCV（yfinance の代替） | `PolygonClient.get_aggs()` |
| 米国マクロ（GDP、貯蓄率） | `BEAClient` |
| 米国雇用・インフレ | `BLSClient` |
| 国際金利差 | `BISClient.rate_differential()` |
| エネルギー・電力 | `EIAClient` |
| コモディティスポット | `CommodityClient.latest()` |
| 日本マクロ | `EStatClient` |
| ニュース・センチメント | `NewsClient`（Marketaux + Newsdata） |
| カタリストの確率 | `PolymarketClient` |
| カレンダー（経済指標・決算） | `FinnhubClient`（無料）または FMP |
| テーマ検出 | `theme-detector` スキル |
| 銘柄スクリーニング | VCP / CANSLIM / PEAD / Dividend / Parabolic 各スキル |
| 仮説カード | `trade-hypothesis-ideator` |
| サイジング | `position-sizer` |
| ポスチャー・エクスポージャー | `exposure-coach` |
| メモリ・ジャーナル | `trader-memory-core` |
| 事後検証 | `signal-postmortem` |
| バックテスト | `backtest-expert` |

---

## スコープ外（マニュアルレビューのゲート）

- 自動売買・ブローカー執行・発注
- OANDA・為替の執行（別プロジェクトで扱う）
- Binance・暗号資産の自動売買
- 人間の承認を経ない、あらゆるクローズドループ処理

このフレームワークが生成する成果物にはすべて `manual_review_required: true` と `data_gaps[]` が付きます。実際に注文を出すのは常に人間です。

---

## プロジェクト内の関連リファレンス

- `skills/theme-detector/references/cross_sector_themes.md` — テーマ定義と構成銘柄
- `skills/theme-detector/references/energy-power-market-signals.md` — スパークスプレッド、キャパシティオークション、LMP の仕組み
- `skills/trade-hypothesis-ideator/references/what-is-priced-in-framework.md` — モデルをトレードに落とし込む3つのフレームワーク
- `scripts/api_clients/README.md` — API クライアントの一覧
- `workflows/` — ワークフローの正本定義
