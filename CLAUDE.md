# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository contains Claude Skills for equity investors and traders. Each skill packages domain-specific prompts, knowledge bases, and helper scripts to assist with market analysis, technical charting, economic calendar monitoring, and trading strategy development. Skills are designed to work in both Claude's web app and Claude Code environments.

⚠️ **Important:** Some skills require paid API subscriptions (FMP API and/or FINVIZ Elite) to function. See the [API Key Management](#api-key-management) section for detailed requirements by skill.

## Repository Architecture

### Skill Structure

Each skill follows a standardized directory structure:

```
<skill-name>/
├── SKILL.md              # Required: Skill definition with YAML frontmatter
├── references/           # Knowledge bases loaded into Claude's context
├── scripts/             # Executable Python scripts (not auto-loaded)
└── assets/              # Templates and resources for output generation
```

**SKILL.md Format:**
- YAML frontmatter with `name` and `description` fields
- `name` must match the directory name for proper skill detection
- Description defines when the skill should be triggered
- Body contains workflow instructions written in imperative/infinitive form
- All instructions assume Claude will execute them, not the user

**Progressive Loading:**
1. Metadata (YAML frontmatter) loads first for skill detection
2. SKILL.md body loads when skill is invoked
3. References load conditionally based on analysis needs
4. Scripts execute on demand, never auto-loaded into context

### Key Design Patterns

**Knowledge Base Organization:**
- `references/` contains markdown files with domain knowledge (sector rotation patterns, technical analysis frameworks, news source credibility guides)
- Knowledge bases provide context without requiring Claude to have specialized training
- References are read selectively during skill execution to minimize token usage

**Script vs. Reference Division:**
- Scripts (`scripts/`) are executable code for API calls, data fetching, report generation
- References (`references/`) are documentation for Claude to read and apply
- Scripts handle I/O; references handle knowledge

**Output Generation:**
- Skills generate markdown reports saved to repository root
- Filename convention: `<skill>_<analysis-type>_<date>.md`
- Reports use structured templates from `assets/` directories

## Common Development Tasks

### Creating a New Skill

Use the skill-creator plugin (available in Claude Code):

```bash
# This invokes the skill-creator to guide you through setup
# Follow the 6-step process: Understanding → Planning → Initializing → Editing → Packaging → Iterating
```

The skill-creator will:
1. Ask clarification questions about the skill's purpose
2. Create the directory structure
3. Generate SKILL.md template
4. Set up references and scripts directories
5. Package the skill into a .zip file

### Packaging Skills for Distribution

Skills are packaged as ZIP files for Claude web app users:

```bash
# Use the skill-creator's packaging script
python3 ~/.claude/plugins/marketplaces/anthropic-agent-skills/skill-creator/scripts/package_skill.py <skill-name>
```

The packaged .zip files are stored in `zip-packages/` and should be regenerated after any skill modifications.

### Testing Skills

Skills are tested by invoking them in Claude Code conversations:

1. Copy skill folder to Claude Code Skills directory
2. Restart Claude Code to detect the skill
3. Trigger the skill by providing input that matches the skill's description
4. Verify that:
   - Skill loads correctly (check YAML frontmatter)
   - References load when needed
   - Scripts execute with proper error handling
   - Output matches expected format

### API Key Management

⚠️ **IMPORTANT:** Several skills require paid API subscriptions to function. Review the requirements below before using these skills.

#### API Requirements by Skill

| Skill | FMP API | FINVIZ Elite | Notes |
|-------|---------|--------------|-------|
| **Economic Calendar Fetcher** | ✅ Required | ❌ Not used | Fetches economic events from FMP |
| **Earnings Calendar** | ✅ Required | ❌ Not used | Fetches earnings dates from FMP |
| **Value Dividend Screener** | ✅ Required | 🟡 Optional (Recommended) | FMP for analysis; FINVIZ reduces execution time by 70-80% |
| Sector Analyst | ❌ Not required | ❌ Not used | Image-based chart analysis |
| Technical Analyst | ❌ Not required | ❌ Not used | Image-based chart analysis |
| Breadth Chart Analyst | ❌ Not required | ❌ Not used | Image-based chart analysis |
| Market News Analyst | ❌ Not required | ❌ Not used | Uses WebSearch/WebFetch |
| US Stock Analysis | ❌ Not required | ❌ Not used | User provides data |
| Backtest Expert | ❌ Not required | ❌ Not used | User provides strategy parameters |
| US Market Bubble Detector | ❌ Not required | ❌ Not used | User provides indicators |

#### API Key Setup

**Financial Modeling Prep (FMP) API:**
```bash
# Set environment variable (preferred method)
export FMP_API_KEY=your_key_here

# Or provide via command-line argument when script runs
python3 scripts/get_economic_calendar.py --api-key YOUR_KEY
```

**FINVIZ Elite API:**
```bash
# Set environment variable
export FINVIZ_API_KEY=your_key_here

# Or provide via command-line argument
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --finviz-api-key YOUR_KEY
```

#### API Pricing and Access

**Financial Modeling Prep (FMP):**
- **Free Tier:** 250 API calls/day (sufficient for occasional use)
- **Starter Tier:** $29.99/month - 750 calls/day
- **Professional Tier:** $79.99/month - 2,000 calls/day
- **Sign up:** https://site.financialmodelingprep.com/developer/docs

**FINVIZ Elite:**
- **Elite Subscription:** $39.99/month or $329.99/year (~$27.50/month)
- Provides advanced screeners, real-time data, and API access
- **Sign up:** https://elite.finviz.com/
- **Note:** FINVIZ Elite is optional for Value Dividend Screener but reduces execution time from 10-15 minutes to 2-3 minutes

**Recommendation for Value Dividend Screener:**
- **Budget Option:** FMP free tier only (run screening every few days)
- **Optimal Option:** FINVIZ Elite ($330/year) + FMP free tier (complete solution, fast execution)
- **Power User:** FMP paid tier only (if you need daily screening without FINVIZ)

#### API Script Pattern

All API scripts follow this pattern:
1. Check for environment variable first
2. Fall back to command-line argument
3. Provide clear error messages if key missing
4. Support both methods for CLI, Desktop, and Web environments
5. Handle rate limits gracefully with retry logic

### Running Helper Scripts

**Economic Calendar Fetcher:** ⚠️ Requires FMP API key
```bash
# Default: next 7 days
python3 economic-calendar-fetcher/scripts/get_economic_calendar.py --api-key YOUR_KEY

# Specific date range (max 90 days)
python3 economic-calendar-fetcher/scripts/get_economic_calendar.py \
  --from 2025-11-01 --to 2025-11-30 \
  --api-key YOUR_KEY \
  --format json
```

**Earnings Calendar:** ⚠️ Requires FMP API key
```bash
# Default: next 7 days, market cap > $2B
python3 earnings-calendar/scripts/fetch_earnings_fmp.py --api-key YOUR_KEY

# Custom date range
python3 earnings-calendar/scripts/fetch_earnings_fmp.py \
  --from 2025-11-01 --to 2025-11-07 \
  --api-key YOUR_KEY
```

**Value Dividend Screener:** ⚠️ Requires FMP API key; FINVIZ Elite optional but recommended
```bash
# Two-stage screening (RECOMMENDED - 70-80% faster)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py --use-finviz

# FMP-only screening (no FINVIZ required)
python3 value-dividend-screener/scripts/screen_dividend_stocks.py

# Custom parameters
python3 value-dividend-screener/scripts/screen_dividend_stocks.py \
  --use-finviz \
  --top 50 \
  --output custom_results.json
```

## Skill Interaction Patterns

### Chart Analysis Skills (Sector Analyst, Breadth Chart Analyst, Technical Analyst)

These skills expect image inputs:
- User provides chart screenshots
- Skill analyzes visual patterns
- Output includes scenario-based probability assessments
- Analysis follows specific frameworks documented in `references/`

**Workflow:**
1. User uploads chart image
2. Skill loads relevant reference framework
3. Analysis generates structured markdown report
4. Report saved to repository root

### News Analysis Skills (Market News Analyst)

This skill uses automated data collection:
- Executes WebSearch/WebFetch queries to gather news
- Focuses on past 10 days of market-moving events
- Applies impact scoring framework: (Price Impact × Breadth) × Forward Significance
- Ranks events by quantitative score

**Key References:**
- `trusted_news_sources.md`: Source credibility tiers
- `market_event_patterns.md`: Historical reaction patterns
- `geopolitical_commodity_correlations.md`: Event-commodity relationships

### Calendar Skills (Economic Calendar Fetcher, Earnings Calendar)

⚠️ **API Requirement:** These skills require FMP API key to function.

These skills fetch future events via FMP API:
- Execute Python scripts to call FMP API endpoints
- Parse JSON responses
- Generate chronological markdown reports
- Include impact assessment (High/Medium/Low)
- Free tier (250 calls/day) is sufficient for most users

**Output Pattern:**
```markdown
# Economic Calendar
**Period:** YYYY-MM-DD to YYYY-MM-DD
**High Impact Events:** X

## YYYY-MM-DD - Day of Week
### Event Name (Impact Level)
- Country: XX (Currency)
- Time: HH:MM UTC
- Previous: Value
- Estimate: Value
**Market Implications:** Analysis...
```

## Multi-Skill Workflows

Skills are designed to be combined for comprehensive analysis:

**Daily Market Monitoring:**
1. Economic Calendar Fetcher → Check today's events
2. Earnings Calendar → Identify reporting companies
3. Market News Analyst → Review overnight developments
4. Breadth Chart Analyst → Assess market health

**Weekly Strategy Review:**
1. Sector Analyst → Identify rotation patterns
2. Technical Analyst → Confirm trends
3. Market Environment Analysis → Macro briefing
4. US Market Bubble Detector → Risk assessment

**Individual Stock Research:**
1. US Stock Analysis → Fundamental/technical review
2. Earnings Calendar → Check earnings dates
3. Market News Analyst → Recent news
4. Backtest Expert → Validate entry/exit strategy

## Important Conventions

### SKILL.md Writing Style

- Use imperative/infinitive verb forms (e.g., "Analyze the chart", "Generate report")
- Write instructions for Claude to execute, not user instructions
- Avoid phrases like "You should..." or "Claude will..." - just state actions directly
- Structure: Overview → When to Use → Workflow → Output Format → Resources

### Reference Document Patterns

- Knowledge bases use declarative statements of fact
- Include historical examples and case studies
- Provide decision frameworks and checklists
- Organize hierarchically (H2 for major sections, H3 for subsections)

### Analysis Output Requirements

All analysis outputs must:
- Be saved as markdown files in repository root
- Include date/time stamps
- Use English language
- Provide probability assessments where applicable
- Include specific trigger levels for actionable scenarios
- Cite references to knowledge base sources

### Error Handling in Scripts

Scripts should:
- Check for API keys before making requests
- Validate date ranges and input parameters
- Provide helpful error messages to stderr
- Return proper exit codes (0 for success, 1 for errors)
- Support retry logic with exponential backoff for rate limits

## Language Considerations

- All SKILL.md files are in English
- Analysis outputs are in English
- Some reference materials (Stanley Druckenmiller Investment) include Japanese content
- README files available in both English (README.md) and Japanese (README.ja.md)
- User interactions may be in Japanese; analysis outputs remain in English

## Distribution Workflow

When skills are ready for distribution:

1. Test skill thoroughly in Claude Code
2. Package skill using skill-creator packaging script
3. Move .zip file to `zip-packages/`
4. Update README.md and README.ja.md with skill description
   - **Important:** Clearly indicate if the skill requires API subscriptions (FMP, FINVIZ Elite)
   - Include pricing information and sign-up links for required APIs
   - Specify if APIs are required, optional, or not needed
5. Commit changes with descriptive message

ZIP packages allow Claude web app users to upload and use skills without cloning the repository.

⚠️ **API Key Requirements in Distribution:**
- When distributing skills that require API keys, clearly document the requirements in the skill's SKILL.md
- Include setup instructions for both environment variables and command-line arguments
- Provide links to API registration and pricing pages
- Distinguish between required APIs (skill won't work without) and optional APIs (enhances performance)
