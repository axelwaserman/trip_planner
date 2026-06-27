"""Wave 0 RED canary: pyproject.toml dependency manifest assertions (D-20).

Per CONTEXT.md D-20 + RESEARCH §"Common Pitfalls" Pitfall 9, Phase 5 must:

- Remove every ``langchain*`` package from the manifest.
- Remove ``langgraph`` (still in pyproject.toml despite PR #1 claiming
  otherwise — caught in Pitfall 9).
- Add ``pydantic-ai>=0.8.1``.
- Bump ``pydantic`` floor to ``>=2.12`` (Pitfall 8 — pydantic-ai-slim 0.8.1
  requires it).

Today (Wave 0) ``pyproject.toml`` still lists langchain*/langgraph and pins
``pydantic>=2.9.0``. ALL THREE TESTS BELOW FAIL RED — that's the expected
state. They turn GREEN in Wave 4 once the dep swap completes.

The file is read via stdlib ``tomllib`` (Python 3.11+; project requires 3.13).
The package-name extractor splits on the PEP 508 version-specifier characters
(``<>=!~``) so ``pydantic-ai>=0.8.1`` and ``pydantic-ai==0.8.1`` both yield
``pydantic-ai``.
"""

import re
import tomllib
from pathlib import Path

# Resolve pyproject.toml deterministically: this file lives at
# tests/unit/test_dependencies.py; pyproject.toml is two parents up.
_PYPROJECT = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def _bare_name(spec: str) -> str:
    """Return the bare package name from a PEP 508 dependency string."""
    return re.split(r"[<>=~!]", spec, maxsplit=1)[0].strip()


def _dependencies() -> list[str]:
    manifest = tomllib.loads(_PYPROJECT.read_text())
    return list(manifest["project"]["dependencies"])


def test_no_langchain_dependencies() -> None:
    """No ``langchain*`` and no ``langgraph`` survive in [project].dependencies."""
    deps = _dependencies()
    offenders: list[str] = []
    for dep in deps:
        name = _bare_name(dep)
        if name.startswith("langchain"):
            offenders.append(name)
        if name == "langgraph":
            offenders.append(name)
    assert not offenders, f"Phase 5 must drop these packages: {offenders}"


def test_pydantic_ai_present() -> None:
    """pydantic-ai is in the manifest (any version specifier)."""
    deps = _dependencies()
    names = [_bare_name(d) for d in deps]
    assert "pydantic-ai" in names, "Phase 5 must add pydantic-ai to dependencies"


def test_pydantic_floor_at_least_2_12() -> None:
    """The ``pydantic`` entry pins floor ``>=2.12`` (Pitfall 8).

    pydantic-ai-slim 0.8.1 requires pydantic>=2.12; the Phase 4.7 floor of
    >=2.9.0 is too low. The test pattern-matches ``>=2.12`` (or higher) in
    the version specifier.
    """
    deps = _dependencies()
    pydantic_specs = [d for d in deps if _bare_name(d) == "pydantic"]
    assert pydantic_specs, "expected exactly one 'pydantic' entry in dependencies"
    spec = pydantic_specs[0]
    # Match either >=2.12, >=2.13, ..., or >=3.x. Anything below 2.12 fails.
    match = re.search(r">=\s*(\d+)\.(\d+)", spec)
    assert match, f"pydantic spec missing >= floor: {spec!r}"
    major, minor = int(match.group(1)), int(match.group(2))
    assert (major, minor) >= (2, 12), f"pydantic floor must be >=2.12 (Pitfall 8); got {spec!r}"
