# Task 3 report: deployment authorization protocol and durable state

## Outcome

Added a standard-library-only deployment control package at
`deployment/server/fogbot_deploy/`. It strictly parses forced SSH commands,
derives stable operation IDs, verifies an exact GitHub Actions run with an
injected public-API transport, persists redacted atomic operation state, and
starts a locally injected transaction at most once per operation.

The package has no production repository identifiers, credentials, release
paths, remote logs, or server access configuration. Production trust
configuration remains an immutable value supplied outside release directories.

## Files added

- `deployment/server/fogbot_deploy/config.py`
- `deployment/server/fogbot_deploy/protocol.py`
- `deployment/server/fogbot_deploy/verifier.py`
- `deployment/server/fogbot_deploy/state.py`
- `deployment/server/fogbot_deploy/cli.py`
- Package initializers below `deployment/`
- `tests/test_fogbot_deploy_protocol.py`

## Test evidence

TDD RED runs were observed before each implementation slice: the initial
protocol tests failed because the package was absent, verifier tests failed
because the verifier was absent, and durable-state/CLI tests failed because
their modules were absent. Focused GREEN run:

```text
PIPENV_DONT_LOAD_ENV=1 pipenv run pytest tests/test_fogbot_deploy_protocol.py -q --basetemp .pytest-task3
11 passed
```

Additional static validation:

```text
PIPENV_DONT_LOAD_ENV=1 pipenv run ruff check deployment/server/fogbot_deploy tests/test_fogbot_deploy_protocol.py
All checks passed

PIPENV_DONT_LOAD_ENV=1 pipenv run mypy deployment/server/fogbot_deploy
Success: no issues found in 6 source files
```

The unchanged `PIPENV_DONT_LOAD_ENV=1 pipenv run check` ran all 130 tests but
returned nonzero during pytest's Windows-profile cleanup of
`pytest-current` (WinError 5), after test execution. Re-running the identical
check with only `PYTEST_ADDOPTS=--basetemp=.pytest-full-task3` isolated pytest
temporary files inside the worktree and completed successfully:

```text
130 passed in 28.76s
All checks passed.
```

`git diff --check` completed with exit code 0 before staging; it is repeated
after staging below.

## Scope and limitations

- No GitHub, server, Discord, production configuration, secrets, database, or
  logs were accessed.
- The injected verifier is independently callable, so the Task 4 transaction
  can repeat it immediately before stopping the service.
- Task 4 remains responsible for release checkout, ancestry/current-release
  monotonicity, backups, migration, service control, and health transitions.
