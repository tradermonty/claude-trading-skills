# Issue #847: preserve indexed theses and serialize cooperating writers

## Selection and boundaries

58 open Issues; active PRs #838/#839/#851/#852/#853 do not change trader-memory persistence. P0 #332 is owned; other P1 items retain existing work, broad adoption work or operational acceptance. Choose unclaimed P2 #847 because lost index entries, duplicate registration and partially applied commands undermine recorded trading decisions. No matching claim/PR/branch/worktree existed. The prior trader-memory client migration PR #825 is merged and its worktree is clean. New isolated branch/worktree starts at `917a9a6fa0784164728021ff93d862fc34367b56`. Never access real thesis state or live accounts.

## Intended behavior

1. Doctor/`validate_state` and `rebuild_index` validate legacy equity shorts with the existing `allow_legacy_short=True` read/recovery exception. Retain their index entries and historical data. Do not permit new equity shorts, change accounting, or relax mutation validation.
2. Before a normal mutator can save YAML, load and structurally validate any existing index under the same state-directory lock. Reject corrupt JSON/unsupported shape with an actionable error pointing to explicit rebuild; preserve YAML and index bytes. Do not silently treat corrupt data as an empty index. Keep explicit rebuild able to recover from a corrupt index.
3. Serialize the complete read/validate/deduplicate/modify/write operation for every public writer: register, update, record_lessons, transition, link_report, mark_reviewed, attach_position, attach_futures_position, open_position, close, trim, terminate, rebuild_index. Futures dispatch must remain inside the same lock. Use an auditable writer registry/decorator after fragment loading; preserve signatures/metadata via wraps and the single thesis_store namespace.
4. Use standard-library advisory OS locking on a persistent state_dir/.lock file (POSIX flock; Windows byte-range locking), plus per-directory thread synchronization and nested-call reentrancy. Canonicalize directory aliases to the same key. Never delete/truncate the lock file while others may be using it. Bound contention waits with a clear failure, release on every exception and process exit. No new dependency. Cooperating processes and the same local filesystem are the supported model; manual writers/network filesystem guarantees are excluded.
5. Lock `validate_state` to avoid reporting the transient YAML/index gap during a cooperating write. Ordinary single-file atomic readers retain existing behavior. Document that lock-file coordination metadata may be created; no doctor business-state repair occurs implicitly. Explicit rebuild shares the writer lock.
6. Preserve validation before invalid commands write business state, idempotent register behavior and review/position semantics. Missing index remains compatible with existing YAML fingerprint fallback; repair is explicit. This does not promise multi-file crash atomicity or automatic rollback after disk failure/process death: doctor and rebuild remain recovery tools.

## TDD and validation

- Baseline the skill suite. Add failing legacy-short recovery/doctor/query/list-active/review-due regressions (both position and provenance markers), while preserving registration/close restrictions.
- Corrupt existing JSON/shape before each representative public writer; assert all thesis/index bytes unchanged and error actionable. Include normal CLI error behavior and explicit rebuild recovery. Enumerate all public writers so a missed operation fails a regression.
- Use spawned independent processes, a coordinated start and a controlled delay around index reads to amplify the old race without barriers inside critical sections. Register distinct origins and one duplicate origin with multiple workers; assert no lost entries, exactly one duplicate thesis, consistent YAML/index and successful doctor. Exercise mixed writes/rebuild, thread contention, nested record_lessons/update, lock exception release and alias paths. Bound subprocess/test waits, keep all state synthetic under tmp_path, and never spawn children as part of module import.
- Keep a platform-neutral lock contract and POSIX/Windows implementation tests; do not claim a native Windows run locally. Verify Windows through hosted CI where available and report it separately.
- Update instructions and EN/JA docs with writer/recovery/locking behavior and limits; changelog and package. Refresh/reset changed verification evidence conservatively.
- Run skill suite and relevant lifecycle/replay/metadata/dependency/package checks, normal pre-commit and all pre-push groups with hooks enabled. Commit/push and create a PR linked to #847 after independent review. No merge.

## Independent review protocol

Plan and code each receive at most three independent rounds. Resolve every actionable finding and get clean follow-up approval. If material findings remain after round three, report them and stop short of claiming completion or publishing a ready PR.

- Plan round 1: approved; implementation must validate nested index-entry mappings, normalize timeout/preflight errors through existing ValueError CLI handling, and test both thread/OS contention plus Windows byte-range behavior. No material findings.
- Code round 1: approved; no actionable findings. Independent reviewer ran all 65 new regressions and verified packaged sources.

## Validation record

- Code round 2: approved with no actionable findings. Full pre-push initially passed 74/75 groups and exposed backup-recipe coordination initialization plus a baseline-rationale prefix contract. Source boundaries are validated before doctor, then all bytes including the initialized lock file are manifested; empty-store recovery includes only coordination metadata. Relevant recovery/baseline suites pass 54 tests; reviewer independently reran 29 backup/baseline cases.

- Existing skill baseline: 732 passed with normal CLI/uv permissions; sandbox-only attempt had 9 uv-cache permission failures.
- Initial Issue regressions: 55 failed / 2 passed before implementation.
- Implementation skill suite: 795 passed before two additional legacy CLI cases; 65 new Issue regressions pass independently. Final full suite: 797 passed.
- A test-only Event/forced-termination interaction was corrected; child termination no longer leaves an IPC condition for the parent to acquire. All child waits/joins are bounded.
- Workflow/verification suites: 102 passed; all current offline workflow golden variants match.
- New lock code includes fork-inheritance reset and mocked Windows byte-range tests; no native Windows result is claimed locally.


## PR #858 review follow-up: read-only doctor

- Give only validate_state/doctor a read-only lock policy. Existing writable directories still coordinate with writers, but diagnostics never mkdir; missing direct-inspection paths and read-only snapshots do not create metadata. CLI missing-path rejection is preserved.
- Fall back to an unlocked diagnostic read only for permission/read-only filesystem errors during coordination setup. Do not suppress writer contention, unrelated I/O errors or disappearance after the access check. Write operations retain their original locking/creation behavior.
- TDD: 7 failures and 3 passes on the uncorrected PR. Thirteen new cases cover missing directories, healthy/inconsistent chmod-555 snapshots, EACCES/EPERM/EROFS, disappearance races, normal writable locking, contention, unrelated EIO and writers refusing permission-denied locks. No real state or accounts are touched.

- Follow-up validation: targeted doctor/index/CLI tests 96 passed; full memory/backup/verification suite 855 passed before adding three write-denial controls. The three controls confirm read-only fallback is never used by mutations. No source state outside synthetic tests is touched.
