# Offline unit tests

Root `conftest.py` installs an in-process socket guard before pytest collection
and keeps it until session finalization. The normal CI matrix and
`bash scripts/run_all_tests.sh` load this policy automatically.

Unmarked tests must mock provider clients or HTTP boundaries. DNS queries,
TCP connections (including `connect_ex`) and UDP `sendto`/`sendmsg` to external hosts
fail with **Outbound network blocked**, naming the operation and destination.
Private LAN and unspecified addresses are not loopback. IPv4/IPv6 loopback,
`localhost`, and Unix-domain IPC remain available for local fixtures. The guard
does not resolve arbitrary names to decide whether they are local.

Attempts are audited as well as interrupted: swallowing the exception, using
`xfail`, or attempting a request from a worker thread cannot make a test pass.
Module/session fixture setup and finalizers are protected. Swallowed attempts
during collection fail the session, even if the collected tests pass.

For a deliberate live integration test, use explicit authorization:

```python
import pytest

@pytest.mark.network
def test_live_provider():
    ...
```

The marker authorizes its active test and fixture phases. Shared fixture
initialization/finalization uses the context of the test that triggers it; keep
live fixtures separate from ordinary unit tests. The marker does not permit
collection-time networking. Do not add it to unit tests to bypass missing mocks.
Scheduled provider canaries remain separate live jobs.

This policy is a Python pytest guard, not an OS firewall. Subprocesses and
non-Python transports are not automatically sandboxed. Tests can replace socket
operations with mocks deliberately. Dependency installation by the matrix
runner occurs outside the test process. Use OS-level isolation when stronger
network containment is required.

Policy regression tests run nested pytest sessions with fake external transports,
so even a broken guard cannot send their external probes. A separate loopback
test checks real local sockets without contacting external services.
