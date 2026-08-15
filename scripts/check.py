"""Run all local quality checks with one cross-platform command."""

from __future__ import annotations

from collections.abc import Sequence
import subprocess
import sys

CheckCommand = tuple[str, Sequence[str]]

DEFAULT_CHECKS: tuple[CheckCommand, ...] = (
    ("dependencies", (sys.executable, "-m", "pip", "check")),
    ("lint", (sys.executable, "-m", "ruff", "check", ".")),
    ("types", (sys.executable, "-m", "mypy")),
    ("tests", (sys.executable, "-m", "pytest")),
)


def run_checks(checks: Sequence[CheckCommand]) -> int:
    """Run every check and return a failing exit code if any check fails."""
    failures: list[str] = []

    for name, command in checks:
        print(f"\n== {name} ==", flush=True)
        result = subprocess.run(list(command), check=False)
        if result.returncode == 0:
            print(f"{name}: PASS", flush=True)
        else:
            failures.append(name)
            print(f"{name}: FAIL (exit code {result.returncode})", flush=True)

    if failures:
        print(f"\nFailed checks: {', '.join(failures)}", flush=True)
        return 1

    print("\nAll checks passed.", flush=True)
    return 0


def main() -> int:
    """Run the project's default local verification suite."""
    return run_checks(DEFAULT_CHECKS)


if __name__ == "__main__":
    raise SystemExit(main())
