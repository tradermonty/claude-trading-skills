"""Exercise the root pytest policy in isolated nested pytest sessions."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Replace OS-facing operations before loading the real guard. Even RED runs
# cannot contact external hosts; a missing guard instead makes the child pass.
STUB_TRANSPORT = """
import builtins
import socket
builtins.original_network_calls = []
def fake_resolve(*args, **kwargs):
    builtins.original_network_calls.append(args)
    return []
def fake_connect(*args, **kwargs):
    builtins.original_network_calls.append(args)
    return 0
socket.getaddrinfo = fake_resolve
socket.gethostbyname = fake_resolve
socket.gethostbyname_ex = fake_resolve
socket.gethostbyaddr = fake_resolve
socket.getnameinfo = fake_resolve
socket.socket.connect = fake_connect
socket.socket.connect_ex = fake_connect
socket.socket.sendto = fake_connect
"""


def _run(tmp_path, body, *, stub=True, extra_conftest=""):
    (tmp_path / "conftest.py").write_text(
        (STUB_TRANSPORT if stub else "") + (ROOT / "conftest.py").read_text() + extra_conftest
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_probe.py").write_text("import socket\nimport pytest\n" + body)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"}
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


EXTERNAL_CALLS = [
    "socket.getaddrinfo('example.com', 443)",
    "socket.gethostbyname('example.com')",
    "socket.gethostbyname_ex('example.com')",
    "socket.gethostbyaddr('203.0.113.7')",
    "socket.getnameinfo(('203.0.113.7', 443), 0)",
    "socket.socket().connect(('203.0.113.7', 443))",
    "socket.socket().connect_ex(('203.0.113.7', 443))",
    "socket.create_connection(('example.com', 443))",
    "socket.socket(socket.AF_INET6).connect(('2001:db8::1', 443))",
    "socket.socket(type=socket.SOCK_DGRAM).sendto(b'x', ('203.0.113.7', 9))",
]
if hasattr(socket.socket, "sendmsg"):
    EXTERNAL_CALLS.append(
        "socket.socket(type=socket.SOCK_DGRAM).sendmsg([b'x'], [], 0, ('203.0.113.7', 9))"
    )
    STUB_TRANSPORT += "socket.socket.sendmsg = fake_connect\n"


@pytest.mark.parametrize("call", EXTERNAL_CALLS)
def test_external_operations_fail_clearly_before_transport(tmp_path, call):
    result = _run(tmp_path, f"def test_probe():\n    {call}\n")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "Outbound network blocked" in result.stdout
    assert "network" in result.stdout and "mock" in result.stdout


@pytest.mark.parametrize("host", ["192.168.1.2", "0.0.0.0", "::", "localhost.example.com"])
def test_private_unspecified_and_deceptive_hosts_are_not_loopback(tmp_path, host):
    result = _run(tmp_path, f"def test_probe():\n    socket.getaddrinfo({host!r}, 443)\n")
    assert result.returncode != 0
    assert "Outbound network blocked" in result.stdout


@pytest.mark.parametrize("catch", ["Exception", "BaseException"])
def test_swallowed_attempt_still_fails(tmp_path, catch):
    result = _run(
        tmp_path,
        f"def test_probe():\n    try:\n        socket.getaddrinfo('example.com', 443)\n"
        f"    except {catch}:\n        pass\n",
    )
    assert result.returncode != 0
    assert "Outbound network blocked" in result.stdout


def test_expected_failure_cannot_hide_outbound_attempt(tmp_path):
    result = _run(
        tmp_path,
        "@pytest.mark.xfail\ndef test_probe():\n    socket.getaddrinfo('example.com', 443)\n",
    )
    assert result.returncode != 0
    assert "Outbound network blocked" in result.stdout


@pytest.mark.parametrize("scope", ["module", "session"])
@pytest.mark.parametrize("phase", ["setup", "teardown"])
def test_fixture_lifecycle_cannot_swallow_attempts(tmp_path, scope, phase):
    attempt = "    try:\n        socket.getaddrinfo('example.com', 443)\n    except BaseException:\n        pass\n"
    fixture = f"\n@pytest.fixture(scope={scope!r}, autouse=True)\ndef fixture_probe():\n"
    fixture += attempt + "    yield\n" if phase == "setup" else "    yield\n" + attempt
    result = _run(tmp_path, "def test_probe():\n    pass\n", extra_conftest=fixture)
    assert result.returncode != 0
    assert "Outbound network blocked" in result.stdout


def test_swallowed_collection_attempt_fails_session(tmp_path):
    result = _run(
        tmp_path,
        "try:\n    socket.getaddrinfo('example.com', 443)\nexcept BaseException:\n    pass\n"
        "def test_probe():\n    pass\n",
    )
    assert result.returncode != 0
    assert "Outbound network blocked" in result.stdout


def test_swallowed_worker_thread_attempt_fails_test(tmp_path):
    result = _run(
        tmp_path,
        """
import threading
def test_probe():
    def worker():
        try:
            socket.getaddrinfo('example.com', 443)
        except BaseException:
            pass
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
""",
    )
    assert result.returncode != 0
    assert "Outbound network blocked" in result.stdout


def test_guard_restores_originals_after_session(tmp_path):
    result = _run(
        tmp_path,
        "def test_probe():\n    pass\n",
        extra_conftest="\ndef pytest_unconfigure(config):\n    assert socket.getaddrinfo is fake_resolve\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_marker_allows_live_context_without_leaking_to_next_test(tmp_path):
    result = _run(
        tmp_path,
        "import builtins\n@pytest.mark.network\ndef test_a_live():\n"
        "    socket.getaddrinfo('example.com', 443)\n"
        "    assert len(builtins.original_network_calls) == 1\n"
        "def test_b_offline():\n    socket.getaddrinfo('example.com', 443)\n",
    )
    assert result.returncode != 0
    assert "1 failed, 1 passed" in result.stdout
    assert "PytestUnknownMarkWarning" not in result.stdout


def test_live_marker_covers_function_fixture_phases(tmp_path):
    result = _run(
        tmp_path,
        """
import builtins
@pytest.fixture
def live_fixture():
    socket.getaddrinfo('example.com', 443)
    yield
    socket.getaddrinfo('example.com', 443)
@pytest.mark.network
def test_probe(live_fixture):
    socket.getaddrinfo('example.com', 443)
    assert len(builtins.original_network_calls) == 2
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_loopback_dns_tcp_udp_and_unix_ipc_work(tmp_path):
    result = _run(
        tmp_path,
        """
def test_probe():
    assert socket.getaddrinfo('localhost', 0)
    assert socket.getaddrinfo('127.0.0.1', 0)
    with socket.socket() as server, socket.socket() as client:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        client.connect(server.getsockname())
        conn, _ = server.accept()
        conn.close()
    with socket.socket(type=socket.SOCK_DGRAM) as server, socket.socket(type=socket.SOCK_DGRAM) as client:
        server.bind(('127.0.0.1', 0))
        assert client.sendto(b'x', server.getsockname()) == 1
        assert server.recvfrom(1)[0] == b'x'
    if socket.has_ipv6:
        assert socket.getaddrinfo('::1', 0, socket.AF_INET6)
    if hasattr(socket, 'AF_UNIX'):
        a, b = socket.socketpair()
        with a, b:
            a.sendall(b'x')
            assert b.recv(1) == b'x'
""",
        stub=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
