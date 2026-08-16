# Module catalog

All files in `Cogs/` are discovered and loaded by `main.py`. Commands are synchronized only to the configured FOG guild. Permission descriptions below combine Discord decorators with runtime checks; Discord channel and role permissions still determine whether the requested operation can succeed.

## Cog overview

| Cog | Responsibilities | Configuration and models |
| --- | --- | --- |
| `Arrival.py` | `on_ready`, `on_member_join`; user synchronization, blacklist enforcement, welcome/log messages, category roles. | `channels.log_channel_id`, `messages.welcome_message`, `roles.categories_roles_ids`; `Users`, `Blacklist`. |
| `Attendence.py` | Mission attendance entry, lookup, and ranking. | `channels.attendance_channel_id`; `Missions`, `Slots`, `Squads`, `Attendance`, `Users`. |
| `Blacklist.py` | Administrative blacklist management and reporting. | `Users`, `Blacklist`. |
| `Departure.py` | `on_member_remove`; marks the user off-guild and logs departure. | `channels.log_channel_id`; `Users`. |
| `ErrorHandler.py` | `on_command_error`, `on_app_command_error`; user-safe error responses and logging. | No models. |
| `Help.py` | Builds command help filtered by default Discord permissions. | Application command tree. |
| `Honeypot.py` | `on_message`; trap deletion/counter, monitored-channel administration. | `honeypot_system`. |
| `Level.py` | `on_message`; experience/level updates, leaderboard, notification preferences, cached preference flush. | `leveling_system.notifications_off_users`; `Users`. |
| `Missions.py` | Mission lifecycle, persistent signup views, reminders, signup moves and sign-out. | Mission permissions/channels/roles; `Missions`, `Squads`, `Slots`, `Users`. |
| `Ranks.py` | `on_attendance`; converts attendance thresholds into database and Discord role promotion. | `roles.recruit_role_id`, `roles.operator_role_id`; `Users`, `Ranks`, `Attendance`. |
| `Recruitment.py` | Candidate recruitment and basic-training completion. | recruiter/training-manager permissions, candidate/recruit/SzWI roles, recruitment messages; `Users`. |
| `Security.py` | `on_member_update`; guards role combinations around unverified/candidate members. | candidate/other-group roles and whitelist. |
| `Tickets.py` | Ticket-create views, ticket open/close/delete UI, transcripts, persistent view restoration, deleted-message cleanup. | ticket system, manager permissions, log channel; ticket models and `ticket/`. |
| `Trainings.py` | Training lifecycle, persistent signup view, attendance. | `permissions.trainers`; `Trainings`, `TrainingSigned`, `Attendance`. |
| `Triggers.py` | `on_message`; configurable keyword-response rules and in-memory cooldowns. | `message_triggers`. |
| `Update.py` | `on_member_update`, `on_message`; keeps usernames and member activity information current. | `Users`. |
| `Utilities.py` | Diagnostics, moderation helpers, role assignment, outbound messages, and configuration administration. | `technical_info`, permissions/channels/roles/ticket categories/triggers; several models. |
| `Warns.py` | Administrative warning writes and warning reports. | `Users`, `Warns`. |

## Commands by cog

### `Attendence.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/misja_obecnosc` | Mission creator or administrator | Derives attendees from slots, records attendance, emits the rank event, and posts a report. |
| `/obecnosc_sprawdz` | Guild command | Shows attendance for a selected member. |
| `/obecnosc_ranking` | Guild command | Shows the attendance leaderboard. |

### `Blacklist.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/blacklist_dodaj` | Administrator | Creates or replaces a member blacklist entry. |
| `/blacklist_usun` | Administrator | Removes a member from the blacklist. |
| `/blacklist_pokaz` | Guild command | Displays blacklist data. |

### `Help.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/help` | Guild command, filtered output | Lists commands the invoking member can use based on default permissions. |

### `Honeypot.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/honeypot_trap_add` | Administrator | Adds a monitored channel and counter message state. |
| `/honeypot_trap_delete` | Administrator | Removes a monitored channel and associated counter state. |

### `Level.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/level` | Guild command | Shows a member's level and experience. |
| `/leaderboard` | Guild command | Shows the experience leaderboard. |
| `/level_notifications` | Guild command | Enables or disables the invoker's level notifications. |

### `Missions.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/misja_stworz` | Configured mission maker or administrator | Creates a future mission and reminder/announcement work. |
| `/misja_anuluj` | Mission creator or administrator | Cancels tasks/messages and deletes the mission. |
| `/misja_edytuj` | Mission creator or administrator | Changes mission name/time and rebuilds signup messages. |
| `/misja_zapisy_stworz` | Mission creator or administrator | Creates a persistent signup message, squad, and slots. |
| `/misja_zapisy_usun` | Mission creator or administrator | Removes one signup message with its squad and slots. |
| `/misja_zapisy_wypisz` | Mission creator or administrator | Removes a selected member from the mission roster. |

See [Mission domain](domain/missions.md) for the complete state transitions and 12-hour self-service sign-out rule.

### `Recruitment.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/rekrutacja` | Configured recruiter or administrator | Moves a candidate to the recruit role and sends the configured message. |
| `/szwi` | Configured recruiter/basic-training manager or administrator | Assigns the SzWI role and sends the configured message. |

### `Tickets.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/ticket_wiadomosc_przycisk` | Administrator | Posts and stores a persistent single-category ticket button. |
| `/ticket_wiadomosc_select` | Administrator | Posts and stores a persistent multi-category ticket select. |

Ticket channel creation and management buttons use the category-specific handler from `ticket/core.py`. Ticket manager visibility comes from `permissions` keys documented in [Configuration](configuration.md).

### `Trainings.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/szkolenie_stworz` | Configured trainer or administrator | Creates a training and persistent signup message. |
| `/szkolenie_anuluj` | Training creator or administrator | Deletes the training message and record. |
| `/szkolenie_obecnosc` | Training creator or administrator | Records attendance from training signups. |

### `Utilities.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/ping` | Guild command | Reports bot latency. |
| `/info` | Guild command | Shows version, update, run date, and uptime information. |
| `/clear` | Administrator | Deletes a requested number of channel messages. |
| `/change_user_missions` | Administrator | Changes a user's cumulative mission attendance. |
| `/assign_categories_roles` | Administrator | Adds configured category roles to a member. |
| `/send_message` | Administrator | Sends administrator-supplied content through the bot. |
| `/sql_query` | Bot owner | Executes one arbitrary SQL statement and returns its result ephemerally. |
| `/permissions_list` | Administrator | Lists configured permission categories. |
| `/permissions_add` | Administrator | Adds a member or role ID to a permission category. |
| `/permissions_remove` | Administrator | Removes a member or role ID from a permission category. |
| `/channels_list` | Administrator | Lists configured channel mappings. |
| `/channels_set` | Administrator | Assigns a Discord channel to a known mapping. |
| `/channels_remove` | Administrator | Clears a known channel mapping. |
| `/ticket_categories_list` | Administrator | Lists configured ticket categories. |
| `/ticket_categories_add` | Administrator | Adds a ticket category definition. |
| `/ticket_categories_remove` | Administrator | Removes a ticket category definition. |
| `/triggers_list` | Administrator | Lists configured message triggers. |
| `/triggers_add` | Administrator | Adds a message trigger. |
| `/triggers_edit` | Administrator | Changes a message trigger. |
| `/triggers_remove` | Administrator | Removes a message trigger. |

Configuration commands mutate the bot's shared in-memory dictionaries/lists. The hourly autosave and graceful shutdown write those values to `configuration.json`.

### `Warns.py`

| Command | Access | Effect |
| --- | --- | --- |
| `/warn_add` | Administrator | Adds an active warning; database triggers update the counter. |
| `/warn_remove` | Administrator | Removes a warning; database triggers update the counter. |
| `/warn_check` | Guild command | Shows warning information for a selected member. |
| `/warn_list_users` | Guild command | Lists users with active warning counts. |

## Listener-only cogs

`Arrival.py`, `Departure.py`, `ErrorHandler.py`, `Ranks.py`, `Security.py`, `Triggers.py`, and `Update.py` expose no slash commands. Their listeners still require the configured guild resources and Discord permissions described above. `Level.py` and `Honeypot.py` also have message listeners; `Tickets.py` watches deleted registered create messages.

## Adding or changing a module

When a command, listener, permission rule, configuration key, persistent view, or model call changes, update this catalog and the relevant domain/configuration document. Add tests at the local boundary; Discord API behavior remains a manual test in a non-production guild.
