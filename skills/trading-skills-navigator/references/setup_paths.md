# Setup Paths

After the recommender returns a workflow, walk the user through installing the
**specific skills that workflow needs** — the actual `required_skills` and
`optional_skills` from the JSON, not a generic list. Pick the path for the
user's environment.

## Which skills does the recommended workflow need?

From the recommender JSON:

- `primary_workflow.required_skills` — must install all of these.
- `primary_workflow.optional_skills` — install if the user wants the optional
  steps.
- `secondary_workflows[].required_skills` — needed only if the user also runs
  the secondary workflow.
- On an **honest gap** (`primary_workflow: null`), there is no workflow to set
  up; install the individual `suggested_skills` instead.

Always tell the user which of those skills need a **paid API key** (check each
skill's row in the repo's API Requirements matrix / `CLAUDE.md`). If the
recommendation was made with `--no-api`, none of the required skills need paid
keys by construction.

## Path A — Claude Web App (`.skill` upload)

The Web App cannot clone the repo. Each skill is uploaded as a `.skill`
package.

1. Get the packaged skills from `skill-packages/` in this repository
   (e.g. `skill-packages/<skill-name>.skill`). For the Navigator itself:
   `skill-packages/trading-skills-navigator.skill`.
2. In the Claude Web App, open **Settings → Capabilities → Skills** (or the
   skill upload entry point) and upload each required `.skill` file.
3. Upload `trading-skills-navigator.skill` too if the user wants the router
   itself in the Web App — it ships with `assets/metadata_snapshot.json`, so
   recommendations work without the repo present.
4. For skills that need API keys, set them as instructed in that skill's
   `SKILL.md` (environment variable or in-conversation argument).
5. Invoke by describing the goal in natural language; the skill triggers from
   its `description`.

> The Navigator's recommender uses the bundled snapshot in this environment,
> so its output is identical to Claude Code.

## Path B — Claude Code (folder copy / clone)

1. Clone or pull this repository.
2. The skills live under `skills/<skill-name>/`. In Claude Code they are
   discovered from the repo automatically; to use one globally, symlink it:

   ```bash
   ln -sfn "$(pwd)/skills/<skill-name>" ~/.claude/skills/<skill-name>
   ```

3. Set any required API keys as environment variables (see `CLAUDE.md` →
   *API Key Management*), e.g.:

   ```bash
   export FMP_API_KEY=...        # FMP-backed skills
   export FINVIZ_API_KEY=...     # FINVIZ Elite (optional accelerator)
   export ALPACA_API_KEY=...     # portfolio-manager (Alpaca)
   export ALPACA_SECRET_KEY=...
   ```

4. Run the recommended workflow's skills in the order the workflow manifest
   (`workflows/<id>.yaml`) lists them. The Navigator's recommender reads the
   repo-root SSoT directly here (no snapshot needed).

## No-API starting path (recommended for new users)

If the user has no paid keys, the safe starting path is **`market-regime-daily`**
(`api_profile: no-api-basic`): `market-breadth-analyzer` → `uptrend-analyzer`
→ `exposure-coach`. Add the journaling loop (`trade-memory-loop`,
`monthly-performance-review`, both no-API) to close the
Plan → Trade → Record → Review → Improve loop. Upgrade to FMP/Alpaca-backed
workflows (`swing-opportunity-daily`, `core-portfolio-weekly`) only when the
user is ready to add paid data.
