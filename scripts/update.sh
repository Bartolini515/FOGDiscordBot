#!/usr/bin/env bash

set -Eeuo pipefail

readonly SERVICE_NAME="fogbot.service"
readonly STOP_TIMEOUT_SECONDS="${FOGBOT_STOP_TIMEOUT_SECONDS:-120}"
readonly PYTHON_BIN="${FOGBOT_PYTHON_BIN:-python3}"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly CONFIG_FILE="$REPO_DIR/configuration.json"

stage="initialization"
service_stop_confirmed=0
service_start_requested=0
service_active_confirmed=0

fail() {
    printf 'FogBot update failed during %s: %s\n' "$stage" "$*" >&2
    exit 1
}

on_interrupt() {
    if (( service_active_confirmed == 1 )); then
        printf 'FogBot update interrupted during %s; the service is already active.\n' "$stage" >&2
    elif (( service_stop_confirmed == 1 && service_start_requested == 0 )); then
        printf 'FogBot update interrupted during %s; the service was left stopped.\n' "$stage" >&2
    else
        printf 'FogBot update interrupted during %s; inspect the service state before continuing.\n' "$stage" >&2
    fi
    exit 130
}

trap on_interrupt INT TERM

[[ "$STOP_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail "FOGBOT_STOP_TIMEOUT_SECONDS must be a positive integer"
command -v git >/dev/null 2>&1 || fail "git is not available"
command -v sudo >/dev/null 2>&1 || fail "sudo is not available"
command -v systemctl >/dev/null 2>&1 || fail "systemctl is not available"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "python interpreter is not available: $PYTHON_BIN"

[[ -d "$REPO_DIR/.git" ]] || fail "repository metadata was not found at $REPO_DIR"
[[ -f "$CONFIG_FILE" ]] || fail "configuration file was not found at $CONFIG_FILE"

stage="checking repository"
git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "the script directory is not inside a Git worktree"
branch="$(git -C "$REPO_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
[[ -n "$branch" ]] || fail "the repository is in detached HEAD state"
upstream="$(git -C "$REPO_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[[ -n "$upstream" ]] || fail "the current branch has no upstream"
[[ -z "$(git -C "$REPO_DIR" status --porcelain)" ]] || fail "the Git worktree contains local changes"

stage="checking configuration"
if ! "$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open(encoding="utf-8") as config_file:
    data = json.load(config_file)

if not isinstance(data, dict) or not isinstance(data.get("technical_info"), dict):
    raise ValueError("technical_info must be a JSON object")
PY
then
    fail "configuration.json is not valid or has no technical_info object"
fi

stage="stopping service"
sudo systemctl stop "$SERVICE_NAME" || fail "systemctl stop failed"

stage="waiting for service to stop"
deadline=$((SECONDS + STOP_TIMEOUT_SECONDS))
while true; do
    service_state="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
    if [[ "$service_state" == "inactive" ]]; then
        service_stop_confirmed=1
        break
    fi
    if (( SECONDS >= deadline )); then
        fail "service did not become inactive within ${STOP_TIMEOUT_SECONDS} seconds"
    fi
    sleep 1
done

stage="reading version"
while true; do
    printf 'Enter version (core.major.minor): '
    if ! IFS= read -r version; then
        fail "no version was provided"
    fi
    version="${version%$'\r'}"
    if [[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        break
    fi
    printf 'Invalid version. Use three numbers such as 1.23.45.\n' >&2
done

stage="updating configuration"
update_date="$(date +%F)" || fail "could not determine the current date"
if ! "$PYTHON_BIN" - "$CONFIG_FILE" "$version" "$update_date" <<'PY'
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

config_path = Path(sys.argv[1])
version = sys.argv[2]
update_date = sys.argv[3]

with config_path.open(encoding="utf-8") as config_file:
    data = json.load(config_file)

if not isinstance(data, dict) or not isinstance(data.get("technical_info"), dict):
    raise ValueError("technical_info must be a JSON object")

data["technical_info"]["version"] = version
data["technical_info"]["last_updated"] = update_date

file_mode = stat.S_IMODE(config_path.stat().st_mode)
temporary_path: str | None = None
try:
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        dir=config_path.parent,
        text=True,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary_file:
        json.dump(data, temporary_file, ensure_ascii=False, indent=4)
        temporary_file.write("\n")
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
    os.chmod(temporary_path, file_mode)
    os.replace(temporary_path, config_path)
    temporary_path = None
finally:
    if temporary_path is not None:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
PY
then
    fail "could not update configuration.json"
fi

stage="pulling latest commit"
git -C "$REPO_DIR" pull --ff-only --quiet \
    || fail "git pull --ff-only failed; the service was left stopped"

stage="starting service"
service_start_requested=1
sudo systemctl start "$SERVICE_NAME" || fail "systemctl start failed; the service was left stopped"

stage="verifying service"
service_state="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
[[ "$service_state" == "active" ]] \
    || fail "service is not active after start; inspect systemd before continuing"
service_active_confirmed=1

commit="$(git -C "$REPO_DIR" rev-parse --short HEAD)"
printf 'FogBot updated to %s on %s (commit %s); service is active.\n' "$version" "$update_date" "$commit"
