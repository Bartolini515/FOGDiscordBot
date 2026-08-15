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

Tests use temporary migrated SQLite databases. They do not read `db/bot.db`, require a token, or connect to Discord.

## Architecture at a glance

`main.py` validates local configuration, owns the bot/database lifecycle, discovers cogs, synchronizes commands to the one FOG guild, reconciles guild members, and saves mutable configuration. Cogs handle Discord interactions and call thin asynchronous models in `db/models.py`. Migrations in `db/migrations/` define the SQLite schema. Mission, training, and ticket cogs reconstruct persistent component views from stored records during cog loading.

Mission signup messages are projections of mission, squad, and slot records. Selecting a new slot clears the member's previous slot in the same mission, writes the new assignment, and refreshes every affected message. Attendance is calculated from occupied slots and emits an internal event used for rank progression.

See [Architecture](docs/architecture.md) and [Mission domain](docs/domain/missions.md) for the complete flows and Mermaid diagrams.

## Repository map

- `Cogs/` — Discord slash commands, listeners, background tasks, and views.
- `db/` — SQLite connection, query models, and immutable yoyo migrations.
- `ticket/` — ticket category contract, handlers, and UI components.
- `scripts/` — portable developer checks.
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

There is currently no CI pipeline and no automated Discord integration suite. The first mandatory mypy scope covers configuration, database, ticket, and script code rather than cogs. Time values are naive and server-local, models return positional tuples, and several historical schema/behavior limitations are recorded in the technical documents.

Production deployment and service restart procedures are intentionally outside this repository guide. Any write to Discord, real configuration/database, systemd, or production requires separate operator approval.
