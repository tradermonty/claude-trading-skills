# Skill Package Cryptographic Signing — Deferral Rationale

**Date:** 2026-05-27
**Status:** Deferred (SHA-256 hashing in version-controlled manifest)
**Owner:** TraderMonty maintainers

---

## Current Security Model

Skill packages (`.skill` ZIP archives) are integrity-protected using:

1. **SHA-256 content hashing** — each `.skill` file's hash is recorded in
   `skill-packages/checksums.json` at sign time (`manage_skill_packages.py sign`).

2. **Build provenance metadata** — `checksums.json` records:
   - `build_timestamp`: ISO-8601 UTC time of signing
   - `source_commit`: git commit hash at sign time
   - `source_dirty`: whether the working tree had uncommitted changes
   - `signed_by`: name/identifier of the signer (CI system or developer)

3. **Version-controlled manifest** — `checksums.json` is committed to git.
   Any tampering with the manifest is detectable via `git log`.

4. **Pre-commit hook** — `skill-package-integrity` hook runs `verify` before
   each commit; a corrupt or unsigned package blocks the commit.

This model provides strong tamper-detection for the **single-developer / small-team
scenario** that TraderMonty currently targets.

---

## Why Full Cryptographic Signing Is Deferred

| Reason | Detail |
|--------|--------|
| **Audience scope** | TraderMonty is used locally by a single trader or a small team. Remote distribution with adversarial supply-chain risk is not the current threat model. |
| **Tooling overhead** | GPG key management, key rotation, and revocation require operational infrastructure not yet justified by the user base. |
| **sigstore complexity** | sigstore/cosign provides excellent transparency-log-backed signing but requires an OIDC identity provider setup that adds friction for local usage. |
| **Git sufficiency** | Commit-hash binding in a SHA-256 manifest provides adequate integrity for a git-backed distribution model. An attacker who can modify `checksums.json` in git also has write access to the repo — at which point signing doesn't add meaningful defence. |

---

## Upgrade Path (when warranted)

When TraderMonty adds:
- A public distribution channel (e.g., GitHub Releases, package registry), **OR**
- Multiple independent contributors who don't all have repo write access, **OR**
- An automated CI/CD pipeline publishing to external consumers

...the following upgrade is recommended:

1. **sigstore / cosign** — keyless signing with OIDC token, verification via
   Rekor transparency log. Works well with GitHub Actions OIDC.
2. **GPG detached signatures** — `gpg --detach-sign checksums.json` → distribute
   `checksums.json.sig` alongside `checksums.json`.

Both approaches add a `.sig` or attestation file alongside `checksums.json` and
require adding a `cmd_sign_crypto()` path in `manage_skill_packages.py`.

---

## Acceptance Criteria for Re-evaluation

This deferral should be re-evaluated when any of the following occurs:
- [ ] TraderMonty distributes packages via a channel other than direct git clone
- [ ] Any `.skill` file is served from a server outside this git repository
- [ ] A security audit recommends cryptographic signing
- [ ] The user base grows to require untrusted third-party skill contributions

---

## References

- `scripts/manage_skill_packages.py` — current sign/verify implementation
- `skill-packages/checksums.json` — live manifest
- Phase 6 of the TraderMonty Second Hardening Pass
