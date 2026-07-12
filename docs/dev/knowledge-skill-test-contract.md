# Knowledge-Only Skill Test Contract

This repository treats knowledge-only, image-input, and orchestration skills as
testable even when they do not ship executable production code. A meaningful
test suite for these skills should protect the contract that a user or agent
relies on at runtime.

Use this minimum contract when adding or reviewing `skills/<skill>/scripts/tests`
for a skill whose main value is instructions, references, templates, or agent
workflow orchestration.

## Minimum checks

1. **Frontmatter identity**
   - `SKILL.md` has parseable YAML frontmatter.
   - `name` equals the skill directory name.
   - `description` contains the trigger surface the catalog relies on.

2. **Referenced local resources**
   - Every required `references/...`, `assets/...`, or local `scripts/...` file
     named by the workflow exists in the skill directory.
   - Required references are explicitly named in `SKILL.md`, not only implied by
     filenames.

3. **Prompt and workflow contract**
   - Required inputs are explicit, such as chart images, headlines, ticker
     symbols, or web search.
   - Required output shape is explicit, such as report path, sections, scoring
     scale, scenario probabilities, or ranking method.
   - Safety boundaries are explicit when the skill uses current data, external
     search, broker-adjacent advice, or multi-agent orchestration.

4. **Determinism**
   - Tests do not call web search, external APIs, brokers, LLMs, or agent tools.
   - Tests assert durable text/resource contracts and use local fixtures when
     executable helper code exists.

## Recommended layout

Place these tests under:

```text
skills/<skill>/scripts/tests/test_skill_contract.py
```

This keeps the suite discoverable by `scripts/run_all_tests.sh`, the pre-push
runner. Also add the test path to `pyproject.toml` and to the CI test job until
the CI matrix is generated automatically.
