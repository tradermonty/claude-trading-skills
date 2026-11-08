# Documented CLI examples — validation and offline execution

`scripts/check_doc_cli_examples.py` enforces that the shell commands shown in
the repository's primary command-reference documents actually work. It catches
the regressions described in issue #336:

- a documented example references a script that does not exist,
- an example passes a flag the target script does not accept,
- an example passes options to a script that defines no argument parser,
- a skip is missing the required reason / owner / expiry, or its expiry has
  passed,
- the English and Japanese versions of a paired document drift apart in the
  commands they document.

Unmarked shell blocks in `skills/*/SKILL.md` and
`skills/*/references/**/*.md` receive static script-and-option validation too.
Skill-local `scripts/foo.py` resolves from the owning skill, including nested
references; repository-qualified `skills/.../scripts/foo.py` resolves from the
repository root. Local paths never silently fall back to an unrelated root script.
Explicit `<!-- exec: ... -->` examples retain their repository-root resolution;
use such a marker for repository-maintenance commands in skill references.
Validation parses AST declarations without importing or executing scripts, including
literal `SUBCOMMAND_TO_SCRIPT` launcher dispatch and explicit successful
`--version` early-return branches. Placeholders may be argument values.

Elsewhere, the full script-and-option gate is opt-in through an HTML `<!-- exec: ... -->`
comment. In the three root command-reference files (`CLAUDE.md`, `README.md`,
and `README.ja.md`), `validate` also checks repository-relative Python script
paths in unmarked fenced `bash`, `sh`, `shell`, and `console` examples. That path-only check does not run the
examples or validate their options. A valid `skip` marker exempts its block.
Because the path-only check resolves paths from the repository root, examples
that use placeholders such as `skills/<skill-name>/...` must carry a valid `<!-- exec: skip ... -->` marker. After `cd`, the rest
of that block is skipped because its working directory is unknown. Heredoc
bodies are ignored. `console` blocks check only `$ ` prompt commands (including
continuations). Simple `sudo`, `time`, and `nohup` wrappers are accepted.
`uv run --directory` commands are skipped; `--project` retains the root context.
These shell-scanning limits also apply to unmarked skill option checks; marked execution remains bash-only.

## Targets

By default `validate` / `execute` scan the following files:

- `CLAUDE.md`
- `README.md`
- `README.ja.md`
- every `skills/*/SKILL.md`

`validate` additionally scans `docs/en/**/*.md`, `docs/ja/**/*.md` and
`skills/*/references/**/*.md`; the default `execute` scope is unchanged.
Reference-only changes also trigger the pre-commit validation hook.

The `EN/JA parity` rule applies only to the paired `README.md` / `README.ja.md`.
`CLAUDE.md` and the `SKILL.md` pages are single-language and are not paired.
`--targets` accepts other paths and glob patterns (e.g. `docs/**/*.md`).

## Marker grammar

Place an HTML comment immediately **above** the fenced shell block it applies
to. The extra markers must never appear inside the code fence, and a skip marker
must be an HTML comment (not a shell comment) so it is not confused with a
real command.

```markdown
<!-- exec: offline ci -->
```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 155.00 --stop 148.50 --account-size 100000 --risk-pct 1.0
```
```

### Modes

| Marker | Meaning |
|--------|---------|
| `offline` | Example runs offline with no API key. `validate` checks the invocation; `execute` may run it on demand. |
| `offline ci` | Like `offline`, and additionally executed by CI in an isolated temp cwd. The target script must be stdlib-only on the import path exercised by the example. |
| `api` | Example needs an API key / paid subscription (FMP, FINVIZ, Alpaca). Only `validate` is performed. Rejected for `ci` execution. |
| `skip reason=... owner=... expires=YYYY-MM-DD` | Skip validation. `reason`, `owner`, and `expires` are all required; an expired skip is an error. |

### Rules

- A marked block that passes options to a script with no argparse parser is an
  **error** (the invocation would silently ignore every flag). Use a
  `skip` only when the CLI is genuinely out of scope.
- An `api` example that also carries `ci` is rejected.
- A `skip` must carry `reason`, `owner`, and an unexpired `expires`.
- Marked examples execute inside a temporary working directory with
  `FMP_API_KEY`, `FINVIZ_API_KEY`, `ALPACA_API_KEY`, and `ALPACA_SECRET_KEY`
  stripped from the environment.
- **Mutation guard.** A temp cwd alone cannot stop a script anchoring its
  output to its own location (repo-relative via `__file__`) or accepting an
  absolute repo path. `execute` therefore snapshots
  `git status --porcelain --untracked-files=all` in the origin repository
  before and after each block: any delta fails that block with
  `mutated the repository`. The guard is skipped for non-git roots (tests).
- **Stdlib-only CI execution.** `execute --ci` runs blocks under the
  interpreter running the checker (`sys.executable`) with `-S`
  (site-packages disabled), so a block marked `offline ci`
  cannot depend on a third-party package that happens to be installed in the
  CI environment without being declared in the skill's `requirements.txt`.
- **Only mark what runs in a fresh clone.** `offline` means runnable offline
  *with the example's inputs present*. An example whose input path
  (`reports/<something>.md`, a fixture file…) does not exist in a fresh clone
  must stay unmarked (or reference a path the example itself creates first);
  execution is what catches such sample-path mismatch, validate alone does
  not infer input/output intent for arbitrary flags.

## Commands

```bash
# Validate marked examples and root-document script paths (offline, deterministic).
python3 scripts/check_doc_cli_examples.py validate

# Execute only examples marked `offline ci`, isolated + API keys stripped.
python3 scripts/check_doc_cli_examples.py execute --ci
```

Exit code is non-zero on any finding or failed execution.

## Coverage vs. correctness

The root documents' unmarked shell examples are checked for existing
repository-relative Python script files. Full option acceptance and optional
offline execution still require an explicit marker. Other documentation pages
are unchanged by the path-only pass. Mark new runnable examples when their
inputs and environment are suitable for the full gate.

## CI and pre-commit

- Pre-commit hook `docs-cli-examples` runs `validate` on
  `CLAUDE.md`, `README.md`, `README.ja.md`, `skills/*/SKILL.md` and the
  validator itself.
- CI job `docs-cli-examples` runs both `validate` and `execute --ci`
  (`--ci` = only `offline ci` blocks, stdlib-only interpreter, temp cwd +
  mutation guard).

## Testing

The gate has an isolated test suite:

```bash
python3 -m pytest scripts/tests/test_check_doc_cli_examples.py -q
```
