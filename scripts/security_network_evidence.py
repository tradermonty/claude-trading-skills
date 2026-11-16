"""Conservative, advisory AST evidence for network timeout prerequisites.

Only direct imported call aliases and constructor-bound clients are resolved.
Dynamic dispatch, rebinding and delegated SDK operations require human review.
A bounded argument is evidence for that call, not a whole-program safety proof.
"""

from __future__ import annotations

import ast
import math
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


def script_evidence(path: Path, relative: str) -> dict:
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
    network_imports = {key for key, names in bindings.items() if any(_network(n) for n in names)}
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

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = canonical(node.func)
        raw = ast.unparse(node.func)
        receiver = ast.unparse(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        method = node.func.attr if isinstance(node.func, ast.Attribute) else name.rsplit(".", 1)[-1]
        direct = _network(name) and (method in HTTP_METHODS or method == "urlopen")
        chained_factory = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Call)
            and canonical(node.func.value.func) in FACTORIES
        )
        bound_client = (receiver in clients or chained_factory) and method in HTTP_METHODS
        if direct or bound_client:
            timeout = next((kw.value for kw in node.keywords if kw.arg == "timeout"), None)
            bounded = _bounded(timeout)
            calls.append({"path": relative, "line": node.lineno, "call": raw, "bounded": bounded})
            if not bounded:
                findings.append(
                    f"{relative}:{node.lineno} {raw}: timeout is missing or unproven (finite positive literal required)"
                )
        elif name in FACTORIES or name == "urllib.request.Request":
            continue
        elif _network(name):
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
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
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
    if network_imports and not calls:
        findings.append(f"{relative}: network import/delegation has no proven request timeout")
    applicability = "network" if calls else ("unproven" if findings else "not_applicable")
    return {"calls": calls, "applicability": applicability, "findings": sorted(set(findings))}
