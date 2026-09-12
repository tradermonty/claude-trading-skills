#!/usr/bin/env python3
"""Enforce per-skill runtime dependency declarations (issue #330).

Every production skill with executable Python must ship a
``skills/<id>/requirements.txt`` that declares all third-party packages
its packaged ``scripts/`` import. CI installs the repository-wide dev
environment, which masks missing declarations via transitive packages;
this check compares the AST import inventory against the declaration so
a standalone ``.skill`` install fails closed instead of degrading
silently (cf. issue #311: missing ``yfinance`` produced an all-zero
regime report that ``exposure-coach`` consumed as valid input).

Requirement-line grammar (single canonical form)::

    <PEP 508 requirement without URL or environment marker>[  # optional: <reason>]

``# optional:`` marks a package the skill degrades without (fallback
path plus an absence test are then mandatory). Everything else is a
required dependency and must install in a clean room.

Fallback semantics (conservative by design): an import counts as a
fallback import when it sits in a ``try`` whose handler catches
ImportError — ``except Exception`` and bare ``except`` count too. A
handler counts as aborting (so the entry must stay required) when it
contains any ``raise`` or any ``.exit()`` call, even inside a nested
``def``; over-declaring as required is always fail-safe. Non-stdlib,
non-first-party imports absent from IMPORT_TO_DIST are errors, never
silent passes.

Subcommands:
  check   fail closed on missing manifests, undeclared imports, stale
          entries, and optional entries without a fallback + test.
  report  machine-readable JSON of the same inventory (warnings included).
  smoke   offline packaged-skill smoke: the committed ``.skill`` must
          contain byte-identical ``requirements.txt`` and compilable
          scripts. No pip, no venv, no network.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
PACKAGES_DIR = ROOT / "skill-packages"

STDLIB_SENTINEL = "# stdlib-only"

# Vendored CPython 3.9 standard-library top-level module snapshot.
# Built from a newer interpreter's module list with post-3.9 additions
# (e.g. tomllib) removed. It is NOT a byte-exact 3.9 manifest: modules
# retired after 3.9 by PEP 594 (distutils, imp, cgi, imghdr, telnetlib,
# …) are absent, so a skill importing one of those would be misreported
# as an unmapped third-party import rather than stdlib. No current skill
# does; the conservative direction keeps the gate fail-closed.
# Deliberately NOT sys.stdlib_module_names: that attribute does not exist
# on the CI-pinned Python 3.9 interpreter.
STDLIB_39 = frozenset(
    """
__future__ _abc _ast _asyncio _bisect _blake2 _bz2 _codecs _codecs_cn
_codecs_hk _codecs_iso2022 _codecs_jp _codecs_kr _codecs_tw _collections
_collections_abc _compat_pickle _contextvars _csv _ctypes _curses
_curses_panel _datetime _dbm _decimal _elementtree _frozen_importlib
_frozen_importlib_external _functools _gdbm _hashlib _heapq _hmac _imp _io
_json _locale _lsprof _lzma _markupbase _md5 _multibytecodec _multiprocessing
_opcode _operator _osx_support _overlapped _pickle _posixshmem _posixsubprocess
_py_abc _pydecimal _pyio _queue _random _sha1 _sha3 _signal _socket _sqlite3
_sre _ssl _stat _statistics _string _strptime _struct _symtable _sysconfig
_thread _threading_local _tkinter _tracemalloc _warnings _weakref _weakrefset
_winapi _zoneinfo abc argparse array ast asyncio atexit base64 bdb binascii
bisect builtins bz2 cProfile calendar cmath cmd code codecs codeop collections
colorsys compileall concurrent configparser contextlib contextvars copy copyreg
csv ctypes curses dataclasses datetime dbm decimal difflib dis doctest email
encodings ensurepip enum errno faulthandler fcntl filecmp fileinput fnmatch
fractions ftplib functools gc genericpath getopt getpass gettext glob graphlib
grp gzip hashlib heapq hmac html http idlelib imaplib importlib inspect io
ipaddress itertools json keyword linecache locale logging lzma mailbox marshal
math mimetypes mmap modulefinder msvcrt multiprocessing netrc nt ntpath
nturl2path numbers opcode operator optparse os pathlib pdb pickle pickletools
pkgutil platform plistlib poplib posix posixpath pprint profile pstats pty pwd
py_compile pyclbr pydoc pydoc_data pyexpat queue quopri random re readline
reprlib resource rlcompleter runpy sched secrets select selectors shelve shlex
shutil signal site smtplib socket socketserver sqlite3 sre_compile sre_constants
sre_parse ssl stat statistics string stringprep struct subprocess symtable sys sysconfig
syslog tabnanny tarfile tempfile termios textwrap threading time timeit tkinter
token tokenize trace traceback tracemalloc tty turtle turtledemo types typing
unicodedata unittest urllib uuid venv warnings wave weakref webbrowser winreg
winsound wsgiref xml xmlrpc zipapp zipfile zipimport zlib zoneinfo
""".split()
)

# Third-party top-level import name -> distribution package name.
IMPORT_TO_DIST = {
    "requests": "requests",
    "yfinance": "yfinance",
    "pandas": "pandas",
    "numpy": "numpy",
    "scipy": "scipy",
    "statsmodels": "statsmodels",
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "finvizfinance": "finvizfinance",
    "PIL": "Pillow",
    "cv2": "opencv-python-headless",
    "pandas_market_calendars": "pandas-market-calendars",
    "manifoldbt": "manifoldbt",
    "yaml": "pyyaml",
    "jsonschema": "jsonschema",
    "packaging": "packaging",
}

# Extra required distributions keyed by skill for runtime uses invisible to
# the AST (e.g. a parser backend named only by a string literal).
EXTRA_DIST_REQUIRED: dict[str, dict[str, str]] = {
    # BeautifulSoup(html, "lxml") in finviz_stock_client.py.
    "canslim-screener": {"lxml": "lxml parser backend selected by string literal"},
}

# skills-index.yaml integrations id -> distribution package, used for the
# warn-only bidirectional consistency lint (promoted to error separately).
INTEGRATION_TO_DIST = {
    "yfinance": "yfinance",
}

# Dynamic-import call shapes that are reported as warnings. Entries are
# "<enclosing-function>:<call>(<literal-arg-or-?>)" so an allowlisted probe
# never silences an unrelated dynamic import elsewhere.
KNOWN_DYNAMIC: dict[str, str] = {
    "missing_required_packages:import_module(?)": (
        "startup required-package probe; statically covered by "
        "REQUIRED_PACKAGES in macro_regime_detector.py"
    ),
}


@dataclass
class RequirementEntry:
    dist: str
    spec: str
    optional: bool
    reason: str = ""


@dataclass
class SkillReport:
    skill_id: str
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)


def executable_skill_ids(root: Path = ROOT) -> list[str]:
    """Return executable skill ids from the canonical CI inventory."""
    sys.path.insert(0, str(root / "scripts"))
    try:
        from ci_test_matrix import executable_test_inventory

        return sorted(executable_test_inventory(root))
    finally:
        sys.path.remove(str(root / "scripts"))


def _first_party_modules(scripts_dir: Path) -> set[str]:
    """All module names owned by the skill itself (any depth + subpackages)."""
    if not scripts_dir.is_dir():
        return set()
    names = {path.stem for path in scripts_dir.rglob("*.py")}
    names |= {path.name for path in scripts_dir.iterdir() if path.is_dir()}
    return names


class _ImportVisitor(ast.NodeVisitor):
    """Collect third-party imports, fallback modes, and dynamic imports.

    Tracks the enclosing function so dynamic-import warnings can name
    their context (e.g. a statically-covered probe stays allowlisted
    without silencing unrelated dynamic imports elsewhere).
    """

    def __init__(self, first_party: set[str]) -> None:
        self.first_party = first_party
        self.third_party: set[str] = set()
        self.modes: dict[str, list[bool]] = {}
        self.dynamic: set[str] = set()
        self._func_stack: list[str] = []
        self._tree: ast.AST | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record(alias.name.split(".")[0], node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module:
            self.generic_visit(node)
            return
        self._record(node.module.split(".")[0], node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        context = self._func_stack[-1] + ":" if self._func_stack else ""
        if isinstance(func, ast.Name) and func.id == "__import__":
            self.dynamic.add(f"{context}__import__({_call_first_arg(node) or '?'})")
        elif isinstance(func, ast.Attribute) and func.attr == "import_module":
            self.dynamic.add(f"{context}import_module({_call_first_arg(node) or '?'})")
        self.generic_visit(node)

    def _record(self, top: str, node: ast.AST) -> None:
        if top in STDLIB_39 or top in self.first_party:
            return
        if top not in IMPORT_TO_DIST:
            self.third_party.add(f"!{top}")
            return
        self.third_party.add(top)
        assert self._tree is not None
        self.modes.setdefault(top, []).append(_in_fallback_try(node, self._tree))


def scan_skill_imports(skill_dir: Path) -> tuple[set[str], set[str], dict[str, bool]]:
    """AST-scan packaged scripts (excluding tests/).

    Returns (imports, dynamic_imports, fallback_imports). ``imports``
    holds third-party top-level names, plus ``!<name>`` sentinels for
    non-stdlib, non-first-party names absent from IMPORT_TO_DIST — those
    are fail-closed (extend the map instead of passing silently).
    ``fallback_imports`` maps a top-level name to True when every observed
    import of it sits inside a ``try`` whose ``except`` swallows
    ImportError without raising/exiting (HAS_* flag or degraded path).
    ``ast`` visits nested scopes, so function-level lazy imports
    (e.g. ``fmp_client.py``'s ``import yfinance``) are detected.
    """
    scripts_dir = skill_dir / "scripts"
    first_party = _first_party_modules(scripts_dir)
    third_party: set[str] = set()
    dynamic: set[str] = set()
    modes: dict[str, list[bool]] = {}

    for path in sorted(scripts_dir.rglob("*.py")):
        if not path.is_file() or "tests" in path.relative_to(scripts_dir).parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        visitor = _ImportVisitor(first_party)
        visitor._tree = tree
        visitor.visit(tree)
        third_party |= visitor.third_party
        dynamic |= visitor.dynamic
        for name, flags in visitor.modes.items():
            modes.setdefault(name, []).extend(flags)

    fallback = {name: (bool(flags) and all(flags)) for name, flags in modes.items()}
    return third_party, dynamic, fallback


def _in_fallback_try(node: ast.AST, tree: ast.AST) -> bool:
    """True when node is inside try/except-ImportError without raise/exit."""
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.Try):
            continue
        if not any(_catches_import_error(h) for h in parent.handlers):
            continue
        if _node_contains(node, parent):
            return not any(_handler_aborts(h) for h in parent.handlers if _catches_import_error(h))
    return False


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in ("ImportError", "Exception")
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id in ("ImportError", "Exception")
            for item in handler.type.elts
        )
    return False


def _handler_aborts(handler: ast.ExceptHandler) -> bool:
    for child in ast.walk(handler):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id == "exit":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "exit":
                return True
    return False


def _node_contains(target: ast.AST, container: ast.AST) -> bool:
    return any(child is target for child in ast.walk(container))


def _call_first_arg(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant):
        return str(node.args[0].value)
    return None


def parse_requirements(path: Path) -> tuple[dict[str, RequirementEntry], list[str]]:
    """Parse a skill requirements.txt; return (entries, errors)."""
    entries: dict[str, RequirementEntry] = {}
    errors: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        req_part, _, comment = line.partition("#")
        req_part = req_part.strip()
        comment = comment.strip()
        if not req_part:
            continue
        optional = comment.lower().startswith("optional:")
        reason = comment[len("optional:") :].strip() if optional else ""
        if optional and not reason:
            errors.append(f"line {lineno}: '# optional:' needs a reason")
        try:
            parsed = Requirement(req_part)
        except InvalidRequirement:
            errors.append(f"line {lineno}: invalid requirement {req_part!r}")
            continue
        if parsed.url is not None:
            errors.append(f"line {lineno}: direct URL references are rejected")
            continue
        if parsed.marker is not None:
            errors.append(
                f"line {lineno}: environment markers are rejected; "
                "use '# optional: <reason>' instead"
            )
            continue
        key = parsed.name.lower()
        if key in entries:
            errors.append(f"line {lineno}: duplicate entry for {parsed.name}")
            continue
        entries[key] = RequirementEntry(
            dist=parsed.name, spec=req_part, optional=optional, reason=reason
        )
    return entries, errors


def load_integrations(root: Path = ROOT) -> dict[str, list[tuple[str, str]]]:
    """Map skill id -> [(integration id, requirement)] from skills-index.yaml."""
    import yaml

    payload = yaml.safe_load((root / "skills-index.yaml").read_text(encoding="utf-8"))
    result: dict[str, list[tuple[str, str]]] = {}
    for item in payload.get("skills", []):
        skill_id = item.get("id")
        if not isinstance(skill_id, str):
            continue
        pairs = []
        for integration in item.get("integrations", []) or []:
            iid = integration.get("id")
            req = integration.get("requirement")
            if isinstance(iid, str) and isinstance(req, str):
                pairs.append((iid, req))
        result[skill_id] = pairs
    return result


def check_skill(
    skill_id: str,
    root: Path = ROOT,
    integrations: dict[str, list[tuple[str, str]] | None] | None = None,
) -> SkillReport:
    """Check one skill; pure offline (filesystem + AST only)."""
    report = SkillReport(skill_id=skill_id)
    skill_dir = root / "skills" / skill_id
    manifest = skill_dir / "requirements.txt"

    if not manifest.is_file():
        report.ok = False
        report.errors.append("missing requirements.txt (fail closed per issue #330)")
        return report

    entries, parse_errors = parse_requirements(manifest)
    for error in parse_errors:
        report.ok = False
        report.errors.append(error)

    third_party, dynamic, fallback = scan_skill_imports(skill_dir)
    for token in sorted(third_party):
        if token.startswith("!"):
            report.ok = False
            report.errors.append(
                f"unmapped third-party import: {token[1:]} "
                "(extend IMPORT_TO_DIST in check_skill_deps.py)"
            )
    third_party = {top for top in third_party if not top.startswith("!")}
    imported_dists = {IMPORT_TO_DIST[top] for top in third_party}
    for extra, _reason in EXTRA_DIST_REQUIRED.get(skill_id, {}).items():
        imported_dists.add(extra)

    declared = {entry.dist.lower(): entry for entry in entries.values()}

    for dist in sorted(imported_dists):
        if dist.lower() not in declared:
            report.ok = False
            report.errors.append(f"undeclared third-party import: {dist}")
    for key, entry in entries.items():
        if key not in {dist.lower() for dist in imported_dists}:
            report.ok = False
            report.errors.append(f"stale entry with no matching import: {entry.dist}")
            continue
        tops = [top for top, dist in IMPORT_TO_DIST.items() if dist.lower() == key]
        if entry.optional:
            if not any(fallback.get(top, False) for top in tops):
                report.ok = False
                report.errors.append(
                    f"optional entry {entry.dist} has no ImportError fallback import"
                )
            elif not _mentioned_in_tests(skill_dir, entry.dist):
                report.ok = False
                report.errors.append(
                    f"optional entry {entry.dist} has no absence test referencing it"
                )
        report.required.append(entry.dist) if not entry.optional else report.optional.append(
            entry.dist
        )

    for item in dynamic:
        if item not in KNOWN_DYNAMIC:
            report.warnings.append(f"dynamic import is not machine-checkable: {item}")

    if integrations is None:
        integrations = load_integrations(root)
    for iid, req in integrations.get(skill_id, []) or []:
        dist = INTEGRATION_TO_DIST.get(iid)
        if dist and req == "required" and dist.lower() not in declared:
            report.warnings.append(
                f"skills-index declares required integration {iid!r} "
                f"but requirements.txt lacks {dist}"
            )

    if not entries and STDLIB_SENTINEL not in manifest.read_text(encoding="utf-8"):
        report.ok = False
        report.errors.append(
            "empty manifest without '# stdlib-only' sentinel; "
            "declare dependencies or mark the skill stdlib-only"
        )
    if not third_party and not entries:
        text = manifest.read_text(encoding="utf-8")
        meaningful = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if meaningful:
            report.ok = False
            report.errors.append("stdlib-only skill must not list requirements")
        elif STDLIB_SENTINEL not in text:
            report.ok = False
            report.errors.append("stdlib-only skill must contain the '# stdlib-only' sentinel")
    if third_party and not entries:
        report.ok = False
        report.errors.append("third-party imports with an empty manifest")
    return report


def _mentioned_in_tests(skill_dir: Path, dist: str) -> bool:
    """True when any test file under the skill mentions the distribution.

    This is a mention check, not a proof of coverage: it pairs with the
    required ImportError-fallback import to evidence a degraded path.
    Absence-behavior quality itself is the owning skill suite's job.
    """
    needle = dist.lower().replace("-", "").replace("_", "")
    for test_dir in (skill_dir / "scripts" / "tests", skill_dir / "tests"):
        if not test_dir.is_dir():
            continue
        for path in test_dir.rglob("test_*.py"):
            try:
                hay = path.read_text(encoding="utf-8").lower()
            except OSError:
                continue
            compact = hay.replace("-", "").replace("_", "")
            if needle in compact or dist.lower() in hay:
                return True
    return False


def run_check(root: Path = ROOT) -> int:
    """Global fail-closed check over every executable skill."""
    integrations = load_integrations(root)
    failed: list[str] = []
    warned: list[str] = []
    for skill_id in executable_skill_ids(root):
        report = check_skill(skill_id, root, integrations)
        for error in report.errors:
            print(f"FAIL {skill_id}: {error}")
        for warning in report.warnings:
            print(f"WARN {skill_id}: {warning}")
            warned.append(skill_id)
        if not report.ok:
            failed.append(skill_id)
        elif report.required or report.optional:
            deps = ", ".join(report.required + [f"{d} (optional)" for d in report.optional])
            print(f"OK {skill_id}: {deps}")
        else:
            print(f"OK {skill_id}: stdlib-only")
    if failed:
        print(f"{len(failed)} skill(s) violate the dependency policy: {', '.join(failed)}")
        return 1
    if warned:
        print(f"warnings in: {', '.join(sorted(set(warned)))}")
    print("all executable skills declare their runtime dependencies")
    return 0


def run_report(root: Path = ROOT) -> int:
    integrations = load_integrations(root)
    payload = {"skills": []}
    for skill_id in executable_skill_ids(root):
        report = check_skill(skill_id, root, integrations)
        payload["skills"].append(
            {
                "id": report.skill_id,
                "ok": report.ok,
                "errors": report.errors,
                "warnings": report.warnings,
                "required": report.required,
                "optional": report.optional,
            }
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def run_smoke(skill_id: str, root: Path = ROOT) -> int:
    """Offline packaged-skill smoke: manifest equality + compilable scripts."""
    sys.path.insert(0, str(root / "scripts"))
    try:
        from ci_test_matrix import ID_RE

        valid = bool(ID_RE.fullmatch(skill_id))
    finally:
        sys.path.remove(str(root / "scripts"))
    if not valid:
        print(f"FAIL: unsafe skill id: {skill_id!r}")
        return 1
    skill_dir = root / "skills" / skill_id
    archive = root / "skill-packages" / f"{skill_id}.skill"
    if not archive.is_file():
        print(f"FAIL {skill_id}: packaged archive is missing: {archive}")
        return 1
    source_manifest = skill_dir / "requirements.txt"
    if not source_manifest.is_file():
        print(f"FAIL {skill_id}: source requirements.txt is missing")
        return 1
    expected = source_manifest.read_bytes()
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        manifest_name = f"{skill_id}/requirements.txt"
        if manifest_name not in names:
            print(f"FAIL {skill_id}: packaged .skill lacks requirements.txt")
            return 1
        if bundle.read(manifest_name) != expected:
            print(f"FAIL {skill_id}: packaged requirements.txt differs from source")
            return 1
        scripts = [n for n in names if n.endswith(".py") and "/tests/" not in n]
        if not scripts:
            print(f"FAIL {skill_id}: packaged .skill contains no scripts")
            return 1
        for name in scripts:
            try:
                compile(bundle.read(name).decode("utf-8"), name, "exec")
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"FAIL {skill_id}: {name} does not compile: {exc}")
                return 1
    print(f"OK {skill_id}: packaged manifest matches source; {len(scripts)} scripts compile")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="fail closed on dependency violations")
    subparsers.add_parser("report", help="JSON inventory report (always exit 0)")
    smoke_parser = subparsers.add_parser("smoke", help="offline packaged-skill smoke")
    smoke_parser.add_argument("--skill", required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        return run_check()
    if args.command == "report":
        return run_report()
    return run_smoke(args.skill)


if __name__ == "__main__":
    raise SystemExit(main())
