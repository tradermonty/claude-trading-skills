"""
Cryptographic signing for TraderMonty skill packages.

Uses HMAC-SHA256 with a configurable secret key.  HMAC-SHA256 provides:
  - Integrity: any change to the manifest payload is detectable.
  - Authentication: only a party with the key can produce a valid signature.

This module replaces the deferred signing noted in
``docs/internal/package-signing-deferral.md``.  See
``docs/internal/key-management.md`` for production key-management guidance.

Key sources (in priority order when using ``SigningKey.best_available``):
  1. ``TRADERMONTY_SIGNING_KEY`` environment variable (hex-encoded bytes).
  2. Dev key file at ``~/.config/tradermonty/dev-signing.key`` (hex-encoded).
  3. Auto-generated dev key written to the same file when ``--dev-key`` is
     passed to the CLI (generates a random 32-byte key on first use).

Test key:
  ``SigningKey.for_testing()`` returns a fixed deterministic key.  It must
  never be used outside automated tests.

Production requirements:
  - Key material: ≥ 32 bytes of cryptographically random data
  - Storage: secrets manager (macOS Keychain, 1Password, HashiCorp Vault, …)
  - Rotation: annually or after suspected compromise
  - Never commit the key to version control
  - The key ID (first 8 hex chars of SHA-256 of key) is recorded in the
    manifest so operators can identify which key was used.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEV_KEY_FILE: Path = Path.home() / ".config" / "tradermonty" / "dev-signing.key"
ENV_VAR: str = "TRADERMONTY_SIGNING_KEY"

# Fixed test key — 32 bytes of "test" repeated; NEVER use outside tests.
_TEST_KEY_HEX: str = "74657374" * 8  # b"test" * 8


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SigningError(Exception):
    """Raised when a signing operation cannot be completed."""


class VerificationError(SigningError):
    """Raised when signature verification fails."""


# ---------------------------------------------------------------------------
# SigningKey
# ---------------------------------------------------------------------------

class SigningKey:
    """HMAC-SHA256 signing key with multiple load strategies.

    Parameters
    ----------
    key_bytes:
        Raw key material.  Must be ≥ 16 bytes.
    source:
        Human-readable description of where the key came from
        (used in error messages and audit logs).
    """

    def __init__(self, key_bytes: bytes, source: str) -> None:
        if len(key_bytes) < 16:
            raise SigningError(
                f"Key from '{source}' is too short "
                f"({len(key_bytes)} bytes; minimum 16 bytes required)"
            )
        self._key: bytes = key_bytes
        self.source: str = source
        # key_id = first 8 hex chars of SHA-256 of the key material
        self.key_id: str = hashlib.sha256(key_bytes).hexdigest()[:8]

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, var: str = ENV_VAR) -> "SigningKey":
        """Load key from an environment variable (hex-encoded)."""
        value = os.environ.get(var, "").strip()
        if not value:
            raise SigningError(
                f"Environment variable '{var}' is not set or empty.  "
                f"Set it to a hex-encoded signing key (≥ 32 hex chars), "
                f"or use from_dev_file() / --dev-key."
            )
        try:
            key_bytes = bytes.fromhex(value)
        except ValueError as exc:
            raise SigningError(
                f"Value of '{var}' is not valid hex: {exc}"
            ) from exc
        return cls(key_bytes, source=f"env:{var}")

    @classmethod
    def from_file(cls, path: Path) -> "SigningKey":
        """Load key from a file containing a single hex-encoded line."""
        if not path.exists():
            raise SigningError(
                f"Key file not found: {path}.  "
                f"Run with --dev-key to generate a key automatically."
            )
        try:
            hex_key = path.read_text(encoding="utf-8").strip()
            key_bytes = bytes.fromhex(hex_key)
        except (ValueError, OSError) as exc:
            raise SigningError(
                f"Could not read key from {path}: {exc}"
            ) from exc
        return cls(key_bytes, source=f"file:{path}")

    @classmethod
    def from_dev_file(cls, path: Path = DEV_KEY_FILE) -> "SigningKey":
        """Load or auto-generate a dev key at *path*.

        If the file does not exist a fresh 32-byte random key is created and
        written (mode 0600).

        .. warning::
            This key is for **local development only**.  It provides
            tamper-detection but does not meet production key-management
            requirements — it is unaudited, unrotated, and stored in a
            plain local file.
        """
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            key_bytes = secrets.token_bytes(32)
            path.write_text(key_bytes.hex(), encoding="utf-8")
            path.chmod(0o600)
        return cls.from_file(path)

    @classmethod
    def for_testing(cls) -> "SigningKey":
        """Return a fixed deterministic key for use in automated tests only.

        .. danger::
            Never use this key outside test suites.  Its value is public.
        """
        return cls(bytes.fromhex(_TEST_KEY_HEX), source="test-key")

    @classmethod
    def best_available(cls, dev_mode: bool = False) -> "SigningKey":
        """Return the best key available in the current environment.

        Priority:
          1. ``TRADERMONTY_SIGNING_KEY`` environment variable.
          2. Dev key file (if *dev_mode* is True **or** the file already exists).

        Raises :exc:`SigningError` if no key is found.
        """
        if os.environ.get(ENV_VAR, "").strip():
            return cls.from_env()
        if dev_mode or DEV_KEY_FILE.exists():
            return cls.from_dev_file()
        raise SigningError(
            f"No signing key available.  "
            f"Set ${ENV_VAR} to a hex-encoded key, or pass --dev-key to "
            "generate/use a local development key."
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> str:
        """Return the HMAC-SHA256 hex digest of *data*."""
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, signature: str) -> bool:
        """Return True iff *signature* matches ``sign(data)``.

        Uses :func:`hmac.compare_digest` to prevent timing attacks.
        """
        expected = self.sign(data)
        try:
            return hmac.compare_digest(expected, signature)
        except TypeError:
            return False

    def __repr__(self) -> str:
        return f"SigningKey(source={self.source!r}, key_id={self.key_id!r})"


# ---------------------------------------------------------------------------
# Manifest signing helpers
# ---------------------------------------------------------------------------

def canonical_json(obj: dict | list) -> bytes:
    """Return canonical (sort_keys, compact) UTF-8 JSON bytes for signing.

    Canonical form ensures identical dicts always produce the same bytes
    regardless of insertion order.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sign_manifest(manifest: dict, key: SigningKey) -> dict:
    """Return a *copy* of *manifest* with signature fields populated.

    The signature covers the canonical JSON of the manifest with the
    ``_signature`` and ``_signature_key_id`` fields removed, so those
    fields can be stored alongside the data without invalidating the
    signature on round-trip.

    Parameters
    ----------
    manifest:
        The full manifest dict (including ``_release`` block).
    key:
        The signing key to use.

    Returns
    -------
    dict
        A deep copy of *manifest* with ``_release._signature`` and
        ``_release._signature_key_id`` set.
    """
    import copy
    m = copy.deepcopy(manifest)
    release = m.setdefault("_release", {})

    # Strip any existing signature before computing the payload
    release.pop("_signature", None)
    release.pop("_signature_key_id", None)

    payload = canonical_json(m)
    release["_signature"] = key.sign(payload)
    release["_signature_key_id"] = key.key_id
    return m


def verify_manifest(manifest: dict, key: SigningKey) -> None:
    """Verify the HMAC-SHA256 signature of *manifest*.

    Parameters
    ----------
    manifest:
        The full manifest dict as loaded from ``checksums.json``.
    key:
        The signing key to verify against.

    Raises
    ------
    VerificationError
        If the signature is missing, the key ID does not match, or the
        signature is invalid (manifest was tampered with).
    """
    import copy

    release = manifest.get("_release", {})
    stored_sig = release.get("_signature")
    stored_key_id = release.get("_signature_key_id")

    if not stored_sig:
        raise VerificationError(
            "Manifest has no _signature field — the package was not cryptographically "
            "signed.  Run `manage_skill_packages.py sign --dev-key` to sign it, "
            "or pass --dev-mode to verify() to accept unsigned manifests with a warning."
        )

    if stored_key_id and stored_key_id != key.key_id:
        raise VerificationError(
            f"Key ID mismatch: manifest was signed with key '{stored_key_id}' "
            f"but current key has ID '{key.key_id}'.  "
            "Use the correct signing key to verify this manifest."
        )

    # Reconstruct the exact payload that was signed
    m = copy.deepcopy(manifest)
    m["_release"].pop("_signature", None)
    m["_release"].pop("_signature_key_id", None)

    payload = canonical_json(m)
    if not key.verify(payload, stored_sig):
        raise VerificationError(
            "INVALID signature — the manifest has been tampered with or was "
            "signed with a different key.  Do NOT trust this package."
        )


def verify_manifest_devmode(manifest: dict, key: SigningKey | None) -> bool:
    """Verify manifest in dev mode: accept unsigned but warn; verify if signed.

    Parameters
    ----------
    manifest:
        The manifest dict.
    key:
        Key to verify against if a signature is present.  Pass None to
        skip verification (unsigned-only dev mode).

    Returns
    -------
    bool
        True if verification passed or manifest is unsigned in dev mode.
    """
    import sys
    release = manifest.get("_release", {})
    if not release.get("_signature"):
        print(
            "  [DEV-MODE WARN] Manifest is not cryptographically signed.  "
            "This is acceptable for local development but NOT for distribution.",
            file=sys.stderr,
        )
        return True

    if key is None:
        print(
            "  [DEV-MODE WARN] Signed manifest found but no key provided — "
            "skipping signature verification.",
            file=sys.stderr,
        )
        return True

    try:
        verify_manifest(manifest, key)
        return True
    except VerificationError as exc:
        print(f"  [ERROR] Signature verification failed: {exc}", file=sys.stderr)
        return False
