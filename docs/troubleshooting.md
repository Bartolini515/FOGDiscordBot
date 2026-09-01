# Troubleshooting

Use this guide for local development and read-only production diagnosis. It intentionally excludes deployment, code updates, service restarts, and writes to the production bot, configuration, or database.

## Local startup exits after creating configuration

This is expected on a clean checkout. The bot copies `configuration.example.json` to `configuration.json` and stops so it cannot accidentally start with placeholder IDs. Edit the generated local file, keep it untracked, then start again.

If startup reports `ConfigurationError`, follow the field path in the message and compare the shape with [Configuration](configuration.md). JSON requires double quotes and does not allow trailing commas.

## Token or environment errors

Confirm a local `.env` exists and contains `DISCORD_BOT_TOKEN`. Do not paste its contents into issues, chat, logs, fixtures, or commits. `DEBUG` must be exactly `True` to enable debug behavior; use `False` normally.

Never test startup using the production token. The automated suite does not require `.env` or Discord.

## Dependency or quality-check failures

Prepare the environment from the committed lockfile:

```text
pipenv verify
pipenv sync --dev
pipenv run check
```

The combined check executes all four stages even when an earlier stage fails:

1. installed-package consistency (`pip check`);
2. Ruff syntax/import/Pyflakes checks;
3. mypy for the initial typed scope;
4. pytest.

Run the corresponding `pipenv run lint`, `pipenv run typecheck`, or `pipenv run test` command to focus on a failing stage. The authoritative interpreter target is Python 3.12.

## GitHub Actions `quality` failures

The `CI` workflow runs the offline checks for every pull request targeting `main` and every push to `main`. Reproduce a failed job locally in this order:

```text
pipenv verify
pipenv sync --dev
pipenv run check
git diff --check
```

`pipenv verify` reports that `Pipfile.lock` does not match `Pipfile`; regenerate the lockfile locally and commit the resulting pair. A synchronization failure means a locked dependency could not be installed. Failures in `pipenv run check` identify one of the four local stages: `pip check`, Ruff, mypy, or pytest. The workflow's whitespace step checks only the pull request range or pushed commit range, while the final cleanliness step fails if any tracked file was modified by a check. Untracked ignored caches created by pytest, Ruff, or mypy are allowed.

CI never starts `main.py`, reads `.env`, `configuration.json`, or `db/bot.db`, and does not contact Discord. A failure involving those boundaries must be reproduced with a safe temporary configuration or database rather than by adding production data to the workflow.

## Migration failures

Migrations are an offline deployment phase. Run the explicit command against the intended database before starting the bot:

```text
python -m scripts.migrate --database <path>
python -m scripts.migrate --database <path> --check
```

`--check` makes no schema changes and exits nonzero when committed migrations are pending. `Database.connect()` never applies migrations; it refuses a database that is not current. Check:

- the process can write the database directory;
- the migration table and error mention in the log;
- no applied `001`/`002` file was edited;
- the same database is not being written by another bot process.

Reproduce schema changes only with a new database in a temporary directory. Do not point tests, experiments, or repair commands at `db/bot.db`. Never remove yoyo history or edit an applied migration file to force a retry; applied migration files are immutable, so add a new forward migration instead.

## Commands are missing

Commands are copied and synchronized to `guild_id`, not globally. Verify locally, without changing the production guild:

- `guild_id` identifies the intended test guild;
- the cog loaded without an exception in `logs/bot.log`;
- the bot application was invited with application-command scope;
- the member satisfies Discord default permissions and the command's runtime allowlist;
- the interaction is in a guild and, for mission creation, the configured channel when that restriction is enabled.

Restarting a service or resynchronizing against production is outside this guide and requires explicit operator approval.

## Persistent buttons or selects do not respond

Persistent views are restored during each relevant cog's `cog_load()`. Check that:

- the matching mission/squad, training/message, or ticket-create record still exists;
- the Discord message and channel still exist;
- the bot can view the channel, read message history, and edit/send messages;
- the component's stored custom ID matches the restored view path;
- only one bot process is serving the database.

The bot cannot restore a deleted Discord message from SQLite. Recreate the feature through its administrator command where supported. Persistent view behavior must be tested in a non-production guild; the unit suite does not call Discord.

## Mission roster appears stale

The database is the durable roster and the message is a projection. Inspect `logs/bot.log` for a failed fetch/edit after a slot change. Common causes are a deleted message, a removed channel, or lost `View Channel`, `Read Message History`, `Send Messages`, or `Manage Messages` permissions.

Do not manually edit the production SQLite database. Correct Discord permissions first, then use the existing mission commands or an approved repair procedure.

## Attendance or rank behavior is surprising

- Attendance is cumulative and recording the same mission twice increments it twice.
- Explicitly mentioned absentees are removed from the occupied-slot set.
- Rank progression depends on migration-seeded thresholds and Discord roles still existing.
- Mission dates and cutoffs use naive local server time.
- The mission is not deleted after attendance is recorded.

Use a temporary migrated database and unit tests to reproduce data behavior. Role adds/removes require a test guild and correct Discord hierarchy.

## Ticket creation fails

Verify the category name exists in `ticket_system.ticket_categories`, its `type` maps to a supported handler (or intentionally falls back to `custom`), and `category_id` identifies a visible Discord category. Manager IDs may represent members or roles and the bot needs permission to create channels and manage overwrites.

Ticket-create messages rely on their SQLite registration for restart restoration. Deleting such a Discord message normally removes the registration through `on_message_delete` while the bot is running.

## Local logs

The primary application log is:

```text
logs/bot.log
```

Review only the minimum relevant lines and anonymize member names, Discord IDs, ticket titles/content, warning reasons, and channel/message data before sharing. Logs may contain operational details even when they do not contain the token.

## Runtime readiness or duplicate instance

The application takes an exclusive instance lock before opening SQLite or contacting Discord. A second process using the same `FOGBOT_INSTANCE_LOCK` exits rather than waiting. Stop the stale local process before investigating its runtime directory; do not delete a lock while a process may still be active.

`ready.json` is created in `FOGBOT_RUNTIME_DIR` only after the bot has connected and completed startup reconciliation. It is removed on disconnect or graceful shutdown. A release SHA of `unknown` is expected for local development without a valid `RELEASE_SHA` file. Runtime paths and health-state fields are described in [Configuration](configuration.md#runtime-paths); do not put production paths or record contents in issues.

## Read-only service diagnosis

The known production unit is `fogbot.service`. These commands inspect state only:

```text
systemctl status fogbot.service
journalctl -u fogbot.service --since "1 hour ago" --no-pager
```

Do not run `start`, `stop`, `restart`, `enable`, `disable`, `daemon-reload`, deployment scripts, or `git pull` without separate explicit approval. The current documentation does not define a production deployment procedure.

## Known limitations

- The `CI` workflow covers offline quality checks; `pipenv run check` remains the local source of truth.
- No automated test connects to Discord or validates real integration permissions/persistent views.
- The initial mypy scope excludes `Cogs/`.
- Time handling is server-local and naive.
- Model methods expose positional tuples.
- Migration `001` contains historical real rank role IDs.
- `training_signed` has no uniqueness constraint for a user/training pair.
- Editing only a mission name follows a known defective path.
- Proposal forwarding assumes the expected proposal message content exists.
- A deployment/runbook and production rollback process are intentionally deferred.
