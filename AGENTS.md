# FogDiscordBot agent guide

## Purpose and scope

This repository contains the `discord.py` bot for one FOG Arma 3 community guild. Its highest-risk domain is the mission lifecycle: scheduling, squads, slots, sign-out rules, attendance, and rank progression. Tickets, trainings, recruitment, moderation, leveling, triggers, and utilities are also in scope.

Keep code, identifiers, comments, and repository documentation in English unless an existing Discord slash command or user-facing Polish message is being preserved. Do not rename commands or rewrite user-facing text incidentally.

## Repository map and sources of truth

- `main.py` is the source of truth for startup, shutdown, cog loading, guild synchronization, autosave, and shared runtime state.
- `configuration.py` and `configuration.example.json` define the safe configuration bootstrap and validated top-level structure.
- `Cogs/` owns Discord commands, listeners, scheduled tasks, and persistent component registration.
- `db/migrations/` is the immutable SQLite schema history.
- `db/models/` defines current SQL query and positional tuple contracts.
- `ticket/` defines ticket categories, handlers, and views.
- `docs/architecture.md` and `docs/domain/missions.md` describe runtime/domain flows.
- `docs/data-model.md`, `docs/configuration.md`, and `docs/modules.md` catalog data, configuration, and interfaces.
- Tests are executable evidence; when documentation and behavior disagree, verify the code and tests, then update all affected sources together.

Follow the closest in-scope `AGENTS.md` if a subdirectory adds one in the future.

## Working rules

- Inspect relevant code, tests, documentation, repository status, and instructions before editing.
- Preserve unrelated and user-authored changes. Prefer the smallest coherent implementation that matches existing patterns.
- For behavior changes, use RED → GREEN → REFACTOR: first observe a focused test fail for the intended reason, implement the minimum change, then improve structure with tests green.
- Do not contact the real Discord API in automated tests. Use temporary directories, temporary migrated SQLite databases, and local fakes at external boundaries.
- Do not read, edit, copy, log, or test against `.env`, `configuration.json`, or `db/bot.db`. Use invented values, `configuration.example.json`, and temporary files.
- Treat Discord user/role/channel/message/guild IDs, names, ticket content, warnings, and logs as sensitive operational data. Anonymize them in fixtures, examples, screenshots, output, issues, and documentation.

## Database changes

Never edit an applied migration, including `001_init.sql` or `002_warns.sql`. Add the next numbered yoyo migration for every schema or seed change. Apply and test it from an empty database in a temporary directory, reconnect, and verify foreign keys and intended cascades. Never use the real `db/bot.db` for verification.

Remember that model methods expose positional SQLite tuples. When changing a `SELECT` list or order, search every destructuring call site and update tests plus `docs/data-model.md`.

## Documentation duties

Update documentation in the same change when modifying:

- slash commands, listeners, permissions, or module responsibilities: `docs/modules.md`;
- configuration keys or value meaning: `configuration.example.json` and `docs/configuration.md`;
- schema, seeds, relations, cascades, or tuple contracts: `docs/data-model.md`;
- startup, shutdown, cog loading, sync, autosave, migrations, or persistent views: `docs/architecture.md`;
- mission, signup, reminder, sign-out, attendance, or rank behavior: `docs/domain/missions.md`;
- local setup or diagnostic behavior: `README.md` and/or `docs/troubleshooting.md`.

Link to detailed documents instead of copying their content into this file. Record durable new architecture choices as future ADRs using `docs/decisions/README.md`; do not invent historical rationale.

## Definition of Done

Run:

```text
pipenv run check
```

All stages must pass: package consistency, Ruff, mypy, and pytest. Also run `git diff --check`, verify relative Markdown links and module/command coverage through the test suite, and inspect the diff for secrets or identifying data. Do not claim a check passed unless its output was observed.

Manual verification is required for real Discord interactions, permissions, role hierarchy, command synchronization, reminders, and persistent views. Perform it only in an approved non-production guild.

## Approval gates

Obtain separate explicit approval before:

- adding or changing a production dependency;
- reading or changing a real `.env`, `configuration.json`, or `db/bot.db`;
- sending messages, changing roles/channels/permissions, or otherwise writing to Discord;
- running systemd mutations, deployment, database repair, or any production operation;
- creating/pushing branches, commits, pull requests, releases, or deployments unless the current user request already authorizes that exact action.

Read-only local inspection and the repository's offline checks are allowed. `systemctl status fogbot.service` and read-only journal inspection are diagnostic examples, but any service mutation needs approval.
