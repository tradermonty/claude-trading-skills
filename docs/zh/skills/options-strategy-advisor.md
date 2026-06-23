---
layout: default
title: "Options Strategy Advisor"
grand_parent: 简体中文
parent: 技能指南
nav_order: 37
lang_peer: /en/skills/options-strategy-advisor/
permalink: /zh/skills/options-strategy-advisor/
generated: false
---

# Options Strategy Advisor
{: .no_toc }

期权交易策略分析与模拟工具。基于 Black-Scholes 模型提供理论定价、希腊字母(Greeks)计算、策略盈亏模拟和风险管理建议。当用户请求期权策略分析、备兑看涨(covered call)、保护性看跌(protective put)、价差(spread)、铁鹰式(iron condor)、财报行情交易,或期权风险管理时使用。包含波动率分析、仓位规模建议,以及基于财报事件的策略推荐。以教育为核心,并提供实战交易模拟。
{: .fs-6 .fw-300 }

<span class="badge badge-free">无需 API</span> <span class="badge badge-optional">FMP 可选</span>

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/options-strategy-advisor.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/options-strategy-advisor){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

本技能基于理论定价模型,提供全面的期权策略分析与教育内容。它帮助交易者在不需要订阅实时市场数据的情况下,理解、分析并模拟各类期权策略。

**核心能力:**
- **Black-Scholes 定价**:计算理论期权价格与希腊字母
- **策略模拟**:对主流期权策略进行盈亏分析
- **财报策略**:结合 Earnings Calendar 的财报前波动率交易
- **风险管理**:仓位规模、希腊字母敞口、最大亏损/盈利分析
- **教育导向**:对策略和风险指标进行详细讲解

**数据来源:**
- FMP API:股票价格、历史波动率、股息、财报日期
- 用户输入:隐含波动率(IV)、无风险利率
- 理论模型:用于定价和希腊字母计算的 Black-Scholes 模型

---

## 2. 使用时机

在以下情况下使用本技能:
- 用户询问期权策略("什么是备兑看涨?"、"铁鹰式策略如何运作?")
- 用户想模拟策略盈亏("我的牛市看涨价差最大盈利是多少?")
- 用户需要希腊字母分析("我的 Delta 敞口是多少?")
- 用户询问财报相关策略("财报前我该买入跨式组合(straddle)吗?")
- 用户想比较不同策略("备兑看涨 vs 保护性看跌?")
- 用户需要仓位规模建议("我应该交易多少份合约?")
- 用户询问波动率("现在的 IV 是不是偏高?")

示例请求:
- "分析一下 AAPL 的备兑看涨策略"
- "MSFT 上 100/105 的牛市看涨价差盈亏如何?"
- "NVDA 财报前我该交易跨式组合吗?"
- "计算我的铁鹰式仓位的希腊字母"
- "比较保护性看跌和备兑看涨在下行保护上的差异"

---

## 3. 前提条件

- **FMP API 密钥** 可选但推荐配置
- FMP 用于获取股票数据;Black-Scholes 计算本身无需 API 即可运行
- 推荐 Python 3.9+

---

## 4. 快速开始

```bash
# 计算 Black-Scholes 价格与希腊字母
python3 options-strategy-advisor/scripts/black_scholes.py \
  --ticker AAPL \
  --strike 150 \
  --days-to-expiry 30 \
  --option-type call

# 分析备兑看涨策略
python3 options-strategy-advisor/scripts/black_scholes.py \
  --ticker AAPL \
  --strategy covered_call \
  --stock-price 155
```

---

## 5. 工作流

### 步骤 1:收集输入数据

**需要用户提供:**
- 股票代码
- 策略类型
- 行权价
- 到期日
- 仓位规模(合约数量)

**用户可选提供:**
- 隐含波动率(IV)——若未提供,则使用历史波动率(HV)
- 无风险利率——默认使用当前 3 个月期国债利率(截至 2025 年约为 5.3%)

**从 FMP API 获取:**
- 当前股价
- 历史价格(用于计算 HV)
- 股息率
- 即将公布的财报日期(用于财报策略)

**用户输入示例:**
```
Ticker: AAPL
Strategy: Bull Call Spread
Long Strike: $180
Short Strike: $185
Expiration: 30 days
Contracts: 10
IV: 25% (or use HV if not provided)
```

### 步骤 2:计算历史波动率(若未提供 IV)

**目标:** 根据历史价格走势估算波动率。

**方法:**
```python
# Fetch 90 days of price data
prices = get_historical_prices("AAPL", days=90)

# Calculate daily returns
returns = np.log(prices / prices.shift(1))

# Annualized volatility
HV = returns.std() * np.sqrt(252)  # 252 trading days
```

**输出:**
- 历史波动率(年化百分比)
- 给用户的提示:"HV = 24.5%,若需更高精度建议使用当前市场 IV"

**用户可覆盖该值:**
- 提供来自券商平台(ThinkorSwim、TastyTrade 等)的 IV
- 脚本支持 `--iv 28.0` 参数

### 步骤 3:使用 Black-Scholes 模型定价期权

**Black-Scholes 模型:**

适用于欧式期权:
```
Call Price = S * N(d1) - K * e^(-r*T) * N(d2)
Put Price = K * e^(-r*T) * N(-d2) - S * N(-d1)

Where:
d1 = [ln(S/K) + (r + σ²/2) * T] / (σ * √T)
d2 = d1 - σ * √T

S = Current stock price
K = Strike price
r = Risk-free rate
T = Time to expiration (years)
σ = Volatility (IV or HV)
N() = Cumulative standard normal distribution
```

**调整项:**
- 计算 Call 时应从 S 中减去股息现值
- 美式期权:使用近似法,或注明"按欧式定价,可能低估美式期权价值"

**Python 实现:**
```python
from scipy.stats import norm
import numpy as np

def black_scholes_call(S, K, T, r, sigma, q=0):
    """
    S: Stock price
    K: Strike price
    T: Time to expiration (years)
    r: Risk-free rate
    sigma: Volatility
    q: Dividend yield
    """
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

**每个期权腿(leg)的输出:**
- 理论价格
- 提示:"由于买卖价差以及美式/欧式定价的差异,市场实际价格可能有所不同"

### 步骤 4:计算希腊字母

**希腊字母(Greeks)** 用于衡量期权价格对各类因素的敏感度:

**Delta(Δ):** 股价每变动 $1,期权价格的变动量
```python
def delta_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.cdf(d1)

def delta_put(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * (norm.cdf(d1) - 1)
```

**Gamma(Γ):** 股价每变动 $1,Delta 的变动量
```python
def gamma(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
```

**Theta(Θ):** 每日期权价格的变动量(时间损耗)
```python
def theta_call(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)

    theta = (-S*norm.pdf(d1)*sigma*np.exp(-q*T)/(2*np.sqrt(T))
             - r*K*np.exp(-r*T)*norm.cdf(d2)
             + q*S*norm.cdf(d1)*np.exp(-q*T))

    return theta / 365  # Per day
```

**Vega(ν):** 波动率每变动 1%,期权价格的变动量
```python
def vega(S, K, T, r, sigma, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return S * np.exp(-q*T) * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1%
```

**Rho(ρ):** 利率每变动 1%,期权价格的变动量
```python
def rho_call(S, K, T, r, sigma, q=0):
    d2 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T)) - sigma*np.sqrt(T)
    return K * T * np.exp(-r*T) * norm.cdf(d2) / 100  # Per 1%
```

**仓位整体希腊字母:**

对于多腿组合策略,将各腿的希腊字母相加:
```python
# Example: Bull Call Spread
# Long 1x $180 call
# Short 1x $185 call

delta_position = (1 * delta_long) + (-1 * delta_short)
gamma_position = (1 * gamma_long) + (-1 * gamma_short)
theta_position = (1 * theta_long) + (-1 * theta_short)
vega_position = (1 * vega_long) + (-1 * vega_short)
```

**希腊字母解读:**

| 希腊字母 | 含义 | 示例 |
|-------|---------|---------|
| **Delta** | 方向性敞口 | Δ = 0.50 → 股价 +$1 时盈利 $50 |
| **Gamma** | Delta 的加速度 | Γ = 0.05 → 股价 +$1 时 Delta 增加 0.05 |
| **Theta** | 每日时间损耗 | Θ = -$5 → 每天因时间流逝损失 $5 |
| **Vega** | 波动率敏感度 | ν = $10 → IV 上升 1% 时盈利 $10 |
| **Rho** | 利率敏感度 | ρ = $2 → 利率上升 1% 时盈利 $2 |

### 步骤 5:模拟策略盈亏

**目标:** 计算到期时在不同股价水平下的盈亏。

**方法:**

生成股价区间(例如当前价格的 ±30%):
```python
current_price = 180
price_range = np.linspace(current_price * 0.7, current_price * 1.3, 100)
```

针对每个价格点计算盈亏:
```python
def calculate_pnl(strategy, stock_price_at_expiration):
    pnl = 0

    for leg in strategy.legs:
        if leg.type == 'call':
            intrinsic_value = max(0, stock_price_at_expiration - leg.strike)
        else:  # put
            intrinsic_value = max(0, leg.strike - stock_price_at_expiration)

        if leg.position == 'long':
            pnl += (intrinsic_value - leg.premium_paid) * 100  # Per contract
        else:  # short
            pnl += (leg.premium_received - intrinsic_value) * 100

    return pnl * num_contracts
```

**关键指标:**
- **最大盈利**:可能的最高盈亏值
- **最大亏损**:可能的最差盈亏值
- **盈亏平衡点**:盈亏为 0 时的股价水平
- **盈利概率**:价格区间中处于盈利状态的占比(简化估算)

**输出示例:**
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

### 步骤 6:生成盈亏图(ASCII 图)

**以图形方式展示不同股价下的盈亏分布:**

```python
def generate_pnl_diagram(price_range, pnl_values, current_price, width=60, height=15):
    """Generate ASCII P/L diagram"""

    # Normalize to chart dimensions
    max_pnl = max(pnl_values)
    min_pnl = min(pnl_values)

    lines = []
    lines.append(f"\nP/L Diagram: {strategy_name}")
    lines.append("-" * width)

    # Y-axis levels
    levels = np.linspace(max_pnl, min_pnl, height)

    for level in levels:
        if abs(level) < (max_pnl - min_pnl) * 0.05:
            label = f"    0 |"  # Zero line
        else:
            label = f"{level:6.0f} |"

        row = label
        for i in range(width - len(label)):
            idx = int(i / (width - len(label)) * len(price_range))
            pnl = pnl_values[idx]
            price = price_range[idx]

            # Determine character
            if abs(pnl - level) < (max_pnl - min_pnl) / height:
                if pnl > 0:
                    char = '█'  # Profit
                elif pnl < 0:
                    char = '░'  # Loss
                else:
                    char = '─'  # Breakeven
            elif abs(level) < (max_pnl - min_pnl) * 0.05:
                char = '─'  # Zero line
            elif abs(price - current_price) < (price_range[-1] - price_range[0]) * 0.02:
                char = '│'  # Current price line
            else:
                char = ' '

            row += char

        lines.append(row)

    lines.append(" " * 6 + "|" + "-" * (width - 6))
    lines.append(" " * 6 + f"${price_range[0]:.0f}" + " " * (width - 20) + f"${price_range[-1]:.0f}")
    lines.append(" " * (width // 2 - 5) + "Stock Price")

    return "\n".join(lines)
```

**输出示例:**
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

### 步骤 7:策略专项分析

根据策略类型提供针对性指导:

**备兑看涨(Covered Call):**
```
Income Strategy: Generate premium while capping upside

Setup:
- Own 100 shares of AAPL @ $180
- Sell 1x $185 call (30 DTE) for $3.50

Max Profit: $850 (Stock at $185+ = $5 stock gain + $3.50 premium)
Max Loss: Unlimited downside (stock ownership)
Breakeven: $176.50 (Cost basis - premium received)

Greeks:
- Delta: -0.30 (reduces stock delta from 1.00 to 0.70)
- Theta: +$8/day (time decay benefit)

Assignment Risk: If AAPL > $185 at expiration, shares called away

When to Use:
- Neutral to slightly bullish
- Want income in sideways market
- Willing to sell stock at $185

Exit Plan:
- Buy back call if stock rallies strongly (preserve upside)
- Let expire if stock stays below $185
- Roll to next month if want to keep shares
```

**保护性看跌(Protective Put):**
```
Insurance Strategy: Limit downside while keeping upside

Setup:
- Own 100 shares of AAPL @ $180
- Buy 1x $175 put (30 DTE) for $2.00

Max Profit: Unlimited (stock can rise infinitely)
Max Loss: -$7 per share = ($5 stock loss + $2 premium)
Breakeven: $182 (Cost basis + premium paid)

Greeks:
- Delta: +0.80 (stock delta 1.00 - put delta 0.20)
- Theta: -$6/day (time decay cost)

Protection: Guaranteed to sell at $175, no matter how far stock falls

When to Use:
- Own stock, worried about short-term drop
- Earnings coming up, want protection
- Alternative to stop-loss (can't be stopped out)

Cost: "Insurance premium" - typically 1-3% of stock value

Exit Plan:
- Let expire worthless if stock rises (cost of insurance)
- Exercise put if stock falls below $175
- Sell put if stock drops but want to keep shares
```

**铁鹰式(Iron Condor):**
```
Range-Bound Strategy: Profit from low volatility

Setup (example on AAPL @ $180):
- Sell $175 put for $1.50
- Buy $170 put for $0.50
- Sell $185 call for $1.50
- Buy $190 call for $0.50

Net Credit: $2.00 ($200 per iron condor)

Max Profit: $200 (if stock stays between $175-$185)
Max Loss: $300 (if stock moves outside $170-$190)
Breakevens: $173 and $187
Profit Range: $175 to $185 (58% probability)

Greeks:
- Delta: ~0 (market neutral)
- Theta: +$15/day (time decay benefit)
- Vega: -$25 (short volatility)

When to Use:
- Expect low volatility, range-bound movement
- After big move, think consolidation
- High IV environment (sell expensive options)

Risk: Unlimited if one side tested
- Use stop loss at 2x credit received (exit at -$400)

Adjustments:
- If tested on one side, roll that side out in time
- Close early at 50% max profit to reduce tail risk
```

### 步骤 8:财报策略分析

**与 Earnings Calendar 集成:**

当用户询问财报策略时,获取财报日期:
```python
from earnings_calendar import get_next_earnings_date

earnings_date = get_next_earnings_date("AAPL")
days_to_earnings = (earnings_date - today).days
```

**财报前策略:**

**多头跨式 / 宽跨式组合(Long Straddle/Strangle):**
```
Setup (AAPL @ $180, earnings in 7 days):
- Buy $180 call for $5.00
- Buy $180 put for $4.50
- Total Cost: $9.50

Thesis: Expect big move (>5%) but unsure of direction

Breakevens: $170.50 and $189.50
Profit if: Stock moves >$9.50 in either direction

Greeks:
- Delta: ~0 (neutral)
- Vega: +$50 (long volatility)
- Theta: -$25/day (time decay hurts)

IV Crush Risk: ⚠️ CRITICAL
- Pre-earnings IV: 40% (elevated)
- Post-earnings IV: 25% (typical)
- IV drop: -15 points = -$750 loss even if stock doesn't move!

Analysis:
- Implied Move: √(DTE/365) × IV × Stock Price
  = √(7/365) × 0.40 × 180 = ±$10.50
- Breakeven Move Needed: ±$9.50
- Probability Profit: ~30-40% (implied move > breakeven move)

Recommendation:
✅ Consider if you expect >10% move (larger than implied)
❌ Avoid if expect normal ~5% earnings move (IV crush will hurt)

Alternative: Buy further OTM strikes to reduce cost
- $175/$185 strangle cost $4.00 (need >$8 move, but cheaper)
```

**空头铁鹰式(Short Iron Condor):**
```
Setup (AAPL @ $180, earnings in 7 days):
- Sell $170/$175 put spread for $2.00
- Sell $185/$190 call spread for $2.00
- Net Credit: $4.00

Thesis: Expect stock to stay range-bound ($175-$185)

Profit Zone: $175 to $185
Max Profit: $400
Max Loss: $100

IV Crush Benefit: ✅
- Short high IV before earnings
- IV drops after earnings → profit on vega
- Even if stock moves slightly, IV drop helps

Greeks:
- Delta: ~0 (market neutral)
- Vega: -$40 (short volatility - good here!)
- Theta: +$20/day

Recommendation:
✅ Good if expect normal earnings reaction (<8% move)
✅ Benefit from IV crush regardless of direction
⚠️ Risk if stock gaps outside range (>10% move)

Exit Plan:
- Close next day if IV crushed (capture profit early)
- Use stop loss if one side tested (-2x credit)
```

### 步骤 9:风险管理指导

**仓位规模:**

```
Account Size: $50,000
Risk Tolerance: 2% per trade = $1,000 max risk

Iron Condor Example:
- Max loss per spread: $300
- Max contracts: $1,000 / $300 = 3 contracts
- Actual position: 3 iron condors

Bull Call Spread Example:
- Debit paid: $2.50 per spread
- Max contracts: $1,000 / $250 = 4 contracts
- Actual position: 4 spreads
```

**组合希腊字母管理:**

```
Portfolio Guidelines:
- Delta: -10 to +10 (mostly neutral)
- Theta: Positive preferred (seller advantage)
- Vega: Monitor if >$500 (IV risk)

Current Portfolio:
- Delta: +5 (slightly bullish)
- Theta: +$150/day (collecting $150 daily)
- Vega: -$300 (short volatility)

Interpretation:
✅ Neutral delta (safe)
✅ Positive theta (time working for you)
⚠️ Short vega: If IV spikes, lose $300 per 1% IV increase
→ Reduce short premium positions if VIX rising
```

**调整与离场:**

```
Exit Rules by Strategy:

Covered Call:
- Profit: 50-75% of max profit
- Loss: Stock drops >5%, buy back call to preserve upside
- Time: 7-10 DTE, roll to avoid assignment

Spreads:
- Profit: 50% of max profit (close early, reduce tail risk)
- Loss: 2x debit paid (cut losses early)
- Time: 21 DTE, close or roll (avoid gamma risk)

Iron Condor:
- Profit: 50% of credit (close early common)
- Loss: One side tested, 2x credit lost
- Adjustment: Roll tested side out in time

Straddle/Strangle:
- Profit: Stock moved >breakeven, close immediately
- Loss: Theta eating position, stock not moving
- Time: Day after earnings (if earnings play)
```

---

## 6. 资源

**脚本(Scripts):**

- `skills/options-strategy-advisor/scripts/black_scholes.py`
