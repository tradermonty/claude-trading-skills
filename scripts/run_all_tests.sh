#!/usr/bin/env bash
# Run the same dynamically discovered test rows used by GitHub Actions.
#
# Mirrors CI's `uv sync --extra dev --extra ci` so optional-dependency tests
# (pyarrow, bs4, statsmodels, ...) run locally instead of skipping silently.
# `--locked` is intentionally omitted: local runs keep uv's normal sync behaviour.
# Skipped tests are reported after the summary; they never change the exit code.
# Must keep working on macOS /bin/bash 3.2 under `set -u` (no empty-array expansion).

set -euo pipefail

UV_RUN=(uv run --extra dev --extra ci)
MATRIX=(python scripts/ci_test_matrix.py)

FAILED=0
TOTAL=0
FAILED_SKILLS=()
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

TEST_OUTPUT=$("${UV_RUN[@]}" "${MATRIX[@]}" list)
TEST_IDS=$(printf '%s\n' "$TEST_OUTPUT" | sed '/^Covered exclusions:/,$d')
while IFS= read -r test_id; do
    [ -n "$test_id" ] || continue
    TOTAL=$((TOTAL + 1))
    echo "--- $test_id ---"
    row_log="$TMP_DIR/row.$TOTAL.log"
    # Grouped pipeline: pipefail makes the `if` see the group's failure.
    if ! { "${UV_RUN[@]}" "${MATRIX[@]}" install --check "$test_id" &&
           "${UV_RUN[@]}" "${MATRIX[@]}" run "$test_id"; } 2>&1 | tee "$row_log"; then
        if "${UV_RUN[@]}" "${MATRIX[@]}" allowed-failure "$test_id"; then
            echo "KNOWN FAILURE: $test_id is non-blocking"
        else
            FAILED=$((FAILED + 1))
            FAILED_SKILLS+=("$test_id")
        fi
    fi
    # Collect pytest `-rs` skip lines, prefixed with the row id.
    { grep -h '^SKIPPED \[' "$row_log" || true; } |
        awk -v id="$test_id" '{ print id ": " $0 }' >> "$TMP_DIR/skips.txt"
    echo ""
done <<< "$TEST_IDS"

touch "$TMP_DIR/skips.txt"
# Sum pytest's grouped "[n]" counts so the header counts tests, not report lines.
SKIP_COUNT=$(awk '{
    if (match($0, /: SKIPPED \[[0-9]+\]/)) {
        s = substr($0, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); n += s
    }
} END { print n + 0 }' "$TMP_DIR/skips.txt")

echo "=== Summary: $((TOTAL - FAILED))/$TOTAL passed ==="
echo "=== Skipped tests: $SKIP_COUNT ==="
cat "$TMP_DIR/skips.txt"
printf '%s\n' "$TEST_OUTPUT" | sed -n '/^Covered exclusions:/,$p'
if [ $FAILED -gt 0 ]; then
    echo "FAILED: ${FAILED_SKILLS[*]}"
    exit 1
fi
