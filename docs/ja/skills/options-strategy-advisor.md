---
layout: default
title: "Options Strategy Advisor"
grand_parent: 日本語
parent: スキルガイド
nav_order: 32
lang_peer: /en/skills/options-strategy-advisor/
permalink: /ja/skills/options-strategy-advisor/
---

# Options Strategy Advisor
{: .no_toc }

オプション取引戦略の分析・シミュレーションツールです。ブラック-ショールズモデルによる理論価格算出、グリークス計算、戦略P/Lシミュレーション、リスク管理ガイダンスを提供します。オプション戦略分析、カバードコール、プロテクティブプット、スプレッド、アイアンコンドル、決算プレー、またはオプションリスク管理を求められた際に使用します。ボラティリティ分析、ポジションサイジング、決算ベースの戦略推奨を含みます。教育的アプローチと実践的なトレードシミュレーションを重視します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span> <span class="badge badge-optional">FMP任意</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/options-strategy-advisor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/options-strategy-advisor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

このスキルは、理論的な価格モデルを使用した包括的なオプション戦略分析と教育を提供します。リアルタイム市場データのサブスクリプションなしで、トレーダーがオプション戦略を理解、分析、シミュレーションするのを支援します。

**コア機能:**
- **ブラック-ショールズ価格算出**: 理論的なオプション価格とグリークス計算
- **戦略シミュレーション**: 主要なオプション戦略のP/L分析
- **決算戦略**: 決算前のボラティリティプレーをEarnings Calendarと統合
- **リスク管理**: ポジションサイジング、グリークスエクスポージャー、最大損失/利益分析
- **教育的フォーカス**: 戦略とリスク指標の詳細な説明

**データソース:**
- FMP API: 株価、ヒストリカルボラティリティ、配当、決算日
- ユーザー入力: インプライドボラティリティ（IV）、リスクフリーレート
- 理論モデル: 価格算出とグリークスにブラック-ショールズを使用

---

## 2. 使用タイミング

以下の場合にこのスキルを使用します:
- オプション戦略についての質問（「カバードコールとは？」「アイアンコンドルはどう動く？」）
- 戦略P/Lのシミュレーション（「ブルコールスプレッドの最大利益は？」）
- グリークス分析（「デルタエクスポージャーは？」）
- 決算戦略（「決算前にストラドルを買うべき？」）
- 戦略の比較（「カバードコール vs プロテクティブプット？」）
- ポジションサイジングのガイダンス（「何枚コントラクトを取引すべき？」）
- ボラティリティについての質問（「IVは今高い？」）

リクエスト例:
- "AAPLのカバードコールを分析して"
- "MSFTの$100/$105ブルコールスプレッドのP/Lは？"
- "NVDA決算前にストラドルを取引すべき？"
- "アイアンコンドルポジションのグリークスを計算して"
- "ダウンサイドプロテクションでプロテクティブプット vs カバードコールを比較して"

---

## 3. 前提条件

- **FMP APIキー** 任意だが推奨
- FMPは株価データ用; ブラック-ショールズはFMPなしでも動作
- Python 3.9+ 推奨

---

## 4. クイックスタート

```bash
# 組み込みのブラック-ショールズ計算例を実行
python3 skills/options-strategy-advisor/scripts/black_scholes.py
```

このスクリプトは組み込みの計算例を実行し、価格計算や戦略のCLI引数を解釈しません。独自の入力には Python の `OptionPricer` API を使用してください。必要な入力は以下のワークフローで確認できます。

---

## 5. ワークフロー

### ステップ1: 入力データの収集

**ユーザーからの必須情報:**
- ティッカーシンボル
- 戦略タイプ
- ストライク価格
- 満期日
- ポジションサイズ（コントラクト数）

**ユーザーからの任意情報:**
- インプライドボラティリティ（IV） - 提供されない場合、ヒストリカルボラティリティ（HV）を使用
- リスクフリーレート - デフォルトは現在の3ヶ月T-billレート（2025年時点で約5.3%）

**FMP APIから取得:**
- 現在の株価
- 過去の株価（HV計算用）
- 配当利回り
- 次の決算日（決算戦略用）

**ユーザー入力の例:**
```
Ticker: AAPL
Strategy: Bull Call Spread
Long Strike: $180
Short Strike: $185
Expiration: 30 days
Contracts: 10
IV: 25% (or use HV if not provided)
```

### ステップ2: ヒストリカルボラティリティの計算（IVが未提供の場合）

**目的:** 過去の価格変動からボラティリティを推定。

**方法:**
```python
# 90日分の価格データを取得
prices = get_historical_prices("AAPL", days=90)

# 日次リターンを計算
returns = np.log(prices / prices.shift(1))

# 年率換算ボラティリティ
HV = returns.std() * np.sqrt(252)  # 252取引日
```

**出力:**
- ヒストリカルボラティリティ（年率換算パーセンテージ）
- ユーザーへの注記: "HV = 24.5%, より正確にはブローカーの現在のIVを使用してください"

**ユーザーによるオーバーライド:**
- ブローカープラットフォーム（ThinkorSwim、TastyTradeなど）からIVを提供
- スクリプトは `--iv 28.0` パラメータを受け付け

### ステップ3: ブラック-ショールズモデルによるオプション価格算出

**ブラック-ショールズモデル:**

ヨーロピアンスタイルオプションの場合:
```
Call Price = S * N(d1) - K * e^(-r*T) * N(d2)
Put Price = K * e^(-r*T) * N(-d2) - S * N(-d1)

ここで:
d1 = [ln(S/K) + (r + σ²/2) * T] / (σ * √T)
d2 = d1 - σ * √T

S = 現在の株価
K = ストライク価格
r = リスクフリーレート
T = 満期までの時間（年）
σ = ボラティリティ（IVまたはHV）
N() = 累積標準正規分布
```

**調整事項:**
- コールの場合、Sから配当の現在価値を差し引く
- アメリカンオプション: 近似を使用するか「ヨーロピアン価格、アメリカンオプションを過小評価する可能性あり」と注記

**Python実装:**
```python
from scipy.stats import norm
import numpy as np

def black_scholes_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    call_price = S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    return call_price

def black_scholes_put(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    put_price = K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)
    return put_price
```

**各オプションレッグの出力:**
- 理論価格
- 注記: "ビッド-アスクスプレッドやアメリカン vs ヨーロピアンの価格差により市場価格と異なる場合があります"

### ステップ4: グリークスの計算

**グリークス**はオプション価格の各種要因に対する感応度を測定します:

**デルタ (Δ):** 株価$1変動あたりのオプション価格変動
```python
def delta_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.cdf(d1)

def delta_put(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * (norm.cdf(d1) - 1)
```

**ガンマ (Γ):** 株価$1変動あたりのデルタ変動
```python
def gamma(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
```

**セータ (Θ):** 1日あたりのオプション価格変動（時間的減衰）
```python
def theta_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    theta = (-S*norm.pdf(d1)*sigma*np.exp(-q*T)/(2*np.sqrt(T))
             - r*K*np.exp(-r*T)*norm.cdf(d2)
             + q*S*norm.cdf(d1)*np.exp(-q*T))
    return theta / 365  # 1日あたり
```

**ベガ (ν):** ボラティリティ1%変動あたりのオプション価格変動
```python
def vega(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return S * np.exp(-q*T) * norm.pdf(d1) * np.sqrt(T) / 100  # 1%あたり
```

**ロー (ρ):** 金利1%変動あたりのオプション価格変動
```python
def rho_call(S, K, T, r, sigma, q=0):
    d2 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T)) - sigma*np.sqrt(T)
    return K * T * np.exp(-r*T) * norm.cdf(d2) / 100  # 1%あたり
```

**ポジショングリークス:**

複数レッグの戦略では、全レッグのグリークスを合計:
```python
# 例: ブルコールスプレッド
# ロング 1x $180 コール
# ショート 1x $185 コール

delta_position = (1 * delta_long) + (-1 * delta_short)
gamma_position = (1 * gamma_long) + (-1 * gamma_short)
theta_position = (1 * theta_long) + (-1 * theta_short)
vega_position = (1 * vega_long) + (-1 * vega_short)
```

**グリークスの解釈:**

| グリーク | 意味 | 例 |
|---------|------|-----|
| **デルタ** | 方向性エクスポージャー | Δ = 0.50 → 株価+$1で$50の利益 |
| **ガンマ** | デルタの加速度 | Γ = 0.05 → 株価+$1でデルタが0.05増加 |
| **セータ** | 日次時間的減衰 | Θ = -$5 → 時間経過で1日$5の損失 |
| **ベガ** | ボラティリティ感応度 | ν = $10 → IV 1%上昇で$10の利益 |
| **ロー** | 金利感応度 | ρ = $2 → 金利1%上昇で$2の利益 |

### ステップ5: 戦略P/Lのシミュレーション

**目的:** 満期時の各株価でのP/Lを計算。

**方法:**

株価範囲を生成（例: 現在価格の±30%）:
```python
current_price = 180
price_range = np.linspace(current_price * 0.7, current_price * 1.3, 100)
```

各価格ポイントでP/Lを計算:
```python
def calculate_pnl(strategy, stock_price_at_expiration):
    pnl = 0
    for leg in strategy.legs:
        if leg.type == 'call':
            intrinsic_value = max(0, stock_price_at_expiration - leg.strike)
        else:  # put
            intrinsic_value = max(0, leg.strike - stock_price_at_expiration)
        if leg.position == 'long':
            pnl += (intrinsic_value - leg.premium_paid) * 100
        else:  # short
            pnl += (leg.premium_received - intrinsic_value) * 100
    return pnl * num_contracts
```

**主要指標:**
- **最大利益**: 最高のP/L
- **最大損失**: 最悪のP/L
- **損益分岐点**: P/L = 0 の株価
- **利益確率**: 利益が出る価格範囲の割合（簡易計算）

**出力例:**
```
Bull Call Spread: $180/$185 on AAPL (30 DTE, 10 contracts)

Current Price: $180.00
Net Debit: $2.50 per spread ($2,500 total)

Max Profit: $2,500 (at $185+)
Max Loss: -$2,500 (at $180-)
Breakeven: $182.50
Risk/Reward: 1:1

Probability Profit: ~55% (if stock stays above $182.50)
```

### ステップ6: P/Lダイアグラムの生成（ASCIIアート）

**各株価でのP/Lの視覚的表現:**

```
P/L Diagram: Bull Call Spread $180/$185
------------------------------------------------------------
 +2500 |                               ████████████████████
       |                         ██████
       |                   ██████
       |             ██████
     0 |       ──────
       | ░░░░░░
       |░░░░░░
 -2500 |░░░░░
      |____________________________________________________________
       $126                  $180                   $234
                          Stock Price

Legend: █ Profit  ░ Loss  ── Breakeven  │ Current Price
```

### ステップ7: 戦略別の分析

戦略タイプに応じたガイダンスを提供:

**カバードコール:**
```
インカム戦略: プレミアムを獲得しつつアップサイドをキャップ

セットアップ:
- AAPL 100株を$180で保有
- $185コールを1枚売り（30 DTE）で$3.50のプレミアム

最大利益: $850 ($185以上 = $5の株価利益 + $3.50のプレミアム)
最大損失: 無制限の下落リスク（株式保有）
損益分岐: $176.50 (取得コスト - 受取プレミアム)
```

**プロテクティブプット:**
```
保険戦略: アップサイドを維持しつつダウンサイドを制限

セットアップ:
- AAPL 100株を$180で保有
- $175プットを1枚買い（30 DTE）で$2.00

最大利益: 無制限（株価は無限に上昇可能）
最大損失: -$7/株 = ($5の株価損失 + $2のプレミアム)
損益分岐: $182 (取得コスト + 支払プレミアム)
```

**アイアンコンドル:**
```
レンジバウンド戦略: 低ボラティリティから利益を得る

セットアップ (AAPL @ $180):
- $175プットを売り $1.50
- $170プットを買い $0.50
- $185コールを売り $1.50
- $190コールを買い $0.50

ネットクレジット: $2.00 ($200/アイアンコンドル)

最大利益: $200 (株価が$175-$185に留まる場合)
最大損失: $300 (株価が$170-$190の外に出る場合)
損益分岐: $173 と $187
```

### ステップ8: 決算戦略分析

**Earnings Calendarとの統合:**

ユーザーが決算戦略について質問した場合、決算日を取得:
```python
from earnings_calendar import get_next_earnings_date
earnings_date = get_next_earnings_date("AAPL")
days_to_earnings = (earnings_date - today).days
```

**決算前戦略:**

**ロングストラドル/ストラングル:**
- テーゼ: 大きな値動き（>5%）を期待するが方向は不明
- IVクラッシュリスク: 決算後のIV低下で、株価が動かなくても損失の可能性

**ショートアイアンコンドル:**
- テーゼ: 株価がレンジ内に留まることを期待
- IVクラッシュのメリット: 高IVで売り、決算後にIV低下で利益

### ステップ9: リスク管理ガイダンス

**ポジションサイジング:**
```
口座サイズ: $50,000
リスク許容度: トレードあたり2% = 最大$1,000リスク

アイアンコンドルの例:
- スプレッドあたり最大損失: $300
- 最大コントラクト: $1,000 / $300 = 3コントラクト

ブルコールスプレッドの例:
- 支払デビット: $2.50/スプレッド
- 最大コントラクト: $1,000 / $250 = 4コントラクト
```

**ポートフォリオグリークス管理:**
```
ポートフォリオガイドライン:
- デルタ: -10 〜 +10（概ねニュートラル）
- セータ: プラスが望ましい（売り手の優位性）
- ベガ: >$500ならモニタリング（IVリスク）
```

**調整と出口:**
```
戦略別出口ルール:

カバードコール:
- 利益: 最大利益の50-75%
- 損失: 株価が>5%下落したらコールを買い戻し
- 時間: 7-10 DTE、アサインメント回避でロール

スプレッド:
- 利益: 最大利益の50%（早期クローズでテールリスク低減）
- 損失: 支払デビットの2倍（早期損切り）

アイアンコンドル:
- 利益: クレジットの50%（早期クローズが一般的）
- 損失: 一方がテストされ、クレジットの2倍の損失
- 調整: テストされた側を時間方向にロール
```

---

## 6. リソース

**スクリプト:**

- `skills/options-strategy-advisor/scripts/black_scholes.py`
