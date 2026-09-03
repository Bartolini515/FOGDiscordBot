# Configuration

The bot reads two local files at startup:

- `.env` contains process secrets and flags.
- `configuration.json` contains guild-specific behavior, Discord IDs, messages, and mutable operational settings.

Neither file should be committed. `configuration.example.json` is the safe structural starting point and contains only zero IDs and empty collections.

## First-start behavior

If `configuration.json` does not exist, startup copies `configuration.example.json` to that path and exits. It never overwrites an existing configuration. Edit the generated file, then run the bot again.

If the file is invalid JSON, misses a required top-level section, uses the wrong basic type, or misses a required honeypot field, startup exits with a `ConfigurationError` explaining the invalid path. The loader validates structure, not the existence of referenced Discord resources.

## Environment variables

Create `.env` locally:

```dotenv
DISCORD_BOT_TOKEN=replace-with-a-test-bot-token
DEBUG=False
```

`DISCORD_BOT_TOKEN` is passed to `bot.run(...)`. `DEBUG` enables additional diagnostic behavior only when its value is exactly `True`. Never put either setting in the JSON example, tests, logs, screenshots, or commits.

## Required top-level shape

| Field | Type | Purpose |
| --- | --- | --- |
| `prefix` | string | Legacy command prefix passed to `commands.Bot`. Slash commands are the main interface. |
| `owner_id` | integer | Discord user ID exposed as bot owner metadata. |
| `guild_id` | integer | The single FOG Discord guild used for command sync and event filtering. |
| `permissions` | object | Named allowlists of Discord user or role IDs. |
| `technical_info` | object | Values shown by `/info`; startup adds `current_run_date`. |
| `channels` | object | Named Discord channel IDs used by features. |
| `roles` | object | Named Discord role IDs or role-ID lists. |
| `ticket_system` | object | Ticket categories and initial ticket messages. |
| `message_triggers` | array | Configurable keyword-response objects. |
| `messages` | object | Configurable user-facing messages. |
| `leveling_system` | object | Leveling notification preferences. |
| `honeypot_system` | object | Honeypot channel and counter state. |

The checked-in example deliberately leaves operational collections empty. A structurally valid example is not a runnable production configuration: set `guild_id` and every ID needed by the features you enable.

## Permissions

Permission lists can contain Discord member IDs and role IDs. Individual cogs also accept Discord administrators where documented.

| Key | Used by |
| --- | --- |
| `mission_makers` | Mission creation; IDs may identify users or roles. |
| `trainers` | Training creation; IDs may identify users or roles. |
| `recruiters` | Recruitment commands and recruitment tickets. |
| `mission_tickets_managers` | Mission ticket visibility and management. |
| `basic_training_tickets_managers` | Basic-training tickets and `/szwi`. |

Other categories can be managed with the administrative `/permissions_*` commands, but they have no effect until code reads the same key.

## Channels

| Key | Required when | Meaning |
| --- | --- | --- |
| `scheduled_missions_channel_id` | Mission creation should be restricted | Allowed mission scheduling channel. Zero/missing disables that location check. |
| `attendance_channel_id` | Recording attendance | Destination for attendance reports. The current command uses this key directly. |
| `log_channel_id` | Join/leave and ticket logging | Operational Discord log channel. |
| `proposals_channel_id` | Proposal tickets | Destination used when forwarding a proposal. |

Administrators can inspect and modify the in-memory mapping with `/channels_list`, `/channels_set`, and `/channels_remove`. Changes are saved by the configuration autosave/shutdown lifecycle.

## Roles

| Key | Required when | Meaning |
| --- | --- | --- |
| `mission_ping_role_id` | Mission announcements | Optional role mentioned for a mission. |
| `candidate_role_id` | Recruitment/security | Candidate role removed on recruitment and observed by security logic. |
| `recruit_role_id` | Recruitment/rank progression | Recruit role assigned after recruitment and used as the entry rank role. |
| `operator_role_id` | Rank progression | Operator role associated with the first progression transition. |
| `szwi_role_id` | Basic training | Role assigned by `/szwi`. |
| `other_group_role_id` | Security | Role checked when validating candidate status. |
| `unverified_roles_whitelist` | Security | Role IDs allowed before verification. |
| `categories_roles_ids` | Arrival/administration | Role IDs treated as member-selectable category roles. |

Use `0` for an intentionally unset scalar role ID and `[]` for an unset role list in examples. Always resolve IDs from the intended test or production guild; identifiers are not portable between guilds.

## Tickets

`ticket_system.ticket_categories` is an array of category objects:

```json
{
  "name": "Example",
  "description": "Safe example category",
  "type": "custom",
  "category_id": 0,
  "prompt_title": true
}
```

- `name` is the configured display/lookup value.
- `description` is shown in ticket selection UI.
- `type` must select one of the seeded values `mission`, `proposal`, `recruitment`, `basic_training`, or `custom`. An unknown value cannot resolve a database type and ticket creation fails; the lower-level handler lookup falls back to `custom` only after a stored type has resolved.
- `category_id` is the Discord category channel under which the ticket channel is created.
- `prompt_title` controls whether the user supplies a title.

`ticket_system.ticket_messages` may contain initial text under the same normalized type names. Ticket creation messages serialize their selected category names in SQLite so their views can be restored after restart.

## Message triggers

Each entry in `message_triggers` supports:

```json
{
  "keyword": "example",
  "response": "Example response",
  "enabled": false,
  "case_sensitive": false,
  "whole_word": true,
  "cooldown_seconds": 0
}
```

The listener ignores disabled or empty-keyword entries. Cooldowns are in-memory and reset on restart. Channel and role restriction code is currently inactive even if similarly named fields are present.

## Messages, technical info, and leveling

- `messages.welcome_message` can use `{mention}` and is sent on member arrival.
- `messages.recruitment_message` and `messages.szwi_message` are used by their respective commands.
- `technical_info.version` and `technical_info.last_updated` are displayed by `/info`; `current_run_date` is maintained by startup.
- `leveling_system.notifications_off_users` is a list of member IDs. `/level_notifications` updates it.

## Honeypot state

All three nested keys are required by the loader:

```json
{
  "honeypot_channels": [],
  "counter_messages": [],
  "trap_counter": 0
}
```

`honeypot_channels` stores monitored channel IDs. `counter_messages` stores the Discord messages updated with the counter. `trap_counter` is the persisted total. Honeypot commands mutate these collections at runtime.

## Privacy and change discipline

- Commit only `configuration.example.json`, with zero IDs and invented text.
- Never inspect, copy, or modify another environment's `configuration.json` as part of tests or documentation work.
- Treat Discord IDs as potentially identifying operational data.
- When a code change reads a new key, update the example, this document, validation when appropriate, and tests in the same change.
