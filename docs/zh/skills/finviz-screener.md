---
layout: default
title: "Finviz Screener"
grand_parent: 简体中文
parent: 技能指南
nav_order: 1
lang_peer: /en/skills/finviz-screener/
permalink: /zh/skills/finviz-screener/
generated: false
---

# FinViz Screener
{: .no_toc }

把自然语言的选股请求转换为 FinViz 筛选器过滤 URL,并在 Chrome 中打开。支持中文与英文输入。
{: .fs-6 .fw-300 }

[下载技能包 (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/finviz-screener.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 查看源码](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/finviz-screener){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概述

FinViz Screener 弥合“你想找什么”与“FinViz 期望的过滤代码”之间的鸿沟。你无需记住 `fa_epsqoq_o25` 或 `ta_sma200_pa` 这类代码,只需用平实的中文(或英文)描述条件,Claude 就为你构建 URL。

**它解决什么:**
- 免去学习 500+ 个 FinViz 过滤代码
- 处理双语输入(中文与英文)
- 从环境变量自动检测 FINVIZ Elite
- 校验所有过滤令牌以防 URL 注入
- 直接在 Chrome 中打开结果,并按操作系统提供回退

**核心能力:**
- 500+ 个过滤代码,覆盖基本面(P/E、股息、成长、利润率)、技术面(RSI、SMA、图形形态)与描述性(板块、市值、国家)
- **主题与子主题交叉筛选** —— 把 30+ 个投资主题与 268 个子主题与任意过滤器组合,筛选跨板块叙事(例如“AI × 物流”“数据中心 × 电力基础设施”“网络安全 × 云”)
- 视图类型选择:Overview、Valuation、Financial、Technical、Ownership、Performance、Custom
- 排序控制(按任意列升序或降序)
- 用于精确条件的范围过滤语法(例如 `fa_div_3to8` 表示股息率 3-8%)
- 参考知识库中 14+ 个预构建筛选配方

---

## 2. 前提条件

- **API 密钥:** 公开 FinViz 筛选器无需
- **FINVIZ Elite(可选):** 设置 `$FINVIZ_API_KEY`(任意非空值)以生成 `elite.finviz.com` URL。该值不会发送给 FinViz —— 它仅作为切换 URL 的本地标志。你必须在浏览器中登录有效的 FINVIZ Elite 订阅
- **Python 3.9+:** 运行 URL 构建脚本所需
- **无额外 Python 依赖** —— 仅使用标准库

> FinViz Screener 完全无需 API 密钥即可工作。仅当你想要实时数据与高级筛选功能时才需要 FINVIZ Elite。
{: .tip }

---

## 3. 快速开始

对 Claude 说:

```
找接近 52 周低点、带内部人买入的超卖大盘股
```

Claude 把它映射为过滤代码,向你展示一张确认表,并在 Chrome 中打开 FinViz 结果页。这就是上手所需的一切。

---

## 4. 工作原理

1. **加载过滤参考** —— Claude 读取把自然语言概念映射到 FinViz 代码的内部过滤知识库。
2. **解释你的请求** —— 用概念映射表把你的描述映射到具体过滤代码(例如“高股息”映射到 `fa_div_o3`,“大盘股”映射到 `cap_large`)。
3. **呈现过滤选择** —— 执行前,Claude 展示一张所选过滤器的表格供你确认。
4. **执行脚本** —— `open_finviz_screener.py` 脚本校验过滤器、构建 URL 并打开 Chrome。
5. **报告结果** —— Claude 报告所构建的 URL、所用模式(Public 或 Elite)并建议后续步骤。

**Elite 自动检测:** 若设置了 `$FINVIZ_API_KEY` 环境变量(任意非空值),脚本生成 `elite.finviz.com` URL。该变量作为本地 URL 切换标志 —— 它不会发送到 FinViz 服务器。你也可用 `--elite` 强制 Elite 模式。要使用 Elite 结果,你的浏览器必须登录有效的 FINVIZ Elite 订阅。

---

## 5. 使用示例

### 示例 1:成长动量

**提示词:**
```
找季度 EPS 增长 > 25%、价格高于 SMA50 与 SMA200、且最近一个季度表现为正的股票
```

**过滤代码:** `fa_epsqoq_o25,ta_sma50_pa,ta_sma200_pa,ta_perf_13wup`

**为何有用:** 识别盈利动量强劲、并经多条均线支撑与持续季度跑赢确认的股票 —— 经典的成长动量形态。

---

### 示例 2:CANSLIM + Minervini + VCP 综合过滤

**提示词:**
```
筛选 EPS 增长超 25%、营收增长超 15%、站上所有主要均线、
接近 52 周高点、且相对成交量超 1.5 倍的股票 —— 在单个 FinViz 筛选中
结合 CANSLIM 基本面与 Minervini 趋势模板标准
```

**过滤代码:** `fa_epsqoq_o25,fa_salesqoq_o15,ta_sma20_pa,ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to10h,sh_relvol_o1.5`

**为何有用:** 在一个 URL 中结合 O'Neil 式基本面成长标准、Minervini 趋势模板与类 VCP 的成交量特征,可在运行专门的 CANSLIM 或 VCP 筛选器前做快速首轮过滤。

---

### 示例 3:高股息价值

**提示词:**
```
筛选股息率 > 4% 且 P/E 低于 15 的股票
```

**过滤代码:** `fa_div_o4,fa_pe_u15`

**为何有用:** 面向收益的快速筛选,锁定估值合理的高股息股票。股息组合构建的扎实起点。

---

### 示例 4:超卖反弹

**提示词:**
```
找接近 52 周低点、带内部人买入的超卖大盘股
```

**过滤代码:** `cap_large,ta_rsi_os30,ta_highlow52w_a0to5l,sh_insidertrans_verypos`

**为何有用:** 识别处于技术极端、且内部人正在买入的大盘股 —— 一种可能标志反转点的逆向信号。

---

### 示例 5:AI 主题股

**提示词:**
```
给我看动量强劲的 AI 与半导体股
```

**过滤代码:** `theme_artificialintelligence,ta_perf_13wup,ta_sma50_pa,ta_sma200_pa`

**说明:** 主题代码通过 `--themes "artificialintelligence"` 传入,而非 `--filters`。`theme_` 前缀会在 URL 中自动添加。

**为何有用:** 用 FinViz 的主题过滤器锁定 AI/半导体领域,并叠加动量确认。快速浮现趋势主题中最强的参与者。

---

### 示例 6:小盘突破

**提示词:**
```
找在高相对成交量上创 52 周新高的小盘股
```

**过滤代码:** `cap_small,ta_highlow52w_b0to5h,sh_relvol_o1.5`

**为何有用:** 锁定小盘突破候选,高相对成交量确认真实买盘 —— 经典的动量入场形态。

---

### 示例 7:日语输入

**提示词:**
```
配当利回り5%以上でROE15%以上の大型株を探して
```

**过滤代码:** `fa_div_o5,fa_roe_o15,cap_large`

**为何有用:** 展示完整的日语支持。Claude 解析日语财务术语并映射到相同的 FinViz 过滤代码,使该技能对双语用户可用。

---

### 示例 8:程序化使用(仅 URL)

**命令:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --filters "fa_div_o3,fa_pe_u20,cap_large" \
  --view valuation \
  --order dividendyield \
  --url-only
```

**输出:**
```
[Public] https://finviz.com/screener.ashx?v=121&f=cap_large,fa_div_o3,fa_pe_u20&o=dividendyield
```

**为何有用:** `--url-only` 标志只打印 URL 而不打开浏览器,适合脚本化、记录日志或嵌入其他工作流。

---

### 示例 9:主题交叉筛选(AI × 物流、数据中心 × 电力)

传统的板块/行业过滤器把你限制在单一维度。FinViz 的主题与子主题过滤器让你沿跨板块的*叙事*轴筛选。

**提示词 A:AI × 物流**
```
找同时处于 AI 与物流主题、季度表现强劲的中盘及以上股票
```

**命令:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --themes "artificialintelligence" \
  --subthemes "ecommercelogistics" \
  --filters "cap_midover,ta_perf_13wup" \
  --url-only
```

**提示词 B:数据中心 × 电力基础设施**
```
给我看数据中心与电力基础设施股
```

**命令:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --subthemes "clouddatacenters,aienergy" \
  --url-only
```

**提示词 C:网络安全 × 云**
```
高 ROE 的网络安全与云股票
```

**命令:**
```bash
python3 skills/finviz-screener/scripts/open_finviz_screener.py \
  --themes "cybersecurity" \
  --subthemes "aicloud" \
  --filters "fa_roe_o15" \
  --url-only
```

**为何有用:** 板块过滤器按公司*是什么*分组(科技、公用事业、房地产)。主题过滤器按公司搭乘的*趋势*分组。组合主题与子主题能发现处于长期成长叙事交叉点的股票 —— 例如投资 AI 自动化的物流公司,或受益于数据中心电力需求的公用事业 —— 而传统板块过滤器会完全错过它们。

---

### 筛选配方

针对常见投资策略的开箱即用过滤组合。每个配方都附迭代优化提示。

#### 配方 1:高股息成长股(Kanchi 式)

**目标:** 高股息 + 股息增长 + 盈利增长,排除股息陷阱。

**过滤器:** `fa_div_3to8,fa_sales5years_pos,fa_eps5years_pos,fa_divgrowth_5ypos,fa_payoutratio_u60,geo_usa`
**视图:** Financial

| 过滤器 | 用途 |
|--------|------|
| `fa_div_3to8` | 股息率 3-8%(封顶高息陷阱) |
| `fa_sales5years_pos` | 5 年营收增长为正 |
| `fa_eps5years_pos` | 5 年 EPS 增长为正 |
| `fa_divgrowth_5ypos` | 5 年股息增长为正 |
| `fa_payoutratio_u60` | 派息率 < 60%(可持续性) |
| `geo_usa` | 美国上市股票 |

**优化:** 从 `fa_div_o3` 起 → 加 `fa_div_3to8` 封顶股息 → 加 `fa_payoutratio_u60` 排除陷阱。

#### 配方 2:Minervini 趋势模板 + VCP

**目标:** 处于 Stage 2 上升趋势且波动率收缩的股票。

**过滤器:** `ta_sma50_pa,ta_sma200_pa,ta_sma200_sb50,ta_highlow52w_0to25-bhx,ta_perf_26wup,sh_avgvol_o300,cap_midover`
**视图:** Technical

| 过滤器 | 用途 |
|--------|------|
| `ta_sma50_pa` | 价格高于 50 日 SMA |
| `ta_sma200_pa` | 价格高于 200 日 SMA |
| `ta_sma200_sb50` | 200 SMA 低于 50 SMA(上升趋势) |
| `ta_highlow52w_0to25-bhx` | 在 52 周高点 25% 以内 |
| `ta_perf_26wup` | 26 周表现为正 |
| `sh_avgvol_o300` | 平均成交量 > 30 万 |
| `cap_midover` | 中盘及以上 |

**VCP 收紧:** 加 `ta_volatility_wo3,ta_highlow20d_b0to5h,sh_relvol_u1`,实现低波动 + 接近 20 日高点 + 低于均量。

#### 配方 3:被不公正抛售的成长股

**目标:** 基本面强劲但近期急跌的公司。

**过滤器:** `fa_sales5years_o5,fa_eps5years_o10,fa_roe_o15,fa_salesqoq_pos,fa_epsqoq_pos,ta_perf_13wdown,ta_highlow52w_10to30-bhx,cap_large,sh_avgvol_o200`
**视图:** Overview → 审视候选后切换到 Valuation

| 过滤器 | 用途 |
|--------|------|
| `fa_sales5years_o5` | 5 年营收增长 > 5% |
| `fa_eps5years_o10` | 5 年 EPS 增长 > 10% |
| `fa_roe_o15` | ROE > 15% |
| `fa_salesqoq_pos` | 环比营收增长为正 |
| `fa_epsqoq_pos` | 环比 EPS 增长为正 |
| `ta_perf_13wdown` | 13 周表现为负 |
| `ta_highlow52w_10to30-bhx` | 低于 52 周高点 10-30% |
| `cap_large` | 大盘 |
| `sh_avgvol_o200` | 平均成交量 > 20 万 |

#### 配方 4:困境反转股

**目标:** 此前盈利下滑、现显示复苏的公司。

**过滤器:** `fa_eps5years_neg,fa_epsqoq_pos,fa_salesqoq_pos,ta_highlow52w_b30h,ta_perf_13wup,cap_smallover,sh_avgvol_o200`
**视图:** Performance

| 过滤器 | 用途 |
|--------|------|
| `fa_eps5years_neg` | 5 年 EPS 增长为负(此前下滑) |
| `fa_epsqoq_pos` | 环比 EPS 增长为正(复苏) |
| `fa_salesqoq_pos` | 环比营收增长为正(复苏) |
| `ta_highlow52w_b30h` | 在 52 周高点 30% 以内 |
| `ta_perf_13wup` | 13 周表现为正 |
| `cap_smallover` | 小盘及以上 |
| `sh_avgvol_o200` | 平均成交量 > 20 万 |

#### 配方 5:动量交易候选

**目标:** 接近 52 周高点、成交量放大的短期动量龙头。

**过滤器:** `ta_sma50_pa,ta_sma200_pa,ta_highlow52w_b0to3h,ta_perf_4wup,sh_relvol_o1.5,sh_avgvol_o1000,cap_midover`
**视图:** Technical

| 过滤器 | 用途 |
|--------|------|
| `ta_sma50_pa` | 价格高于 50 日 SMA |
| `ta_sma200_pa` | 价格高于 200 日 SMA |
| `ta_highlow52w_b0to3h` | 在 52 周高点 3% 以内 |
| `ta_perf_4wup` | 4 周表现为正 |
| `sh_relvol_o1.5` | 相对成交量 > 1.5 倍 |
| `sh_avgvol_o1000` | 平均成交量 > 100 万 |
| `cap_midover` | 中盘及以上 |

#### 提示:迭代优化

筛选最好当作对话来做:

1. **从宽泛起步** —— 用 3-4 个核心过滤器得到初始集合
2. **检查数量** —— >100 个结果?加过滤器。<5 个结果?放松约束
3. **切换视图** —— 先 `overview`,再用 `financial` 或 `valuation` 深入
4. **叠加技术面** —— 确认基本面后,加 `ta_` 过滤器来把握入场时机

---

## 6. 解读输出

执行后,Claude 报告:

1. **所构建的 URL** —— 含全部已应用过滤器的完整 FinViz 筛选器 URL。
2. **模式** —— 使用的是 Public 还是 Elite 模式。
3. **过滤摘要** —— 列出每个已应用过滤代码及其含义的表格。
4. **建议的后续步骤** —— 例如“按股息率排序”或“切换到 Financial 视图查看详细比率”。

FinViz 结果页本身以可排序表格显示股票。用视图选择器(Overview、Valuation、Financial、Technical、Ownership、Performance)查看不同数据点。

---

## 7. 技巧与最佳实践

- **用范围过滤器以求精确。** 与其组合分开的“大于”与“小于”过滤器,不如用范围语法:`fa_div_3to8` 表示股息率在 3% 到 8% 之间。这能排除极端水平的股息陷阱。
- **组合基本面与技术面过滤器。** 把盈利增长(`fa_epsqoq_o25`)与趋势确认(`ta_sma50_pa,ta_sma200_pa`)配对的成长动量形态,比单独任一更可靠。
- **从宽到窄。** 从 2-3 个过滤器开始,仅当结果集过大时再加。过度过滤会剔除好候选。
- **有策略地使用 `--view`。** `valuation` 视图最适合股息/价值筛选;`technical` 视图最适合动量与突破筛选。
- **检查 `--order` 选项。** 按对你的策略最相关的指标(如 `dividendyield`、`-marketcap`、`change`)排序,会让最佳候选优先浮现。
- **日语用户:** 该技能原生处理全角字符与日语财务术语,无需翻译步骤。

---

## 8. 与其他技能组合

| 工作流 | 如何组合 |
|--------|----------|
| **成长股深剖** | 用 FinViz Screener 构建初始范围,再把头部结果喂给 CANSLIM Screener 做严格的 7 分量评分 |
| **股息组合构建** | 用 FinViz 筛选(`fa_div_o3,fa_pe_u20`),再用 Value Dividend Screener 做可持续性分析 |
| **基于主题的投资** | 用 Theme Detector 识别火热主题,再用带主题过滤器的 FinViz Screener(`--themes "artificialintelligence"`)找个股 |
| **技术确认** | FinViz 浮现候选后,用 Technical Analyst 对头部标的做详细看图 |
| **仓位测算** | 识别出入场候选后,把它们交给 Position Sizer 做基于风险的股数计算 |

---

## 9. 故障排查

### Chrome 不打开

**原因:** 未安装 Chrome,或路径未被检测到。

**修复:** 脚本按以下顺序回退:Chrome > 默认浏览器 > `webbrowser.open()`。在 macOS 上,确保 Google Chrome 安装在 `/Applications/`。在 Linux 上,确保 `google-chrome` 或 `chromium-browser` 在你的 PATH 中。

### “Invalid filter token” 错误

**原因:** 某过滤代码含无效字符(空格、`&`、`=`)。

**修复:** 过滤令牌只能含小写字母、数字、下划线与点。检查手动输入的过滤代码是否有拼写错误。

### “Unknown filter prefix” 警告

**原因:** 某过滤器使用了已知集合之外的前缀。

**修复:** 这是警告而非错误。URL 仍会被构建。该警告提示你前缀未被识别,可能意味着拼写错误或一个尚未编目的新 FinViz 过滤器。

### Elite 模式未激活

**原因:** 未设置 `$FINVIZ_API_KEY` 环境变量,或你的浏览器未登录 FINVIZ Elite。

**修复:** 设置 `export FINVIZ_API_KEY=1`(任意非空值)以切换到 Elite URL。然后确保在 Chrome 中登录了你的 FINVIZ Elite 账户。该环境变量是本地标志 —— 它不会向 FinViz 认证。

---

## 10. 参考资料

### CLI 参数

| 参数 | 必需 | 默认 | 说明 |
|------|------|------|------|
| `--filters` | 否* | -- | 逗号分隔的 FinViz 过滤代码 |
| `--themes` | 否* | -- | 逗号分隔的主题 slug(如 `artificialintelligence,cybersecurity`) |
| `--subthemes` | 否* | -- | 逗号分隔的子主题 slug(如 `aicloud,aienergy`) |
| `--elite` | 否 | 自动检测 | 强制 Elite 模式(`elite.finviz.com`) |
| `--view` | 否 | `overview` | 视图类型:overview、valuation、financial、technical、ownership、performance、custom |
| `--order` | 否 | 无 | 排序代码(如 `-marketcap`、`dividendyield`)。前缀 `-` 表示降序 |
| `--url-only` | 否 | `false` | 只打印 URL 而不打开浏览器 |

\* `--filters`、`--themes`、`--subthemes` 至少需提供其一。

### 视图类型代码

| 名称 | 代码 | 最适合 |
|------|------|--------|
| Overview | `111` | 通用筛选、初看 |
| Valuation | `121` | P/E、P/B、PEG、股息分析 |
| Ownership | `131` | 机构持仓、内部人活动 |
| Performance | `141` | 各时间框架的收益 |
| Custom | `152` | 用户自定义列 |
| Financial | `161` | 营收、利润率、ROE、负债比率 |
| Technical | `171` | RSI、SMA、beta、波动率 |

### 常用过滤代码速查

| 概念 | 过滤代码 |
|------|----------|
| 高股息(>3%) | `fa_div_o3` |
| 低 P/E(<20) | `fa_pe_u20` |
| EPS 环比增长 >25% | `fa_epsqoq_o25` |
| 价格高于 SMA200 | `ta_sma200_pa` |
| RSI 超卖(<30) | `ta_rsi_os30` |
| 大盘 | `cap_large` |
| 内部人买入 | `sh_insidertrans_verypos` |
| AI 主题 | `theme_artificialintelligence` |
| 接近 52 周高点 | `ta_highlow52w_b0to5h` |
| 高相对成交量 | `sh_relvol_o1.5` |

> **说明:** 主题与子主题代码使用 `--themes` / `--subthemes` 选项,而非 `--filters`。脚本在构建 URL 时自动添加 `theme_` / `subtheme_` 前缀。
