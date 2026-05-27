"""Unit tests for load_env.py — no network, no real secrets file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Import the module itself. `import X.Y.Z as alias` triggers `from X.Y import Z`,
# and `scripts/api_clients/__init__.py` re-exports `load_env` as a function,
# shadowing the module. Bypass that via sys.modules.
import scripts.api_clients.load_env  # noqa: E402,F401 ensures module is loaded

le = sys.modules["scripts.api_clients.load_env"]


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Reset the module load flag and clear any test env vars between tests."""
    monkeypatch.setattr(le, "_LOADED", False)
    for k in list(os.environ.keys()):
        if k.startswith(
            ("TEST_", "MY_", "FAKE_", "MARKETAUX_", "NEWSDATA_", "APIFY_", "MULTILINE_")
        ):
            monkeypatch.delenv(k, raising=False)
    return tmp_path


def write(tmp_env, body: str) -> Path:
    p = tmp_env / "secrets.env"
    p.write_text(body)
    return p


# ── shell-export format ─────────────────────────────────────────────


def test_simple_assignment(tmp_env):
    p = write(tmp_env, "TEST_KEY=abc123\n")
    seen = le.load_env(path=p, override=True)
    assert seen == {"TEST_KEY": "***REDACTED***"}
    assert os.environ["TEST_KEY"] == "abc123"


def test_export_prefix(tmp_env):
    p = write(tmp_env, 'export TEST_KEY="hello world"\n')
    le.load_env(path=p, override=True)
    assert os.environ["TEST_KEY"] == "hello world"


def test_single_quotes_stripped(tmp_env):
    p = write(tmp_env, "TEST_KEY='secret'\n")
    le.load_env(path=p, override=True)
    assert os.environ["TEST_KEY"] == "secret"


def test_double_quotes_stripped(tmp_env):
    p = write(tmp_env, 'TEST_KEY="secret"\n')
    le.load_env(path=p, override=True)
    assert os.environ["TEST_KEY"] == "secret"


def test_comments_ignored(tmp_env):
    p = write(tmp_env, "# a comment\n  # indented comment\nTEST_KEY=value\n")
    seen = le.load_env(path=p, override=True)
    assert "TEST_KEY" in seen


def test_blank_lines_ignored(tmp_env):
    p = write(tmp_env, "\n\nTEST_KEY=value\n\n")
    seen = le.load_env(path=p, override=True)
    assert seen == {"TEST_KEY": "***REDACTED***"}


def test_empty_value_skipped(tmp_env):
    p = write(tmp_env, "TEST_KEY=\nOTHER_KEY=value\n")
    seen = le.load_env(path=p, override=True)
    assert "TEST_KEY" not in seen
    assert "OTHER_KEY" in seen


def test_leading_whitespace_in_value_stripped(tmp_env):
    # Marketeaux line in real file had a leading space; the parser must strip
    p = write(tmp_env, "TEST_KEY=   spaced_value   \n")
    le.load_env(path=p, override=True)
    assert os.environ["TEST_KEY"] == "spaced_value"


def test_lowercase_keys_ignored(tmp_env):
    # The regex requires uppercase keys; protects against stray prose lines
    p = write(tmp_env, "lowercase_key=abc\nUPPERCASE_KEY=def\n")
    seen = le.load_env(path=p, override=True)
    assert "UPPERCASE_KEY" in seen
    assert "lowercase_key" not in seen
    assert "LOWERCASE_KEY" not in seen


# ── provider-block format ───────────────────────────────────────────


def test_provider_block_marketaux(tmp_env):
    body = """\
Provider  :Marketeaux
API Key   :marketaux_secret
Base URL  :
"""
    p = write(tmp_env, body)
    le.load_env(path=p, override=True)
    assert os.environ["MARKETAUX_API_KEY"] == "marketaux_secret"  # pragma: allowlist secret


def test_provider_block_newsdata(tmp_env):
    body = "Provider :Newsdata IO\nAPI Key :nd_secret\n"
    p = write(tmp_env, body)
    le.load_env(path=p, override=True)
    assert os.environ["NEWSDATA_API_KEY"] == "nd_secret"  # pragma: allowlist secret


def test_provider_block_unknown_provider_uses_fallback_name(tmp_env):
    body = "Provider :Acme Corp\nAPI Key :acme123\n"
    p = write(tmp_env, body)
    le.load_env(path=p, override=True)
    # spaces become underscores, uppercased, _API_KEY suffix
    assert os.environ["ACME_CORP_API_KEY"] == "acme123"  # pragma: allowlist secret


def test_provider_block_empty_value_skipped(tmp_env):
    body = "Provider :Marketeaux\nAPI Key :\n"
    p = write(tmp_env, body)
    seen = le.load_env(path=p, override=True)
    assert "MARKETAUX_API_KEY" not in seen


def test_orphan_api_key_without_provider_ignored(tmp_env):
    # "API Key :something" without a preceding "Provider :Name" must not set anything
    p = write(tmp_env, "API Key :orphan_value\n")
    seen = le.load_env(path=p, override=True)
    assert seen == {}


# ── override semantics ──────────────────────────────────────────────


def test_existing_env_var_not_overridden_by_default(tmp_env, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "preset_value")
    p = write(tmp_env, "TEST_KEY=file_value\n")
    le.load_env(path=p, override=False)
    assert os.environ["TEST_KEY"] == "preset_value"


def test_override_true_replaces(tmp_env, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "preset_value")
    p = write(tmp_env, "TEST_KEY=file_value\n")
    le.load_env(path=p, override=True)
    assert os.environ["TEST_KEY"] == "file_value"


# ── missing file ────────────────────────────────────────────────────


def test_missing_file_returns_empty(tmp_env):
    bogus = tmp_env / "does_not_exist.env"
    assert le.load_env(path=bogus) == {}


# ── get_api_key ─────────────────────────────────────────────────────


def test_get_api_key_required_raises(tmp_env, monkeypatch):
    monkeypatch.delenv("NEVER_SET_KEY_XYZ", raising=False)
    monkeypatch.setattr(le, "_LOADED", True)  # skip auto-load
    with pytest.raises(RuntimeError, match="Missing API key NEVER_SET_KEY_XYZ"):
        le.get_api_key("NEVER_SET_KEY_XYZ")


def test_get_api_key_optional_returns_none(tmp_env, monkeypatch):
    monkeypatch.delenv("MAYBE_KEY_XYZ", raising=False)
    monkeypatch.setattr(le, "_LOADED", True)
    assert le.get_api_key("MAYBE_KEY_XYZ", required=False) is None


def test_get_api_key_returns_value(tmp_env, monkeypatch):
    monkeypatch.setenv("PRESENT_KEY", "value123")
    monkeypatch.setattr(le, "_LOADED", True)
    assert le.get_api_key("PRESENT_KEY") == "value123"


def test_get_api_key_error_does_not_echo_value(tmp_env, monkeypatch):
    # Security: error message must not leak any other env var's value
    monkeypatch.setenv("OTHER_SECRET", "do_not_leak_this")
    monkeypatch.setattr(le, "_LOADED", True)
    with pytest.raises(RuntimeError) as ei:
        le.get_api_key("MISSING_KEY_NAME")
    assert "do_not_leak_this" not in str(ei.value)


# ── never-echo-values invariant ─────────────────────────────────────


def test_load_env_return_only_redacts_values(tmp_env):
    p = write(tmp_env, "REAL_SECRET=should_not_appear\nOTHER=also_secret\n")
    seen = le.load_env(path=p, override=True)
    for v in seen.values():
        assert v == "***REDACTED***"
        assert "should_not_appear" not in v
        assert "also_secret" not in v
