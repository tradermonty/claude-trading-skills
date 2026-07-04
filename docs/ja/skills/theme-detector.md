---
layout: default
title: Theme Detector
grand_parent: 日本語
parent: スキルガイド
nav_order: 4
lang_peer: /en/skills/theme-detector/
permalink: /ja/skills/theme-detector/
---

# Theme Detector
{: .no_toc }

クロスセクターの上昇・下落テーマを3次元スコアリングで検出するスキルです。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span> <span class="badge badge-optional">FINVIZ Elite任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/theme-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/theme-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

Theme Detectorは、FINVIZの業種・セクターパフォーマンスデータを複数タイムフレームで分析し、市場で注目されている上昇テーマ（ブルテーマ）と下落テーマ（ベアテーマ）を検出するスキルです。

**3次元スコアリングモデル:**

| 次元 | スケール | 意味 |
|------|---------|------|
| **Theme Heat v2** | 0-100 | テーマの強度（モメンタム、出来高、上昇トレンド比率、ブレッド、任意の個別株リーダーシップ証拠） |
| **Lifecycle Maturity** | Emerging / Accelerating / Trending / Mature / Exhausting | テーマの成熟度（履歴ベースの持続期間、極端度、バリュエーション、ETF本数） |
| **Confidence** | Low / Medium / High | 検出の信頼度（定量データ、カバレッジ、リーダーシップ証拠、ナラティブの一致度） |

**主な特徴:**
- 14以上のクロスセクターテーマを定義済み（AI/半導体、クリーンエネルギー、サイバーセキュリティ、ゴールド、バイオテク等）
- Direction-aware分析: ベアテーマもブルテーマと同等の感度でスコアリング
- ライフサイクルステージ分類: Emerging → Accelerating → Trending → Mature → Exhausting
- ETF増殖スコアリング: ETFが多いテーマは成熟度が高い（クラウデッドトレード警告）
- Monty's Uptrend Ratio Dashboardとの統合
- `--scan-hits` による 5D+20%、EP9M、レンジ拡大、新高値、高RS の個別株リーダーシップ証拠
- `--history-file` によるテーマ履歴、1日/5日変化、20日z-score、持続期間の追跡
- WebSearchベースのナラティブ確認

**解決する問題:**
- 市場全体のテーマ的な流れを体系的に把握
- 「いまどのテーマが熱いのか」「どのテーマが枯れつつあるのか」を定量的に回答
- テーマ投資のタイミング判断（Emergingで入るか、Exhaustingで出るか）

---

## 2. 前提条件

コア機能はAPIキーなしで動作します。FINVIZ EliteとFMP APIは任意で精度と速度を向上させます。

| 項目 | 要否 | 説明 |
|------|------|------|
| Python 3.9+ | 必須 | スクリプト実行用 |
| `requests` | 必須 | HTTP通信 |
| `beautifulsoup4` | 必須 | FINVIZ HTMLスクレイピング |
| `lxml` | 必須 | HTML解析 |
| `pandas` | 必須 | データ集計・分析 |
| `numpy` | 必須 | 数値計算 |
| `yfinance` | 必須 | ETFデータ取得 |
| `finvizfinance` | 任意 | FINVIZ Eliteモード用 |
| `PyYAML` | 任意 | `--themes-config` カスタムテーマ用 |
| FINVIZ Elite APIキー | 任意 | 高速モード（2-3分 vs 5-8分）、全業種フルカバレッジ |
| FMP APIキー | 任意 | P/Eバリュエーションデータの取得 |

**インストール:**

```bash
pip install requests beautifulsoup4 lxml pandas numpy yfinance
```

> FINVIZ Elite未使用時はパブリックスクレイピングモード（無料）で動作しますが、レートリミットにより実行時間が長くなります（5-8分）。
{: .note }

---

## 3. クイックスタート

### 最小限の実行（APIキー不要）

```bash
python3 skills/theme-detector/scripts/theme_detector.py --output-dir reports/
```

### FINVIZ Elite モード（高速）

```bash
python3 skills/theme-detector/scripts/theme_detector.py \
  --finviz-api-key $FINVIZ_API_KEY \
  --output-dir reports/
```

### 個別株リーダーシップ + 履歴を使う日次実行

```bash
python3 skills/theme-detector/scripts/theme_detector.py \
  --scan-hits data/theme_scan_hits_YYYY-MM-DD.json \
  --history-file reports/theme_detector_history.json \
  --as-of-date YYYY-MM-DD \
  --output-dir reports/
```

`--scan-hits` はJSON/JSONL/CSVを受け取り、`scan_type` がある行はそのまま使い、無い行は `return_5d`、`change_pct`、`volume`、`relative_volume`、`true_range` / `atr_20`、`close_location`、`new_high`、`rs_rating` などから 5D+20%、EP9M、レンジ拡大、新高値、高RS を判定します。リーダーシップ証拠が無い場合は0点としてTheme Heatを押し下げず、カバレッジ不足としてConfidence側に反映します。

### Claudeへの自然言語

```
いま市場でどんなテーマが注目されている？ブルとベアの両方教えて。
```

> **注意:** スクリプト単体の出力ではConfidenceはMediumが上限です（3つの確認レイヤーのうち2つ）。ClaudeのWebSearchによるナラティブ確認でHighに昇格可能です。
{: .note }

---

## 4. 仕組み

### ワークフロー

```
Step 1: 業種データ収集（FINVIZ）
  ↓
Step 2: テーマ分類（業種→テーママッピング）
  ↓
Step 3: Heat計算（カバレッジ付きコンポーネント）
  ↓
Step 4: 個別株リーダーシップ証拠（任意）
  ↓
Step 5: ライフサイクル / 履歴 / 加速度評価
  ↓
Step 6: ナラティブ確認（WebSearch）
  ↓
Step 7: What Changed Today / Leadership Evidence / レポート生成
```

**Step 1: 業種データ収集**
- FINVIZから約145業種のパフォーマンスデータを取得
- Elite: CSV APIで全銘柄データ、Public: HTMLスクレイピングで上位約20銘柄/業種

**Step 2: テーマ分類**
- `references/cross_sector_themes.md` に定義されたテーマ定義に基づき、業種をテーマにマッピング
- 例: Semiconductors, Software-Application, Software-Infrastructure → 「AI & Semiconductors」テーマ
- 14以上のテーマ: AI/半導体、クリーンエネルギー、サイバーセキュリティ、Cloud/SaaS、バイオテク、インフラ、ゴールド/貴金属、防衛、ヘルスケア、不動産、暗号資産、中国/新興市場等

**Step 3: Theme Heat計算**

Theme Heat (0-100) は利用可能なサブスコアから算出されます。欠損データは50点として中立加点せず、カバレッジ不足としてConfidence側に反映します：

| サブスコア | 内容 |
|-----------|------|
| **Momentum Strength** | 複数タイムフレーム（1W, 1M, 3M, 6M, 1Y）のパフォーマンス |
| **Volume Intensity** | 出来高の異常度（平均比） |
| **Uptrend Signal** | Monty's Uptrend Ratio（上昇トレンド比率、MA10、傾き） |
| **Breadth Signal** | テーマ内業種のうち、方向性に沿ったweighted returnを持つ業種の割合（LEADテーマなら正のリターン、LAGテーマなら負のリターン）。業種レベルの参加率 |

**Step 4: ライフサイクル評価**

| ステージ | 特徴 | 投資判断 |
|---------|------|---------|
| **Emerging** | 低Heat、短期間、少数ETF | 先行投資のチャンス |
| **Accelerating** | 中Heat、モメンタム加速中 | 追加投資の好機 |
| **Trending** | 高Heat、メディア注目度上昇 | ポジション維持 |
| **Mature** | 高Heat、ETF増殖、バリュエーション上昇 | 慎重にポジション管理 |
| **Exhausting** | Heat低下、RSI極端、ETF飽和 | 利益確定を検討 |

**Step 5: ナラティブ確認**
- 上位テーマについてWebSearchで最新ニュースを検索
- 定量データとナラティブの一致度でConfidenceを調整

---

## 5. 使用例

### 例1: クイックテーマスキャン

**プロンプト:**
```
いま市場で注目されているテーマを教えて
```

**Claudeの動作:**
```bash
python3 skills/theme-detector/scripts/theme_detector.py --output-dir reports/
```

**期待される出力:** テーマダッシュボード（Heat、Direction、Lifecycle、Confidence）と上位テーマの詳細分析

**なぜ有用か:** 5-8分で市場全体のテーマ的な流れを把握できます。

---

### 例2: FINVIZ Elite高速モード

**プロンプト:**
```
FINVIZ Eliteを使ってテーマスキャンを高速実行して
```

**Claudeの動作:**
```bash
python3 skills/theme-detector/scripts/theme_detector.py \
  --finviz-api-key $FINVIZ_API_KEY \
  --output-dir reports/
```

**なぜ有用か:** 2-3分で完了し、全業種のフルカバレッジが得られます。パブリックモードの約20銘柄/業種制限がなくなります。

---

### 例3: ライフサイクル評価の活用

**プロンプト:**
```
AI/半導体テーマはまだ初期段階？それとも成熟して過密状態？
```

**Claudeの動作:**
- Theme Detectorを実行してAI/半導体テーマのライフサイクルステージを確認
- ETF増殖スコア（SMH, SOXX, AIQ, BOTZ, CHAT等の本数）を評価
- RSI極端度、バリュエーション水準を確認

**なぜ有用か:** テーマが「まだ乗れる段階」か「すでにクラウデッドトレード」かを判断できます。

---

### 例4: ベアテーマの特定

**プロンプト:**
```
いま下落圧力が強いセクターやテーマは何？
```

**Claudeの動作:**
- Direction = Bearish のテーマを抽出
- 下落モメンタムが加速中か減速中かを評価
- ミーンリバージョン（平均回帰）の可能性があるかを分析

**なぜ有用か:** ベアテーマを特定することで、避けるべきセクターや逆張り機会を把握できます。

---

### 例5: Heatスコアの解釈

**プロンプト:**
```
Theme Heatスコア85と45の違いは？投資判断にどう使う？
```

**Claudeの動作:**
- Heatスコアの4つのサブスコアの内訳を解説
- Heat 85 = 「モメンタム・出来高・ブレッドすべてが強い。メインストリームテーマ」
- Heat 45 = 「一部のシグナルのみ。Emergingか、衰退の初期段階」
- ライフサイクルとの組み合わせで投資判断が変わることを説明

**なぜ有用か:** スコアの数値だけでなく、投資判断への活用方法を理解できます。

---

### 例6: テーマから個別銘柄の調査

**プロンプト:**
```
サイバーセキュリティテーマのHeatが高い。この中で買い候補になる個別銘柄を調べて。
```

**Claudeの動作:**
1. Theme Detectorレポートからサイバーセキュリティテーマの代表銘柄を確認（CRWD, PANW, FTNT, ZS, NET等）
2. FinViz Screenerで `theme_cybersecurity` フィルターを適用
3. 個別銘柄のファンダメンタル/テクニカル分析

**なぜ有用か:** テーマレベルの分析から個別銘柄の投資判断まで一貫したワークフローを構築できます。

---

## 6. 出力の読み方

### テーマダッシュボード

レポートの冒頭にテーマダッシュボードが表示されます：

| テーマ | Heat | Direction | Lifecycle | Confidence |
|--------|------|-----------|-----------|------------|
| AI & Semiconductors | 85 | Bullish | Trending | Medium |
| Gold & Precious Metals | 72 | Bullish | Accelerating | Medium |
| Clean Energy & EV | 35 | Bearish | Exhausting | Medium |

### フィールドの読み方

| フィールド | 意味 |
|----------|------|
| **Heat** | テーマの総合的な勢い（高いほど注目度が高い） |
| **Direction** | LEAD（相対的にアウトパフォーム）/ LAG（相対的にアンダーパフォーム）/ Neutral（中立）。LAGテーマでも絶対リターンが正の場合がある（ショートシグナルではない） |
| **Lifecycle** | テーマの成熟段階（Emerging → Exhausting） |
| **Confidence** | 検出精度の信頼度（High = 定量+ナラティブ一致） |

### テーマ詳細セクション

各テーマの詳細には以下が含まれます：
- 構成業種のパフォーマンス一覧
- 代表銘柄リスト
- プロキシETF（テーマへのエクスポージャー手段）
- ライフサイクル評価の根拠

---

## 7. Tips & ベストプラクティス

### 投資判断への活用

| Lifecycle | Heat高 | Heat低 |
|-----------|--------|--------|
| **Emerging** | 早期参入の好機、積極的にリサーチ | 様子見、シグナルが明確になるのを待つ |
| **Trending** | メインポジション維持 | テーマの勢い鈍化、利益確定を検討 |
| **Exhausting** | クラウデッドトレード警告、慎重に | 逆張り機会の可能性を検討 |

### FINVIZ Elite vs Public モードの比較

| 項目 | Elite | Public |
|------|-------|--------|
| 業種カバレッジ | 全約145業種 | 全約145業種 |
| 銘柄数/業種 | フルユニバース | 約20銘柄（1ページ目） |
| レートリミット | 0.5秒/リクエスト | 2.0秒/リクエスト |
| データ鮮度 | リアルタイム | 15分遅延 |
| 実行時間 | 2-3分 | 5-8分 |
| 料金 | $39.50/月 | 無料 |

### 定期実行のすすめ

- **週1回**のテーマスキャンで市場の流れを把握するのが効果的
- テーマのLifecycle変化（Emerging→Trending等）は数週間単位で起こるため、毎日の実行は不要
- 大きなニュースイベント後は臨時スキャンが有効

---

## 8. 他スキルとの連携

### Theme Detector → FinViz Screener

テーマレベルの分析から個別銘柄の探索へ：

```
1. Theme Detector: Cybersecurity テーマの Heat=82, Lifecycle=Trending を確認
2. FinViz: theme_cybersecurity フィルターで個別銘柄を一覧表示
3. 追加フィルター: ta_sma200_pa,fa_epsqoq_o25 でモメンタム銘柄に絞り込み
```

### Theme Detector → CANSLIM / VCP

テーマが強い銘柄群でグロース株・ブレイクアウト候補を精密検出：

```
1. Theme Detector: AI & Semiconductors の代表銘柄リスト取得
2. CANSLIM: --universe NVDA AVGO AMD MRVL で7コンポーネント分析
3. VCP: --universe で同じ銘柄群のVCPパターン検出
```

### Theme Detector → Sector Analyst

テーマ検出の結果をセクターチャート分析で視覚的に確認：

```
1. Theme Detector: セクター別のテーマ動向を定量的に把握
2. Sector Analyst: チャートによるローテーションパターンの視覚的確認
```

### Breadth Chart Analyst → Theme Detector

市場幅の健全性を確認した上でテーマ分析：

```
1. Breadth Chart Analyst: 市場全体の健全性を確認
2. Theme Detector: 健全な市場環境でのBullishテーマに集中
   （市場幅が悪化している場合はBearishテーマの分析に重点）
```

---

## 9. トラブルシューティング

### 実行時間が長い（5分以上）

**原因:** Publicモード（パブリックスクレイピング）のレートリミット

**対処:**
1. FINVIZ Elite APIキーの導入を検討（2-3分に短縮）
2. `--max-themes 5` でテーマ数を制限
3. `--max-stocks-per-theme 10` で代表銘柄数を制限（デフォルト値）

### テーマが検出されない

**原因:** 市場が横ばいでモメンタムシグナルが弱い

**対処:**
1. ベアテーマも含めて確認（Direction = Bearish）
2. `--max-themes` を増やして閾値の低いテーマも表示
3. 市場が低ボラの時期はテーマ検出が困難なのは正常
4. テーマ検出には最低2業種のマッチが必要（themes.yaml の `cross_sector_min_matches` で設定）

### yfinance / pandasエラー

```
ModuleNotFoundError: No module named 'pandas'
```

**対処:**
```bash
pip install pandas numpy yfinance
```

### FINVIZスクレイピング失敗

```
WARNING: FINVIZ request failed with status 403
```

**対処:**
1. 一時的なレートリミット。数分待って再試行
2. Publicモードではレートリミットが厳しいため、間隔を空けて実行
3. FINVIZ Eliteの導入でこの問題を回避可能

### ライフサイクル評価が不正確に見える

**原因:** ETFカタログが静的で、最新のETFが反映されていない可能性

**対処:**
1. `references/thematic_etf_catalog.md` を手動で更新
2. ライフサイクル評価はあくまで目安として利用
3. WebSearchで最新情報を補完

---

## 10. リファレンス

### CLIオプション一覧

```bash
python3 skills/theme-detector/scripts/theme_detector.py [OPTIONS]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--output-dir` | 出力ディレクトリ | `reports/` |
| `--finviz-api-key` | FINVIZ Elite APIキー | `$FINVIZ_API_KEY` |
| `--fmp-api-key` | FMP APIキー（バリュエーション用） | `$FMP_API_KEY` |
| `--finviz-mode` | FINVIZモード: `elite` / `public` | 自動検出 |
| `--max-themes` | レポートに含める最大テーマ数 | `10` |
| `--max-stocks-per-theme` | テーマあたりの最大代表銘柄数 | `10` |
| `--top` | 詳細セクションに表示するトップN件 | `3` |
| `--themes-config` | カスタムテーマYAMLパス | 内蔵 `themes.yaml` |
| `--discover-themes` | 未マッチ業種から自動テーマ発見 | `false` |
| `--dynamic-stocks` | FINVIZによる動的銘柄選択 | `false` |
| `--dynamic-min-cap` | 動的銘柄の最小時価総額 (micro/small/mid) | `small` |
| `--scan-hits` | 個別株リーダーシップのJSON/JSONL/CSV | なし |
| `--history-file` | テーマ履歴JSON | `<output-dir>/theme_detector_history.json` |
| `--no-history-update` | 履歴を読み込むが今回分を書き込まない | `false` |
| `--as-of-date` | 決定論的な実行日 (YYYY-MM-DD) | 当日 |

### 定義済みテーマ一覧

| テーマ | 構成業種例 | プロキシETF |
|--------|-----------|------------|
| AI & Semiconductors | Semiconductors, Software-Application/Infrastructure | SMH, SOXX, AIQ, BOTZ |
| Clean Energy & EV | Solar, Utilities-Renewable, Auto Manufacturers | ICLN, QCLN, TAN, DRIV |
| Cybersecurity | Software-Infrastructure, IT Services | CIBR, HACK, BUG |
| Cloud Computing & SaaS | Software-Application/Infrastructure, IT Services | SKYY, WCLD, CLOU |
| Biotech & Genomics | Biotechnology, Drug Manufacturers, Medical Devices | XBI, IBB, ARKG |
| Infrastructure & Construction | Engineering, Building Materials, Steel | PAVE, IFRA |
| Gold & Precious Metals | Gold, Silver, Other Precious Metals | GLD, GDX, SLV |
| Defense & Aerospace | Aerospace & Defense | ITA, XAR, PPA |
| Healthcare Innovation | Medical Devices, Health IT, Diagnostics | XLV, IBB |
| Real Estate & REITs | REIT各種 | VNQ, XLRE |
| Crypto & Blockchain | FinTech, Software-Infrastructure | BITO, ARKF |
| China & Emerging Markets | 各セクター（中国/新興国） | FXI, KWEB, EEM |
| Energy & Oil | Oil & Gas各種 | XLE, USO |
| Consumer & Retail | Internet Retail, Specialty Retail, Restaurants | XLY, XRT |

### 出力ファイル

| ファイル | 形式 | 用途 |
|----------|------|------|
| `theme_detector_YYYY-MM-DD_HHMMSS.json` | JSON | プログラマティック利用 |
| `theme_detector_YYYY-MM-DD_HHMMSS.md` | Markdown | 人間向けレポート |

### 関連ファイル

| ファイル | 説明 |
|----------|------|
| `skills/theme-detector/SKILL.md` | スキル定義 |
| `skills/theme-detector/references/cross_sector_themes.md` | テーマ定義（構成業種、ETF、銘柄） |
| `skills/theme-detector/references/thematic_etf_catalog.md` | テーマ別ETFカタログ |
| `skills/theme-detector/references/theme_detection_methodology.md` | 3Dスコアリングモデルの技術文書 |
| `skills/theme-detector/references/finviz_industry_codes.md` | FINVIZ業種コードマッピング |
| `skills/theme-detector/scripts/theme_detector.py` | メインスクリプト |
| `skills/theme-detector/scripts/theme_classifier.py` | テーマ分類エンジン |
| `skills/theme-detector/scripts/finviz_industry_scanner.py` | FINVIZデータ収集 |
| `skills/theme-detector/scripts/calculators/lifecycle_calculator.py` | ライフサイクル評価 |
