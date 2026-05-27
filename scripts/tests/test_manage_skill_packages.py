"""Tests for scripts/manage_skill_packages.py — signing + package integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from manage_skill_packages import (  # noqa: E402
    cmd_sign,
    cmd_verify,
    cmd_list,
    MANIFEST_VERSION,
    _manifest_is_v2,
    _manifest_is_signed,
)
from signing import SigningKey, VerificationError, sign_manifest, verify_manifest  # noqa: E402


# ---------------------------------------------------------------------------
# Shared test key fixture
# ---------------------------------------------------------------------------

_TEST_KEY = SigningKey.for_testing()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_package(pkg_dir: Path, skill_id: str, content: bytes = b"fake-zip-content") -> Path:
    pkg_dir.mkdir(parents=True, exist_ok=True)
    pkg = pkg_dir / f"{skill_id}.skill"
    pkg.write_bytes(content)
    return pkg


def _write_skill_md(skills_dir: Path, skill_id: str) -> None:
    d = skills_dir / skill_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {skill_id}\n---\n", encoding="utf-8")


def _patch_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect module-level paths to tmp_path and inject the test signing key."""
    import manage_skill_packages as m
    monkeypatch.setattr(m, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(m, "PACKAGES_DIR", tmp_path / "skill-packages")
    monkeypatch.setattr(m, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(m, "CHECKSUMS_FILE", tmp_path / "skill-packages" / "checksums.json")
    # Inject test signing key so all sign/verify calls work without a real key
    monkeypatch.setenv("TRADERMONTY_SIGNING_KEY", _TEST_KEY._key.hex())


def _make_sign_args(
    signed_by: str = "test-runner",
    dev_key: bool = False,
    signing_key_file: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        signed_by=signed_by,
        dev_key=dev_key,
        signing_key_file=signing_key_file,
    )


def _make_verify_args(
    dev_mode: bool = False,
    dev_key: bool = False,
    signing_key_file: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        dev_mode=dev_mode,
        dev_key=dev_key,
        signing_key_file=signing_key_file,
    )


def _write_test_key(tmp_path: Path) -> Path:
    """Write the test key to a temp file and return its path."""
    key_file = tmp_path / "test.key"
    key_file.write_text(_TEST_KEY._key.hex(), encoding="utf-8")
    return key_file


# ---------------------------------------------------------------------------
# sign — basic functionality
# ---------------------------------------------------------------------------


def test_sign_creates_checksums_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    result = cmd_sign(_make_sign_args())
    assert result == 0
    checksums = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())
    assert "alpha" in checksums
    assert len(checksums["alpha"]["sha256"]) == 64


def test_sign_computes_correct_sha256(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    content = b"binary-skill-content"
    _write_package(tmp_path / "skill-packages", "beta", content)
    cmd_sign(_make_sign_args())
    checksums = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())
    expected = hashlib.sha256(content).hexdigest()
    assert checksums["beta"]["sha256"] == expected


def test_sign_records_stale_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import os, time
    _patch_dirs(monkeypatch, tmp_path)
    base = time.time()
    pkg = _write_package(tmp_path / "skill-packages", "gamma")
    os.utime(pkg, (base - 200, base - 200))  # package older
    _write_skill_md(tmp_path / "skills", "gamma")  # SKILL.md is newer
    cmd_sign(_make_sign_args())
    checksums = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())
    assert checksums["gamma"]["stale"] is True


def test_sign_no_packages_returns_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    (tmp_path / "skill-packages").mkdir(parents=True)
    result = cmd_sign(_make_sign_args())
    assert result == 1


# ---------------------------------------------------------------------------
# Phase 6 — Release metadata in v2 manifest
# ---------------------------------------------------------------------------


def test_sign_writes_v2_release_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Phase 6: sign must write _release metadata block."""
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args(signed_by="CI-pipeline"))
    manifest = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())

    assert "_release" in manifest, "checksums.json must contain _release metadata"
    release = manifest["_release"]
    assert release["manifest_version"] == MANIFEST_VERSION
    assert release["build_timestamp"], "build_timestamp must be non-empty"
    assert release["signed_by"] == "CI-pipeline"
    assert "signing_note" in release, "signing_note (deferral rationale) must be present"


def test_sign_captures_source_commit_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """source_commit field must be present (empty string if git unavailable)."""
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args())
    manifest = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())
    release = manifest["_release"]
    assert "source_commit" in release, "source_commit field must appear in _release"
    assert "source_dirty" in release, "source_dirty field must appear in _release"


def test_manifest_is_v2_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """_manifest_is_v2() correctly identifies v2 vs v1 manifests."""
    # v2: has _release with manifest_version == MANIFEST_VERSION
    v2 = {"_release": {"manifest_version": MANIFEST_VERSION}, "alpha": {"sha256": "abc"}}
    assert _manifest_is_v2(v2) is True

    # v1: no _release key
    v1 = {"alpha": {"sha256": "abc"}}
    assert _manifest_is_v2(v1) is False

    # Old _release without correct version
    old = {"_release": {"manifest_version": "1.0"}}
    assert _manifest_is_v2(old) is False


def test_signing_deferral_doc_exists() -> None:
    """Cryptographic signing deferral must be documented."""
    project_root = Path(__file__).resolve().parents[2]
    deferral_doc = project_root / "docs" / "internal" / "package-signing-deferral.md"
    assert deferral_doc.is_file(), (
        "docs/internal/package-signing-deferral.md is missing. "
        "Cryptographic signing deferral must be explicitly documented."
    )
    content = deferral_doc.read_text()
    assert "SHA-256" in content, "Deferral doc must describe the current SHA-256 hashing model"
    assert "deferred" in content.lower(), "Deferral doc must explain why crypto signing is deferred"


# ---------------------------------------------------------------------------
# verify — integrity checks
# ---------------------------------------------------------------------------


def test_verify_passes_on_intact_packages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args())
    assert cmd_verify(_make_verify_args()) == 0


def test_verify_fails_on_corrupt_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    pkg = _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args())
    pkg.write_bytes(b"tampered-content")
    assert cmd_verify(_make_verify_args()) == 1


def test_verify_fails_when_package_deleted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    pkg = _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args())
    pkg.unlink()
    assert cmd_verify(_make_verify_args()) == 1


def test_verify_fails_on_unsigned_new_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args())
    _write_package(tmp_path / "skill-packages", "beta")  # not signed
    assert cmd_verify(_make_verify_args()) == 1


def test_verify_fails_when_no_checksums_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    assert cmd_verify(_make_verify_args()) == 1


def test_verify_shows_provenance_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """verify output should include build provenance when manifest is v2."""
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args(signed_by="Alice"))
    cmd_verify(_make_verify_args())
    out = capsys.readouterr().out
    assert "Built:" in out, "verify output should include build timestamp"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_exits_ok_with_packages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    _write_package(tmp_path / "skill-packages", "alpha")
    cmd_sign(_make_sign_args())
    result = cmd_list()
    assert result == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "STALE" in out or "FRESH" in out


def test_list_exits_ok_with_no_packages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    (tmp_path / "skill-packages").mkdir(parents=True)
    assert cmd_list() == 0


# ---------------------------------------------------------------------------
# Phase 1 — Cryptographic signing (signing.py unit tests)
# ---------------------------------------------------------------------------


class TestSigningKey:
    def test_test_key_creates_successfully(self) -> None:
        key = SigningKey.for_testing()
        assert key.key_id, "key_id must be non-empty"
        assert key.source == "test-key"

    def test_key_too_short_raises_error(self) -> None:
        from signing import SigningError
        with pytest.raises(SigningError, match="too short"):
            SigningKey(b"short", source="bad")

    def test_from_env_reads_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import signing
        key_hex = "ab" * 16
        monkeypatch.setenv(signing.ENV_VAR, key_hex)
        key = SigningKey.from_env()
        assert key.key_id, "key_id must be set"

    def test_from_env_missing_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import signing
        from signing import SigningError
        monkeypatch.delenv(signing.ENV_VAR, raising=False)
        with pytest.raises(SigningError):
            SigningKey.from_env()

    def test_from_env_invalid_hex_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import signing
        from signing import SigningError
        monkeypatch.setenv(signing.ENV_VAR, "not-valid-hex!!!")
        with pytest.raises(SigningError, match="not valid hex"):
            SigningKey.from_env()

    def test_from_file_reads_key(self, tmp_path: Path) -> None:
        key_file = tmp_path / "test.key"
        key_file.write_text("ab" * 16, encoding="utf-8")
        key = SigningKey.from_file(key_file)
        assert key.key_id

    def test_from_file_missing_raises_error(self, tmp_path: Path) -> None:
        from signing import SigningError
        with pytest.raises(SigningError, match="not found"):
            SigningKey.from_file(tmp_path / "nonexistent.key")

    def test_from_dev_file_generates_key(self, tmp_path: Path) -> None:
        key_file = tmp_path / "dev-signing.key"
        key = SigningKey.from_dev_file(key_file)
        assert key_file.exists(), "Dev key file must be created"
        assert len(key_file.read_text().strip()) >= 32, "Key must be hex-encoded"

    def test_from_dev_file_reuses_existing_key(self, tmp_path: Path) -> None:
        key_file = tmp_path / "dev-signing.key"
        key1 = SigningKey.from_dev_file(key_file)
        key2 = SigningKey.from_dev_file(key_file)
        assert key1.key_id == key2.key_id, "Same file must produce same key_id"

    def test_key_id_is_deterministic(self) -> None:
        k1 = SigningKey.for_testing()
        k2 = SigningKey.for_testing()
        assert k1.key_id == k2.key_id

    def test_sign_produces_hex_string(self) -> None:
        key = SigningKey.for_testing()
        sig = key.sign(b"hello world")
        assert len(sig) == 64, "HMAC-SHA256 should produce 64 hex chars"
        int(sig, 16)  # must be valid hex

    def test_verify_correct_signature(self) -> None:
        key = SigningKey.for_testing()
        data = b"test payload"
        sig = key.sign(data)
        assert key.verify(data, sig)

    def test_verify_wrong_data_fails(self) -> None:
        key = SigningKey.for_testing()
        sig = key.sign(b"original")
        assert not key.verify(b"tampered", sig)

    def test_verify_tampered_signature_fails(self) -> None:
        key = SigningKey.for_testing()
        data = b"test payload"
        sig = key.sign(data)
        bad_sig = "ff" * 32
        assert not key.verify(data, bad_sig)


class TestSignManifest:
    def test_sign_adds_signature_to_release_block(self) -> None:
        key = SigningKey.for_testing()
        manifest = {"_release": {"manifest_version": "3.0"}, "skill-a": {"sha256": "abc"}}
        signed = sign_manifest(manifest, key)
        assert "_signature" in signed["_release"]
        assert len(signed["_release"]["_signature"]) == 64

    def test_sign_adds_key_id(self) -> None:
        key = SigningKey.for_testing()
        manifest = {"_release": {}, "x": {}}
        signed = sign_manifest(manifest, key)
        assert signed["_release"]["_signature_key_id"] == key.key_id

    def test_sign_is_deterministic_for_same_key_and_data(self) -> None:
        key = SigningKey.for_testing()
        manifest = {"_release": {"ts": "2026-01-01"}, "pkg": {"sha256": "aa" * 32}}
        s1 = sign_manifest(manifest, key)
        s2 = sign_manifest(manifest, key)
        assert s1["_release"]["_signature"] == s2["_release"]["_signature"]

    def test_sign_different_key_produces_different_signature(self) -> None:
        import signing
        k1 = SigningKey.for_testing()
        k2 = SigningKey(b"different_key_material_32_bytes!!", source="test2")
        manifest = {"_release": {}, "pkg": {"sha256": "bb" * 32}}
        s1 = sign_manifest(manifest, k1)
        s2 = sign_manifest(manifest, k2)
        assert s1["_release"]["_signature"] != s2["_release"]["_signature"]


class TestVerifyManifest:
    def _make_signed(self) -> tuple[dict, SigningKey]:
        key = SigningKey.for_testing()
        manifest = {"_release": {"manifest_version": "3.0"}, "pkg": {"sha256": "cc" * 32}}
        signed = sign_manifest(manifest, key)
        return signed, key

    def test_verify_valid_signature_passes(self) -> None:
        signed, key = self._make_signed()
        verify_manifest(signed, key)  # must not raise

    def test_verify_missing_signature_raises(self) -> None:
        manifest = {"_release": {"manifest_version": "3.0"}}
        key = SigningKey.for_testing()
        with pytest.raises(VerificationError, match="no _signature"):
            verify_manifest(manifest, key)

    def test_verify_tampered_manifest_raises(self) -> None:
        signed, key = self._make_signed()
        # Tamper: change a package hash
        signed["pkg"]["sha256"] = "dd" * 32
        with pytest.raises(VerificationError, match="INVALID signature|tampered"):
            verify_manifest(signed, key)

    def test_verify_wrong_key_raises(self) -> None:
        signed, _ = self._make_signed()
        wrong_key = SigningKey(b"wrong_key_material_123456789012", source="wrong")
        with pytest.raises(VerificationError):
            verify_manifest(signed, wrong_key)

    def test_verify_wrong_key_id_raises(self) -> None:
        signed, _ = self._make_signed()
        # Forge a key_id mismatch
        wrong_key = SigningKey(b"wrong_key_material_123456789012", source="wrong")
        with pytest.raises(VerificationError, match="Key ID mismatch|INVALID"):
            verify_manifest(signed, wrong_key)


class TestManageSkillPackagesSignature:
    """Integration tests: sign + verify with cryptographic signatures."""

    def test_sign_with_key_creates_signature(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_dirs(monkeypatch, tmp_path)
        _write_package(tmp_path / "skill-packages", "alpha")
        result = cmd_sign(_make_sign_args())
        assert result == 0
        manifest = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())
        assert "_signature" in manifest["_release"], "Manifest must contain a signature"
        assert len(manifest["_release"]["_signature"]) == 64

    def test_verify_signed_manifest_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_dirs(monkeypatch, tmp_path)
        _write_package(tmp_path / "skill-packages", "alpha")
        cmd_sign(_make_sign_args())
        assert cmd_verify(_make_verify_args()) == 0

    def test_verify_unsigned_manifest_fails_without_dev_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A manifest with no signature must fail verify unless dev-mode."""
        _patch_dirs(monkeypatch, tmp_path)
        _write_package(tmp_path / "skill-packages", "alpha")
        # Write a manifest without a signature
        checksums_file = tmp_path / "skill-packages" / "checksums.json"
        checksums_file.write_text(
            json.dumps({
                "_release": {"manifest_version": "3.0"},
                "alpha": {"file": "alpha.skill", "sha256": "a" * 64, "size_bytes": 4, "stale": False},
            }, indent=2),
            encoding="utf-8",
        )
        # Write the actual package so hash check doesn't fail first
        (tmp_path / "skill-packages" / "alpha.skill").write_text("test")
        result = cmd_verify(_make_verify_args(dev_mode=False))
        assert result == 1, "Unsigned manifest must fail verify without --dev-mode"

    def test_verify_unsigned_manifest_passes_with_dev_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Unsigned manifest is accepted in dev mode with a warning."""
        _patch_dirs(monkeypatch, tmp_path)
        content = b"pkg-content"
        _write_package(tmp_path / "skill-packages", "alpha", content)
        sha = hashlib.sha256(content).hexdigest()
        checksums_file = tmp_path / "skill-packages" / "checksums.json"
        checksums_file.write_text(
            json.dumps({
                "_release": {"manifest_version": "3.0"},
                "alpha": {"file": "alpha.skill", "sha256": sha, "size_bytes": len(content), "stale": False},
            }, indent=2),
            encoding="utf-8",
        )
        result = cmd_verify(_make_verify_args(dev_mode=True))
        assert result == 0, "Unsigned manifest should pass in dev mode"
        err = capsys.readouterr().err
        assert "DEV-MODE" in err or "not cryptographically signed" in err

    def test_verify_tampered_manifest_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Tampering with the manifest after signing must fail signature verification."""
        _patch_dirs(monkeypatch, tmp_path)
        _write_package(tmp_path / "skill-packages", "alpha")
        cmd_sign(_make_sign_args())

        # Tamper with the manifest
        checksums_file = tmp_path / "skill-packages" / "checksums.json"
        manifest = json.loads(checksums_file.read_text())
        # Add a fake package to the manifest (without re-signing)
        manifest["evil-package"] = {"file": "evil.skill", "sha256": "f" * 64}
        checksums_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        result = cmd_verify(_make_verify_args())
        assert result == 1, "Tampered manifest must fail signature verification"

    def test_verify_with_wrong_key_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Verifying with a different key than was used to sign must fail."""
        _patch_dirs(monkeypatch, tmp_path)
        _write_package(tmp_path / "skill-packages", "alpha")
        cmd_sign(_make_sign_args())

        # Switch to a different key for verification
        wrong_key = SigningKey(b"a_completely_different_key_12345", source="wrong")
        wrong_key_file = tmp_path / "wrong.key"
        wrong_key_file.write_text(wrong_key._key.hex(), encoding="utf-8")
        monkeypatch.delenv("TRADERMONTY_SIGNING_KEY", raising=False)

        result = cmd_verify(_make_verify_args(signing_key_file=str(wrong_key_file)))
        assert result == 1, "Wrong key must fail signature verification"

    def test_manifest_is_signed_detection(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_dirs(monkeypatch, tmp_path)
        _write_package(tmp_path / "skill-packages", "alpha")
        cmd_sign(_make_sign_args())
        manifest = json.loads((tmp_path / "skill-packages" / "checksums.json").read_text())
        assert _manifest_is_signed(manifest) is True

    def test_unsigned_manifest_is_not_signed(self) -> None:
        manifest = {"_release": {"manifest_version": "3.0"}}
        assert _manifest_is_signed(manifest) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
