# Documentation Contributor Guide

This guide explains how to write and maintain articles in the `docs/` directory. Follow these conventions so that new pages look consistent, render correctly on the Jekyll site, and integrate smoothly with the bilingual (English / Japanese) structure.

---

## Table of Contents

- [Directory Structure](#directory-structure)
- [Page Types](#page-types)
- [YAML Frontmatter Reference](#yaml-frontmatter-reference)
- [Hand-Written Skill Guide (★) Template](#hand-written-skill-guide--template)
- [Auto-Generated Skill Guide Template](#auto-generated-skill-guide-template)
- [Bilingual (en/ja) Rules](#bilingual-enja-rules)
- [Styling Reference](#styling-reference)
- [Checklist: Adding a New Skill Guide](#checklist-adding-a-new-skill-guide)
- [Conventions and Pitfalls](#conventions-and-pitfalls)

---

## Directory Structure

```
docs/
├── _config.yml                  # Jekyll configuration (theme, callouts, search)
├── _includes/
│   └── nav_footer_custom.html   # EN/JP language toggle in sidebar
├── _sass/
│   └── custom/custom.scss       # Badge styles, hero, category cards
├── index.md                     # Root landing page (language selector)
├── en/                          # English documentation
│   ├── index.md                 # EN top page (parent for all EN children)
│   ├── getting-started.md
│   ├── skill-catalog.md         # Full catalog table (all skills)
│   └── skills/
│       ├── index.md             # Skill Guides index (★ legend, guide table)
│       ├── vcp-screener.md      # Example: hand-written ★ guide
│       └── sector-analyst.md    # Example: auto-generated guide
├── ja/                          # Japanese documentation (mirrors en/)
│   ├── index.md
│   ├── getting-started.md
│   ├── skill-catalog.md
│   └── skills/
│       ├── index.md
│       ├── vcp-screener.md      # Translated ★ guide
│       └── sector-analyst.md    # Untranslated stub
└── internal/                    # Internal docs (excluded from Jekyll build)
    ├── README.md
    └── revisions/
```

**Key points:**
- `en/` and `ja/` are parallel trees with identical file names.
- `internal/` is excluded from the site build via `_config.yml`.
- This README is for contributors on GitHub; it is not part of the published site navigation.

---

## Page Types

| Type | Location | Purpose |
|------|----------|---------|
| **Landing page** | `index.md` (root) | Language selector only |
| **Top page** | `en/index.md`, `ja/index.md` | Category cards, quick-start steps |
| **Getting Started** | `en/getting-started.md` | Installation, API setup, first-skill tutorial |
| **Skill Catalog** | `en/skill-catalog.md` | Full table of all skills with descriptions and API badges |
| **Skill Guide (★)** | `en/skills/<name>.md` | Hand-written 10-section detailed guide |
| **Skill Guide (auto)** | `en/skills/<name>.md` | Auto-generated from SKILL.md: overview, workflow, resources |

Hand-written guides are marked with ★ in `en/skills/index.md` and `ja/skills/index.md`.

---

## Skill Doc Ownership

The committed `docs/{en,ja}/skills/*.md` pages are the **source of truth** — the
generator does not own them retroactively (most pages, especially the JA
translations, were hand-curated after first generation).

- A page declares ownership via a `generated:` frontmatter key:
  `generated: true` = generator-owned (drift-gated); `generated: false` **or the
  key absent** = hand-maintained & protected. Skills in the generator's
  `HAND_WRITTEN` set are always protected.
- `generate_skill_docs.py --overwrite` **refuses** hand-maintained pages.
  `--force` is the only override and is **never** used in CI/pre-commit.
- The `skill-docs-drift` pre-commit hook + CI step run
  `generate_skill_docs.py --check`, which content-compares **only**
  `generated: true` pages and verifies every skill has EN+JA pages with a valid
  marker. It **never** reverts hand-maintained pages.
- A brand-new auto page created by the generator is stamped `generated: true`
  (gate-owned until a human hand-edits it and flips the marker to `false` /
  removes it). After adding or removing skills, re-run the generator to refresh
  `nav_order` on generator-owned pages.

> Skill-doc ownership is declared by the per-page `generated:` marker
> (introduced in #104). The earlier per-skill doc-ownership boolean in
> `skills-index.yaml` was removed as a follow-up cleanup.

---

## YAML Frontmatter Reference

Every page requires YAML frontmatter. Fields vary by page type.

### Skill Guide Frontmatter (en)

```yaml
---
layout: default
title: "Skill Name"          # Displayed in sidebar and browser tab
grand_parent: English        # Always "English" for en/ skill guides
parent: Skill Guides         # Always "Skill Guides" for en/ skill guides
nav_order: 44                # Position in sidebar (see numbering rules below)
lang_peer: /ja/skills/skill-name/   # URL of the Japanese version
permalink: /en/skills/skill-name/   # Explicit URL path
---
```

### Skill Guide Frontmatter (ja)

```yaml
---
layout: default
title: "Skill Name"          # Keep the English skill name as title
grand_parent: 日本語          # Always "日本語" for ja/ skill guides
parent: スキルガイド           # Always "スキルガイド" for ja/ skill guides
nav_order: 44                # Must match the en/ counterpart
lang_peer: /en/skills/skill-name/
permalink: /ja/skills/skill-name/
---
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `layout` | Yes | Always `default` |
| `title` | Yes | Page title. Use the English skill name even in ja/ pages |
| `grand_parent` | Yes (skills) | `English` or `日本語`. Omit for top-level pages |
| `parent` | Yes | `Skill Guides` (en) or `スキルガイド` (ja). For top-level pages, use `English` or `日本語` |
| `nav_order` | Yes | Numeric sidebar position. See [nav_order numbering](#nav_order-numbering) |
| `lang_peer` | Yes | Absolute URL path to the other-language version |
| `permalink` | Yes | Explicit URL path (prevents Jekyll auto-generation) |
| `has_children` | Conditional | Set to `true` only on index pages that have child pages |
| `nav_exclude` | Conditional | Set to `true` to hide from sidebar (used on root `index.md`) |

---

## Hand-Written Skill Guide (★) Template

Hand-written guides use a 10-section structure. This is the gold standard for documentation quality.

### Section Structure

```markdown
# Skill Name
{: .no_toc }

One-sentence description of what the skill does.
{: .fs-6 .fw-300 }

[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/<name>.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/<name>){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview
## 2. Prerequisites
## 3. Quick Start
## 4. How It Works
## 5. Usage Examples
## 6. Understanding the Output
## 7. Tips & Best Practices
## 8. Combining with Other Skills
## 9. Troubleshooting
## 10. Reference
```

### Section Guidelines

| Section | Content | Tips |
|---------|---------|------|
| **1. Overview** | What the skill does, what problem it solves, key features | Start with "what it solves" to hook the reader |
| **2. Prerequisites** | API keys, Python version, dependencies | Use `{: .api_required }` callout for API requirements |
| **3. Quick Start** | Minimal command to get first results | Include both CLI and natural-language prompt examples |
| **4. How It Works** | Internal pipeline, algorithm, phases | Use ASCII diagrams or numbered steps |
| **5. Usage Examples** | 4-6 real-world scenarios with prompts and expected output | Each example: Prompt → What happens → Why useful |
| **6. Understanding the Output** | Output file format, field definitions, rating tables | Use tables for score ranges and interpretations |
| **7. Tips & Best Practices** | Expert advice for getting the most value | Bullet list of actionable tips |
| **8. Combining with Other Skills** | Multi-skill workflows | Table format: Workflow name → Steps |
| **9. Troubleshooting** | Common errors and fixes | H3 per error scenario with Cause → Fix format |
| **10. Reference** | CLI arguments table, scoring component weights | Full table of all flags with defaults |

### Japanese ★ Guide Conventions

Japanese translations should:
- Keep the `# Skill Name` title in English (same as en/ version)
- Translate all section headings (e.g., "1. 概要", "2. 前提条件", "3. クイックスタート")
- Translate descriptions and explanations into natural Japanese
- Keep CLI commands, code blocks, and technical terms (API names, parameter flags) in English
- Use Japanese badge text: `API不要`, `FMP必須`, `FINVIZ任意`
- Use `目次` instead of `Table of Contents` in the TOC summary

Standard section heading translations:

| EN | JA |
|----|-----|
| 1. Overview | 1. 概要 |
| 2. Prerequisites | 2. 前提条件 |
| 3. Quick Start | 3. クイックスタート |
| 4. How It Works | 4. 仕組み |
| 5. Usage Examples | 5. 使用例 |
| 6. Understanding the Output | 6. 出力の読み方 |
| 7. Tips & Best Practices | 7. Tips & ベストプラクティス |
| 8. Combining with Other Skills | 8. 他スキルとの連携 |
| 9. Troubleshooting | 9. トラブルシューティング |
| 10. Reference | 10. リファレンス |

---

## Auto-Generated Skill Guide Template

Auto-generated guides are simpler and extracted from the skill's SKILL.md. They follow this structure:

```markdown
# Skill Name
{: .no_toc }

Description from SKILL.md frontmatter.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[Download Skill Package (.skill)](...){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View Source on GitHub](...){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview
## 2. When to Use
## 3. Prerequisites
## 4. Quick Start
## 5. Workflow
## 6. Resources
```

Auto-generated guides typically have 6 sections instead of 10. They lack the detailed examples, troubleshooting, and CLI reference found in ★ guides.

---

## Bilingual (en/ja) Rules

### Creating Both Versions

Every skill guide must have files in **both** `en/skills/` and `ja/skills/`:
- Same file name in both directories
- Same `nav_order` value in both
- `lang_peer` fields pointing to each other

### Fully Translated Page

Both files contain complete content in their respective languages. See `vcp-screener.md` for a reference implementation.

### Untranslated Stub (ja/)

If a Japanese translation is not yet available, create a stub page:

```markdown
---
layout: default
title: "Skill Name"
grand_parent: 日本語
parent: スキルガイド
nav_order: 44
lang_peer: /en/skills/skill-name/
permalink: /ja/skills/skill-name/
---

# Skill Name
{: .no_toc }

Description (can remain in English).
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

> **Note:** This page has not yet been translated into Japanese.
> Please refer to the [English version]({{ '/en/skills/skill-name/' | relative_url }}) for the full guide.
{: .warning }

---

[スキルパッケージをダウンロード (.skill)](...){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](...){: .btn .fs-5 .mb-4 .mb-md-0 }

[English版ガイドを見る]({{ '/en/skills/skill-name/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
```

### Language Toggle

The sidebar language toggle (`EN | JP`) is rendered automatically by `_includes/nav_footer_custom.html` when `lang_peer` is set.

---

## Styling Reference

### API Badges

```markdown
<!-- Required API -->
<span class="badge badge-api">FMP Required</span>

<!-- Optional API -->
<span class="badge badge-optional">FINVIZ Optional</span>

<!-- No API needed -->
<span class="badge badge-free">No API</span>

<!-- Workflow skill -->
<span class="badge badge-workflow">Workflow</span>
```

Japanese equivalents:

```markdown
<span class="badge badge-api">FMP必須</span>
<span class="badge badge-optional">FINVIZ任意</span>
<span class="badge badge-free">API不要</span>
<span class="badge badge-workflow">ワークフロー</span>
```

### Callouts

Four callout types are defined in `_config.yml`:

```markdown
> This is a note.
{: .note }

> This is a warning.
{: .warning }

> This is a tip.
{: .tip }

> FMP API key is required.
{: .api_required }
```

### Buttons

```markdown
<!-- Primary button (blue) -->
[Label](url){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }

<!-- Secondary button (outline) -->
[Label](url){: .btn .fs-5 .mb-4 .mb-md-0 }
```

### Table of Contents

Always use this exact pattern at the top of every page (after the subtitle):

```markdown
<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>
```

For Japanese pages, replace the summary text:

```markdown
<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>
```

### Internal Links

Always use Liquid's `relative_url` filter for internal links:

```markdown
<!-- Link to another page -->
[FinViz Screener]({{ '/en/skills/finviz-screener/' | relative_url }})

<!-- Link to Japanese version -->
[日本語版]({{ '/ja/skills/skill-name/' | relative_url }})
```

Never hardcode absolute URLs for internal pages. The `relative_url` filter ensures correct paths regardless of the `baseurl` setting.

### External Links (GitHub)

```markdown
<!-- Download button -->
[Download Skill Package (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/<name>.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }

<!-- Source link button -->
[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/<name>){: .btn .fs-5 .mb-4 .mb-md-0 }
```

### Code Blocks

Always specify the language for syntax highlighting:

````markdown
```bash
python3 skills/vcp-screener/scripts/screen_vcp.py --output-dir reports/
```

```python
import os
fmp_api_key = os.environ.get('FMP_API_KEY')
```

```yaml
---
layout: default
title: "Skill Name"
---
```
````

### Heading Exclusion

Use `{: .no_toc }` on the page title (H1) to exclude it from the auto-generated TOC:

```markdown
# Skill Name
{: .no_toc }
```

---

## Checklist: Adding a New Skill Guide

Follow these steps when adding a new skill guide page:

### 1. Create the English page

- [ ] Create `docs/en/skills/<skill-name>.md`
- [ ] File name: kebab-case, lowercase, matching the skill directory name
- [ ] Add YAML frontmatter (see [reference above](#skill-guide-frontmatter-en))
- [ ] Choose a `nav_order` number (see [numbering rules](#nav_order-numbering))
- [ ] Write content using the [★ template](#hand-written-skill-guide--template) or [auto template](#auto-generated-skill-guide-template)

### 2. Create the Japanese page

- [ ] Create `docs/ja/skills/<skill-name>.md` with matching file name
- [ ] Use the ja/ frontmatter pattern (see [reference above](#skill-guide-frontmatter-ja))
- [ ] Same `nav_order` as the en/ version
- [ ] Either translate fully or use the [untranslated stub pattern](#untranslated-stub-ja)

### 3. Update index pages

- [ ] Add the skill to `docs/en/skills/index.md` (Available Guides table)
  - Include ★ marker if hand-written
  - Include API badge
- [ ] Add the skill to `docs/ja/skills/index.md` (利用可能なガイド table)
  - Same ★ marker and badge

### 4. Update catalog pages

- [ ] Add the skill to the appropriate category in `docs/en/skill-catalog.md`
- [ ] Add the skill to the matching category in `docs/ja/skill-catalog.md`

### 5. Verify

- [ ] `lang_peer` links are correct in both directions
- [ ] `permalink` paths match the file locations
- [ ] `nav_order` does not conflict with existing pages
- [ ] API badges are consistent across index, catalog, and guide pages
- [ ] All internal links use `{{ '...' | relative_url }}` syntax

---

## Conventions and Pitfalls

### nav_order Numbering

Current `nav_order` assignments for top-level en/ pages:

| nav_order | Page |
|-----------|------|
| 1 | Getting Started |
| 2 | Skill Catalog |
| 3 | Skill Guides (index) |

Skill guide pages use `nav_order` values from 1 to ~50. To avoid conflicts:
1. Check existing values in `docs/en/skills/` before assigning
2. Use the next available number
3. Ensure en/ and ja/ versions use the **same** `nav_order`

### File Naming

- Always use **kebab-case**: `vcp-screener.md`, not `VCP_Screener.md`
- The file name should match the skill directory name under `skills/`
- Never include spaces in file names

### Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Forgetting `lang_peer` | No language toggle in sidebar | Add the field pointing to the counterpart |
| Missing `permalink` | Jekyll generates unexpected URL paths | Always set explicit `permalink` |
| Mismatched `nav_order` | EN and JA pages appear at different sidebar positions | Use identical values |
| Hardcoded internal URLs | Links break if `baseurl` changes | Use `{{ '...' | relative_url }}` |
| Forgetting to update index pages | New guide is invisible in the guide listing | Update both `en/skills/index.md` and `ja/skills/index.md` |
| Forgetting to update catalog | Skill missing from the catalog overview | Update both `en/skill-catalog.md` and `ja/skill-catalog.md` |
| Using `{:toc}` without `{: .no_toc }` on H1 | Page title appears redundantly in TOC | Add `{: .no_toc }` after the H1 |
| Badge inconsistency | Confusing API requirement information | Keep badges identical across guide, index, and catalog |

### Content Language Rules

- **English pages (`en/`)**: All content in English
- **Japanese pages (`ja/`)**: Descriptions and explanations in Japanese; code, CLI commands, parameter names, and technical terms remain in English
- **Skill titles**: Always in English in both en/ and ja/ pages (for searchability)
- **API badge text**: Localized (`FMP Required` vs `FMP必須`)

### Jekyll Build Notes

- This `docs/README.md` is visible on GitHub but will also be processed by Jekyll. It is not linked in the site navigation because it has no `parent` or `nav_order` frontmatter.
- `docs/internal/` is excluded from the build via `_config.yml`.
- Custom callout types (`warning`, `note`, `tip`, `api_required`) are defined in `_config.yml` under the `callouts` key.
- Custom badge CSS classes (`badge-free`, `badge-api`, `badge-optional`, `badge-workflow`) are defined in `_sass/custom/custom.scss`.
