"""Conservative, advisory AST evidence for network timeout prerequisites.

Only direct imported call aliases and constructor-bound clients are resolved.
Dynamic dispatch, rebinding and delegated SDK operations require human review.
A bounded argument is evidence for that call, not a whole-program safety proof.

Two skill-level proofs (issue #778) are applied by :func:`skill_evidence`:

* ``timeout=self.<attr>`` is bounded when ``<attr>`` is assigned exactly once
  in the whole skill, as a top-level ``__init__`` statement of the enclosing
  class with a finite positive literal, and no dynamic attribute write exists.
* A call into a sibling script module counts as delegated, not unproven, when
  that module is unambiguous, has no dynamic code loading, and is itself fully
  proven. Reaching through the module (``mod.requests.get``) is not delegation.
"""

from __future__ import annotations

import ast
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "request",
    "stream",
    "send",
    "urlretrieve",
}
NETWORK_MODULES = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib.request",
    "urllib3",
    "http.client",
    "socket",
    "ftplib",
    "smtplib",
    "websocket",
    "websockets",
    "yfinance",
    "alpaca",
}
FACTORIES = {
    "requests.Session",
    "requests.session",
    "httpx.Client",
    "httpx.AsyncClient",
    "aiohttp.ClientSession",
    "urllib3.PoolManager",
    "http.client.HTTPConnection",
    "http.client.HTTPSConnection",
}


def _network(name: str) -> bool:
    return any(
        name == module or name.startswith(module + ".") for module in NETWORK_MODULES
    ) or any(part.endswith("fmp_client") for part in name.split("."))


def _bounded(value: ast.expr | None) -> bool:
    if isinstance(value, ast.Constant):
        try:
            return (
                type(value.value) in (int, float) and math.isfinite(value.value) and value.value > 0
            )
        except OverflowError:
            return False
    if isinstance(value, ast.Tuple) and len(value.elts) == 2:
        return all(_bounded(item) and isinstance(item, ast.Constant) for item in value.elts)
    return False


DYNAMIC_ATTRIBUTES = {
    "__dict__",
    "__setattr__",
    "__delattr__",
    "__getattribute__",
    "__getattr__",
    "attrgetter",
    "methodcaller",
}
DYNAMIC_CALLS = {"__import__", "exec", "eval", "compile", "vars"}
# Rebinding these on a class or instance changes attribute lookup itself.
HOOK_ATTRIBUTES = {
    "__class__",
    "__init__",
    "__getattribute__",
    "__getattr__",
    "__setattr__",
    "__delattr__",
}
# Defining any of these in a class body defeats the constant-attribute proof.
CLASS_HOOKS = {"__getattribute__", "__getattr__", "__setattr__", "__delattr__", "__slots__"}
# Names whose mere reference (other than a literal-name direct call) can write
# an attribute the scan cannot name.
WRITER_NAMES = {"setattr", "delattr", "vars", "__builtins__"}


@dataclass
class SkillContext:
    """Whole-skill facts that a single-file scan cannot see."""

    attribute_stores: Counter = field(default_factory=Counter)
    poisoned: bool = True  # unknown writes: no attribute proof
    proven_modules: frozenset[str] = frozenset()
    # proven module -> top-level classes/functions it defines itself
    provider_symbols: dict[str, frozenset[str]] = field(default_factory=dict)
    # client attribute name (``self.<name> = requests.Session()``) -> provider files
    client_attributes: dict[str, frozenset[str]] = field(default_factory=dict)


def _store_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _store_names(item)]
    if isinstance(target, ast.Starred):
        return _store_names(target.value)
    return []


def attribute_writes(tree: ast.AST) -> tuple[Counter, bool]:
    """Count every way a file can (re)bind an attribute name.

    Returns ``(counts, poisoned)``. ``poisoned`` means a write whose attribute
    name cannot be determined statically, which defeats every attribute proof.
    """
    counts: Counter = Counter()
    poisoned = False
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in WRITER_NAMES:
            parent = parents.get(node)
            literal_call = (
                isinstance(parent, ast.Call)
                and parent.func is node
                and node.id in ("setattr", "delattr")
                and len(parent.args) >= 2
                and isinstance(parent.args[1], ast.Constant)
                and isinstance(parent.args[1].value, str)
            )
            if not literal_call:
                poisoned = True  # aliased, passed, vars(), __builtins__ ...
        if isinstance(node, ast.Name) and node.id == "getattr":
            # Dynamic attribute reads can reach a client under any name.
            parent = parents.get(node)
            if not (
                isinstance(parent, ast.Call)
                and parent.func is node
                and len(parent.args) >= 2
                and isinstance(parent.args[1], ast.Constant)
                and isinstance(parent.args[1].value, str)
            ):
                poisoned = True
        if isinstance(node, ast.Name) and node.id in ("attrgetter", "methodcaller"):
            poisoned = True
        if isinstance(node, ast.Import) and any(
            item.name.split(".")[0] in ("builtins", "operator") for item in node.names
        ):
            poisoned = True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in (
            "builtins",
            "operator",
        ):
            poisoned = True
        if isinstance(node, ast.ClassDef):
            # Any lookup hook or metaclass in the skill (including a subclass
            # of a proven class) can change what an attribute read returns.
            hooked = {
                stmt.name
                for stmt in node.body
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
            } | {
                target.id
                for stmt in node.body
                if isinstance(stmt, (ast.Assign, ast.AnnAssign))
                for target in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target])
                if isinstance(target, ast.Name)
            }
            if node.keywords or hooked & CLASS_HOOKS:
                poisoned = True
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [node.target]
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            targets = [node.optional_vars]
        for target in targets:
            names = _store_names(target)
            counts.update(names)
            if HOOK_ATTRIBUTES.intersection(names):
                poisoned = True  # e.g. Client.__init__ = ..., obj.__class__ = ...
        if isinstance(node, ast.ClassDef):
            # Class-body names (attributes, methods, properties) shadow or
            # override instance attributes of the same name.
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    counts[stmt.name] += 1
                elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    for target in stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]:
                        if isinstance(target, ast.Name):
                            counts[target.id] += 1
        if isinstance(node, ast.Attribute) and node.attr in DYNAMIC_ATTRIBUTES:
            poisoned = True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("setattr", "delattr"):
                if (
                    len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                ):
                    counts[node.args[1].value] += 1
                else:
                    poisoned = True
            elif node.func.id == "vars":
                poisoned = True
    return counts, poisoned


def has_dynamic_code(tree: ast.AST) -> bool:
    """True when a module can load or run code the scan cannot follow."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            item.name.split(".")[0] in ("importlib", "runpy") for item in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in (
            "importlib",
            "runpy",
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in DYNAMIC_CALLS
        ):
            return True
    return False


def _constant_self_attributes(tree: ast.AST, context: SkillContext) -> dict[int, set[str]]:
    """Map ``id(ClassDef)`` to attributes proven to hold one bounded literal."""
    proven: dict[int, set[str]] = {}
    if context.poisoned:
        return proven
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        if cls.bases or cls.keywords or cls.decorator_list:
            continue  # inherited, metaclass or decorator lookup is not traced
        body_names = {
            stmt.name
            for stmt in cls.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        } | {
            target.id
            for stmt in cls.body
            if isinstance(stmt, (ast.Assign, ast.AnnAssign))
            for target in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target])
            if isinstance(target, ast.Name)
        }
        if body_names & CLASS_HOOKS:
            continue
        init = next(
            (
                stmt
                for stmt in cls.body
                if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__"
            ),
            None,
        )
        if init is None or init.decorator_list or not init.args.args:
            continue
        me = init.args.args[0].arg
        names: set[str] = set()
        for stmt in init.body:  # top-level statements only: never conditional
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Attribute)
                and isinstance(stmt.targets[0].value, ast.Name)
                and stmt.targets[0].value.id == me
                and _bounded(stmt.value)
                and context.attribute_stores[stmt.targets[0].attr] == 1
            ):
                names.add(stmt.targets[0].attr)
        proven[id(cls)] = names
    return proven


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return None


def skill_evidence(
    scripts: list[tuple[Path, str]], context_sources: list[Path] | None = None
) -> list[dict]:
    """Evaluate a skill's scripts together so the two skill-level proofs apply.

    ``scripts`` holds ``(path, relative)`` pairs; ``relative`` is the path
    under the skill root (for example ``scripts/fmp_client.py``).
    ``context_sources`` are further files that can mutate the scripts at run
    time (for example package ``__init__.py`` files). They are not reported on,
    but their attribute writes count, and an unreadable one blocks the
    attribute proof.
    """
    trees: dict[str, ast.AST | None] = {relative: _parse(path) for path, relative in scripts}
    extra = [_parse(path) for path in context_sources or []]
    stores: Counter = Counter()
    poisoned = any(tree is None for tree in [*trees.values(), *extra])
    for tree in [*trees.values(), *extra]:
        if tree is not None:
            counts, dynamic = attribute_writes(tree)
            stores.update(counts)
            poisoned = poisoned or dynamic

    def module_name(relative: str) -> str:
        parts = Path(relative).with_suffix("").parts
        return ".".join(parts[1:] if parts and parts[0] == "scripts" else parts)

    # sys.path tweaks can make ``sub/x.py`` importable as ``x``, so a stem shared
    # by two scripts is ambiguous even when the dotted names differ.
    stems = Counter(Path(relative).stem for relative in trees)
    candidates = {
        module_name(relative): relative
        for relative, tree in trees.items()
        if tree is not None and stems[Path(relative).stem] == 1 and not has_dynamic_code(tree)
    }
    # Only a module's own top-level classes and functions can be delegated to;
    # an imported name it merely re-exports (``from requests import get``) is not.
    symbols = {
        module: frozenset(
            stmt.name
            for stmt in trees[relative].body
            if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        )
        for module, relative in candidates.items()
    }

    def run(proven: frozenset[str], attributes: dict[str, frozenset[str]]) -> dict[str, dict]:
        context = SkillContext(stores, poisoned, proven, symbols, attributes)
        return {relative: script_evidence(path, relative, context) for path, relative in scripts}

    def client_attributes(results: dict[str, dict]) -> dict[str, frozenset[str]]:
        # Every file's own client attributes: reaching one from another file
        # (``client.http.get``) bypasses the owner's bounded call sites.
        owners: dict[str, set[str]] = {}
        for relative, evidence in results.items():
            for name in evidence.get("client_attributes", []):
                owners.setdefault(name, set()).add(relative)
        return {name: frozenset(files) for name, files in owners.items()}

    proven: frozenset[str] = frozenset()
    results = run(proven, {})
    attributes = client_attributes(results)
    if poisoned:
        # Dynamic attribute access, lookup hooks or unreadable sources make the
        # owner-attribute rule unsound, so no delegation is proven either.
        results = run(proven, attributes)
        return [results[relative] for _, relative in scripts]
    for _ in range(len(trees) + 2):
        results = run(proven, attributes)
        grown = frozenset(
            module for module, relative in candidates.items() if not results[relative]["findings"]
        )
        if grown == proven:
            return [results[relative] for _, relative in scripts]
        proven = grown
    # No fixed point: fall back to the plain per-file verdicts.
    results = run(frozenset(), attributes)
    return [results[relative] for _, relative in scripts]


def script_evidence(path: Path, relative: str, context: SkillContext | None = None) -> dict:
    context = context or SkillContext()
    findings: list[str] = []
    calls: list[dict] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return {
            "calls": [],
            "applicability": "unproven",
            "findings": [f"{relative}: source cannot be inspected ({type(exc).__name__})"],
        }
    bindings: dict[str, set[str]] = {}

    def delegated(name: str) -> str | None:
        """Module a name delegates to: exactly ``<proven module>.<symbol>``."""
        for module in context.proven_modules:
            if name == module:
                return module
            rest = name[len(module) + 1 :] if name.startswith(module + ".") else ""
            if rest and "." not in rest and rest in context.provider_symbols.get(module, ()):
                return module
        return None

    def is_net(name: str) -> bool:
        return _network(name) and delegated(name) is None

    def bind(local, imported):
        bindings.setdefault(local, set()).add(imported)
        if imported.endswith(".*") and _network(imported):
            findings.append(f"{relative}: wildcard network import is unproven")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                bind(
                    item.asname or item.name.split(".")[0],
                    item.name if item.asname else item.name.split(".")[0],
                )
                if _network(item.name):
                    bind(item.name, item.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                bind(item.asname or item.name, f"{node.module}.{item.name}")
    network_imports = {key for key, names in bindings.items() if any(is_net(n) for n in names)}
    for local in network_imports:
        if len(bindings[local]) != 1:
            findings.append(f"{relative}: ambiguous/rebound network import alias {local}")
    # Ambiguities are gaps rather than a lexical-scope/data-flow claim.
    imports = {local: sorted(names)[0] for local, names in bindings.items()}

    def canonical(expr):
        if isinstance(expr, ast.Name):
            return imports.get(expr.id, expr.id)
        if isinstance(expr, ast.Attribute):
            return canonical(expr.value) + "." + expr.attr
        return ""

    assignments: dict[str, list[ast.expr | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            assignments.setdefault(ast.unparse(target), []).append(value)
    # Context-manager targets are constructor-bound clients too.
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    assignments.setdefault(ast.unparse(item.optional_vars), []).append(
                        item.context_expr
                    )
    clients = {
        target
        for target, values in assignments.items()
        if any(isinstance(v, ast.Call) and canonical(v.func) in FACTORIES for v in values)
    }
    # A class-body client (``http = requests.Session()``) is used as
    # ``self.http`` / ``Cls.http``; track those receivers too.
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in clients for t in stmt.targets
            ):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        clients.update({f"self.{t.id}", f"cls.{t.id}", f"{cls.name}.{t.id}"})
    # Resolve direct receiver aliases transitively; escaping a bound method is
    # still a gap because we do not prove indirect callable dispatch.
    changed = True
    while changed:
        before = len(clients)
        for target, values in assignments.items():
            if any(v is not None and ast.unparse(v) in clients for v in values):
                clients.add(target)
        changed = len(clients) != before
    for target, values in assignments.items():
        if target in clients and not all(
            (isinstance(v, ast.Call) and canonical(v.func) in FACTORIES)
            or (v is not None and ast.unparse(v) in clients)
            for v in values
        ):
            findings.append(f"{relative}: network receiver {target} is rebound or unproven")
        for value in values:
            method_alias = isinstance(value, ast.Attribute) and ast.unparse(value.value) in clients
            if value is not None and (_network(canonical(value)) or method_alias):
                findings.append(f"{relative}: network callable alias {target} is unproven")
        if target in network_imports:
            findings.append(f"{relative}: network import {target} is rebound")

    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    constant_attributes = _constant_self_attributes(tree, context)

    def attribute_bounded(timeout) -> bool:
        """``timeout=self.<attr>`` inside a plain method of a proven class."""
        if not (isinstance(timeout, ast.Attribute) and isinstance(timeout.value, ast.Name)):
            return False
        func = parents.get(timeout)
        while func is not None and not isinstance(
            func, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            func = parents.get(func)
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        cls = parents.get(func)
        if not isinstance(cls, ast.ClassDef) or func.decorator_list or not func.args.args:
            return False
        me = func.args.args[0].arg
        if timeout.value.id != me or any(
            isinstance(n, ast.Name) and n.id == me and isinstance(n.ctx, (ast.Store, ast.Del))
            for n in ast.walk(func)
        ):
            return False
        return timeout.attr in constant_attributes.get(id(cls), set())

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = canonical(node.func)
        raw = ast.unparse(node.func)
        receiver = ast.unparse(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        method = node.func.attr if isinstance(node.func, ast.Attribute) else name.rsplit(".", 1)[-1]
        direct = is_net(name) and (method in HTTP_METHODS or method == "urlopen")
        chained_factory = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Call)
            and canonical(node.func.value.func) in FACTORIES
        )
        bound_client = (receiver in clients or chained_factory) and method in HTTP_METHODS
        if direct or bound_client:
            timeout = next((kw.value for kw in node.keywords if kw.arg == "timeout"), None)
            bounded = _bounded(timeout) or attribute_bounded(timeout)
            calls.append({"path": relative, "line": node.lineno, "call": raw, "bounded": bounded})
            if not bounded:
                findings.append(
                    f"{relative}:{node.lineno} {raw}: timeout is missing or unproven (finite positive literal required)"
                )
        elif name in FACTORIES or name == "urllib.request.Request":
            continue
        elif _network(name) and delegated(name):
            # A call into a fully proven sibling module: its own requests are
            # the evidence, so record the delegation instead of a gap.
            calls.append(
                {
                    "path": relative,
                    "line": node.lineno,
                    "call": raw,
                    "bounded": True,
                    "delegated_to": delegated(name),
                }
            )
        elif is_net(name):
            # Exception constructors and local URL parsing are not requests.
            if not any(part in name for part in ("Exception", "Error")):
                findings.append(f"{relative}:{node.lineno} {raw}: network operation is unproven")
        elif method in HTTP_METHODS and receiver.rsplit(".", 1)[-1].lower() in {
            "client",
            "transport",
            "session",
            "sess",
        }:
            findings.append(f"{relative}:{node.lineno} {raw}: unknown network receiver")
        elif name == "getattr" and node.args and _network(canonical(node.args[0])):
            findings.append(f"{relative}:{node.lineno}: dynamic network dispatch is unproven")
    # Audit uses of known clients, not just discovered requests. Otherwise a
    # bounded request could mask a second request through an escaped receiver.
    local_attributes = {
        "headers",
        "cookies",
        "params",
        "auth",
        "proxies",
        "adapters",
        "close",
        "mount",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.expr):
            continue
        raw = ast.unparse(node)
        if raw not in clients:
            continue
        if isinstance(getattr(node, "ctx", None), ast.Store):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            call = parents.get(parent)
            if parent.attr in local_attributes:
                continue
            if parent.attr in HTTP_METHODS and isinstance(call, ast.Call) and call.func is parent:
                continue  # recorded and checked above
        if isinstance(parent, ast.Assign) and parent.value is node:
            if all(ast.unparse(target) in clients for target in parent.targets):
                continue
        if isinstance(parent, ast.AnnAssign) and parent.value is node:
            if ast.unparse(parent.target) in clients:
                continue
        findings.append(
            f"{relative}:{node.lineno}: network client {raw} escapes through unproven use"
        )

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        name = canonical(node)
        is_network_callable = name in FACTORIES or (
            _network(name) and name.rsplit(".", 1)[-1] in (HTTP_METHODS | {"urlopen"})
        )
        if not is_network_callable:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Call) and parent.func is node:
            continue  # direct calls checked above; factories' result audited below
        findings.append(
            f"{relative}:{node.lineno}: network callable {ast.unparse(node)} escapes through unproven use"
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or canonical(node.func) not in FACTORIES:
            continue
        parent = parents.get(node)
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node:
            continue
        if isinstance(parent, ast.withitem) and parent.context_expr is node:
            continue
        if isinstance(parent, ast.Attribute) and parent.value is node:
            outer = parents.get(parent)
            if parent.attr in HTTP_METHODS and isinstance(outer, ast.Call) and outer.func is parent:
                continue
        findings.append(
            f"{relative}:{node.lineno}: constructed network client escapes through unproven use"
        )
    # A subclass of a delegated class is itself scanned here, and any reach
    # into the base's client attributes is caught below; only attribute-lookup
    # hooks or a metaclass in the subclass escape that, so those are gaps.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_network(canonical(b)) and delegated(canonical(b)) for b in node.bases):
            continue
        body_names = {
            stmt.name
            for stmt in node.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        } | {
            target.id
            for stmt in node.body
            if isinstance(stmt, (ast.Assign, ast.AnnAssign))
            for target in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target])
            if isinstance(target, ast.Name)
        }
        if node.keywords or body_names & CLASS_HOOKS:
            findings.append(
                f"{relative}:{node.lineno}: subclass {node.name} of a delegated client "
                "overrides attribute lookup"
            )
    # Another file's client attribute (``self.http = requests.Session()``)
    # reached from here bypasses that file's bounded call sites. Local,
    # request-free uses such as ``client.session.close()`` are allowed.
    # ``adapters``/``mount`` lead to request-sending objects, so they are not exempt.
    request_free = {"headers", "cookies", "params", "auth", "proxies"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attr = node.attr
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            attr = node.args[1].value  # getattr(c, "http") is a read of .http
        else:
            continue
        if ast.unparse(node) in clients:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            outer = parents.get(parent)
            if parent.attr in request_free:
                continue
            if parent.attr == "close" and isinstance(outer, ast.Call) and outer.func is parent:
                continue
        owners = context.client_attributes.get(attr, frozenset())
        if owners - {relative}:
            findings.append(
                f"{relative}:{node.lineno}: client attribute {ast.unparse(node)} of "
                f"{', '.join(sorted(owners - {relative}))} is reached outside its owner"
            )
    # A network module or imported callable passed around or returned as a
    # value (``return requests``) can be called later without a timeout.
    # Type annotations are never evaluated as calls, so they are exempt.
    annotations = [
        n.annotation for n in ast.walk(tree) if isinstance(n, (ast.arg, ast.AnnAssign))
    ] + [
        n.returns for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    in_annotation = {
        id(sub)
        for ann in annotations
        if ann is not None and not any(isinstance(n, ast.NamedExpr) for n in ast.walk(ann))
        for sub in ast.walk(ann)
    }

    def availability_check(node: ast.expr, parent) -> bool:
        """``requests is None``, ``not requests`` or ``if requests:`` only."""
        if isinstance(parent, ast.Compare):
            return all(isinstance(op, (ast.Is, ast.IsNot)) for op in parent.ops) and all(
                isinstance(c, ast.Constant) and c.value is None
                for c in [parent.left, *parent.comparators]
                if c is not node
            )
        if isinstance(parent, ast.UnaryOp):
            return isinstance(parent.op, ast.Not)
        if isinstance(parent, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            return parent.test is node
        if isinstance(parent, ast.BoolOp):
            # Only as a pure condition; ``requests or x`` as a value passes it on.
            outer = parents.get(parent)
            return isinstance(outer, (ast.If, ast.While, ast.Assert, ast.UnaryOp)) or (
                isinstance(outer, ast.IfExp) and outer.test is parent
            )
        return False

    for node in ast.walk(tree):
        if id(node) in in_annotation:
            continue
        if not (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in network_imports
        ):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            continue
        if isinstance(parent, ast.Call) and parent.func is node:
            continue  # direct calls are checked above
        if availability_check(node, parent):
            continue
        if any(part in canonical(node) for part in ("Exception", "Error")):
            continue  # exception classes in except/isinstance are not requests
        findings.append(f"{relative}:{node.lineno}: network name {node.id} escapes as a value")
    if network_imports and not calls:
        findings.append(f"{relative}: network import/delegation has no proven request timeout")
    applicability = "network" if calls else ("unproven" if findings else "not_applicable")
    # Register every attribute name on a client's path (``self.a.b``,
    # ``self.pool['h']``) and class-body client names, so consumers cannot
    # reach any of them.
    class_body_names = {
        target.id
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef)
        for stmt in cls.body
        if isinstance(stmt, (ast.Assign, ast.AnnAssign))
        for target in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target])
        if isinstance(target, ast.Name)
    }
    own: set[str] = set()
    for target in clients:
        try:
            expr = ast.parse(target, mode="eval").body
        except SyntaxError:
            continue
        own.update(n.attr for n in ast.walk(expr) if isinstance(n, ast.Attribute))
        if isinstance(expr, ast.Name) and expr.id in class_body_names:
            own.add(expr.id)
    own_attributes = sorted(own)
    return {
        "calls": calls,
        "applicability": applicability,
        "findings": sorted(set(findings)),
        "client_attributes": own_attributes,
    }
