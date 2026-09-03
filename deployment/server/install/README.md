# FogBot manual helper installation

These are static review examples. They **must not be installed verbatim**.
They contain deliberate placeholders and generic illustrative absolute paths only.

Before any installation, perform approved read-only server inspection to establish
the service account/group, ownership, the immutable release/shared/state layout,
available capacity, existing systemd unit, current symlink convention, and the
root-owned helper location. Fill placeholders only from that inspection, review the
rendered files, and obtain a separate approval for each server-side change.

The unit keeps runtime configuration outside `current`, uses release-local Python,
has finite start/stop bounds, and does not invoke a shell. The sudoers template
permits only the root-owned deployment helper's strict `current`, `status`, and
`submit` grammar; it does not grant general root or arbitrary systemctl access.
The optional sysusers/tmpfiles examples establish only restrictive directory shape.

No deployment is automatic: this repository deliberately includes no CD workflow.
Do not add tokens, keys, IP addresses, production account names, secret contents,
or production paths to these templates.

## Installing the root-owned helper

The manual installer is `installer.py`; it uses only the Python standard library,
never invokes a shell, contacts GitHub, changes systemd, or edits sudoers. It
copies only the `deployment/` package, never the application tree. Consequently
`.env`, `configuration.json`, `db/bot.db`, logs, and other runtime state are not
copied into the helper source directory.

The copied runtime package must expose this stable entry point:

```text
deployment.server.fogbot_deploy.entrypoint.main(argv, *, config_path) -> int
```

The generated `/usr/local/libexec/fogbot-deploy` wrapper passes already-tokenized
arguments as `argv[1:]`, imports the entry point from a fixed absolute source
directory, and refuses direct non-root execution. The exact sudoers rule remains
the only intended operator path.

Before every server-side change obtain separate approval and confirm an
appropriate backup or snapshot. First perform read-only inspection of the
service account/group, current systemd unit, release/shared/state layout,
ownership/modes, Python/Pipenv/Git versions, disk space, backups, and network
route. This installer does not stop or restart FogBot.

## Non-secret configuration

Copy `fogbot-deploy.config.example.json` to an administrative location and fill
the example values only after inspection. It accepts public GitHub identity/CI
values, absolute filesystem paths, and bounded `health_policy` values. It does
not accept tokens, SSH keys, Discord credentials, environment values, arbitrary
commands, or network endpoints. The workflow path must be exactly
`.github/workflows/ci.yml`; `configuration.json` and `bot.db` must remain under
`shared`, never in a release directory.

The example accepts a compact `health_policy` input and canonicalizes it to the
runtime's current `policy` shape: `startup_timeout_seconds`,
`stop_timeout_seconds`, `health_timeout_seconds`, and the fixed one-second
`health_poll_seconds`. An already canonical `policy` object is accepted too.
The `github.activation_timestamp` and `minimum_activation_run_id` fields define
the server-side trust boundary.

## Manual installation command

Run the following as root on the already-inspected server, changing only paths
that were confirmed by inspection:

```text
cd /path/to/reviewed/FogDiscordBot
/usr/bin/python3 -m deployment.server.install.installer \
  --source-root /path/to/reviewed/FogDiscordBot \
  --config /path/to/fogbot-deploy.config.json \
  --install-root /usr/local/libexec/fogbot-deploy-src/<reviewed-source-id> \
  --helper-path /usr/local/libexec/fogbot-deploy \
  --config-destination /etc/fogbot-deploy/config.json
```

The source directory must contain the reviewed `entrypoint.py`. The configured
`source_repository` must be a root-owned Git clone with a trusted `origin`; each
deployment refreshes only `origin main` and then uses the exact verified SHA.
The installer
rejects symlinks, traversal paths, invalid CI identity, unbounded timeouts,
missing entry point, and persistent files below `releases`. It writes the
configuration with mode `0600`, wrapper with `0755`, and restrictive source
permissions where POSIX modes are available. Existing targets are rejected by
default; do not use `--replace` without a new review and approval.

After staging, independently verify root ownership, modes, file sizes, and the
wrapper's absolute source/config paths without printing configuration contents.
Only then fill and review `fogbot.service.template`,
`fogbot-deploy.sudoers.template`, `fogbot.sysusers.template`, and
`fogbot.tmpfiles.template`. Validate the rendered sudoers file with `visudo -cf`.
The rendered systemd unit must set `FOGBOT_CONFIG_PATH`, `FOGBOT_DB_PATH`,
`FOGBOT_LOG_DIR`, `FOGBOT_RUNTIME_DIR`, `FOGBOT_RELEASE_FILE`, and
`FOGBOT_INSTANCE_LOCK` to the same shared/state paths used in the helper config;
otherwise the bot would create state inside an immutable release.
The operator rule must allow only the exact `current`, `status`, and `submit`
grammar for `/usr/local/libexec/fogbot-deploy`, not arbitrary root or systemctl.
Systemd changes, first deployment, migrations, and rollback tests each need a
separate approval.

The local control plane uses only:

```text
version fogbot
deployment-status fogbot <operation_id>
change fogbot deploy <sha> <run_id> <run_attempt> <repo_id> <version> -Approve
```

Never use raw SSH, arbitrary remote commands, or production secrets. Before the
first deployment validate `current`, malformed-command rejection, exact
SHA/run/repository verification, replay idempotency, offline SQLite migration,
single-process locking, failed-start classification, host-restart recovery,
and backup validation. Discord checks belong only to an approved non-production
guild.
