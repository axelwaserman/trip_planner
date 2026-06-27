"""Wave 0 RED canary: no ``langchain*`` imports survive in ``app/``.

Per CONTEXT.md D-20 anti-pattern lock, the Phase 5 rewrite must remove every
``langchain``/``langchain_core``/``langchain_*`` import from the production
tree. The test AST-walks ``backend/app/**/*.py`` and collects any node whose
module starts with ``langchain``.

Today (Wave 0) the chat service, providers, factory, and protocol all import
``langchain_core``/``langchain_openai``/``langchain_anthropic``/
``langchain_ollama``. The test fails RED with a list of every offender. It
turns GREEN in Wave 4 once the rewrites complete.
"""

import ast
from pathlib import Path

# Resolve backend/app/ deterministically: this file lives at
# tests/unit/test_no_langchain_imports.py; backend/app is two parents up
# then ``/app``.
_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"


def test_no_langchain_imports_in_app_tree() -> None:
    """No file under ``backend/app/`` imports any ``langchain*`` module."""
    offenders: list[tuple[str, str]] = []
    for py_file in _APP_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # skip files that can't parse — surfaced by other tools
        rel = py_file.relative_to(_APP_ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("langchain"):
                    offenders.append((str(rel), node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("langchain"):
                        offenders.append((str(rel), alias.name))

    assert not offenders, "Lingering langchain imports under backend/app/ — Phase 5 must remove all of:\n" + "\n".join(
        f"  {file}: {module}" for file, module in offenders
    )
