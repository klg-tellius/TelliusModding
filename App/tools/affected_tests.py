"""Run only the tests that can see a change.

Reads the changed files from git (the working tree and index against ``--base``, ``HEAD`` by
default, plus untracked files), follows ``fe_modding``'s own import graph backwards, and picks
every test module that imports a changed module directly or through other modules. A changed
test module, or a test helper next to the tests, is picked as well.

    python -m tools.affected_tests                 # list and run them with unittest
    python -m tools.affected_tests --base main     # everything changed since main
    python -m tools.affected_tests --list          # only print the test modules
    python -m tools.affected_tests --direct        # only tests importing a changed module themselves
    python -m tools.affected_tests --pytest -n 8   # run them with pytest (extra args passed on)

Run from ``App/``. A change outside ``App/fe_modding`` and ``App/tests`` (docs, wiki, release
files) picks no tests. A change to a module nothing imports by name (loaded by string, such as a
plugin) is missed; the full suite before a PR catches that.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PACKAGE = "fe_modding"
TESTS = APP / "tests"


def module_name(path: Path) -> str | None:
    """``fe_modding.formats.map_file`` for ``App/fe_modding/formats/map_file.py``."""
    try:
        rel = path.resolve().relative_to(APP)
    except ValueError:
        return None
    if rel.suffix != ".py" or rel.parts[0] not in (PACKAGE, "tests"):
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path, name: str, known: set[str]) -> set[str]:
    """The ``fe_modding`` modules (and test helpers) that ``path`` imports."""
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except SyntaxError:
        return set()
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found: set[str] = set()

    def add(candidate: str) -> None:
        # the module itself, else its package (an attribute import such as ``from x import y``)
        while candidate:
            if candidate in known:
                found.add(candidate)
                return
            candidate = candidate.rpartition(".")[0]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[:len(base) - node.level + 1]
                origin = ".".join(base + ([node.module] if node.module else []))
            else:
                origin = node.module or ""
            if not origin.startswith("tests.") and origin in {p.stem for p in TESTS.glob("*.py")}:
                origin = f"tests.{origin}"  # a test importing a helper as a top-level module
            for alias in node.names:
                add(f"{origin}.{alias.name}")
    found.discard(name)
    return found


def import_graph() -> dict[str, set[str]]:
    """Module -> the modules it imports, for every module of the package and the tests."""
    files = {module_name(p): p for p in [*(APP / PACKAGE).rglob("*.py"), *TESTS.glob("*.py")]}
    files.pop(None, None)
    known = set(files)
    return {name: _imports(path, name, known) for name, path in files.items()}


def changed_files(base: str) -> list[Path]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(["git", *args], cwd=APP, capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line]

    root = Path(git("rev-parse", "--show-toplevel")[0])
    names = set(git("diff", "--name-only", base)) | set(git("ls-files", "--others", "--exclude-standard"))
    if base != "HEAD":
        names |= set(git("diff", "--name-only", "HEAD"))
    return [root / n for n in sorted(names)]


def affected_tests(changed: list[Path], graph: dict[str, set[str]], direct: bool = False) -> list[str]:
    """The test modules that import a changed module, through any chain of imports (or, with
    ``direct``, only the ones importing it themselves)."""
    users: dict[str, set[str]] = {}
    for module, deps in graph.items():
        for dep in deps:
            users.setdefault(dep, set()).add(module)
    todo = [m for m in (module_name(p) for p in changed if p.exists() or p.suffix == ".py") if m]
    seen = set(todo)
    if direct:
        seen |= {user for module in todo for user in users.get(module, ())}
        todo = []
    while todo:
        for user in users.get(todo.pop(), ()):
            if user not in seen:
                seen.add(user)
                todo.append(user)
    return sorted(m for m in seen if m.startswith("tests.test_"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="HEAD", help="git revision to compare with (default HEAD)")
    parser.add_argument("--list", action="store_true", help="print the test modules without running them")
    parser.add_argument("--direct", action="store_true",
                        help="only tests that import a changed module themselves (quicker, can miss some)")
    parser.add_argument("--pytest", action="store_true", help="run with pytest; other arguments go to it")
    args, extra = parser.parse_known_args(argv)
    tests = affected_tests(changed_files(args.base), import_graph(), direct=args.direct)
    if not tests:
        print("No tests can see these changes.")
        return 0
    print(f"{len(tests)} test modules:", " ".join(t.removeprefix("tests.") for t in tests), flush=True)
    if args.list:
        return 0
    if args.pytest:
        command = [sys.executable, "-m", "pytest", *(f"tests/{t.removeprefix('tests.')}.py" for t in tests), *extra]
    else:
        command = [sys.executable, "-m", "unittest", *tests, *extra]
    return subprocess.run(command, cwd=APP).returncode


if __name__ == "__main__":
    sys.exit(main())
