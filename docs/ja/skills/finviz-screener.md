---
layout: default
title: FinViz Screener
grand_parent: 日本語
parent: スキルガイド
nav_order: 1
lang_peer: /en/skills/finviz-screener/
permalink: /ja/skills/finviz-screener/
---

# FinViz Screener
{: .no_toc }

自然言語でFinVizのスクリーニング条件を構築し、Chromeで結果を表示するスキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FINVIZ Elite は任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/finviz-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/finviz-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

FinViz Screenerは、日本語または英語の自然言語による指示をFinVizのフィルターコードに変換し、スクリーニングURLを構築してChromeで開くスキルです。

**主な特徴:**
- 日本語・英語どちらの自然言語でも条件指定が可能
- 500以上のFinVizフィルターコードに対応（ファンダメンタル、テクニカル、記述的フィルター）
- **テーマ×サブテーマのクロス検索** -- 30以上の投資テーマと268のサブテーマを組み合わせ、「AI × 物流」「データセンター × 電力」「サイバーセキュリティ × クラウド」のようなセクター横断スクリーニングが可能
- FINVIZ Elite の自動検出（`$FINVIZ_API_KEY` 環境変数から判定）
- Chrome優先のブラウザ起動（OS別のフォールバック対応）
- URLインジェクション防止のための厳格なフィルター検証

**解決する問題:**
- FinVizの複雑なフィルターコードを覚える必要がなくなります
- 「高配当で成長している小型株」のような条件を、正しいフィルターの組み合わせに即座に変換します
- Eliteユーザーは自動的にリアルタイムデータのスクリーナーURLが生成されます

---

## 2. 前提条件

| 項目 | 要否 | 説明 |
|------|------|------|
| Python 3.7+ | 必須 | スクリプト実行用 |
| FINVIZ Elite アカウント | 任意 | 契約済みの場合、`$FINVIZ_API_KEY` 環境変数を設定すると Elite URL を生成 |
| Chromeブラウザ | 推奨 | 未インストール時はデフォルトブラウザで代替 |

追加のPythonパッケージのインストールは不要です（標準ライブラリのみ使用）。

> `$FINVIZ_API_KEY` 環境変数に任意の値を設定すると、スクリプトは `elite.finviz.com` のURLを生成します（値はFinVizサーバーには送信されません）。Elite スクリーナーを利用するには、Chrome で FINVIZ Elite 契約済みアカウントにログインしている必要があります。未設定時は `finviz.com`（パブリック）にフォールバックします。
{: .tip }

---

## 3. クイックスタート

Claudeに自然言語で条件を伝えるだけで使えます：

```
高配当で割安な大型株を探して
```

Claudeが以下の流れで処理します：
1. 条件をフィルターコードに変換（`cap_large,fa_div_o3,fa_pe_u20,fa_pb_u2`）
2. フィルター一覧を確認用に表示
3. 確認後、URLを構築してChromeで開く

---

## 4. 仕組み

### ワークフロー

```
ユーザーの自然言語 → フィルター変換 → フィルター確認 → URL構築 → Chrome起動
```

**Step 1: フィルターリファレンスの読み込み**
- `references/finviz_screener_filters.md` に定義された500以上のフィルターコードを参照

**Step 2: 自然言語の解釈**
- 日本語/英語のキーワードをFinVizフィルターコードにマッピング
- 範囲指定（「配当3-8%」）は `{from}to{to}` 構文（例: `fa_div_3to8`）に変換

**Step 3: フィルター確認**
- 選択されたフィルターを表形式で表示し、ユーザーに確認を求める

**Step 4: スクリプト実行**
- `skills/finviz-screener/scripts/open_finviz_screener.py` でURL構築とChromeオープン
- `$FINVIZ_API_KEY` が設定されていれば `elite.finviz.com`、なければ `finviz.com` のURLを生成（環境変数はURL切替フラグとして機能）

**Step 5: 結果レポート**
- 構築されたURL、使用モード（Elite/Public）、適用フィルターのサマリー、次のステップの提案

### URL構造

```
https://finviz.com/screener.ashx?v={view}&f={filters}&o={order}
```

- `v` : ビュータイプ（overview=111, valuation=121, financial=161, technical=171 等）
- `f` : カンマ区切りのフィルターコード
- `o` : ソート順（`-marketcap` で時価総額降順など）

---

## 5. 使用例

### 例1: グロースモメンタム株

**プロンプト:**
```
EPS成長率が25%以上、SMA50とSMA200の上にあるモメンタム株を見つけて
```

**Claudeの動作:**
- フィルター: `fa_epsqoq_o25,ta_sma50_pa,ta_sma200_pa`
- ビュー: Technical (v=171)
- グロースとモメンタムの両方の条件を満たす銘柄を一覧表示

**なぜ有用か:** 業績成長がテクニカルトレンドでも確認されている銘柄に絞り込めます。

---

### 例2: CANSLIM + Minervini + VCP 統合フィルタ

**プロンプト:**
```
CANSLIMとMinerviniの条件を組み合わせたスクリーニングをしたい。
EPS成長25%以上、52週高値に近い、出来高が増加傾向、SMA全部の上にある銘柄
```

**Claudeの動作:**
- フィルター: `fa_epsqoq_o25,ta_highlow52w_b0to10h,sh_relvol_o1.5,ta_sma20_pa,ta_sma50_pa,ta_sma200_pa`
- ビュー: Performance (v=141)
- CANSLIM の C条件 + Minervini の Trend Template に近い条件の統合

**なぜ有用か:** 複数の投資手法の核心条件を1つのスクリーナーに統合し、高品質な候補銘柄を絞り込めます。

---

### 例3: 高配当バリュー株

**プロンプト:**
```
配当利回り3-8%、PER 10-20倍、PBR 2倍以下、ROE 15%以上の高配当バリュー株を探して
```

**Claudeの動作:**
- フィルター: `fa_div_3to8,fa_pe_10to20,fa_pb_u2,fa_roe_o15`
- ビュー: Valuation (v=121)
- 範囲指定 `fa_div_3to8` で配当トラップ（超高利回り）を除外

**なぜ有用か:** 配当利回りに上限を設けることで、減配リスクの高い銘柄を除外しつつ安定した配当収入を目指せます。

---

### 例4: 売られ過ぎリバウンド候補

**プロンプト:**
```
RSI30以下の売られすぎ大型株で、52週安値付近にあるものを表示して
```

**Claudeの動作:**
- フィルター: `cap_large,ta_rsi_os30,ta_highlow52w_a0to5l`
- ビュー: Technical (v=171)
- 大型株に限定することで流動性リスクを軽減

**なぜ有用か:** 一時的に売られ過ぎた優良大型株の反発エントリー候補を発見できます。

---

### 例5: AIテーマ株

**プロンプト:**
```
AIテーマの銘柄で、直近パフォーマンスが良好なものを見せて
```

**Claudeの動作:**
- フィルター: `theme_artificialintelligence`
- ソート: `-perf13w`（13週パフォーマンス降順）
- ビュー: Performance (v=141)

**注:** テーマはCLIでは `--themes "artificialintelligence"` で指定します（`--filters` に `theme_*` を渡すとエラーになります）。上記はURL `f=` パラメータに入る表現です。

**なぜ有用か:** FinVizのテーマフィルター機能を使い、特定の投資テーマに直接アクセスできます。

---

### 例6: 小型株ブレイクアウト候補

**プロンプト:**
```
小型株で、52週高値から5%以内、出来高が通常の1.5倍以上のブレイクアウト候補を探して
```

**Claudeの動作:**
- フィルター: `cap_small,ta_highlow52w_b0to5h,sh_relvol_o1.5`
- ビュー: Overview (v=111)
- ブレイクアウトの2大条件（新高値近辺 + 出来高増加）を組み合わせ

**なぜ有用か:** 小型株のブレイクアウトエントリーポイントを効率的に発見できます。

---

### 例7: 日本語入力の柔軟性

**プロンプト:**
```
テクノロジーセクターの半導体関連で、機関保有率60%以上、インサイダー買いがある銘柄
```

**Claudeの動作:**
- フィルター: `sec_technology,ind_semiconductors,sh_instown_o60,sh_insidertrans_verypos`
- ビュー: Ownership (v=131)
- 日本語キーワード「半導体」「機関保有率」「インサイダー買い」を正確にマッピング

**なぜ有用か:** FinVizのフィルターコードを知らなくても、日本語の投資用語だけで高度なスクリーニングが実行できます。

---

### 例8: プログラマティック使用（`--url-only`）

**CLI コマンド:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --filters "cap_mega,fa_div_o3,fa_pe_u15,ta_sma200_pa" \
  --view valuation \
  --url-only
```

**出力:**
```
https://finviz.com/screener.ashx?v=121&f=cap_mega,fa_div_o3,fa_pe_u15,ta_sma200_pa
```

**なぜ有用か:** `--url-only` オプションを使えば、ブラウザを開かずにURLだけを取得できます。スクリプトやSlack連携、定期実行での利用に便利です。

---

### 例9: テーマのクロス検索（AI × 物流、データセンター × 電力）

従来のセクター/業種フィルターは1次元的な分類に限定されます。テーマ/サブテーマフィルターを使えば、セクターを横断する*投資テーマ*軸でスクリーニングが可能です。

**プロンプトA: AI × 物流**
```
AI関連の物流銘柄で、中型以上、直近四半期パフォーマンス良好なものを探して
```

**コマンド:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --themes "artificialintelligence" \
  --subthemes "ecommercelogistics" \
  --filters "cap_midover,ta_perf_13wup" \
  --url-only
```

**プロンプトB: データセンター × 電力インフラ**
```
データセンターと電力インフラ関連の銘柄を見せて
```

**コマンド:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --subthemes "clouddatacenters,aienergy" \
  --url-only
```

**プロンプトC: サイバーセキュリティ × クラウド**
```
サイバーセキュリティとクラウド関連で、ROEが高い銘柄
```

**コマンド:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --themes "cybersecurity" \
  --subthemes "aicloud" \
  --filters "fa_roe_o15" \
  --url-only
```

**なぜ有用か:** セクターフィルターは企業の*業種*（テクノロジー、公益事業、不動産等）で分類します。テーマフィルターは企業が*乗っているトレンド*で分類します。テーマとサブテーマを組み合わせることで、長期的な成長テーマの交差点にある銘柄を発掘できます。たとえば、AI自動化に投資する物流企業や、データセンター電力需要に恩恵を受ける電力会社など、従来のセクターフィルターでは見つけられない銘柄群です。

---

### スクリーニングレシピ

よく使われる投資戦略のためのフィルター組み合わせ集です。各レシピには段階的な絞り込みのヒントも含まれています。

#### レシピ1: 高配当成長株（Kanchiスタイル）

**目的:** 高利回り + 配当成長 + 業績成長を兼ね備え、利回りトラップを除外。

**フィルター:** `fa_div_3to8,fa_sales5years_pos,fa_eps5years_pos,fa_divgrowth_5ypos,fa_payoutratio_u60,geo_usa`
**ビュー:** Financial

| フィルター | 目的 |
|-----------|------|
| `fa_div_3to8` | 利回り3-8%（超高利回りトラップを除外） |
| `fa_sales5years_pos` | 5年売上成長率がプラス |
| `fa_eps5years_pos` | 5年EPS成長率がプラス |
| `fa_divgrowth_5ypos` | 5年配当成長率がプラス |
| `fa_payoutratio_u60` | 配当性向60%未満（持続可能性） |
| `geo_usa` | 米国上場株 |

**絞り込みのヒント:** `fa_div_o3` から始めて → `fa_div_3to8` で上限を設定 → `fa_payoutratio_u60` でトラップを除外。

#### レシピ2: Minervini Trend Template + VCP

**目的:** Stage 2上昇トレンドの銘柄でボラティリティが収縮しているもの。

**フィルター:** `ta_sma50_pa,ta_sma200_pa,ta_sma200_sb50,ta_highlow52w_0to25-bhx,ta_perf_26wup,sh_avgvol_o300,cap_midover`
**ビュー:** Technical

| フィルター | 目的 |
|-----------|------|
| `ta_sma50_pa` | 株価が50日SMAの上 |
| `ta_sma200_pa` | 株価が200日SMAの上 |
| `ta_sma200_sb50` | 200 SMAが50 SMAの下（上昇トレンド） |
| `ta_highlow52w_0to25-bhx` | 52週高値から25%以内 |
| `ta_perf_26wup` | 26週パフォーマンスがプラス |
| `sh_avgvol_o300` | 平均出来高30万株超 |
| `cap_midover` | 中型株以上 |

**VCP絞り込み:** `ta_volatility_wo3,ta_highlow20d_b0to5h,sh_relvol_u1` を追加して、低ボラティリティ + 20日高値付近 + 出来高減少を確認。

#### レシピ3: 不当に売られた成長株

**目的:** ファンダメンタルズが堅調なのに直近で急落した銘柄。

**フィルター:** `fa_sales5years_o5,fa_eps5years_o10,fa_roe_o15,fa_salesqoq_pos,fa_epsqoq_pos,ta_perf_13wdown,ta_highlow52w_10to30-bhx,cap_large,sh_avgvol_o200`
**ビュー:** Overview → 候補確認後に Valuation に切替

| フィルター | 目的 |
|-----------|------|
| `fa_sales5years_o5` | 5年売上成長率 > 5% |
| `fa_eps5years_o10` | 5年EPS成長率 > 10% |
| `fa_roe_o15` | ROE > 15% |
| `fa_salesqoq_pos` | 前四半期比売上成長がプラス |
| `fa_epsqoq_pos` | 前四半期比EPS成長がプラス |
| `ta_perf_13wdown` | 13週パフォーマンスがマイナス |
| `ta_highlow52w_10to30-bhx` | 52週高値から10-30%下落 |
| `cap_large` | 大型株 |
| `sh_avgvol_o200` | 平均出来高20万株超 |

#### レシピ4: ターンアラウンド銘柄

**目的:** 業績が過去に悪化していたが、直近で回復傾向を見せている銘柄。

**フィルター:** `fa_eps5years_neg,fa_epsqoq_pos,fa_salesqoq_pos,ta_highlow52w_b30h,ta_perf_13wup,cap_smallover,sh_avgvol_o200`
**ビュー:** Performance

| フィルター | 目的 |
|-----------|------|
| `fa_eps5years_neg` | 5年EPS成長率がマイナス（過去の悪化） |
| `fa_epsqoq_pos` | 前四半期比EPS成長がプラス（回復） |
| `fa_salesqoq_pos` | 前四半期比売上成長がプラス（回復） |
| `ta_highlow52w_b30h` | 52週高値から30%以内 |
| `ta_perf_13wup` | 13週パフォーマンスがプラス |
| `cap_smallover` | 小型株以上 |
| `sh_avgvol_o200` | 平均出来高20万株超 |

#### レシピ5: モメンタムトレード候補

**目的:** 52週高値付近で出来高が増加している短期モメンタムリーダー。

**フィルター:** `ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to3h,ta_perf_4wup,sh_relvol_o1.5,sh_avgvol_o1000,cap_midover`
**ビュー:** Technical

| フィルター | 目的 |
|-----------|------|
| `ta_sma50_pa` | 株価が50日SMAの上 |
| `ta_sma200_pa` | 株価が200日SMAの上 |
| `ta_highlow52w_b0to3h` | 52週高値から3%以内 |
| `ta_perf_4wup` | 4週パフォーマンスがプラス |
| `sh_relvol_o1.5` | 相対出来高 > 1.5倍 |
| `sh_avgvol_o1000` | 平均出来高100万株超 |
| `cap_midover` | 中型株以上 |

#### Tips: 段階的な絞り込み

スクリーニングは対話的に進めるのが最も効果的です：

1. **広く始める** — コアフィルター3-4個で初期セットを作成
2. **件数を確認** — 100件超なら条件追加、5件未満なら条件を緩和
3. **ビューを切替** — まず `overview` で概要確認、次に `financial` や `valuation` で詳細分析
4. **テクニカルを重ねる** — ファンダメンタルズ確認後に `ta_` フィルターでエントリータイミングを計る

---

## 6. 出力の読み方

FinViz Screenerの結果は、FinVizのウェブサイト上で表示されます。

### ビュータイプの選び方

| ビュー | コード | 用途 |
|--------|--------|------|
| Overview | v=111 | 銘柄の概要確認（セクター、時価総額、P/E等） |
| Valuation | v=121 | バリュエーション比較（P/E、P/B、PEG、P/S等） |
| Ownership | v=131 | 機関投資家保有率、インサイダー取引 |
| Performance | v=141 | 期間別リターン（1W、1M、3M、6M、1Y） |
| Custom | v=152 | ユーザー定義カラム |
| Financial | v=161 | 財務指標（ROE、ROA、マージン、負債比率等） |
| Technical | v=171 | テクニカル指標（RSI、SMA、ベータ、ATR等） |

### 結果の確認ポイント

1. **銘柄数の確認** - 条件が厳しすぎて0件の場合は条件を緩和
2. **ソート順の活用** - カラムヘッダーをクリックしてソート切替
3. **ビューの切替** - 目的に応じてタブを切り替えて多角的に確認

---

## 7. Tips & ベストプラクティス

### フィルターの組み合わせ方

- **最大5-7フィルター**を目安にしてください。多すぎると結果が0件になりがちです
- **ファンダメンタル + テクニカル** の組み合わせが最も実用的です
- **範囲指定** (`fa_div_3to8`) を活用して極端な値を除外しましょう

### レシピの活用

以下のようなプリセットレシピが特に人気です：

| レシピ名 | フィルター例 | ビュー |
|----------|-------------|--------|
| 高配当成長株（Kanchi） | `fa_div_3to8,fa_sales5years_pos,fa_divgrowth_5ypos,fa_payoutratio_u60,geo_usa` | Financial |
| Minervini + VCP | `ta_sma50_pa,ta_sma200_pa,ta_sma200_sb50,ta_highlow52w_0to25-bhx,cap_midover` | Technical |
| 不当に売られた成長株 | `fa_sales5years_o5,fa_eps5years_o10,ta_perf_13wdown,cap_large` | Overview |
| ターンアラウンド | `fa_eps5years_neg,fa_epsqoq_pos,ta_perf_13wup,cap_smallover` | Performance |
| モメンタム候補 | `ta_highlow52w_b0to3h,ta_perf_4wup,sh_relvol_o1.5,cap_midover` | Technical |

### Elite vs Public の違い

| 項目 | Public | Elite |
|------|--------|-------|
| データ更新頻度 | Nasdaq: 15分遅延 / NYSE・AMEX: 20分遅延 | リアルタイム |
| URL | finviz.com | elite.finviz.com |
| 料金 | 無料 | $39.50/月 |
| 検出方法 | `$FINVIZ_API_KEY` 未設定 | `$FINVIZ_API_KEY` に任意の値を設定（URL切替フラグ） |

---

## 8. 他スキルとの連携

### FinViz → CANSLIM Screener

FinVizでグロース条件の粗い絞り込みを行い、CANSLIM Screenerで7コンポーネントの深い分析を実施：

```
1. FinViz: fa_epsqoq_o25,ta_sma200_pa で候補リスト取得
2. CANSLIM: リスト銘柄を --universe で渡して詳細スコアリング
```

### FinViz → VCP Screener

FinVizでStage 2のトレンドテンプレート条件を満たす銘柄をプレスクリーニング：

```
1. FinViz: ta_sma20_pa,ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to25h
2. VCP: 候補銘柄のVCPパターン（ボラティリティ収縮）を詳細分析
```

### FinViz → Theme Detector

FinVizのテーマフィルターで個別銘柄を確認し、Theme Detectorでテーマ全体の強度を把握：

```
1. Theme Detector: テーマの Heat/Lifecycle/Confidence を確認
2. FinViz: `--themes "artificialintelligence"` 等でテーマ銘柄の個別確認
```

---

## 9. トラブルシューティング

### Chromeが開かない

**原因:** Chromeがインストールされていない、またはパスが通っていない

**対処:**
- macOS: `/Applications/Google Chrome.app` に Chrome が存在するか確認
- `--url-only` オプションでURLだけ取得し、手動でブラウザに貼り付け

### フィルターコードが無効と表示される

**原因:** フィルターコードの形式が正しくない

**対処:**
- フィルターコードは小文字の英数字、アンダースコア、ドット、ハイフンのみ使用可能
- `references/finviz_screener_filters.md` で正確なコードを確認

### 結果が0件

**原因:** フィルター条件が厳しすぎる

**対処:**
1. フィルター数を減らして段階的に追加
2. 範囲条件を広げる（例: `fa_pe_u10` → `fa_pe_u20`）
3. 時価総額フィルターを外して全銘柄で検索

---

## 10. リファレンス

### CLIオプション一覧

```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py [OPTIONS]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--filters` | カンマ区切りのフィルターコード* | - |
| `--themes` | カンマ区切りのテーマスラッグ*（例: `artificialintelligence,cybersecurity`） | - |
| `--subthemes` | カンマ区切りのサブテーマスラッグ*（例: `aicloud,aienergy`） | - |
| `--view` | ビュータイプ: overview, valuation, financial, technical, ownership, performance, custom | overview |
| `--order` | ソート順（例: `-marketcap`, `dividendyield`） | - |
| `--elite` | Elite モードを強制 | `$FINVIZ_API_KEY` から自動検出 |
| `--url-only` | URLを出力するだけでブラウザを開かない | false |

\* `--filters`、`--themes`、`--subthemes` のうち少なくとも1つが必須です。

### よく使うフィルターコード

| カテゴリ | コード | 意味 |
|----------|--------|------|
| 時価総額 | `cap_small`, `cap_mid`, `cap_large`, `cap_mega` | 小型/中型/大型/超大型 |
| P/E | `fa_pe_u10`, `fa_pe_u20`, `fa_pe_profitable` | P/E 10倍未満/20倍未満/黒字 |
| 配当 | `fa_div_o3`, `fa_div_o5`, `fa_div_3to8` | 利回り3%超/5%超/3-8%範囲 |
| EPS成長 | `fa_epsqoq_o25`, `fa_epsqoq_o50` | 四半期EPS成長25%超/50%超 |
| RSI | `ta_rsi_os30`, `ta_rsi_ob70` | RSI 30以下/70以上 |
| SMA | `ta_sma50_pa`, `ta_sma200_pa` | SMA50上/SMA200上 |
| 52週 | `ta_highlow52w_b0to5h`, `ta_highlow52w_a0to5l` | 高値5%以内/安値5%以内 |
| セクター | `sec_technology`, `sec_healthcare`, `sec_energy` | テクノロジー/ヘルスケア/エネルギー |
| テーマ | `theme_artificialintelligence`, `theme_cybersecurity` | AI/サイバーセキュリティ |
| 出来高 | `sh_relvol_o1.5`, `sh_relvol_o2`, `sh_avgvol_o500` | 相対出来高1.5倍超/2倍超/平均50万超 |

> **注:** テーマ（`theme_*`）・サブテーマ（`subtheme_*`）のコードは `--themes` / `--subthemes` オプションで指定します（`--filters` には渡せません）。スクリプトが自動的にプレフィックスを付与してURLを構築します。

### 関連ファイル

| ファイル | 説明 |
|----------|------|
| `skills/finviz-screener/SKILL.md` | スキル定義（ワークフロー） |
| `skills/finviz-screener/references/finviz_screener_filters.md` | 完全なフィルターコードリファレンス |
| `skills/finviz-screener/scripts/open_finviz_screener.py` | URL構築・ブラウザ起動スクリプト |
