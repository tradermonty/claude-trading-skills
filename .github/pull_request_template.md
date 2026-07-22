## Summary / 概要

-

## Related issue / 関連Issue

- Refs or Closes #

## Scope and safety / スコープと安全性

- [ ] This PR does not provide financial advice, buy/sell signals, profit guarantees, or broker execution. / 金融助言、売買推奨、利益保証、発注実行を含みません。
- [ ] I removed secrets, API keys, personal information, brokerage account data, and proprietary customer data. / 秘密情報、APIキー、個人情報、証券口座情報、顧客固有情報を含みません。
- [ ] This PR contains no unsafe live write and does not mix unrelated cleanup. / 危険なlive writeや無関係な整理を含みません。

## Local validation / ローカル検証

- [ ] Targeted tests passed with `python3.9 -m pytest <target> -q` (or the repository-compatible Python noted below). / 対象テストが通過しました。
- [ ] The full skill suite passed with `bash scripts/run_all_tests.sh`, or N/A is explained below. / 全skill testまたはN/A理由を記録しました。
- [ ] `ruff check skills/ scripts/` passed. / lintが通過しました。
- [ ] `ruff format --check skills/ scripts/` passed. / format checkが通過しました。
- [ ] `codespell --toml pyproject.toml skills/ scripts/` passed. / スペルcheckが通過しました。
- [ ] `pre-commit run --all-files` passed. / 全pre-commit hookが通過しました。
- [ ] `git diff --check` passed. / whitespace checkが通過しました。

## CI and generated-artifact gates / CI・生成物ゲート

Mark non-applicable items as N/A and explain them under reviewer notes. / 非該当項目はN/Aとし、レビュー補足に理由を書いてください。

- [ ] GitHub Actions Lint, Security, Metadata + Workflow checks, tests, and Coverage are green. / GitHub Actionsの全gateがgreenです。
- [ ] If a skill changed, EN and JA skill docs are present or regenerated, and its `.skill` package passed `python3 scripts/package_skills.py --check --skill <skill-name>`. / skill変更時は英日文書とpackageを確認しました。
- [ ] If a skill package needed regeneration, `python3 scripts/package_skills.py --skill <skill-name>` was run before the package check. / 必要なpackageを再生成しました。
- [ ] Index/workflow metadata passed `python3 scripts/validate_skills_index.py`, `python3 scripts/validate_skills_index.py --strict-workflows`, and `python3 scripts/validate_skills_index.py --strict-metadata`. / index・workflow metadataを検証しました。
- [ ] Skillsets passed `python3 scripts/validate_skillsets.py`. / skillsetを検証しました。
- [ ] Skill docs passed `python3 scripts/generate_skill_docs.py --check`. / skill文書のdriftを確認しました。
- [ ] Workflow docs passed `python3 scripts/generate_workflow_docs.py --check`. / workflow文書のdriftを確認しました。
- [ ] Skillset docs passed `python3 scripts/generate_skillset_docs.py --check`. / skillset文書のdriftを確認しました。
- [ ] README/catalog output passed `python3 scripts/generate_catalog_from_index.py --check`. / catalogのdriftを確認しました。
- [ ] Navigator snapshot passed `python3 skills/trading-skills-navigator/scripts/build_snapshot.py --check`. / navigator snapshotを確認しました。
- [ ] Vendored FMP clients passed `python3 scripts/generate_fmp_client.py --check`. / FMP clientのdriftを確認しました。
- [ ] Changed skill packages passed `python3 scripts/check_package_drift_for_changed_skills.py`. / 変更skillのpackage driftを確認しました。
- [ ] FMP package mirrors passed the repository CI command below. / FMP package mirrorのdriftを確認しました。

```bash
python3 scripts/package_skills.py --check --skill pead-screener --skill earnings-trade-analyzer --skill ibd-distribution-day-monitor --skill vcp-screener --skill parabolic-short-trade-planner --skill ftd-detector --skill canslim-screener --skill macro-regime-detector --skill market-top-detector
```

## Reviewer notes and N/A reasons / レビュー補足・N/A理由

-
