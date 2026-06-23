---
layout: default
title: 新手入门
parent: 简体中文
nav_order: 1
lang_peer: /en/getting-started/
permalink: /zh/getting-started/
---

# 新手入门
{: .no_toc }

本指南介绍 Claude Trading Skills 的安装方法、API 密钥配置，以及如何运行你的第一个技能。
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>目录</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 你需要准备什么

| 项目 | 必需/可选 | 说明 |
|------|-----------|------|
| Claude 账户 | 必需 | Pro / Team / Enterprise 套餐（支持 Skills 功能的套餐） |
| Python 3.9+ | 必需 | 用于运行脚本。多数技能使用 Python 辅助脚本 |
| FMP API 密钥 | 可选 | Financial Modeling Prep API。部分技能必需（有免费档） |
| FINVIZ Elite | 可选 | 推荐用于加速股息筛选器、提升 Theme Detector 精度 |
| Alpaca 账户 | 可选 | Portfolio Manager 技能获取持仓数据时需要 |

---

## 安装方法

### 在 Claude Web App 中使用

1. 从 `skill-packages/` 目录下载你想用的技能的 `.skill` 文件（ZIP 格式）。
2. 在浏览器中打开 Claude，进入 **Settings → Skills**。
3. 上传下载好的 `.skill` 文件。
4. 在新会话中该技能会自动启用。

> 详情请参阅 Anthropic 的 [Skills 发布文章](https://www.anthropic.com/news/skills)。
{: .note }

### 在 Claude Code（桌面端 / CLI）中使用

```bash
# 1. 克隆仓库
git clone https://github.com/tradermonty/claude-trading-skills.git

# 2. 将想用的技能文件夹复制到 Claude Code 的 Skills 目录
#    （Claude Code → Settings → Skills → Open Skills Folder 查看路径）
cp -r claude-trading-skills/skills/finviz-screener /path/to/skills-directory/

# 3. 重启或重新加载 Claude Code
```

> `.skill` 包从源文件夹生成，但会排除测试和本地构建产物。若要自定义，请编辑源文件夹，并在分发前运行 `python3 scripts/package_skills.py --skill <skill-name>`。
{: .tip }

---

## 配置 API 密钥

### Financial Modeling Prep (FMP)

多数筛选类技能使用的基本面数据 API。

| 套餐 | 价格 | API 调用上限 | 适用 |
|------|------|-------------|------|
| Free | 免费 | 250 次/天 | 少量个股筛选足够 |
| Starter | $29.99/月 | 750 次/天 | CANSLIM 40 只全量筛选 |
| Professional | $79.99/月 | 2,000 次/天 | 大规模筛选、多技能并用 |

**注册：** [https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

```bash
# 用环境变量设置（推荐）
export FMP_API_KEY=your_key_here

# 或在运行脚本时用参数指定
python3 scripts/screen_canslim.py --api-key YOUR_KEY
```

### FINVIZ Elite

用于加速股息筛选器（执行时间缩短 70-80%）以及提升 Theme Detector 的精度。

| 套餐 | 价格 | 备注 |
|------|------|------|
| Elite 月付 | $39.50/月 | 实时数据、高速 API |
| Elite 年付 | $299.50/年（约 $24.96/月） | 有年度折扣 |

**注册：** [https://elite.finviz.com/](https://elite.finviz.com/)

```bash
export FINVIZ_API_KEY=your_key_here
```

### Alpaca Trading

Portfolio Manager 技能用其获取持仓数据并执行交易。

| 套餐 | 价格 | 备注 |
|------|------|------|
| 模拟交易（Paper） | 免费 | 模拟环境，全部 API 可用 |
| 实盘交易（Live） | 免费（无佣金） | 可买卖股票与 ETF |

**注册：** [https://alpaca.markets/](https://alpaca.markets/)

```bash
export ALPACA_API_KEY="your_api_key_id"
export ALPACA_SECRET_KEY="your_secret_key"
export ALPACA_PAPER="true"  # 模拟交易时
```

---

## 试用第一个技能 —— FinViz Screener

FinViz Screener 无需 API 密钥，是最易上手的技能。只需用自然语言给出筛选条件，它就会生成带过滤参数的 FinViz URL 并在 Chrome 中打开。

### 使用示例

试着这样对 Claude 说：

```
帮我找 EPS 增速 25% 以上、且站在 SMA200 之上的个股
```

### Claude 会做什么

1. 解析用户的自然语言，转换为 FinViz 过滤代码
   - `fa_epsqoq_o25`（EPS 季度环比增速 > 25%）
   - `ta_sma200_pa`（位于 SMA200 之上）
2. 以表格形式列出所选过滤条件供你确认
3. 确认后构建 URL，并在 Chrome 中打开结果页

### 预期输出

- Chrome 浏览器中显示 FinViz Screener 的结果
- 符合条件的个股以表格列出
- 可在 Overview / Valuation / Financial / Technical 等视图间切换查看详情

> FinViz Screener 的详细用法请见 [FinViz Screener 指南]({{ '/zh/skills/finviz-screener/' | relative_url }})。
{: .tip }

---

## 故障排查

### 技能无法加载

| 原因 | 处理 |
|------|------|
| SKILL.md 的 `name` 字段与文件夹名不一致 | 确认 `name` 与文件夹名完全一致 |
| 技能文件夹放错位置 | 确认已正确复制到 Claude Code 的 Skills 目录 |
| 未重启 Claude Code | 添加新技能后需要重启 |

### API 密钥错误

```
ERROR: FMP API key not found. Set FMP_API_KEY environment variable or use --api-key argument.
```

**处理：**
1. 确认环境变量已正确设置：`echo $FMP_API_KEY`
2. 在 shell 配置文件（`.zshrc` / `.bashrc`）中添加 `export FMP_API_KEY=...` 并重新加载
3. 仍不行时，用 `--api-key` 参数直接传入

### 脚本报错（缺少依赖包）

```
ModuleNotFoundError: No module named 'requests'
```

**处理：**

```bash
pip install requests beautifulsoup4 lxml pandas numpy yfinance
```

> 所需依赖因技能而异。请查看各技能指南的“前提条件”一节。
{: .note }

### FMP API 限流

```
ERROR: 429 Too Many Requests - Rate limit exceeded
```

**处理：**
1. 脚本会在 60 秒后自动重试
2. 超出免费档（250 次/天）上限时，会在次日（UTC 0 点）重置
3. 用 `--max-candidates` 参数减少分析对象可降低用量
4. 若使用频繁，可考虑升级到 FMP Starter（$29.99/月）
