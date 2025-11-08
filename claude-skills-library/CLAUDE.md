# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is a **Claude Skills Library** - a collection of professional Claude Code skills for various domains. Each skill extends Claude's capabilities with specialized knowledge, workflows, and tools. Skills are self-contained packages that follow a standardized structure and can be distributed as `.zip` files.

## Skill Architecture

### Standard Skill Structure

Every skill follows this three-tier structure:

```
skill-name/
├── SKILL.md              # Main skill documentation (metadata + workflow)
├── scripts/              # Executable code (Python/Bash)
├── references/           # Documentation loaded on-demand to inform decisions
└── assets/               # Templates and boilerplate files used in output
```

**Progressive Disclosure Pattern:**
1. **Metadata** (in SKILL.md frontmatter): When to use the skill
2. **SKILL.md**: Core workflows and instructions
3. **Resources**: Loaded on-demand as needed (references for guidance, scripts for execution, assets for output generation)

### Resource Directory Purposes

- **`scripts/`**: Executable code that performs automation, data processing, or specific operations. May be executed without loading into context.

- **`references/`**: Documentation intended to be loaded into Claude's context to inform process and thinking. Examples: methodology guides, API references, schemas, detailed workflows.

- **`assets/`**: Files not loaded into context, but used within Claude's output. Examples: templates, boilerplate code, document templates.

## Common Development Commands

### Creating a New Skill

```bash
# Initialize new skill structure
python /Users/takueisaotome/.claude/plugins/marketplaces/anthropic-agent-skills/skill-creator/scripts/init_skill.py <skill-name> --path ./

# This creates:
# - skill-name/ directory with standard structure
# - SKILL.md with template and structure guidance
# - Empty scripts/, references/, assets/ directories
```

### Packaging a Skill

```bash
# Package skill into distributable .zip
python3 /Users/takueisaotome/.claude/plugins/marketplaces/anthropic-agent-skills/skill-creator/scripts/package_skill.py ./skill-name ./

# This:
# 1. Validates skill structure (checks SKILL.md exists, runs quick_validate)
# 2. Creates skill-name.zip in specified output directory
# 3. Includes all files with proper relative paths
```

### Validating a Skill

```bash
# Quick validation before packaging
python3 /Users/takueisaotome/.claude/plugins/marketplaces/anthropic-agent-skills/skill-creator/scripts/quick_validate.py ./skill-name
```

## Current Skills in Library

| Skill | Version | Domain | Key Components |
|-------|---------|--------|----------------|
| data-scientist | 1.0 | Data Science | auto_eda.py, model_comparison.py, timeseries_analysis.py |
| project-manager | 1.0 | Project Management | project_health_check.py, PMBOK templates, EVM analysis |
| business-analyst | 1.0 | Business Analysis | business_analysis.py, BABOK templates, stakeholder analysis |
| data-visualization-expert | 1.0 | Data Visualization | create_visualization.py, visualization_templates.py, color_palettes.json |
| vendor-estimate-reviewer | 1.0 | Vendor Estimate Evaluation | analyze_estimate.py, review_checklist.md, cost_estimation_standards.md, risk_factors.md |
| vendor-rfq-creator | 1.0 | RFQ Creation | rfq_checklist_ja.md, rfq_template_ja.md |
| vendor-estimate-creator | 1.0 | Cost Estimation | estimation_methodology.md, effort_estimation_standards.md, roi_analysis_guide.md, estimate_template_ja.md |
| project-plan-creator | 1.0 | Project Planning | project_charter_guide.md, project_plan_template.md (with 5 Mermaid diagrams) |
| bug-ticket-creator | 1.0 | Bug Reporting, QA | defect_classification_guide.md, severity_priority_guide.md, reproduction_steps_guide.md, bug_ticket_template_ja.md, bug_ticket_template_en.md |
| itil4-consultant | 1.0 | IT Service Management, ITIL 4 | 34 Practices knowledge base (4 comprehensive guides), Maturity assessment framework, 5 consulting workflows, Department-specific scenarios |
| mermaid-to-pdf | - | Documentation | markdown_to_pdf.py, mermaid_to_image.py |
| uat-testcase-generator | - | QA Testing | generate_uat_testcases.py, Excel generation |
| salesforce-cli-expert | - | Salesforce | CLI reference guide |

## Skill Development Workflow

### 1. Initialize Skill Structure

Use `init_skill.py` to create the standardized directory structure with SKILL.md template.

### 2. Choose Structure Pattern

The SKILL.md template provides guidance on 4 structure patterns:
- **Workflow-Based**: Sequential step-by-step processes
- **Task-Based**: Different operations/capabilities
- **Reference/Guidelines**: Standards or specifications
- **Capabilities-Based**: Multiple interrelated features

Choose pattern(s) that fit your skill's purpose. Most skills combine patterns.

### 3. Develop Skill Components

**SKILL.md Guidelines:**
- Use imperative/infinitive form (verb-first instructions)
- Include clear "When to Use" section with specific scenarios
- Provide concrete examples and workflows
- Reference bundled resources appropriately

**Add Resources:**
- `scripts/`: Add executable Python/Bash scripts for automation
- `references/`: Add methodology guides, best practices, API docs
- `assets/`: Add templates, boilerplate, document templates

### 4. Package and Distribute

Use `package_skill.py` to create distributable `.zip` file. Validation runs automatically before packaging.

### 5. Update Repository Documentation

After creating a skill, update `README.md` with:
- Entry in "Available Skills" section with overview
- Entry in "Skill Catalog" table
- Deep dive section with workflows, examples, and best practices
- Version history entry

## Key Standards and Frameworks

Skills in this library follow industry standards:

- **Data Science**: 7-phase analysis workflow, statistical rigor, proper train/test splits
- **Project Management**: PMBOK® Guide v3 (10 knowledge areas, 5 process groups)
- **Business Analysis**: BABOK® Guide v3 (6 knowledge areas)
- **Requirements**: ISO/IEC/IEEE 29148 compliant documentation
- **Process Modeling**: BPMN notation, value stream mapping

## File Organization

```
claude-skills-library/
├── README.md                    # Comprehensive skill documentation
├── CLAUDE.md                    # This file
├── skill-name/                  # Skill source folders
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   └── assets/
├── skill-name.zip               # Packaged skills (root level)
└── zip-packages/                # Alternative location for packaged skills
```

**Note**: Packaged `.zip` files are typically placed in repository root for easy distribution.

## Python Script Patterns

Many skills include Python automation scripts. Common patterns:

### CLI Interface Pattern
```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tool description")
    parser.add_argument("input_file", help="Input file path")
    parser.add_argument("--output", "-o", help="Output directory")
    args = parser.parse_args()
```

### Class-Based Analyzers
```python
class FinancialAnalyzer:
    @staticmethod
    def calculate_roi(total_benefit: float, total_cost: float) -> float:
        """Calculate Return on Investment"""
        return ((total_benefit - total_cost) / total_cost) * 100
```

### Data Processing Pattern
```python
def profile_dataset(df: pd.DataFrame) -> Dict:
    """Generate comprehensive data profile with quality metrics"""
    # Analysis logic
    return profile_dict
```

## Template Standards

Templates in `assets/` directories follow professional standards:

- **BRD/Requirements**: ISO/IEC/IEEE 29148 compliant structure
- **Business Cases**: Include ROI, NPV, IRR, Payback Period calculations
- **Reports**: Structured sections with clear headers, tables, and metrics
- **Process Documentation**: BPMN notation, swimlane diagrams

## Skill Metadata Format

SKILL.md frontmatter (YAML):
```yaml
---
name: skill-name
description: Complete and informative explanation of what the skill does and when to use it. Include WHEN to use this skill - specific scenarios, file types, or tasks that trigger it.
---
```

The `description` field is critical - it determines when Claude Code automatically suggests the skill.
