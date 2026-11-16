"""Guards for the thesis_store source-fragment layout (Issue #502).

thesis_store.py executes every file listed in ``_PART_FILES`` into its own
namespace. These tests keep that wiring honest: no fragment can be packaged
without being executed, the lint-only ``TYPE_CHECKING`` declarations cannot
drift from the runtime namespace, and imports kept only for the fragments
cannot be deleted from thesis_store.py without a test failing.
"""

import ast
import importlib
import types
from pathlib import Path

import thesis_store as store

SCRIPTS = Path(store.__file__).resolve().parent
PARTS_DIR = SCRIPTS / "thesis_store_parts"


def _fragment_paths() -> list[Path]:
    return sorted(p for p in PARTS_DIR.glob("*.py") if p.name != "__init__.py")


def _type_checking_blocks(tree: ast.Module) -> list[ast.If]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.If) and ast.unparse(node.test) == "TYPE_CHECKING"
    ]


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _loaded_names(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def test_part_files_match_fragment_directory():
    on_disk = [p.name for p in _fragment_paths()]
    assert on_disk, "no fragments found"
    assert len(store._PART_FILES) == len(set(store._PART_FILES))
    assert sorted(store._PART_FILES) == on_disk


def test_fragment_declarations_match_runtime_namespace():
    namespace = vars(store)
    for path in _fragment_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        blocks = _type_checking_blocks(tree)
        assert len(blocks) == 1, f"{path.name}: expected one TYPE_CHECKING block"
        functions = [
            namespace[node.name] for node in tree.body if isinstance(node, ast.FunctionDef)
        ]
        assert functions, f"{path.name}: defines no functions"
        for fn in functions:
            assert isinstance(fn, types.FunctionType)
            assert fn.__code__.co_filename == str(path), f"{fn.__name__} not from {path.name}"
            assert fn.__globals__ is namespace, f"{fn.__name__} globals are not thesis_store's"

        declared: dict[str, object] = {}
        for stmt in blocks[0].body:
            if isinstance(stmt, ast.Assign):
                (target,) = stmt.targets
                value = stmt.value
                assert isinstance(target, ast.Name)
                assert isinstance(value, ast.Attribute)
                assert ast.unparse(value.value) == "thesis_store"
                assert target.id == value.attr, f"{path.name}: {target.id} aliases {value.attr}"
                assert hasattr(store, target.id), f"{path.name}: thesis_store.{target.id} missing"
                declared[target.id] = getattr(store, target.id)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name == "thesis_store":
                        continue
                    declared[alias.asname or alias.name] = importlib.import_module(alias.name)
            elif isinstance(stmt, ast.ImportFrom):
                module = importlib.import_module(stmt.module)
                for alias in stmt.names:
                    declared[alias.asname or alias.name] = getattr(module, alias.name)
            else:
                raise AssertionError(f"{path.name}: unexpected statement in TYPE_CHECKING block")

        for name, expected in declared.items():
            assert namespace.get(name) is expected, f"{path.name}: {name} differs at runtime"
            for fn in functions:
                assert fn.__globals__.get(name) is expected


def test_entry_type_checking_imports_name_real_fragment_definitions():
    tree = ast.parse((SCRIPTS / "thesis_store.py").read_text(encoding="utf-8"))
    (block,) = _type_checking_blocks(tree)
    for stmt in block.body:
        assert isinstance(stmt, ast.ImportFrom)
        prefix, _, fragment = stmt.module.partition(".")
        assert prefix == "thesis_store_parts"
        fragment_tree = ast.parse((PARTS_DIR / f"{fragment}.py").read_text(encoding="utf-8"))
        defined = _top_level_names(fragment_tree)
        for alias in stmt.names:
            assert alias.asname is None
            assert alias.name in defined, f"{alias.name} is not defined in {fragment}.py"
            assert hasattr(store, alias.name)


def test_fragment_only_imports_are_used_by_fragments():
    source = (SCRIPTS / "thesis_store.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    entry_uses = _loaded_names(tree)
    fragment_uses: set[str] = set()
    for path in _fragment_paths():
        fragment_uses |= _loaded_names(ast.parse(path.read_text(encoding="utf-8")))

    checked = 0
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if "# noqa: F401" not in lines[node.lineno - 1]:
            continue
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            assert name in fragment_uses or name in entry_uses, (
                f"import {name} is marked noqa: F401 but nothing uses it"
            )
            checked += 1
        assert any((alias.asname or alias.name) in fragment_uses for alias in node.names), (
            f"line {node.lineno}: noqa: F401 import is not used by any fragment"
        )
    assert checked
