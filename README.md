# FogDiscordBot

FogDiscordBot is the single-guild Discord bot used by the FOG Arma 3 community. It automates mission scheduling and slot signups, attendance and rank progression, trainings, tickets, warnings, recruitment, moderation, and selected server utilities.

The application is written for Python 3.12 with `discord.py`. It stores domain state in SQLite, applies schema migrations with yoyo, and uses persistent Discord views so mission, training, and ticket controls can survive a restart.

## Requirements

- Python 3.12
- Pipenv
- a Discord application/bot for a non-production test guild
- Discord IDs for the guild resources required by the features you enable

Do not use the production token, configuration, or database for local development and tests.

## Set up a clean checkout

Install the locked production and development dependencies:

```text
pipenv sync --dev
```

Copy `configuration.example.json` to the ignored `configuration.json` and fill in test-guild values. On the first run, the bot performs this copy itself without overwriting an existing file, then exits so you can edit it.

Create an ignored `.env`:

```dotenv
DISCORD_BOT_TOKEN=replace-with-a-test-bot-token
DEBUG=False
```

The example configuration intentionally contains zero IDs and empty collections. It defines the required structure but is not ready to connect to a guild. See [Configuration](docs/configuration.md) for every known key and safe configuration rules.

## Run locally

After configuring a test guild:

```text
pipenv run python main.py
```

Startup applies pending yoyo migrations to `db/bot.db`, loads every module in `Cogs/`, and synchronizes slash commands only to the configured `guild_id`. Do not run this command as part of automated verification because it connects to Discord and remains active.

## Quality checks

Run the complete local Definition of Done:

```text
pipenv run check
```

It runs installed-package consistency, Ruff, mypy, and pytest, continuing through every stage and returning a failure code if any stage fails. Focused commands are also available:

```text
pipenv run lint
pipenv run typecheck
pipenv run test
```

GitHub Actions runs the same quality contract for pull requests targeting `main` and pushes to `main`. The [CI workflow](.github/workflows/ci.yml) has one stable `quality` job that verifies the lockfile, installs development dependencies, runs `pipenv run check`, checks the event diff for whitespace errors, and rejects tracked-file changes made by checks. It does not load `.env`, use `configuration.json` or `db/bot.db`, start `main.py`, or connect to Discord.

Tests use temporary migrated SQLite databases. They do not read `db/bot.db`, require a token, or connect to Discord.

## Update the deployed service

On the Linux host that runs the approved `fogbot.service`, use the deployment helper from a clean checkout with an upstream tracking branch:

```text
chmod +x scripts/update.sh
./scripts/update.sh
```

The helper stops the service, shows the current `technical_info.version`, asks for a new `core.major.minor` version such as `1.23.45`, writes that version and the current `YYYY-MM-DD` date to `technical_info`, fast-forwards the checkout with `git pull --ff-only`, and starts the service again. It requires `git`, `python3`, `sudo`, and `systemctl`, and waits up to 120 seconds for systemd to confirm the stop. A mode-only change caused by `chmod +x scripts/update.sh` is accepted when the file content still matches `HEAD`; all other local changes stop the process. Once the stop is confirmed, a failure or interruption leaves the service stopped so the operator can inspect the host before restarting it.

## Architecture at a glance

`main.py` validates local configuration, owns the bot/database lifecycle, discovers cogs, synchronizes commands to the one FOG guild, reconciles guild members, and saves mutable configuration. Cogs handle Discord interactions and call thin asynchronous models in `db/models/`. Migrations in `db/migrations/` define the SQLite schema. Mission, training, and ticket cogs reconstruct persistent component views from stored records during cog loading.

Mission signup messages are projections of mission, squad, and slot records. Selecting a new slot clears the member's previous slot in the same mission, writes the new assignment, and refreshes every affected message. Attendance is calculated from occupied slots and emits an internal event used for rank progression.

See [Architecture](docs/architecture.md) and [Mission domain](docs/domain/missions.md) for the complete flows and Mermaid diagrams.

## Repository map

- `Cogs/` — Discord slash commands, listeners, background tasks, and views.
- `db/` — SQLite connection, query models, and immutable yoyo migrations.
- `ticket/` — ticket category contract, handlers, and UI components.
- `scripts/` — developer checks and the controlled service update helper.
- `tests/` — offline tests using temporary resources.
- `docs/` — technical and domain documentation.
- `AGENTS.md` — repository rules and source-of-truth map for AI coding agents.

## Documentation index

- [Architecture and lifecycle](docs/architecture.md)
- [Mission, signup, attendance, and rank flow](docs/domain/missions.md)
- [SQLite data model](docs/data-model.md)
- [Configuration reference](docs/configuration.md)
- [Cog and command catalog](docs/modules.md)
- [Troubleshooting and read-only service diagnosis](docs/troubleshooting.md)
- [Future architecture decision records](docs/decisions/README.md)

## Known boundaries

The CI pipeline runs the offline quality checks, but there is no automated Discord integration suite. The first mandatory mypy scope covers configuration, database, ticket, and script code rather than cogs. Time values are naive and server-local, models return positional tuples, and several historical schema/behavior limitations are recorded in the technical documents.

The service update helper documents the controlled deployment flow, but running it against a real host remains an operator action. The CI pipeline and automated tests never access the production configuration, database, systemd, or Discord.
