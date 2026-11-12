"""Implementation package for the workflow replay harness (Issue #502).

``scripts/workflow_replay.py`` stays the entry point and the import surface:
CI, docs, and the guided runner invoke ``python3 scripts/workflow_replay.py``,
and tests ``import workflow_replay`` and monkeypatch helpers on it. A package
directory named ``scripts/workflow_replay/`` would collide with that module
name on ``sys.path``, so the split modules live here under a distinct name and
the shim re-exports every name the monolithic module defined.

Package functions look helpers up in their own module globals. The shim
therefore uses a module subclass that forwards a rebinding such as
``monkeypatch.setattr(workflow_replay, "_run_cli", fake)`` to each package
module holding the same object, so patches made on the shim affect replay
behavior exactly as they did when everything lived in one namespace.

The split is a pure move: function and class bodies are verbatim copies of the
former module. ``constants.REPO_ROOT`` walks one extra parent because this
package sits one directory deeper than the old module; its value is unchanged.

Modules, in dependency order (each imports only from modules above it):

- ``constants``: repository paths and fixed constants
- ``common``: shared errors, loaders, CLI runner, validation helpers
- ``normalize``: path canonicalization, digests, output normalization
- ``artifacts``: artifact discovery, file and provenance validation
- ``steps_*``: one module of step adapters per canonical workflow
- ``registry``: ``EXECUTORS`` mapping step ids to step adapters
- ``manifest``: coverage manifest and replay spec validation
- ``execution``: replay execution and transactional publication
- ``golden``: golden comparison, check, and regeneration
- ``cli``: argument parser and ``main``
"""
