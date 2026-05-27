# Key Management

This document describes how to create, store, rotate, and reference signing keys for
TraderMonty skill package attestation.  See [release-attestation.md](release-attestation.md)
for the full release workflow.

---

## What Is a Key ID?

The **key ID** is the first 8 hex characters of the SHA-256 hash of the raw key bytes.

```python
import hashlib
key_id = hashlib.sha256(key_bytes).hexdigest()[:8]
```

The key ID is recorded in every signed manifest under `signing_key_id`.  It allows an
operator to identify which key was used to sign a manifest without exposing any key
material.  Key IDs are NOT secret.

Example: if the key material is 32 random bytes, the key ID might be `a3f19c2b`.

---

## Production Key Requirements

| Requirement | Detail |
|---|---|
| **Minimum length** | ≥ 32 bytes (256 bits) of cryptographically random data |
| **Encoding** | Hex-encoded (64 lowercase hex characters for a 32-byte key) |
| **Generation** | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| **Storage** | Secrets manager — do NOT commit to version control |
| **Access** | Inject at build time via `TRADERMONTY_SIGNING_KEY` environment variable |
| **Rotation** | Annually, or immediately after suspected compromise |
| **Backup** | Store a recovery copy in a separate, access-controlled secrets store |
| **Audit** | Log every signing operation: who signed, when, which manifest |

### Recommended Secrets Managers

- **macOS:** Keychain (`security add-generic-password`) or 1Password CLI (`op`)
- **CI/CD:** GitHub Actions Secrets, GitLab CI Variables, or HashiCorp Vault
- **Self-hosted:** HashiCorp Vault with AppRole authentication

### Injecting the Key in CI

```yaml
# GitHub Actions example
- name: Sign skill packages
  env:
    TRADERMONTY_SIGNING_KEY: ${{ secrets.TRADERMONTY_SIGNING_KEY }}
  run: |
    python3 scripts/manage_skill_packages.py sign \
      --builder "github-actions" \
      --output skill-packages/manifest.json
```

---

## Development Key Setup

The `--dev-key` flag causes the signing module to read from (or auto-generate) a local
dev key stored at:

```
~/.config/tradermonty/dev-signing.key
```

### First-time setup

```bash
# Option A: Let the tool auto-generate a dev key on first use
python3 scripts/manage_skill_packages.py sign --dev-key --builder "$(whoami)"

# Option B: Generate manually and save
python3 -c "import secrets; print(secrets.token_hex(32))" \
  > ~/.config/tradermonty/dev-signing.key
chmod 600 ~/.config/tradermonty/dev-signing.key
```

The auto-generated key is written with mode `0o600` (owner read/write only).

### Dev key limitations

- Dev keys are **not** suitable for production releases
- Manifests signed with a dev key will have `dirty`-flagging disabled (no source_commit
  enforcement) in dev mode
- Never copy a dev key into a CI environment or commit it to version control
- Dev key IDs begin with whatever random prefix the generated key produces — there is no
  special marking, so always track which manifests used dev vs. production keys

---

## Key Rotation Procedure

Follow this procedure when rotating the production signing key:

### 1. Generate the new key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Save output securely in your secrets manager — never echo to terminal in production
```

### 2. Record the new key ID

```bash
python3 -c "
import hashlib, sys
key_hex = input('Enter new key hex: ').strip()
key_bytes = bytes.fromhex(key_hex)
print('New key ID:', hashlib.sha256(key_bytes).hexdigest()[:8])
"
```

### 3. Update your secrets manager

Store the new key under the same secret name (`TRADERMONTY_SIGNING_KEY`) in your secrets
manager.  Keep the OLD key available for verification of historical manifests — do NOT
delete it until all consumers have migrated.

### 4. Re-sign the manifest

After rotating:

```bash
TRADERMONTY_SIGNING_KEY="<new-key>" \
  python3 scripts/manage_skill_packages.py sign \
  --builder "$(git config user.name)" \
  --output skill-packages/manifest.json
```

The new manifest will show the new `signing_key_id`.

### 5. Verify with the new key

```bash
TRADERMONTY_SIGNING_KEY="<new-key>" \
  python3 scripts/manage_skill_packages.py verify \
  --manifest skill-packages/manifest.json
```

### 6. Commit and notify

```bash
git add skill-packages/manifest.json
git commit -m "chore: rotate signing key (key_id=$(new-key-id))"
```

Notify all operators that the key has rotated and they should use the new key for future
verification.

---

## Historical Manifest Verification

Older manifests signed with a previous key can still be verified by temporarily setting
`TRADERMONTY_SIGNING_KEY` to the old key value:

```bash
TRADERMONTY_SIGNING_KEY="<old-key>" \
  python3 scripts/manage_skill_packages.py verify \
  --manifest skill-packages/archive/manifest-2025-01-15.json
```

---

## Key Security Checklist

- [ ] Key material is ≥ 32 bytes (64 hex chars)
- [ ] Key is stored in a secrets manager, not in a file on disk or in source control
- [ ] Key file (if used) has mode `0o600`
- [ ] `.gitignore` excludes `*.key`, `*.hex`, `.env`, and secrets files
- [ ] `TRADERMONTY_SIGNING_KEY` is never logged or printed
- [ ] Rotation schedule is documented and calendared
- [ ] Old keys are retained for historical verification but not for new signing
- [ ] CI pipeline uses the production key only via injected secrets, never hardcoded

---

## Related Documentation

- [Release Attestation](release-attestation.md) — full release workflow using these keys
- `scripts/signing.py` — `SigningKey` class implementation
- `scripts/manage_skill_packages.py` — `sign` and `verify` subcommands
