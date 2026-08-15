import importlib
import sys

import pytest


def _load_check_module():
    try:
        return importlib.import_module("scripts.check")
    except ModuleNotFoundError:
        pytest.fail("scripts.check has not been implemented")


def test_run_checks_continues_after_failure_and_returns_nonzero(capsys):
    check = _load_check_module()
    commands = [
        ("first", [sys.executable, "-c", "print('first-ran')"]),
        ("failing", [sys.executable, "-c", "print('failing-ran'); raise SystemExit(3)"]),
        ("last", [sys.executable, "-c", "print('last-ran')"]),
    ]

    exit_code = check.run_checks(commands)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "first: PASS" in output
    assert "failing: FAIL (exit code 3)" in output
    assert "last: PASS" in output
    assert "Failed checks: failing" in output
