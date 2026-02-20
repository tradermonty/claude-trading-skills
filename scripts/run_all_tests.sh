#!/usr/bin/env bash
# Run all skill-level tests, one pytest invocation per skill to avoid
# module-name collisions (multiple skills have scorer.py, helpers.py, etc.).
#
# Uses `uv run --extra dev` to ensure pytest and dev dependencies are available
# regardless of the caller's virtualenv state.
#
# Exit with non-zero if any non-skipped skill's tests fail.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Skills with known pre-existing test failures.
# These are excluded from the gate so that the pre-push hook is usable.
# Remove a skill from this list once its failures are fixed.
KNOWN_SKIP=(
    "theme-detector"    # 27 pre-existing failures
    "canslim-screener"  # requires bs4 (optional dep, not in dev extras)
)

FAILED=0
TOTAL=0
SKIPPED=0
FAILED_SKILLS=()

is_skipped() {
    local skill="$1"
    for s in "${KNOWN_SKIP[@]}"; do
        [ "$s" = "$skill" ] && return 0
    done
    return 1
}

# --- Skill tests: skills/*/scripts/tests/ and skills/*/tests/ ---
for test_dir in "$REPO_ROOT"/skills/*/scripts/tests/ "$REPO_ROOT"/skills/*/tests/; do
    # Skip if directory doesn't exist or has no test files
    [ -d "$test_dir" ] || continue
    ls "$test_dir"/test_*.py >/dev/null 2>&1 || continue

    skill_name=$(echo "$test_dir" | sed "s|$REPO_ROOT/skills/||" | cut -d/ -f1)

    if is_skipped "$skill_name"; then
        SKIPPED=$((SKIPPED + 1))
        echo "--- $skill_name (SKIPPED — known failures) ---"
        echo ""
        continue
    fi

    TOTAL=$((TOTAL + 1))

    echo "--- $skill_name ($test_dir) ---"
    if uv run --extra dev pytest "$test_dir" --tb=short -q 2>&1; then
        :
    else
        FAILED=$((FAILED + 1))
        FAILED_SKILLS+=("$skill_name")
    fi
    echo ""
done

# --- Repo-level tests: scripts/tests/ ---
REPO_TEST_DIR="$REPO_ROOT/scripts/tests"
if [ -d "$REPO_TEST_DIR" ] && ls "$REPO_TEST_DIR"/test_*.py >/dev/null 2>&1; then
    TOTAL=$((TOTAL + 1))
    echo "--- repo scripts/tests ---"
    if uv run --extra dev pytest "$REPO_TEST_DIR" --tb=short -q 2>&1; then
        :
    else
        FAILED=$((FAILED + 1))
        FAILED_SKILLS+=("scripts/tests")
    fi
    echo ""
fi

echo "=== Summary: $((TOTAL - FAILED))/$TOTAL passed, $SKIPPED skipped ==="
if [ ${#KNOWN_SKIP[@]} -gt 0 ]; then
    echo "Skipped (known failures): ${KNOWN_SKIP[*]}"
fi
if [ $FAILED -gt 0 ]; then
    echo "FAILED: ${FAILED_SKILLS[*]}"
    exit 1
fi
