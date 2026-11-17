# Kanchi personal-skill offline smoke

These are fictional inputs for #507's personal-skill verification layer. There
are no account identifiers, keys, real holdings or user journal files. The single
`manifest.json` lists the supported skills, inputs, output files and expected
classifications. It covers the review-monitor and US-tax-accounting CLIs only;
other #507 skills, live samples and nightly infrastructure remain separate.

Run from the repository root in the locked development environment:

```bash
python -m pytest scripts/tests/test_kanchi_personal_smoke.py -q
```

The test executes the real CLIs with standard-library-only Python (`-S`), isolated
user homes and temporary output directories. A socket audit hook records and
rejects attempts before execution; a swallowed-attempt probe checks the hook.
Tests validate nonempty JSON/Markdown or CSV/Markdown, the fixed fixture date,
T1 review escalation and the manifest's classifications, and unchanged fixture
bytes. Exit 0 alone is not accepted as a successful smoke result. The existing
root CI test row executes these tests without provider secrets.

The tax cases exercise the current code's ordinary/qualified-likely and
assumption-required classifications (common/preferred boundary, REIT and BDC).
They do not verify current tax law or replace a tax professional's review. No
new tax rules or financial recommendations are introduced here. Real user data
must not be substituted into these public fixtures.
