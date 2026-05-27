# Release Attestation

## What is a Release Attestation?

A release attestation is a cryptographically signed, machine-verifiable record that a
specific set of skill packages was built from a known source commit, by a named builder,
at a recorded timestamp, and that the resulting packages have not been modified since
signing.

Attestation binds together:
- **What** was built (package hash list)
- **From what** (source commit, dirty flag)
- **By whom** (builder identity, signing key ID)
- **When** (timestamp)
- **How** (tool version, signing algorithm)

An attested release allows an operator to independently verify that the packages they
received match the packages that were built and signed.

---

## What the v3 Manifest Captures

The v3 manifest (produced by `scripts/manage_skill_packages.py`) includes the following
provenance fields:

| Field | Description |
|---|---|
| `source_commit` | Short SHA of the HEAD git commit at build time |
| `dirty` | `true` if the working tree had uncommitted changes at build time |
| `builder` | Name or ID of the person or CI system that built the packages |
| `timestamp` | ISO-8601 UTC timestamp of when the manifest was created |
| `version` | Integer manifest format version (currently `3`) |
| `signing_key_id` | First 8 hex chars of the SHA-256 of the signing key — identifies which key was used without revealing key material |
| `packages[].hash` | SHA-256 hex digest of the `.skill` zip file for each package |
| `packages[].name` | Skill name |
| `packages[].size` | File size in bytes |
| `manifest_signature` | HMAC-SHA256 signature over the canonical manifest JSON |

---

## Fields Required for an Attested Release

A release is considered **attested** only if the manifest satisfies ALL of the following:

1. `source_commit` is present and non-empty (not `"unknown"` or `"dirty"`)
2. `dirty` is `false` — no uncommitted changes at build time
3. `builder` is present and not `"unknown"`
4. `timestamp` is a valid ISO-8601 UTC timestamp
5. `signing_key_id` is present and matches a key in the current key registry
6. `manifest_signature` is present and verifies against the payload using the identified key
7. Every entry in `packages[]` has a non-empty `hash` field
8. The actual `.skill` files on disk match their recorded `hash` values (verified by `verify`)

A manifest with `dirty: true` may be used for development testing but **must not** be
used as a production release attestation.

---

## Commands to Produce an Attested Release

### Prerequisites

- Working tree must be clean (`git status` shows no modifications)
- Signing key must be available via `TRADERMONTY_SIGNING_KEY` env var or the production
  key store
- All skills must have their SKILL.md frontmatter validated

### Step-by-step

```bash
# 1. Ensure clean working tree
git status
# Expected: nothing to commit, working tree clean

# 2. Package all skills
python3 scripts/manage_skill_packages.py package --all --output-dir skill-packages/

# 3. Build and sign the manifest
#    Production: key from TRADERMONTY_SIGNING_KEY env var
TRADERMONTY_SIGNING_KEY="$(cat /path/to/prod-key.hex)" \
  python3 scripts/manage_skill_packages.py sign \
  --builder "$(git config user.name)" \
  --output skill-packages/manifest.json

# 4. Verify the manifest and all package hashes
python3 scripts/manage_skill_packages.py verify \
  --manifest skill-packages/manifest.json

# 5. Run the full release gate (includes verify as one of its checks)
python3 scripts/run_release_gate.py

# 6. Commit the manifest (never commit the key)
git add skill-packages/manifest.json
git commit -m "release: attest $(date -u +%Y-%m-%d) build"
```

### Development / CI (dev key)

```bash
# Use the auto-generated dev key (stored in ~/.config/tradermonty/dev-signing.key)
python3 scripts/manage_skill_packages.py sign \
  --dev-key \
  --builder "ci-runner" \
  --output skill-packages/manifest.json

python3 scripts/manage_skill_packages.py verify \
  --dev-mode --dev-key \
  --manifest skill-packages/manifest.json
```

---

## Verifying an Attested Release

A recipient of a release can verify attestation by:

```bash
# Clone the repository and check out the attested commit
git clone https://github.com/tradermonty/tradermonty.git
git checkout <source_commit>

# Verify the manifest signature and all package hashes
TRADERMONTY_SIGNING_KEY="$(cat /path/to/prod-key.hex)" \
  python3 scripts/manage_skill_packages.py verify \
  --manifest skill-packages/manifest.json
```

---

## Related Documentation

- [Key Management](key-management.md) — production key requirements, dev key setup,
  rotation procedure, and key ID semantics
- `scripts/signing.py` — HMAC-SHA256 signing implementation
- `scripts/manage_skill_packages.py` — packaging, signing, and verification CLI
