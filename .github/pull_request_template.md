## Summary

-

## Scope checks / スコープ確認

- [ ] This PR does not provide financial advice, buy/sell signals, profit guarantees, or broker execution. / 金融助言・売買推奨・利益保証・発注実行ではありません。
- [ ] I removed secrets, API keys, personal information, brokerage account data, and proprietary customer data. / 秘密情報・個人情報・口座情報・顧客固有情報を含めていません。
- [ ] The change is limited to the intended files and does not mix unrelated cleanup. / 無関係な整理を混ぜていません。

## Validation / 検証

- [ ] Targeted pytest or equivalent tests passed. / 対象テストを実行しました。
- [ ] `ruff check` passed for changed Python/script files. / 変更した Python/script に対して実行しました。
- [ ] `ruff format --check` passed for changed Python/script files. / format check を実行しました。
- [ ] `codespell` was considered or run for changed docs/text/scripts. / docs/text/script のスペル確認をしました。
- [ ] Security checks are clean or not applicable: `detect-secrets`, Bandit, no unsafe live writes. / secrets・SAST・危険な live write を確認しました。
- [ ] `pre-commit run --files <changed files>` passed, or any skipped hook is explained below. / changed-file scoped hook を実行しました。
- [ ] `git diff --check` passed. / whitespace diff check を実行しました。

## Skill and docs gates / スキル・docs ゲート

- [ ] If a skill changed, EN and JA skill docs are present or regenerated. / skill 変更時は EN/JA docs を確認しました。
- [ ] If a skill changed, the matching `.skill` package was regenerated or package drift was checked. / skill 変更時は package を再生成または drift check しました。
- [ ] If `skills-index.yaml`, `workflows/`, or `skillsets/` changed, generated docs/catalog/snapshot checks passed. / SSoT 変更時は generator drift を確認しました。
- [ ] If README or catalog sections changed, `python3 scripts/generate_catalog_from_index.py --check` passed. / README/catalog 変更時は catalog drift を確認しました。

## Notes for reviewers / レビュー補足

-
