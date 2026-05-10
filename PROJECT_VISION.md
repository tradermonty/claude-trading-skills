# Claude Trading Skills Project Vision

Version: 0.1
Last updated: 2026-05-03

Japanese version: [PROJECT_VISION.ja.md](PROJECT_VISION.ja.md)

Claude Trading Skills is a Claude Skills-based trading process OS for time-constrained individual investors.

It helps investors use long-term investing as their foundation, take disciplined swing-trading opportunities only when market conditions allow, and improve continuously through risk management, journaling, and review.

## 1. Mantra

**Empower solo traders, growing together.**

This project exists to help individual traders move beyond isolated discretionary decisions and build repeatable processes, explicit risk management, journaling, review, and continuous improvement loops with Claude Skills.

Here, **solo** does not mean isolated. The project is designed for traders who make their own decisions and take their own risk, while allowing workflows, reviews, and improvement practices to grow through shared practice.

## 2. Important Notice and Disclaimer

This repository provides Claude Skills and related materials for educational, research, and process-improvement purposes. It does not provide financial advice, investment advisory services, trading signals, broker execution, tax advice, or legal advice.

Investing and trading involve risk, including loss of principal. Historical data, backtests, screening results, sample reports, and AI-generated analysis do not guarantee future results. All trading decisions, position sizing, risk management, tax/regulatory compliance, and broker usage decisions are solely the user's responsibility.

This project is provided under the MIT License. The software and materials are provided **"AS IS, WITHOUT WARRANTY"**, as stated in the license.

## 3. Origin and Why It Is Open Source

This project started because the author wanted to use AI to improve his own trading process.

For individual traders, especially those who invest and trade while also having work, family, or other life responsibilities, time, information overload, emotional control, and risk management are real constraints. Claude Trading Skills was created to make it easier to maintain a process for market review, candidate generation, trade planning, risk management, journaling, and review under those constraints.

The project is first and foremost a practical tool that the author uses daily and weekly. It exists to improve the author's own trading process, build a more resilient decision process, and keep learning from records and reviews. At the same time, it is open source because the same workflows may be useful to other people facing similar constraints.

The stance is **first for self, open for others**. The first user is the author. Even when outside feedback is limited, the project should keep improving as a tool the author actually uses. On top of that, the project aims to let workflows, reviews, and improvement practices accumulate as shared practical knowledge for individual traders.

Claude Trading Skills does not provide a finished formula for winning. The author is also a trader still learning. This repository is not a place to hand out "answers." It is a place to share practical workflows that help individual traders strengthen their judgment, manage risk, learn from records, and improve gradually.

## 4. Core Thesis

The goal of this project is not to predict markets better than everyone else.

The goal is to help individual investors and traders make decisions that are more structured, risk-aware, reviewable, and improvable.

The core flow of this project is not:

```text
Ask -> Signal -> Trade
```

The core loop is:

```text
Plan -> Trade -> Record -> Review -> Improve
```

Claude Trading Skills is not a signal engine. It aims to be a **decision-process OS** that helps individual traders use AI to build a more resilient decision process while consistently managing judgment, risk, records, and improvement.

## 5. Purpose

Claude Trading Skills is a repository of Claude Skills focused on US stocks, ETFs, dividend investing, swing trading, macro analysis, and strategy research, with options and event-driven strategies included where appropriate.

The skills support decisions such as:

- Understanding market conditions
- Screening trade or investment candidates
- Building trade plans
- Calculating position size
- Reviewing portfolio risk
- Recording trade hypotheses
- Reviewing outcomes and identifying improvements
- Testing new strategy ideas

The project is not merely a collection of useful analysis tools. It aims to be a **decision-support system** for individual traders.

In particular, it aims to help individual investors who use long-term investing as their base and want to use limited time efficiently for swing trading when market conditions allow, without taking excessive risk and while improving through records and review.

## 6. What This Project Is / Is Not

| This project is | This project is not |
| --- | --- |
| A decision-support system | Financial advice or investment advisory service |
| A trading workflow toolkit | A buy/sell signal service |
| A risk management and review framework | A profit guarantee system |
| A Claude Skills repository | A broker execution platform |
| A system that supports the trader's learning loop | A fully automated trading bot |

This project does not replace the trader's judgment. It helps make the trader's decision process explicit, repeatable, reviewable, and improvable.

Final decisions and risk responsibility always remain with the user. The detailed disclaimer is centralized in "Important Notice and Disclaimer," and this stance should not change as the project grows.

## 7. Target Users

The primary audience is **time-constrained individual investors and swing traders**.

More specifically, the project is designed for people who use long-term investing and dividend investing as the foundation for wealth building, while seeking additional return through short- to medium-term swing trades when market conditions are favorable. They have work, family, or life constraints, so they need to make daily decisions more efficient and systematize risk management and journaling.

### Primary Users

The first users to prioritize are:

| Persona | Main Goal | Needed Path |
| --- | --- | --- |
| Part-time swing trader | Daily market review, candidate generation, trade planning | `market-regime-daily` / `swing-opportunity-daily` |
| Growth investor who wants stronger risk control | Separate offensive markets from defensive markets | `market-regime` / `exposure` workflow |
| Dividend and long-term investor | Find dividend stocks, review holdings, check portfolio structure | `core-portfolio` / `dividend-income` |

### Secondary / Advanced Users

The project can also support:

| Persona | Main Goal | Needed Path |
| --- | --- | --- |
| Event / earnings trader | Find opportunities after earnings, news, or economic events | `advanced-satellite` / `earnings-event` |
| Short-strategy trader | Monitor weak stocks or overextended stocks in risk-off environments | `advanced-satellite` / `risk-off-short` |
| Strategy researcher / developer | Test hypotheses and improve strategies | `strategy-research` |
| Advanced user | Extend custom workflows, YAML manifests, and CLI tools | manifests / scripts / API matrix |

This project is not primarily designed for:

- Users expecting fully automated trading
- Users who want guaranteed profit or outsourced trading signals
- Users who do not want to manage risk or keep records
- Users focused only on short-term scalping

## 8. Core + Satellite Operating Philosophy

The primary user of this project operates with a **Core + Satellite** structure:

- **Core**: Long-term investing, dividend stocks, ETFs, portfolio management
- **Satellite**: Swing trading, themes, breakouts, post-earnings momentum
- **Advanced Satellite**: Short strategies, event strategies, options strategies where appropriate
- **Shared Layer**: Market regime, risk management, position sizing, journaling, review

The key is not to mix the purpose, timeframe, and risk profile of Core and Satellite activities.

This project provides an operating process for individual investors who use long-term wealth building as the foundation and seek disciplined short- to medium-term trading opportunities only when market conditions allow.

Advanced Satellite includes areas with higher risk, more complex assumptions, or additional execution constraints. Short strategies, event strategies, and options strategies should only be used with sufficient experience, explicit loss limits, manual review, understanding of API and broker constraints, and pre-validated workflows. A heavily implemented skill is not necessarily part of the first recommended path for the primary user.

## 9. Current State

This repository already contains many skills. Broadly, they cover:

- **Market analysis**: Market regime, breadth, sectors, macro, news, bubble risk
- **Screening**: CANSLIM, VCP, dividend stocks, post-earnings momentum, themes, institutional flows
- **Trade planning**: Breakouts, Parabolic Short, position sizing, exposure management
- **Portfolio and records**: Portfolio management, hypothesis tracking, trade records, postmortems
- **Strategy research**: Backtesting, strategy idea generation, edge research pipeline
- **Quality and meta-skills**: Skill design, review, integration testing, improvement loops

Individual skills have become substantial. From a user's perspective, several problems remain:

- It is hard to know which skill to use
- It is hard to see how multiple skills should be sequenced
- The full before-and-after trade workflow is not yet clearly packaged
- GitHub and `.skill` files can be intimidating for less technical users
- Skill outputs are not yet fully connected to a continuous learning loop

The next stage is less about adding more skills and more about **bundling skills into usable forms**, **guiding users to the right path**, and **turning them into operational workflows**.

## 10. Strategic Direction: From Skill Collection to Trading OS

The next direction of the project can be summarized as:

> From a skill collection to a Trading OS for solo traders.

By Trading OS, we mean a workflow layer that connects market context, risk budgeting, strategy selection, candidate generation, trade planning, manual execution gates, journaling, review, and improvement for daily and weekly investment decisions.

This Trading OS is not meant to make individual traders win easily. It is meant to help them stay in the game, manage risk, learn from records, and improve their decision process gradually, even with limited time.

The ideal experience looks like this:

1. A user describes what kind of trading or investing they want to do in natural language
2. The system understands their goals, experience, time budget, risk tolerance, and API environment
3. It recommends an appropriate skillset and workflow
4. The user can review market conditions, risk, candidates, and trade plans in order
5. After the trade, the user records the hypothesis and outcome, then feeds the lessons into the next iteration

If this flow works, even users who are not comfortable with GitHub or tool setup can access the value of the project step by step.

## 11. Project Architecture

The project should be organized in these layers:

```text
1. Individual Skills
    |
2. Skill Inventory / API Matrix
    |
3. Skillsets
    |
4. Workflows
    |
5. Trading Skills Navigator
    |
6. User Entry Points
    |
7. Journal / Postmortem / Learning Loop
```

Each layer has a distinct role:

| Layer | Role |
| --- | --- |
| Skills | Small specialist capabilities for analysis, calculation, planning, and records |
| Skill Inventory / API Matrix | The single source of truth for use cases, required APIs, difficulty, and inputs/outputs |
| Skillsets | Purpose-specific bundles that define which skills belong together |
| Workflows | Operational sequences, decision gates, and artifact handoffs |
| Navigator | An interactive guide that recommends skillsets and workflows based on user goals |
| User Entry Points | Docs, starter prompts, CLI, future web UI, and other ways to start using the project |
| Learning Loop | Journaling, review, and improvement mechanisms that grow both the skills and the trader |

This structure reduces drift between skill source files, documentation, recommendation logic, and workflows. The Navigator provides interactive recommendations, while User Entry Points provide static docs, starter prompts, CLI tools, and future web UI paths.

## 12. Roadmap

### Phase 0: Vision and Metadata — ✅ partially complete (2026-05-09)

> **Status:** `skills-index.yaml` lands as the SSoT in PR #84. All 54 skills carry id / display_name / category / status / summary / integrations[]. timeframe / difficulty fill-in remains follow-up work.

First, organize the existing skill set and make the overall project easier to explain.

Main tasks:

- Document the project vision and roadmap
- Create `skills-index.yaml` or `skills-inventory.yaml`
- Update skill list, categories, and API requirements
- Structure each skill's use case, timeframe, difficulty, and required APIs
- Clean up stale descriptions and duplicated wording

Definition of done:

- `PROJECT_VISION.md` and `PROJECT_VISION.ja.md` exist
- `skills-index.yaml` or `skills-inventory.yaml` exists
- All skills have initial classifications for category, use case, required API, difficulty, and timeframe
- The API requirements matrix is current
- Docs are consistent with the actual number of skills, categories, and descriptions

### Phase 1: Trading Skills Navigator v0

Create a meta-skill that acts as the guide for this repository.

When the user says, "I want to do X," the Navigator recommends the right skills, combinations, setup path, and workflow.

Phase 1 focuses on interactive AI recommendations. It should guide users toward the right skillset and workflow based on their goals, experience, time budget, and API environment.

Example questions:

- "I want to invest long term but swing trade only when the market is favorable"
- "I have 15 minutes each morning and want to know whether I can take risk today"
- "I want to separate long-term holdings from short-term trading risk"
- "I want to review my holdings and dividend candidates this week"
- "I want to do swing trading"
- "I want to find dividend stocks"
- "I want to use short strategies"
- "I want to know what works without API keys"
- "I want a beginner-friendly starting path"

Definition of done:

- `skills/trading-skills-navigator/` exists
- It can return a recommended skillset and workflow for 10 representative user questions
- It can separate API-key and no-API paths
- It can explain setup paths for Claude Web App and Claude Code

### Phase 2: Skillsets

Create purpose-specific manifests that bundle skills.

Initial candidates:

- `core-portfolio`
- `market-regime`
- `swing-opportunity`
- `trade-memory-loop`
- `dividend-income`
- `strategy-research`
- `advanced-satellite`

`advanced-satellite` includes higher-complexity strategies such as risk-off short, earnings event, options, and thematic momentum.

Definition of done:

- YAML manifests exist for the 7 major skillsets
- Each skillset defines required / recommended / optional skills
- Each skillset documents target users, timeframe, required APIs, and when not to use it
- The Navigator can use skillset manifests for recommendations

### Phase 3: Workflows — ✅ partially complete (2026-05-09)

> **Status:** PR #85 ships the 5 Core + Satellite manifests (`core-portfolio-weekly`, `market-regime-daily`, `swing-opportunity-daily`, `trade-memory-loop`, `monthly-performance-review`) under `workflows/`, validated by `--strict-workflows`. Advanced workflows (`risk-off-short-daily`, `earnings-weekly`, `strategy-research-pipeline`) remain follow-up.

Skillsets are not enough for real operations. Trading requires sequence, decision gates, and artifact handoffs.

A typical workflow:

1. **Market Context**: Review market conditions
2. **Risk Budget**: Decide how much risk to take
3. **Strategy Selection**: Select which strategy is allowed today
4. **Candidate Generation**: Find candidates
5. **Trade Planning**: Define entry / stop / target / size
6. **Manual Execution Gate**: Review before any real order
7. **Monitoring**: Monitor triggers and invalidation
8. **Journal / Postmortem**: Record and review

Initial candidates:

- `core-portfolio-weekly`
- `market-regime-daily`
- `swing-opportunity-daily`
- `trade-memory-loop`
- `monthly-performance-review`

Advanced workflow candidates:

- `risk-off-short-daily`
- `earnings-weekly`
- `macro-morning-brief`
- `strategy-research-pipeline`

Definition of done:

- At least 3 operational workflows are defined in YAML
- Each workflow has inputs, outputs, decision gates, skills used, and manual review items
- There is a daily / weekly path that a part-time trader can run in 15-60 minutes
- Each trade workflow connects to a journal entry or postmortem
- At least 1 workflow can be explained end-to-end with sample data

### Phase 4: User-Friendly Entry Points

Make the project easier for users who are not comfortable with GitHub or `.skill` files.

Phase 4 focuses on static entry points and distribution paths. It should provide docs, quickstarts, starter prompts, CLI tools, and eventually web UI paths so a new user can start even without the Navigator.

Candidates:

- Core + Satellite quickstart
- "Find Your Workflow" document
- 15-minute daily routine
- 60-minute weekly review
- Starter prompts
- Skill download checklist
- API setup guide
- `scripts/recommend_skills.py`
- Static recommender page

Definition of done:

- A new user can choose a starting route within 5 minutes
- No-API and FMP / Alpaca paths are clearly separated
- A user can tell which `.skill` files to upload to Claude Web App
- Starter prompts are available for first use

### Phase 5: Learning Loop

Strengthen the mechanisms for recording trade outcomes and feeding them back into improvement.

Target loop:

```text
Plan -> Trade -> Record -> Review -> Improve -> Adjust Workflow
```

Related skills:

- `trader-memory-core`
- `signal-postmortem`
- `backtest-expert`
- `edge-signal-aggregator`
- `skill-integration-tester`
- `dual-axis-skill-reviewer`

Definition of done:

- At least 1 sample operating example exists for Plan -> Trade -> Record -> Review -> Improve
- Trade journal and postmortem templates are available
- The system can record which skill-derived signal or workflow input worked
- Failure cases can feed into workflow or skillset improvements

## 13. Success Metrics

Project success should not be measured only by returns or hit rate. The key question is whether the process is actually used, improved, and sustained.

Initial observable metrics:

- The author has used at least one of `market-regime-daily`, `core-portfolio-weekly`, or `trade-memory-loop` for 3+ months
- At least 3 workflows are defined in YAML or Markdown with inputs, outputs, decision gates, and record destinations
- At least 80% of major skills are registered in `skills-index.yaml` or `skills-inventory.yaml` with category, use case, required API, difficulty, and timeframe
- Trading Skills Navigator v0 returns reasonable skillset / workflow recommendations for 10 representative user questions under human review
- At least 80% of primary-path skills used by `core-portfolio`, `market-regime`, `swing-opportunity`, and `trade-memory-loop` pass the initial quality gate
- At least 1 public sample operating example tracks Plan -> Trade -> Record -> Review -> Improve

Future external metrics:

- Real users provide workflow improvement feedback through GitHub issues, PRs, discussions, X, or similar channels
- A new user can choose a starting route from README or quickstart within 5 minutes
- Both no-API and FMP / Alpaca paths are verified to work

## 14. Design Principles

Future development should follow these principles:

1. **Process over prediction**
   - Prioritize repeatable decision processes over predictions themselves.

2. **Risk first**
   - Review market conditions and risk budget before candidates or signals.

3. **Human judgment stays central**
   - The project supports human judgment; it does not automate trading decisions.

4. **Recommendations must be explainable**
   - The system should explain why a skill, workflow, or risk setting is suggested.

5. **Compose small skills**
   - Prefer small, focused skills composed together over large all-purpose skills.

6. **Accessible for beginners, extensible for advanced users**
   - Provide simple entry paths for non-GitHub users while keeping room for deep customization.

7. **Record and improve**
   - A trade does not end at execution; it ends when it is recorded, reviewed, and used for improvement.

8. **Maintain a single source of truth**
   - Skill metadata should live in as few canonical places as possible. Catalogs, API matrices, Navigator recommendations, and workflow manifests should be generated from or validated against shared metadata where possible.

## 15. Near-Term Priorities

Near-term work should proceed in this order:

- ✅ **Done (2026-05-09)**: Project vision documents (`PROJECT_VISION.md` / `PROJECT_VISION.ja.md`)
- ✅ **Done (2026-05-09)**: `skills-index.yaml` SSoT + validator (PR #84)
- ✅ **Done (2026-05-09)**: 5 core workflow manifests under `workflows/` (PR #85)
- ✅ **Done (2026-05-09)**: Auto-generated workflow doc pages (PR #86)
- **Now**: Fill in `timeframe` / `difficulty` for all 54 skills (gates `--strict-metadata`)
- **Next**: Create Trading Skills Navigator
- **Next**: Define major skillsets in YAML
- **Next**: Add advanced workflow manifests (`risk-off-short-daily`, `earnings-weekly`, `strategy-research-pipeline`)
- **Next**: Create "Find Your Workflow" documentation
- **Later**: Add bundle builder or recommender CLI if needed
- **Later**: Explore a web app proof of concept

It is safer to build structured knowledge and a guide first, rather than jumping directly to web apps or bundle ZIPs.

## 16. Community and Governance

This project is published under the MIT License. Issues and PRs are welcome, but the project does not handle requests for financial advice, individual buy/sell recommendations, or profit guarantees.

Helpful contributions include:

- Workflow recipe improvements
- Skill metadata and API requirement fixes
- Documentation, starter prompt, and quickstart improvements
- Tests, fixtures, and runbooks
- Practical pitfalls and improvement ideas found through real use

For now, discussion and coordination should happen through GitHub Issues and Pull Requests. Rather than trying to grow a large community quickly, the project prioritizes keeping the tool useful for the author's own practice and accumulating improvements from actual use.

## 17. Long-Term Vision

Long term, this project should become a place where:

- Individual traders can find strategies and workflows that fit them
- Market regime can guide risk exposure
- Trade plans are explicit before execution
- Results are recorded after trades and used for learning
- Skills and workflows improve through practice
- Beginners have approachable entry points and advanced users have room to extend

Eventually, users should be able to share workflow recipes, postmortem templates, strategy research notes, and skill improvement proposals so individual traders' practical knowledge can improve the whole project.

The essence of this project is not to hand traders an "answer."

It is to create an environment where traders can strengthen their judgment, manage risk, learn from records, and grow continuously.

**Empower solo traders, growing together.**
