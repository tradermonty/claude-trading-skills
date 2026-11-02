# Hand-maintained skill guide drift report

Run the offline report from the repository root with Python 3.12:

```bash
python3 scripts/report_skill_doc_drift.py \
  --json-output reports/skill-doc-drift.json \
  --markdown-output reports/skill-doc-drift.md
```

The **Hand-maintained skill docs drift** workflow runs this command on pull
requests and main, adds warning annotations and a job summary, and retains both
reports as the `skill-doc-drift` artifact. Findings return exit code 0; unreadable
inputs or failed output writes return 1. This report does not change the existing
generated-page drift gate or EN/JA command-parity gate.

Only existing EN/JA skill pages without `generated: true` frontmatter are assessed.
The summary counts pages with findings, individual findings, unknown-history
pages, and unchecked imports. JSON contains each page's source/page commit times,
missing flags, findings and unchecked imports. Use the same revision and full git
history when comparing counts; the assessed HEAD is included in both reports.

Missing flags are flagged when SKILL.md has a newer last commit than the page.
With missing or shallow history, dates remain unknown and missing flags receive a
separate visible finding. File modification times are never substituted. Current
working-tree content is analyzed, but its uncommitted edits have no new commit
timestamp. Missing flag mentions are a review signal: not every flag necessarily
belongs in every guide.

Python fences are parsed with AST, never executed or imported. Static checks cover
repository import paths and top-level exported names, plus local skill helpers
with a preceding literal repository-root `sys.path` setup. External, dynamic,
relative and conditional imports, and dynamic exports, are explicitly unchecked.
This is not a complete Python interpreter or proof that every example runs. The
Trader Memory Core guides additionally have targeted import/signature and
fictional temporary-state lifecycle tests.

Annotations are capped at 20; the artifact retains every finding. Refresh pages
against the actual CLI/API and validate examples before shrinking parity
exceptions. Do not regenerate hand-maintained guides or add exemptions simply to
lower the reported count.
