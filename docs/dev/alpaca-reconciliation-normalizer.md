# Saved Alpaca broker-input normalization (#493)

This is the offline broker-input slice. The existing comparator and manual
workflow gate remain unchanged. Complete memory export/account attribution,
live broker capture and machine-enforced replay gating remain under #493.

## Final plan

Independent plan review approved round 2 after explicitly adding the reconciler's
required asset_type field to the output whitelist. Precision and OS-specific
output-file guarantees were clarified before implementation.

1. Add a stdlib-only saved Alpaca JSON normalizer, with explicit operator account
   alias, aware source timestamp and complete-list confirmation. Never infer
   verified empty accounts or fetch live data.
2. Validate every native equity row, currency, side and signed plain-string
   quantity. Reject unsupported instruments, duplicates, contradictory signs and
   invalid quantities instead of dropping or netting positions.
3. Reuse the existing reconciliation snapshot/decimal/read contracts. Emit only
   the required header and sorted equity symbol/direction/absolute-quantity rows.
   Use Decimal.copy_abs and exact formatting, preserving precision independently
   of the caller's decimal context. Ignore private native fields and prices.
4. Keep inputs unchanged. Default to stdout; optional file publication stages
   complete JSON in the destination folder and links it exclusively to a new
   destination. Never overwrite existing files or aliases; fail safely on an
   unsupported filesystem. POSIX mode and Windows ACL boundaries stay explicit.
5. Test the real normalizer and comparator CLI paths with fictional positions,
   matches/discrepancies, error/privacy/immutability and publication failures.
   Rebuild and test the standalone portfolio-manager package outside the repo.
6. Independently review code, resolve findings within three rounds, run focused
   and mandatory repository/push gates, then commit and create a PR with Refs
   #493. No merge, Issue closure, order, memory edit or live provider call.

## Acceptance and limitations

The new artifact is input to reconciliation, not an allocation report, account
identity proof, source-authenticity check or order authorization. Complete=true,
account_scope and as_of reflect explicit operator assertions, including on an
empty list. No actual broker/memory snapshot is captured by this command.

The original comparator's long-only memory restriction remains: a short broker
position normalizes successfully but can produce a direction mismatch requiring
manual review. Missing prices do not prevent quantity comparison. Live freshness
and complete account selection cannot be established from a saved list alone.

Tests pin positive absolute decimal quantities including fractional shares and
more than 28 significant digits with decimal precision reduced to six. File
output uses a private staged file and an exclusive hardlink on a supporting
filesystem; failure never falls back to overwriting user data. Test evidence is
offline and fictional, distinct from hosted CI and native broker acceptance.
