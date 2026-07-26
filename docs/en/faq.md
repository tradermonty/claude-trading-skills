---
layout: default
title: Frequently Asked Questions
parent: English
nav_order: 10
lang_peer: /ja/faq/
permalink: /en/faq/
---

# Frequently Asked Questions
{: .no_toc }

Answers to common first-timer questions about installing, running, and safely
interpreting Claude Trading Skills.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Q01. Do I need to know how to code?

No. The packaged Claude Web path requires no code: download a `.skill` file,
upload it, and describe the task in ordinary language. Some skills also include
Python helper scripts, and the Claude Code path assumes that you are comfortable
with files and a terminal. Start with the
[Claude Web instructions]({{ '/en/getting-started/' | relative_url }}) if you
want the simplest route.

## Q02. Which Claude plan or account do I need?

Anthropic currently lists Skills for Free, Pro, Max, Team, and Enterprise
accounts in its
[official Skills help](https://support.claude.com/en/articles/12512180-use-skills-in-claude).
Team and Enterprise availability can also depend on organization settings.
Claude Code is a separate product path: the Claude.ai Free plan does not include
Claude Code, and its supported account options are maintained in the
[Claude Code setup guide](https://code.claude.com/docs/en/getting-started).

## Q03. Should I use Claude Web or Claude Code?

Use Claude Web when you want to upload one packaged skill and work through a
conversation without managing a repository. Use Claude Code when you want the
full source tree, local helper scripts, repeatable file-based workflows, or to
customize a skill. The analysis goals are similar, but installation and tool
access differ between the two surfaces.

## Q04. Which skill should I try first?

Try FinViz Screener. Its basic path accepts a natural-language screening request
and builds a FinViz filter URL without an API key. The
[Getting Started tutorial]({{ '/en/getting-started/' | relative_url }}) walks
through an example. Other no-paid-data starting points are listed there as well.

## Q05. Do I need a paid market-data service or broker API?

Not for every workflow. FMP, FINVIZ Elite, and Alpaca are optional or
skill-specific integrations; several skills work from public CSVs, screenshots,
or local files. Check the `integrations` field for the selected skill in
`skills-index.yaml` before starting. “No API” still means that you must supply
the input data named by that skill.

## Q06. What will it cost?

Repository use does not create a subscription charge by itself. Your cost
depends on the Claude surface and plan you choose, plus any optional data
services. Check [Claude's current pricing](https://claude.com/pricing) and each
data provider directly rather than relying on amounts copied into this
repository, because access and prices can change.

## Q07. Will a skill trade automatically or send broker orders?

No. This repository supports research, screening, position sizing, journaling,
and rebalancing proposals; it does not place orders. Even when a skill reads
portfolio data from Alpaca, a human must review the output and separately
confirm and execute any trade with the broker. Test unfamiliar workflows with
non-production data first.

## Q08. Is the output financial advice?

No. The material is educational and research-oriented and is not financial advice,
a recommendation, or a guarantee of performance. Treat every result as an input
to your own decision process. Verify calculations, assumptions, liquidity,
taxes, and account constraints before acting, and consult a qualified
professional when appropriate.

## Q09. How should I handle API keys and private portfolio data?

Keep credentials in environment variables or an approved secret manager. Never
paste them into prompts, commit them to Git, or store them in generated reports.
Use the narrowest permissions available and prefer paper or sandbox credentials
while testing. If a secret is exposed, revoke or rotate it immediately. Review
each skill's inputs and outputs before supplying private account data.

## Q10. Can I ask questions in Japanese?

Yes. You can write a Japanese prompt even when a skill contains English
technical terms. Include the ticker, time frame, input source, and desired output
format explicitly. This site provides matched English and Japanese guides so
you can compare terminology when needed.

## Q11. How reliable are the results?

No skill can guarantee complete or correct results. Market data can be delayed,
missing, revised, or interpreted differently across providers. Check the source
and timestamp, inspect warnings and assumptions, reproduce important
calculations, and compare the result with an independent source before making a
decision.

## Q12. What should I check if a skill does not appear or run?

For Claude Web, confirm that Code execution and file creation is enabled, then
open Customize > Skills and check that the uploaded skill is listed and toggled
on. For Claude Code, confirm that the skill folder contains `SKILL.md` in the
expected skills directory and reload after creating a new top-level skills
directory. If the skill starts but fails, read its prerequisites for required
files, Python dependencies, and API credentials.
