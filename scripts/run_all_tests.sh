#!/usr/bin/env bash
# Run the same dynamically discovered test rows used by GitHub Actions.

set -euo pipefail

FAILED=0
TOTAL=0
FAILED_SKILLS=()
TEST_OUTPUT=$(uv run --extra dev python scripts/ci_test_matrix.py list)
TEST_IDS=$(printf '%s\n' "$TEST_OUTPUT" | sed '/^Covered exclusions:/,$d')
while IFS= read -r test_id; do
    [ -n "$test_id" ] || continue
    TOTAL=$((TOTAL + 1))
    echo "--- $test_id ---"
    if ! uv run --extra dev python scripts/ci_test_matrix.py install "$test_id" ||
       ! uv run --extra dev python scripts/ci_test_matrix.py run "$test_id"; then
        if uv run --extra dev python scripts/ci_test_matrix.py allowed-failure "$test_id"; then
            echo "KNOWN FAILURE: $test_id is non-blocking"
        else
            FAILED=$((FAILED + 1))
            FAILED_SKILLS+=("$test_id")
        fi
    fi
    echo ""
done <<< "$TEST_IDS"

echo "=== Summary: $((TOTAL - FAILED))/$TOTAL passed ==="
printf '%s\n' "$TEST_OUTPUT" | sed -n '/^Covered exclusions:/,$p'
if [ $FAILED -gt 0 ]; then
    echo "FAILED: ${FAILED_SKILLS[*]}"
    exit 1
fi
