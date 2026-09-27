"""Static guards for the i18n wiring (docs/i18n-spec.md §9).

A function that both calls ``_()`` and assigns ``_`` (``for _, row in …``,
``a, _ = …``) raises UnboundLocalError at the ``_()`` call — Python treats
``_`` as local for the whole function. Comprehensions have their own scope,
so ``[x for _ in …]`` is fine.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_FILES = sorted(
    [*ROOT.glob("*.py"), *(ROOT / "uvalu").glob("*.py"), *(ROOT / "uvalu" / "pages_").glob("*.py")]
)


def _assigns_underscore(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            continue
        targets = []
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            if isinstance(node, ast.comprehension):
                continue
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            targets = [node.optional_vars]
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and n.id == "_" and isinstance(n.ctx, ast.Store):
                    return True
    return False


def _calls_underscore(fn: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"
               for n in ast.walk(fn))


def _own_body_nodes(fn):
    """Nodes of fn excluding nested function/class bodies (their own scope)."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def test_no_function_shadows_gettext_underscore():
    bad = []
    for path in UI_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.Module(body=list(_own_body_nodes(fn)), type_ignores=[])
            if _calls_underscore(body) and _assigns_underscore(body):
                bad.append(f"{path.relative_to(ROOT)}:{fn.lineno} {fn.name}")
    assert not bad, "functions that call _() but also assign _ (rename the throwaway):\n" + "\n".join(bad)


def test_module_level_underscore_not_rebound():
    """A module that imports _ must not rebind it at module level either."""
    bad = []
    for path in UI_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_it = any(isinstance(n, ast.ImportFrom) and any(a.name == "_" for a in n.names)
                         for n in tree.body)
        if imports_it and _assigns_underscore(ast.Module(body=[n for n in tree.body
                                                                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
                                                          type_ignores=[])):
            bad.append(str(path.relative_to(ROOT)))
    assert not bad, bad
