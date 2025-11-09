## Summary

このPRは、トレーディングスキルセットに2つの新しい高度なスキルを追加します：

1. **Options Strategy Advisor** - Black-Scholesモデルを使用したオプション戦略分析
2. **Pair Trade Screener** - 統計的裁定取引のためのペアトレードスクリーナー
3. **FMP API Research Report** - Institutional Flow Tracker用のAPI調査レポート

---

## 🎯 Options Strategy Advisor

### 概要
Black-Scholesモデルを使用して、17種類以上のオプション戦略の理論価格とリスク指標を計算・分析するスキルです。リアルタイムのオプションチェーンデータを必要とせず、FMP APIの無料プラン（250リクエスト/日）のみで動作します。

### 主な機能

**対応戦略（17+種類）:**
- **収益戦略**: Covered Call, Cash-Secured Put, Poor Man's Covered Call
- **保護戦略**: Protective Put, Collar
- **方向性戦略**: Bull Call Spread, Bear Call Spread, Bull Put Spread, Bear Put Spread
- **ボラティリティ戦略**: Long Straddle, Short Straddle, Long Strangle, Short Strangle
- **レンジ戦略**: Iron Condor, Iron Butterfly
- **高度な戦略**: Calendar Spread, Diagonal Spread

**Black-Scholes価格計算エンジン:**
- ヨーロピアン型コール・プットオプションの理論価格計算
- すべてのギリシャ指標の計算:
  - **Delta (Δ)**: 株価変動に対するオプション価格の感応度
  - **Gamma (Γ)**: Deltaの変化率
  - **Theta (Θ)**: 時間減衰（1日あたりの価値減少）
  - **Vega (ν)**: ボラティリティ変動に対する感応度
  - **Rho (ρ)**: 金利変動に対する感応度
- ヒストリカル・ボラティリティ（HV）計算
- 本質的価値・時間価値の分析
- FMP APIからの株価・配当データ取得

**ワークフロー:**
1. ティッカー、行使価格、満期日、ボラティリティの収集
2. HV計算（IVが提供されない場合）
3. Black-Scholesでオプション価格計算
4. 全ギリシャ指標の計算
5. P/Lシミュレーション（株価範囲全体）
6. ASCII P/L図の生成
7. 戦略固有の分析とリスク評価
8. アーニングス戦略の統合
9. リスク管理ガイダンス

### 技術仕様

**ファイル構成:**
```
options-strategy-advisor/
├── SKILL.md                      # スキル定義（650+ 行）
├── scripts/
│   └── black_scholes.py          # 価格計算エンジン（496 行）
└── README.md                     # 使用ガイド（470 行）
```

**主要クラス（black_scholes.py）:**
```python
class OptionPricer:
    def __init__(self, S, K, T, r, sigma, q=0):
        # S: 株価, K: 行使価格, T: 満期までの年数
        # r: リスクフリーレート, sigma: ボラティリティ, q: 配当利回り

    def call_price(self) -> float
    def put_price(self) -> float
    def call_delta(self) -> float
    def put_delta(self) -> float
    def gamma(self) -> float
    def theta(self, option_type: str) -> float
    def vega(self) -> float
    def rho(self, option_type: str) -> float
```

**ユーティリティ関数:**
- `calculate_historical_volatility(prices, window=30)` - HV計算（年率換算）
- `fetch_historical_prices_for_hv(symbol, api_key, days=90)` - FMP APIから価格取得

### 利点

✅ **コスト効率**: FMP APIの無料プラン（250リクエスト/日）で十分
✅ **教育的**: 戦略の仕組みとリスク指標の理解に最適
✅ **実用的**: ブローカーから実際のIVを入力可能
✅ **統合性**: Earnings Calendar、Technical Analyst、Portfolio Managerと連携
✅ **理論的正確性**: Black-Scholes公式による正確な計算

### 制限事項

- アメリカン型オプションには対応していません（ヨーロピアン型のみ）
- リアルタイムのビッド/アスクスプレッドは含まれません
- 実際のIVの代わりにHVを使用（ユーザーが実IV入力可能）
- 配当は一定利回りとして扱います

---

## 📊 Pair Trade Screener

### 概要
統計的裁定取引のためのペアトレードスクリーナー。共和分検定を使用して、長期的な均衡関係にある株式ペアを発見し、平均回帰の機会を特定します。

### 主な機能

**統計的分析:**
- 相関分析（最小相関係数: 0.70）
- 共和分検定（ADF検定）
- ヘッジ比率計算（OLS回帰によるベータ）
- 半減期推定（平均回帰速度）
- Zスコアフレームワーク（エントリー: ±2.0σ、エグジット: 0）

**スクリプト:**
- `find_pairs.py` (578行) - セクター内ペア自動検出
- `analyze_spread.py` (450行) - 個別ペア分析とシグナル生成

**リファレンス:**
- `methodology.md` (62ページ) - 統計的裁定取引理論ガイド
- `cointegration_guide.md` (54ページ) - 共和分検定ガイド

### 使用例
```bash
# セクター内ペア検出
python3 find_pairs.py --sector Technology --min-correlation 0.70

# 個別ペア分析
python3 analyze_spread.py --symbol-a AAPL --symbol-b MSFT
```

---

## 📄 FMP API Research Report

Institutional Flow Tracker スキルの実装可能性を調査した詳細なレポート（832行）。FMP APIの機能、制限事項、代替案を文書化しています。

**主な発見:**
- 13Fデータ利用可能（Ultimate $149/月）
- インサイダー取引データ利用可能（Starter $14/月）
- ブロック取引データは利用不可

---

## 🧪 テストプラン

- [x] Options Strategy Advisor SKILL.md の構文確認
- [x] black_scholes.py の実行可能性確認
- [x] ギリシャ指標計算の正確性確認（理論値との照合）
- [x] HV計算の正確性確認
- [x] FMP API統合のテスト（株価・配当データ取得）
- [x] README の完全性確認
- [x] Pair Trade Screener の統計的手法の妥当性確認
- [x] 共和分検定の実装確認
- [ ] 実際のトレーディング環境での統合テスト
- [ ] 他スキル（Earnings Calendar、Technical Analyst）との統合テスト

---

## 📚 ドキュメント

すべてのスキルに包括的なドキュメントが含まれています：
- SKILL.md: 完全なワークフロー定義
- README.md: インストール、使用方法、例、ベストプラクティス
- references/: 理論的背景と手法ガイド（Pair Trade Screener）

---

## 🔧 API要件

- **FMP API**: 無料プラン（250リクエスト/日）で両スキルとも動作
- **FINVIZ Elite**: 不要（他のスキルでは任意）

---

## 📦 ファイル変更

**新規ファイル:**
- `options-strategy-advisor/SKILL.md` (650+ 行)
- `options-strategy-advisor/scripts/black_scholes.py` (496 行)
- `options-strategy-advisor/README.md` (470 行)
- `pair-trade-screener/SKILL.md` (完全なワークフロー)
- `pair-trade-screener/scripts/find_pairs.py` (578 行)
- `pair-trade-screener/scripts/analyze_spread.py` (450 行)
- `pair-trade-screener/references/methodology.md` (62 ページ)
- `pair-trade-screener/references/cointegration_guide.md` (54 ページ)
- `pair-trade-screener/README.md`
- `FMP_Institutional_Data_Research_2025-11-08.md` (832 行)

**合計:** 3つの新しいスキル、1つのリサーチレポート、3,900+ 行のコード・ドキュメント
