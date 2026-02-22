# Documentation Directory

This directory contains project-wide documentation, revision histories, and improvement records.

## Directory Structure

```
docs/
├── README.md (this file)
├── kanchi-dividend-skills-runbook.md
└── revisions/
    └── bubble-detector-v2.0-revision.md
```

## `revisions/`

Contains detailed revision and improvement records for each skill.

### Files:

- **`bubble-detector-v2.0-revision.md`** - Comprehensive improvement summary for Bubble Detector skill v2.0
  - Problems identified (4 key issues)
  - Solutions implemented
  - Comparison of improvements (10 points → 3 points case study)
  - Important lessons learned
  - Next steps

## Usage

When making significant improvements to a skill:

1. Document the revision in `docs/revisions/[skill-name]-[version]-revision.md`
2. Include:
   - Problems identified
   - Solutions implemented
   - Before/after comparison
   - Lessons learned
3. Reference the revision document in the skill's main documentation if needed

## Related Directories

- `/[skill-name]/references/` - Skill-specific reference materials
- `/[skill-name]/SKILL.md` - Main skill definition (auto-loaded by Claude Code)

## Runbooks

- **`kanchi-dividend-skills-runbook.md`** - 運用順序固定用の手順書
  - 3スキルの実行順序 (`SOP -> 監視 -> 税務/口座配置`)
  - 日次/週次/月次/四半期/年次の運用リズム
  - スキル間の入力/出力受け渡し
