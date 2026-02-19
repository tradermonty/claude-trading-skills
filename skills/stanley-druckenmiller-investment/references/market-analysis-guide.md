# ドラッケンミラー流市場分析ガイド

## マクロ経済分析フレームワーク

### 1. 中央銀行政策の評価

#### 分析ポイント
- **金利政策の方向性**: 緩和・中立・引き締めのサイクル位置
- **流動性の変化**: マネーサプライ、QE/QTの動向
- **政策の持続可能性**: 行き過ぎた政策の兆候を探る
- **市場期待との乖離**: 中銀の意図と市場の理解のギャップ

#### 警戒すべき政策ミスのサイン
- 長期間の極端な低金利維持
- インフレ圧力を無視した緩和継続
- 急激すぎる政策転換
- 市場との対話の失敗

### 2. 18か月先の未来予測

#### 予測の構成要素
1. **経済サイクルの位置**
   - 拡大初期・中期・後期・減速・後退のどの段階か
   - 次の転換点はいつ頃か

2. **政策サイクルとの関係**
   - 金融政策は経済に対して先行的か後追いか
   - 財政政策の影響度

3. **市場期待の織り込み度**
   - コンセンサス予想は楽観的か悲観的か
   - サプライズの可能性はどこにあるか

### 3. グローバル資産配分の決定

#### 資産クラス別評価基準

**株式**
- 流動性環境（緩和的か引き締め的か）
- 企業収益の方向性（改善か悪化か）
- バリュエーション（割高か割安か）
- センチメント（楽観か悲観か）

**債券**
- 金利の方向性予測
- イールドカーブの形状
- クレジットスプレッドの動向
- インフレ期待

**通貨**
- 金利差の動向
- 経常収支の状況
- 政治的安定性
- 資本フローの方向

**コモディティ**
- 需給バランス
- ドルの強弱
- インフレ/デフレ圧力
- 地政学リスク

## From Data to Decision (シグナル→アクション変換)

The Strategy Synthesizer uses the following rules to convert multi-skill signals into actionable decisions. See `references/conviction_matrix.md` for the full cross-reference tables.

### Green Light Conditions (Aggressive Posture)
- Breadth composite >= 60 **AND** Uptrend zone = Bull/Strong Bull
- Market Top score < 40 (low distribution risk)
- Macro Regime = broadening **AND** confidence = high
- FTD state = FTD_CONFIRMED (if applicable)
- **Action:** 80-100% equity, concentrated positions, standard stops

### Yellow Light Conditions (Cautious Posture)
- Breadth composite 40-59 **OR** Uptrend zone = Neutral
- Market Top score 40-60 (moderate risk)
- Macro Regime = transitional
- Mixed signal convergence (convergence score 40-60)
- **Action:** 50-70% equity, reduced sizing, tighter stops

### Red Light Conditions (Defensive Posture)
- Breadth composite < 40 **OR** Uptrend zone = Bear
- Market Top score >= 60 (elevated/high risk)
- Macro Regime = contraction
- FTD state = RALLY_FAILED
- **Action:** 0-30% equity, high cash, no new entries

### Pattern-Specific Overrides
- **Policy Pivot detected:** Overweight bonds + equity even if signals are mixed (anticipate regime shift)
- **Unsustainable Distortion detected:** Override green light → reduce to yellow light minimum
- **Extreme Contrarian detected:** Override red light → allow pilot equity entries (FTD confirmation)

---

## ポジション構築の実践

### 確信度の評価基準

#### 高確信度（大きく張る）の条件
1. **複数の要因が同じ方向を示す**（"ダックが列を成す"）
2. **市場のコンセンサスと大きく乖離**
3. **リスク・リワードが非常に有利**
4. **明確な触媒（カタリスト）が存在**

#### 低確信度（様子見）のサイン
- 相反するシグナルが混在
- 不確実性が極めて高い
- リスク・リワードが不明確
- タイミングが読めない

### エントリーとエグジットの判断

#### エントリー条件
1. **テクニカル確認**: トレンドの初期段階を確認
2. **ファンダメンタルズ**: 投資テーマが明確
3. **センチメント**: 過度な楽観・悲観の存在
4. **リスク管理**: 最大損失が許容範囲内

#### エグジット条件
- **投資理由の消失**: 当初のシナリオが崩れた
- **目標達成**: 想定した利益に到達
- **より良い機会**: 他により魅力的な投資機会が出現
- **リスク環境の変化**: 市場環境が大きく変化

## 危機対応プロトコル

### ベアマーケット突入の兆候

1. **金融政策の転換点**
   - 緩和から引き締めへの明確な転換
   - 流動性の急速な収縮

2. **信用市場のストレス**
   - クレジットスプレッドの急拡大
   - 銀行間市場の機能不全

3. **センチメントの極端な楽観**
   - 全員が強気
   - リスクの過小評価
   - レバレッジの過剰利用

### 危機時の行動指針

1. **即座の防御態勢**
   - リスク資産の削減
   - レバレッジの解消
   - 流動性の確保

2. **安全資産へのシフト**
   - 長期国債
   - 金
   - 安全通貨（円、スイスフラン等）

3. **逆張り機会の探索**
   - 過度な売りによる歪み
   - 質への逃避による優良資産の割安化
   - 政策対応による転換点

## 日常的なモニタリング項目

### 毎日チェックすべき指標
- 主要国の金利動向
- 株式市場の内部構造（上昇/下落銘柄数等）
- 通貨市場の動き
- VIX等のボラティリティ指標
- クレジット市場の動向

### 週次・月次でレビューすべき項目
- 経済指標の予想と実績の乖離
- 中央銀行高官の発言トーン
- 資金フローデータ
- ポジショニングデータ
- センチメント指標

### 四半期ごとの大局観チェック
- 投資テーマの妥当性確認
- 18か月先予測の修正
- ポートフォリオ全体のリスク評価
- 新たな投資機会の発掘
