# ADR-0001: Keep Discord cogs thin and place reusable workflow rules in functions

- Status: accepted
- Date: 2026-08-20
- Owners: FOG bot maintainers

## Context

The bot's Discord cogs combine interaction registration with formatting, validation, date handling, permission decisions, and data transformations. That makes small changes difficult to test without constructing Discord interactions and encourages repeated implementations of the same cross-cutting rules. The SQLite model package exposes positional tuple contracts and is the source of truth for database queries; those contracts must remain stable.

The refactor must preserve public slash-command names, decorators, responses, permissions, model-call order, persistent component identifiers, and Discord side effects. Production dependencies, migrations, and `db/models.py` (the `db.models` package) are outside this decision.

## Decision

Use three explicit layers:

1. `Cogs/` remains the Discord boundary. Cog classes own decorators, listeners, views, locks, background tasks, model calls, interaction responses, and component registration.
2. `utils/` contains small stateless cross-cutting helpers for database presence, Discord-shaped input, response splitting, and date normalization.
3. `services/` contains typed, function-based domain transformations and decisions with dependencies passed as arguments. Ticket-specific helpers stay in `ticket/services.py` alongside the existing ticket package.

Services must not introduce global state, service classes, database query replacements, or Discord API calls unless the existing ticket transcript boundary explicitly requires an async channel iterator. Private cog aliases may remain when tests or local component code depend on an existing name; public commands and configuration names are not renamed.

## Alternatives considered

- **Move all command bodies into service classes.** Rejected because it would transfer lifecycle state, locks, and Discord registration away from cogs and add indirection without preserving a simpler boundary.
- **Create one large shared helpers module.** Rejected because unrelated domains would regain a single high-coupling module; small utilities and domain services are easier to discover and test.
- **Change database models while extracting workflows.** Rejected because positional tuple contracts and migration history are shared integration boundaries and are explicitly out of scope.

## Consequences

Pure rules can be tested with small fakes and temporary data without connecting to Discord. Repeated formatting and validation behavior has one implementation, and cog methods remain focused on side-effect ordering. The repository has more modules and explicit imports, and some private compatibility aliases remain until callers can be migrated safely. Manual verification is still required for permissions, persistent views, reminders, and real Discord message edits.

## Verification and follow-up

Each refactoring stage adds focused contract tests and runs `pipenv run check` plus `git diff --check`. The final audit checks module and command coverage, relative documentation links, and the absence of secrets or production identifiers in the diff. Real Discord interaction checks remain a separate, approval-gated checklist for a non-production guild.

See [architecture](../architecture.md), [module catalog](../modules.md), and the [mission domain](../domain/missions.md) for the current boundaries and behavior.
