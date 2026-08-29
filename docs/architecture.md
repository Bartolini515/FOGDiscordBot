# Architecture

FogDiscordBot is a single-process `discord.py` application for one FOG Discord guild. It combines Discord interaction handlers, an asynchronous SQLite data layer, persistent component views, and a JSON configuration file. This document describes the current implementation; it is not a deployment runbook.

## Repository map

- `main.py` owns process startup, bot lifecycle, cog discovery, guild command synchronization, configuration autosave, and shutdown.
- `configuration.py` creates and validates local configuration.
- `utils/` contains stateless helpers shared across cogs and services.
- `services/` contains typed, explicit-dependency workflow functions grouped by domain.
- `Cogs/` contains Discord slash commands, listeners, views, and background loops.
- `db/database.py` owns the SQLite connection and yoyo migration step.
- `db/models/` contains asynchronous, SQL-oriented data access classes, with one model class per module.
- `db/migrations/` is the immutable history of the database schema.
- `ticket/` contains ticket categories, handlers, and Discord UI components.
- `scripts/check.py` is the portable local quality entry point.
- `tests/` exercises configuration and domain behavior without connecting to Discord.

## Process lifecycle

```mermaid
flowchart TD
    A["Run main.py"] --> B["Resolve runtime paths"]
    B --> C{"configuration.json exists?"}
    C -- No --> D["Copy configuration.example.json"]
    D --> E["Exit and ask the operator to configure it"]
    C -- Yes --> F["Validate configuration and load .env"]
    F --> G["Acquire instance lock"]
    G --> H["Create MyBot and Database"]
    H --> I["setup_hook"]
    I --> J["Apply yoyo migrations"]
    J --> K["Open aiosqlite connection and enable foreign keys"]
    K --> L["Load every Cogs/*.py extension"]
    L --> M["Start autosave and readiness heartbeat tasks"]
    M --> N["Sync application commands to the configured guild"]
    N --> O["on_ready: reconcile users, then publish readiness"]
    O --> P["Serve Discord events and interactions"]
    P --> Q["disconnect: invalidate readiness"]
    P --> R["close: invalidate, cancel tasks, save, close, release lock"]
```

`main.py` uses all Discord intents and copies the application command tree into `guild_id`. This deliberately targets the single FOG guild instead of globally publishing commands. Cog modules are discovered from the filesystem and loaded as extensions, so a new cog becomes part of startup automatically when it provides the normal `setup(bot)` entry point. Importing `main.py` has no startup side effects; the callable `main()` owns configuration bootstrap, environment loading, instance locking, and Discord startup.

Before creating the database connection or contacting Discord, `main()` acquires the configured exclusive runtime lock. The runtime path contract is documented in [Configuration](configuration.md#runtime-paths). `ready.json` is atomically written only after `on_ready` completes member reconciliation, refreshed while Discord remains ready, and removed on disconnect and shutdown. Autosave and heartbeat tasks are cancelled during shutdown; the lock is released only after Discord shutdown completes.

Cog classes remain the Discord interaction boundary: decorators, persistent views, locks, and component registration stay in `Cogs/`. Stateless cross-cutting operations live in `utils/`, while multi-step workflows live in `services/` and receive their dependencies explicitly. This separation changes code organization only; command names, responses, permissions, model calls, and side-effect ordering remain the same.

The durable rationale and constraints for this split are recorded in [ADR-0001](decisions/0001-service-boundaries.md).

Member and moderation services centralize guild targeting, invite snapshots, configured permission checks, blacklist date calculations, role-whitelist decisions, rank thresholds, and known command-error messages. They do not own Discord state or database connections; cogs still control the surrounding side effects.

Administration services own pure SQL result formatting and mutation rules for configured permissions, channels, ticket categories, and message triggers. `Utilities` keeps command decorators and sends the existing responses around those operations.

Help, leveling, trigger matching, and honeypot state transformations are exposed as pure service functions. Level and trigger caches, the leveling background loop, cooldown dictionaries, and honeypot Discord message updates remain owned by their cogs.

Attendance and training services render reports and signup content, normalize command dates, and derive present-user lists. The cogs retain database writes, role changes, attendance dispatch, interaction responses, locks, and persistent view registration.

Ticket-local services own ticket-admin checks, semicolon category parsing, persistent create-view IDs, and transcript HTML rendering. `ticket/core.py` continues to own category contracts, database adapters, type handlers, channel permissions, and ticket lifecycle persistence; `Cogs/Tickets.py` remains the interaction and view-registration boundary.

Mission services own roster rendering, command/stored-date parsing, the 12-hour self-service cutoff, signup-slot normalization, slot projections, and persistent component IDs. `Cogs/Missions.py` retains mission locks, scheduling tasks, database/model calls, Discord message edits, responses, and component registration, so the service boundary does not alter mission side-effect ordering.

The `on_ready` reconciliation marks every database user as off-guild, then inserts or updates the current non-bot guild members as present. It preserves historical users for attendance, warning, and mission references.

An hourly background loop writes the in-memory configuration dictionary to `configuration.json`. The same save happens during graceful shutdown. Commands that edit configuration therefore change the shared dictionary first and rely on this lifecycle for persistence.

## SQLite and migrations

`Database.connect()` applies every pending yoyo migration before opening the long-lived `aiosqlite` connection. The connection then executes `PRAGMA foreign_keys = ON`; this must remain enabled for the documented cascades and `SET NULL` behavior.

The committed migrations are the schema source of truth. Applied migrations must never be edited. Add schema changes as the next numbered migration and validate them against a new temporary database. Tests do not use `db/bot.db`.

Model classes in `db/models/` are thin asynchronous query collections. They commit writes themselves and normally return positional SQLite rows rather than named domain objects. Consult [Data model](data-model.md) before changing query columns or destructuring call sites.

## Persistent views

Discord component callbacks must survive process restarts:

- `MissionsCog.cog_load()` restores signup selects and sign-out buttons from mission, squad, and slot records. It also recreates future one-hour reminders.
- `TrainingsCog.cog_load()` restores training signup views for stored message IDs.
- `TicketsCog.cog_load()` restores button- and select-based ticket creation views from serialized categories.

The database is the durable source for these registrations. `bot.add_view(...)` rebinds callbacks to existing Discord messages; it does not recreate missing messages. If a message, channel, or permission changed outside the bot, restoration can log an error or leave the component unusable until an administrator recreates it.

Mission and training interactions use in-memory `asyncio.Lock` instances to serialize related edits in this process. These locks do not coordinate multiple bot processes, so only one application instance should write the same database and Discord messages.

## Main data flows

### Mission signup

```mermaid
sequenceDiagram
    actor Member
    participant View as "SlotSelect view"
    participant Cog as "MissionsCog"
    participant Model as "Slots model"
    participant DB as "SQLite"
    participant Discord

    Member->>View: Select a slot
    View->>Cog: Validate mission and member
    Cog->>Model: assign_user_to_slot
    Model->>DB: Clear the member's prior slot in this mission
    Model->>DB: Assign the selected slot
    DB-->>Cog: Commit
    Cog->>Discord: Rebuild affected signup messages
    Discord-->>Member: Updated roster
```

The mission, squad, and slot records hold the durable state; the Discord messages are projections rebuilt from those records. The complete workflow is in [Mission domain](domain/missions.md).

### Attendance and rank promotion

`/misja_obecnosc` derives attendees from occupied mission slots, removes explicitly mentioned absentees, and increments attendance records. It then dispatches the internal `attendance` event. `RanksCog` handles that event, compares the new total with the seeded rank thresholds, updates the user's database rank, and adjusts Discord roles when promotion is due.

### Tickets

Ticket create messages store their selected categories as JSON in `ticket_create_messages`. A persistent view reconstructs `TicketCategory` values, normalizes the category name, and selects a handler from `ticket.core.TYPE_HANDLERS`. Handlers create category-specific channels, permission overwrites, initial messages, and buttons. Ticket lifecycle state is stored in `tickets`.

## External boundaries

- Discord is the interaction, identity, permissions, role, channel, and message boundary.
- `configuration.json` is local operational state and may contain real Discord IDs; it is intentionally ignored by Git.
- `.env` provides `DISCORD_BOT_TOKEN` and `DEBUG`; it is not a configuration fallback.
- SQLite is local persistent domain state.
- `logs/bot.log` and the service journal are operational evidence, not domain state.

Automated tests stop at these boundaries. They do not use a bot token, connect to Discord, validate guild permissions, or exercise restored components against real messages.
