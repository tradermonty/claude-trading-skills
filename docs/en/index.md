---
layout: default
title: English
nav_order: 1
has_children: true
lang_peer: /ja/
permalink: /en/
---

# Claude Trading Skills
{: .no_toc }

<div class="hero">
  <p class="hero-mantra">Empower Solo Traders and Growing Together</p>
  <p class="hero-tagline">Claude-powered skills for systematic market analysis, screening, and trading</p>
</div>

## What are Claude Trading Skills?

Claude Trading Skills is a curated collection of **Claude skills** for equity investors and traders. Each skill packages domain-specific prompts, knowledge bases, and helper scripts so Claude can assist with market analysis, stock screening, strategy validation, portfolio management, and more.

Describe what you are looking for in natural language, and receive structured reports with actionable insights in Markdown and JSON formats.

<div class="category-cards">
  <div class="category-card">
    <h3>Stock Screening</h3>
    <p>CANSLIM, VCP, FinViz, dividend screeners, and more. Multiple investment methodologies translated into systematic screening skills that generate ranked candidate lists from natural language instructions.</p>
  </div>
  <div class="category-card">
    <h3>Market Analysis</h3>
    <p>Sector rotation, market breadth, technical analysis, and news analysis. Evaluate overall market health, direction, and positioning using chart-based and data-driven skills.</p>
  </div>
  <div class="category-card">
    <h3>Strategy & Research</h3>
    <p>Backtesting, options strategies, theme detection, pair trading, and edge research. Build, test, and refine investment strategies with professional-grade frameworks.</p>
  </div>
  <div class="category-card">
    <h3>Portfolio & Execution</h3>
    <p>Portfolio Manager, Position Sizer, Earnings Calendar, and Economic Calendar. Cover holdings management, risk-based position sizing, and event monitoring.</p>
  </div>
</div>

---

## How It Works

<div class="steps">
  <div class="step">
    <span class="step-number">1</span>
    <h4>Install</h4>
    <p>Upload a <code>.skill</code> file to Claude Web App, or clone the repository and copy skill folders into Claude Code.</p>
  </div>
  <div class="step">
    <span class="step-number">2</span>
    <h4>Describe</h4>
    <p>Tell Claude what you are looking for in natural language -- English or Japanese. No special syntax required.</p>
  </div>
  <div class="step">
    <span class="step-number">3</span>
    <h4>Get Analysis</h4>
    <p>Receive structured reports and actionable insights in Markdown + JSON format, ready for review and decision-making.</p>
  </div>
</div>

---

## Featured Skills

| Skill | Highlights | API |
|-------|-----------|-----|
| [FinViz Screener]({{ '/en/skills/finviz-screener/' | relative_url }}) | Translate natural language into FinViz filter URLs. 500+ filter codes, Japanese/English input, opens results in Chrome | No API needed |
| [CANSLIM Screener]({{ '/en/skills/canslim-screener/' | relative_url }}) | Full 7-component CANSLIM scoring (C, A, N, S, L, I, M) with composite 0-100 ratings and bear market protection | FMP Required |
| [VCP Screener]({{ '/en/skills/vcp-screener/' | relative_url }}) | Detect Minervini's Volatility Contraction Pattern automatically. 3-phase pipeline with trade setups and pivot points | FMP Required |
| [Theme Detector]({{ '/en/skills/theme-detector/' | relative_url }}) | Identify bullish and bearish market themes with 3-dimensional scoring: Heat, Lifecycle, and Confidence | Optional |

Browse the full catalog in [Skill Catalog]({{ '/en/skill-catalog/' | relative_url }}).

---

## Operational Workflows

For multi-skill routines (Core + Satellite), see [Workflows]({{ '/en/workflows/' | relative_url }}). Each workflow names the exact skills, decision gates, and artifacts in order — auto-generated from the canonical YAML manifests.

[Skillsets]({{ '/en/skillsets/' | relative_url }}) is the companion "what to install for a goal" layer — category-scoped skill bundles tied to those workflows, auto-generated from `skillsets/*.yaml`.

---

## Get Started

New here? Visit [Getting Started]({{ '/en/getting-started/' | relative_url }}) for installation instructions, API key setup, and your first skill tutorial.
