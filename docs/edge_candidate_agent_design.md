# 米国株「エッジ候補発掘」エージェントスキル設計案（個別株ロング中心 / 数日〜数週間＋数ヶ月）

## 0. 目的
日々の株式相場（主に米国株）の動きを観察し、**再現性のある期待値（Edge）候補**を「研究チケット」として自動生成するエージェントスキルを設計する。

- **目的の中心**：売買指示ではなく **「検証可能な仮説」を量産 → 優先度付け → 検証し、残るものだけを戦略化**
- **想定スタイル**：米国株・個別株ロング中心
- **想定ホライズン**：数日〜数週間（メイン）、ときどき数ヶ月
- **成果物**：
  1) 日次の「市場状態（レジーム）ラベル」
  2) 異常検知サマリ
  3) エッジ候補（研究チケット）Top N
  4) 検証仕様（バックテスト設定）と却下条件（p-hacking抑止）
  5) 既存エッジの劣化監視レポート

---

## 1. 前提・スコープ
### 1.1 取扱い範囲
- **EOD中心**（日足・出来高）を基本。必要に応じて「寄り/引け」など時間帯分解を追加。
- **ロング中心**なので、以下を強く意識する：
  - 地合い悪化（相関上昇・ボラ上昇・ブレッドス悪化）時に**無理に攻めない**設計
  - “勝ちやすい局面”を見極め、銘柄スキャンの質を上げる

### 1.2 データ前提（最小）
- 株価：Open/High/Low/Close/AdjClose
- 出来高：Volume
- ベンチ：SPY（＋QQQ、IWMは任意）
- セクターETF：XLF/XLK/XLE/XLV/XLY/XLP/XLI/XLU/XLB（任意だが推奨）
- ブレッドス（可能なら）：A/D、MA上比率、新高値/新安値
  ※無ければ「銘柄ユニバース内の集計」で代用

### 1.3 任意（あると強い）
- オプション：IV、スキュー、満期構造（最低限 VIXでも可）
- マクロ：金利（米10年等）、ドル指数、クレジット系ETF（HYG等）
- イベント：決算日、ガイダンス等（外部データ or 企業カレンダー）

---

## 2. 設計原則（このスキルが強くなる条件）
1. **レジーム条件付き**（同じシグナルでも相場状態で期待値が反転するため）
2. **観察→仮説→定義→検証**をテンプレ化（雑感を排除）
3. **説明可能性**（「なぜ残るか」を構造/行動/リスクプレミアムでタグ付け）
4. **コスト・容量を織り込む**（流動性・スリッページ・ギャップ耐性）
5. **却下条件を同時に設計**（p-hacking／後付け最適化を抑止）
6. **劣化監視が標準機能**（エッジは減価償却する）

---

## 3. 全体アーキテクチャ
```
[Data Ingestion] -> [Feature Store]
                      |
                      v
              [Market Regime Agent]  -> regime_label, regime_scores
                      |
                      v
   [Sector/Theme Agent] -> sector_RS, dispersion, leadership
                      |
                      v
  [Scanner + Anomaly Detector] -> candidates, anomalies
                      |
                      v
   [Hypothesis Generator] -> research_tickets (if-then + mechanism)
                      |
                      v
 [Backtest Spec Generator] -> test_configs + rejection_criteria
                      |
                      v
 [Ranking/Selection] -> top_N_tickets + daily_report
                      |
                      v
 [Edge Monitor] -> live_edges healthcheck, decay alerts
```

---

## 4. スキルのインターフェース
### 4.1 入力
- 日次データ（EOD更新）
  - `prices[symbol][date] = {O,H,L,C,V}`
- ユニバース定義
  - 例：価格>5、平均出来高>1M、時価総額>2B など（任意）
- オプション：イベントカレンダー（決算日など）

### 4.2 出力（毎日）
- `regime`: 市場状態ラベル（RiskOn / Neutral / RiskOff）＋根拠スコア
- `market_summary`: 指標サマリ（ブレッドス、相関、ボラ、ディスパージョン等）
- `anomalies`: 異常検知Top K（何がどれだけ異常か）
- `tickets`: 研究チケットTop N（仮説＋特徴量定義＋テスト仕様）
- `watchlist`: スキャン候補（長いリスト、特徴量付き）
- `monitor`: 既存戦略/エッジのヘルス（劣化検知）

---

## 5. 観察する主要特徴量（最小セット）
### 5.1 レジーム（市場状態）
**狙い**：ロングの勝率・リスクリワードを左右する“環境”を毎日数値化する。

- トレンド：
  - `MA50_slope`, `MA200_slope`, `Price_vs_MA200`
  - `Return_20D`（SPY / QQQ）
- ボラ：
  - `RV_10`, `RV_20`（実現ボラ、標準偏差×sqrt(252)など）
  - `Vol_trend = RV_10 / RV_60`（増えているか）
- 相関：
  - `AvgPairCorr_20`（ユニバース内の平均相関）
- ブレッドス：
  - `PctAboveMA50`, `PctAboveMA200`
  - `A/D`（ユニバース内で上昇銘柄数-下落銘柄数でも可）
- ディスパージョン：
  - `CrossSectionStd_1D`, `CrossSectionStd_20D`（銘柄間ばらつき）

**レジーム分類例（ヒューリスティック）**
- RiskOn：`Price>MA200` かつ `PctAboveMA50` 高め かつ `AvgPairCorr` 低〜中
- RiskOff：`RV_20` 上昇 & `AvgPairCorr` 上昇 & `PctAboveMA50` 低下
- Neutral：それ以外

> 実装ではスコアリング（0〜100）にして、閾値でラベル化すると安定。

---

### 5.2 セクター/テーマ（追い風の方向）
- `Sector_RS_1M/3M`：セクターETF vs SPY の相対強度
- `Sector_Dispersion`：セクター内銘柄のばらつき（選別相場か）
- `Leadership_Consistency`：強いセクターが継続しているか

---

### 5.3 個別（ロングで勝ちやすい形）
#### (A) 相対強度
- `RS_1M/3M/6M`: 銘柄リターン - SPYリターン
- `Rank_RS`: ユニバース内順位

#### (B) トレンド構造
- `Close_vs_MA20/50/200`
- `HH_20`（20日高値更新）
- `PullbackDepth`: 高値からの下落率
- `DaysSinceHigh`: 高値からの経過日数

#### (C) 需給（出来高）
- `RelVolume = Volume / SMA(Volume, 20)`
- `VolumeZ`: z-score（過去N日平均との差）
- `UpVolMinusDownVol`: 上昇日出来高 - 下落日出来高（簡易）

#### (D) リスク（落ち方）
- `ATR_14`, `ATRpct`
- `Gap = Open/PrevClose - 1`
- `TailRiskProxy`: 大陰線＋出来高急増＋下ヒゲ無し等のパターン検出

---

## 6. 異常検知（Anomaly Detector）
### 6.1 目的
日々のデータから「**分布の端**」を拾い、仮説の材料（edge candidate）にする。

### 6.2 検知ルール（例）
- **単変量**：Zスコア（|z|>2 など）
  - `Return_1D_z`, `Volume_z`, `Gap_z`, `ATRpct_z`
- **連続性**：連続3日以上の偏り（例：出来高急増が継続）
- **同時発生**（コンボ）：
  - 相関↑ + ボラ↑ + ブレッドス↓（典型的なRiskOff）
  - ブレッドス↓ + 指数上昇（指数の“中身”が弱い）

### 6.3 出力
- `anomalies = [{type, scope(market/sector/stock), metric, value, z, comment}]`

---

## 7. スキャナー（候補抽出）設計
### 7.1 目的
ロング中心で勝ちやすい銘柄の「型」を機械的に抽出し、候補の質を上げる。

### 7.2 基本スキャナー（推奨：最初は2本だけ）
#### Scanner A：中期相対強度（コア）
- 条件例：
  - `RS_6M` 上位X%
  - `Close > MA200`（トレンド健全）
  - `ATRpct` が極端でない（過度に荒い銘柄除外）
- 期待：数週間〜数ヶ月の“質の高いロング候補”を安定供給

#### Scanner B：押し目 or ブレイクアウト（タイミング）
- 押し目条件例：
  - `Close > MA50 > MA200`
  - 直近3〜7日下落、かつ `RelVolume` 低下（売り枯れ）
  - `PullbackDepth` が“浅い”（定義は固定）
- ブレイクアウト条件例：
  - `HH_20 == True`
  - `RelVolume > threshold`
  - 当日陰線を除外（引けの強さ）

### 7.3 追加（任意）
- 決算ギャップ（イベント系）：ギャップアップ＋出来高急増＋引け強い

---

## 8. エッジ候補（仮説）ライブラリ：ロング中心で使いやすい8型
> ここは **「観察→if-then→テスト仕様」**の定型化が目的。
> まずはこの8型を“雛形”として持ち、日々の異常やスキャン結果を当てはめる。

1. **中期モメンタム（6-1 / 12-1）**
   - if：6M相対強度上位＋トレンド健全
   - then：20〜60営業日の超過リターンが正か

2. **ブレイクアウト＋出来高**
   - if：20日高値更新＋相対出来高高＋引け強い
   - then：5〜20営業日の上振れが残るか

3. **上昇トレンド内の浅い押し目**
   - if：MA並び良好＋短期調整＋出来高減少
   - then：反転までの時間が短いか

4. **決算ギャップ後ドリフト**
   - if：決算翌日ギャップアップ＋出来高急増＋引け強い
   - then：10〜40営業日でドリフトがあるか

5. **セクター相対強度 × 銘柄相対強度（二段ロケット）**
   - if：強いセクター内の強い銘柄
   - then：5〜30営業日の超過リターンが改善するか

6. **投げ（急落）後の戻り（平均回帰）**
   - if：単日急落＋出来高急増＋長期トレンド健全
   - then：3〜10営業日でリバウンドが出るか

7. **低ボラ・高品質の“負けにくさ”**
   - if：中期強い＋下方ボラが低い
   - then：リスク調整後成績が改善するか

8. **レジーム転換の初動**
   - if：相関↓・ボラ↓・ブレッドス↑などでRiskOnへ遷移
   - then：強い銘柄バスケットの20〜60営業日が改善するか

---

## 9. 研究チケット（Research Ticket）スキーマ
**出力は「検証可能」かつ「後で同じ条件で再現できる」ことが最重要。**
Markdown + YAMLフロントマター形式を推奨。

### 9.1 テンプレ
```yaml
---
id: "EDGE-YYYYMMDD-###"
date: "YYYY-MM-DD"
regime: "RiskOn|Neutral|RiskOff"
hypothesis_type: "momentum|breakout|pullback|earnings_drift|sector_x_stock|panic_reversal|low_vol_quality|regime_shift"
mechanism_tag: "structure|behavior|risk_premium|uncertain"
priority_score: 0-100
universe: "US equities (filters...)"
holding_horizon: "5D|20D|60D"
entry_timing: "close|next_open|VWAP_proxy"
cost_model: "bps + slippage"
---
```

**Observation（観察）**
- 何が起きたか（数値／分位／Zスコア）
- 例：`RelVolume=3.1 (z=2.4)`, `HH_20=True`, `Sector_RS_1M=+6% vs SPY`

**Hypothesis（if-then 1文）**
- `if [condition] then [measurable outcome] over [horizon]`

**Rationale（なぜ残るか）**
- 構造（フロー/制度/ヘッジ）
- 行動（過剰反応/損切り/注目）
- リスクプレミアム（耐えると報われるがテールあり）
- 不確実（暫定）

**Signal Definition（特徴量定義）**
- 特徴量一覧・算出式・閾値
- レジームフィルタ（適用する/しない）

**Test Spec（検証仕様）**
- 期間：例 2015-01-01〜現在（うち直近2年はホールドアウト）
- ユニバース：流動性・価格・上場年数・除外銘柄
- エントリー：条件成立日の引け or 翌日寄り
- エグジット：固定ホールド（5/20/60日）＋損切り無し/ありの両方
- コスト：片道 x bps、スリッページは出来高/ATRでモデル化（簡易でOK）
- 評価指標：平均超過、Sharpe、Sortino、最大DD、勝率、テール（1%分位）

**Rejection Criteria（却下条件）**
- コスト込み期待値が負
- レジーム別に片側でしか勝てず、そのレジーム頻度が低すぎる
- 期間分割で符号が反転（安定性不足）
- 極端な少数銘柄依存（トップ10銘柄除外で崩壊 等）

**Implementation Notes（実装メモ）**
- 執行（寄り/引け/VWAP）
- 容量（平均出来高の何%まで）
- ギャップ耐性（ストップ無効化リスク）

---

## 10. 優先度付け（Ranking / Scoring）
研究チケットの優先順位は、**「効果量 × 安定性 × 容量 /（コスト × テール）」**で概ね決まる。

### 10.1 例：EdgeScore
- `Effect`：平均超過リターン（bps/日）やt値
- `Stability`：期間分割・レジーム分割での一貫性
- `Capacity`：流動性、出来高、スリッページ耐性
- `Cost`：取引頻度×コスト
- `Tail`：最大DD、下方分位損失
- `MechanismConfidence`：structure > behavior > risk_premium > uncertain の順に重み

---

## 11. 検証（バックテスト）設計ガイド
### 11.1 最低限の落とし穴対策
- サバイバーシップバイアス（可能なら生存バイアスの少ないデータ）
- 先読み禁止（決算・指数採用・リバランス情報の扱い）
- コスト必須（ロングでも特に短期はコストで死ぬ）
- 多重検定（シグナル試行数をメタデータで管理）

### 11.2 分割方法（推奨）
- Walk-forward（例：3年学習→6ヶ月検証をスライド）
- 直近はホールドアウト（触らない期間）を固定

### 11.3 レジーム別評価（必須）
- `RiskOn/Neutral/RiskOff` で分解し、どの環境で生きるかを明確化
- ロング中心なら「RiskOffで無理に勝とうとしない」戦略設計が合理的

---

## 12. 劣化監視（Edge Monitor）
### 12.1 監視項目（月次推奨）
- 勝率、平均損益、平均保有日数、コスト比率
- 最大DD、下方1%分位損失
- レジーム別成績
- “寄与上位銘柄”偏り（少数依存の検知）

### 12.2 劣化アラート例
- 直近Nトレードの平均が、過去分布から有意に悪化
- レジーム別で主要レジームの期待値が0以下に落ちた
- コスト比率が上昇（出来高低下・スリッページ増大）

---

## 13. MVP（最小実用）構成：まずこれで回す
1. **Market Regime Agent**（RiskOn/Neutral/RiskOff を毎日出す）
2. **Scanner 2本**
   - A：中期相対強度上位
   - B：押し目（またはブレイクアウト）
3. **研究チケット自動生成**（テンプレに埋めるだけでOK）
4. **固定ホールドの検証**（5D/20D/60D の3パターンだけ）
5. **レジーム分解レポート**（勝ちやすい環境の特定）

> ここまでで「観察→仮説→検証→学習」が回り、エージェントが“資産化”し始める。

---

## 14. 次の拡張（Roadmap）
- オプション/IV導入（ボラ需給の説明力が上がる）
- 決算イベントの精緻化（ギャップ後の“引けの強さ”など）
- ニュース/8-K/アナリスト修正の取り込み（ただし先読み厳禁）
- 銘柄クラスタリング（テーマ循環の検出）
- アクティブラーニング（有望チケットに計算資源を集中）
- 実運用連携（ウォッチリスト→発注前チェック→ポジション管理）

---

## 15. 実装メモ（ディレクトリ例）
```
edge_agent/
  data/
    raw/
    processed/
  features/
    build_features.py
    feature_defs.yaml
  agents/
    regime_agent.py
    sector_agent.py
    scanner_agent.py
    anomaly_agent.py
    hypothesis_agent.py
    backtest_spec_agent.py
    monitor_agent.py
  backtest/
    engine.py
    cost_model.py
    metrics.py
  reports/
    daily_report.md
    tickets/
      EDGE-YYYYMMDD-001.md
  configs/
    universe.yaml
    thresholds.yaml
```

---

## 付録：日次レポート（サンプル構成）
- 今日のレジーム：RiskOn / Neutral / RiskOff（根拠3点）
- 市場サマリ：ボラ、相関、ブレッドス、ディスパージョン
- セクター上位/下位（相対強度）
- 異常検知Top5
- 研究チケットTop3（仮説＋検証仕様）
- ウォッチリスト（スキャナーベース）
