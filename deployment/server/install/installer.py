"""Install the root-owned FogBot deployment helper without a shell.

The installer is intentionally a small, standard-library-only bootstrap tool.  It
does not install packages, edit systemd, edit sudoers, or contact a remote service.
An operator must review the inspected server layout and run it manually as root.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import Any


MAXIMUM_CONFIG_BYTES = 64 * 1024
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SAFE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]{0,127}\Z")
_SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")

_GITHUB_KEYS = frozenset(
    {
        "repository_owner",
        "repository_name",
        "repository_id",
        "head_repository_id",
        "workflow_id",
        "workflow_path",
        "main_branch",
        "minimum_activation_run_id",
        "activation_timestamp",
        "max_run_age_seconds",
    }
)
_LAYOUT_KEYS = frozenset(
    {
        "releases",
        "source_repository",
        "shared",
        "state",
        "operations",
        "backups",
        "configuration",
        "database",
        "readiness",
        "instance_lock",
        "sha_marker",
        "minimum_free_bytes",
    }
)
_POLICY_KEYS = frozenset(
    {
        "stop_timeout_seconds",
        "startup_timeout_seconds",
        "health_timeout_seconds",
        "health_poll_seconds",
    }
)
_HEALTH_POLICY_KEYS = frozenset({"stop_timeout_seconds", "startup_timeout_seconds", "observation_window_seconds"})
_CONFIG_BASE_KEYS = frozenset({"github", "layout"})


class InstallationConfigError(ValueError):
    """Controlled validation failure that is safe to show to an operator."""


def validate_config(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate and copy the non-secret helper configuration.

    The returned value is a new dictionary containing only the allow-listed
    fields.  This intentionally does not accept environment variables, tokens,
    arbitrary command paths, or application configuration values.
    """

    if not isinstance(value, Mapping) or not _CONFIG_BASE_KEYS <= set(value) or set(value) - _CONFIG_BASE_KEYS not in (
        {"policy"},
        {"health_policy"},
    ):
        raise InstallationConfigError("invalid_config_keys")
    github = _mapping(value, "github", _GITHUB_KEYS)
    layout = _mapping(value, "layout", _LAYOUT_KEYS)
    if "health_policy" in value:
        health_policy = _mapping(value, "health_policy", _HEALTH_POLICY_KEYS)
        policy = {
            "stop_timeout_seconds": health_policy["stop_timeout_seconds"],
            "startup_timeout_seconds": health_policy["startup_timeout_seconds"],
            "health_timeout_seconds": health_policy["observation_window_seconds"],
            "health_poll_seconds": 1,
        }
    else:
        policy = _mapping(value, "policy", _POLICY_KEYS)

    _validate_github(github)
    paths = _validate_layout(layout)
    _validate_policy(policy)

    # Rebuild from validated scalar values rather than retaining caller-owned
    # nested mappings or unknown fields.
    return {
        "github": dict(github),
        "layout": paths,
        "policy": dict(policy),
    }


def load_config(path: Path) -> dict[str, dict[str, Any]]:
    """Load only the allow-listed deployment config, never a production config."""

    regular = _regular_file(path)
    if regular.stat().st_size > MAXIMUM_CONFIG_BYTES:
        raise InstallationConfigError("config_too_large")
    try:
        payload = regular.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise InstallationConfigError("config_unavailable") from None
    return validate_config(value)


def render_helper(source_root: Path, config_path: Path, *, python_executable: str = "/usr/bin/python3") -> str:
    """Render the fixed-path Python entry point installed in ``libexec``.

    The runtime package supplies ``entrypoint.main(argv, config_path=...)``.
    No input is interpreted as shell text and the wrapper refuses direct
    non-root execution.  The root-owned sudoers rule remains the only intended
    operator entry point.
    """

    source = _safe_absolute_path(source_root, "source_root")
    config = _safe_absolute_path(config_path, "config_path")
    if not isinstance(python_executable, str) or not python_executable.startswith("/") or any(
        character in python_executable for character in "\r\n\x00"
    ):
        raise InstallationConfigError("invalid_python_executable")
    return f'''#!{python_executable}
"""Root-owned FogBot deployment helper.  Generated; do not edit."""

from __future__ import annotations

import os
from pathlib import Path
import sys

_SOURCE_ROOT = {source.as_posix()!r}
_CONFIG_PATH = {config.as_posix()!r}

if getattr(os, "geteuid", lambda: 1)() != 0:
    raise SystemExit("root_required")

sys.path.insert(0, _SOURCE_ROOT)
from deployment.server.fogbot_deploy.entrypoint import main  # entrypoint import

raise SystemExit(main(sys.argv[1:], config_path=Path(_CONFIG_PATH)))
'''


def install_helper(
    source_root: Path,
    config_source: Path,
    install_root: Path,
    helper_path: Path,
    config_destination: Path,
    *,
    python_executable: str = "/usr/bin/python3",
    replace: bool = False,
) -> None:
    """Install a reviewed deployment package and its fixed wrapper atomically.

    Only the repository's ``deployment`` package is copied.  This prevents
    application state such as ``.env``, ``configuration.json`` and
    ``db/bot.db`` from entering the root-owned helper installation.  Existing
    destinations are rejected unless ``replace=True`` is deliberately supplied.
    """

    source = _safe_absolute_path(source_root, "source_root")
    source_status = _regular_directory(source)
    deployment = source / "deployment"
    _regular_directory(deployment)
    _assert_no_symlinks(deployment)
    entrypoint = deployment / "server" / "fogbot_deploy" / "entrypoint.py"
    _regular_file(entrypoint)
    config_value = load_config(config_source)
    destination = _safe_absolute_path(install_root, "install_root")
    helper = _safe_absolute_path(helper_path, "helper_path")
    config = _safe_absolute_path(config_destination, "config_destination")
    if destination == source or destination in source.parents:
        raise InstallationConfigError("install_root_overlaps_source")
    if source in destination.parents:
        raise InstallationConfigError("install_root_overlaps_source")
    if not replace and any(path.exists() or path.is_symlink() for path in (destination, helper, config)):
        raise InstallationConfigError("target_exists")
    if os.name == "posix" and os.geteuid() != 0:
        raise InstallationConfigError("must_run_as_root")
    del source_status  # The existence/type check above is the only source metadata needed.

    destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    helper.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    config.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        staged_package = stage / "deployment"
        shutil.copytree(deployment, staged_package, symlinks=False)
        _assert_no_symlinks(stage)
        _chmod_tree(stage)
        if destination.exists() or destination.is_symlink():
            if not replace:
                raise InstallationConfigError("target_exists")
            _remove_existing_tree(destination)
        os.replace(stage, destination)
        stage = Path()

        _atomic_write(config, _json_bytes(config_value), 0o600, replace=replace)
        rendered = render_helper(destination, config, python_executable=python_executable).encode("utf-8")
        _atomic_write(helper, rendered, 0o755, replace=replace)
    except Exception:
        if stage != Path() and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def _mapping(value: Mapping[str, Any], key: str, expected_keys: frozenset[str]) -> Mapping[str, Any]:
    nested = value.get(key)
    if not isinstance(nested, Mapping) or set(nested) != expected_keys:
        raise InstallationConfigError(f"invalid_{key}_keys")
    return nested


def _validate_github(github: Mapping[str, Any]) -> None:
    for key in ("repository_owner", "repository_name"):
        value = github[key]
        if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
            raise InstallationConfigError("invalid_repository_configuration")
    branch = github["main_branch"]
    if not isinstance(branch, str) or not _SAFE_BRANCH.fullmatch(branch) or branch.startswith("/") or ".." in branch:
        raise InstallationConfigError("invalid_branch_configuration")
    if github["workflow_path"] != ".github/workflows/ci.yml":
        raise InstallationConfigError("invalid_workflow_configuration")
    for key in ("repository_id", "head_repository_id", "workflow_id", "minimum_activation_run_id"):
        _positive_int(github[key], key)
    timestamp = github["activation_timestamp"]
    if not isinstance(timestamp, str):
        raise InstallationConfigError("invalid_activation_timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise InstallationConfigError("invalid_activation_timestamp") from None
    if parsed.tzinfo is None:
        raise InstallationConfigError("invalid_activation_timestamp")
    age = github["max_run_age_seconds"]
    if not isinstance(age, int) or isinstance(age, bool) or not 300 <= age <= 604800:
        raise InstallationConfigError("invalid_max_run_age")


def _validate_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    paths = {key: _safe_absolute_path(layout[key], key) for key in _LAYOUT_KEYS if key != "minimum_free_bytes"}
    for child, parent in (
        (paths["operations"], paths["state"]),
        (paths["backups"], paths["state"]),
        (paths["readiness"], paths["state"]),
        (paths["instance_lock"], paths["state"]),
        (paths["sha_marker"], paths["state"]),
        (paths["configuration"], paths["shared"]),
        (paths["database"], paths["shared"]),
    ):
        if child == parent or parent not in child.parents:
            raise InstallationConfigError("invalid_layout_relationship")
    if paths["configuration"].name != "configuration.json" or paths["database"].name != "bot.db":
        raise InstallationConfigError("invalid_persistent_file_name")
    if paths["releases"] in paths["configuration"].parents or paths["releases"] in paths["database"].parents:
        raise InstallationConfigError("persistent_file_in_release")
    free_bytes = layout["minimum_free_bytes"]
    if not isinstance(free_bytes, int) or isinstance(free_bytes, bool) or not 0 <= free_bytes <= 2**63 - 1:
        raise InstallationConfigError("invalid_capacity")
    paths["minimum_free_bytes"] = free_bytes
    return {key: os.fspath(value) if isinstance(value, Path) else value for key, value in paths.items()}


def _validate_policy(policy: Mapping[str, Any]) -> None:
    for key, value in policy.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 3600:
            raise InstallationConfigError(f"invalid_policy_{key}")


def _positive_int(value: object, key: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InstallationConfigError(f"invalid_{key}")


def _safe_absolute_path(value: object, key: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise InstallationConfigError(f"invalid_{key}")
    candidate = Path(value)
    if not candidate.is_absolute() or ".." in candidate.parts or any(
        character in os.fspath(candidate) for character in "\x00\r\n"
    ):
        raise InstallationConfigError(f"invalid_{key}")
    return candidate


def _regular_file(path: Path) -> Path:
    try:
        status = path.lstat()
    except OSError:
        raise InstallationConfigError("config_unavailable") from None
    if not stat.S_ISREG(status.st_mode):
        raise InstallationConfigError("config_unavailable")
    return path


def _regular_directory(path: Path) -> Path:
    try:
        status = path.lstat()
    except OSError:
        raise InstallationConfigError("source_unavailable") from None
    if not stat.S_ISDIR(status.st_mode) or stat.S_ISLNK(status.st_mode):
        raise InstallationConfigError("source_unavailable")
    return path


def _assert_no_symlinks(root: Path) -> None:
    for directory, directories, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current.is_symlink():
            raise InstallationConfigError("source_symlink")
        if any((current / name).is_symlink() for name in (*directories, *files)):
            raise InstallationConfigError("source_symlink")


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _chmod_tree(root: Path) -> None:
    if os.name != "posix":
        return
    for directory, directories, files in os.walk(root):
        current = Path(directory)
        os.chmod(current, 0o750)
        for name in directories:
            os.chmod(current / name, 0o750)
        for name in files:
            os.chmod(current / name, 0o640)


def _remove_existing_tree(path: Path) -> None:
    try:
        status = path.lstat()
    except OSError:
        return
    if stat.S_ISLNK(status.st_mode) or stat.S_ISREG(status.st_mode):
        raise InstallationConfigError("unsafe_existing_target")
    if not stat.S_ISDIR(status.st_mode):
        raise InstallationConfigError("unsafe_existing_target")
    shutil.rmtree(path)


def _atomic_write(path: Path, payload: bytes, mode: int, *, replace: bool) -> None:
    if path.exists() or path.is_symlink():
        if not replace:
            raise InstallationConfigError("target_exists")
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                raise InstallationConfigError("unsafe_existing_target")
        except OSError:
            raise InstallationConfigError("unsafe_existing_target") from None
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), mode)
            else:
                os.chmod(temporary, mode)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise InstallationConfigError("install_write_failed") from None
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI used by a human administrator on the already-inspected server."""

    parser = argparse.ArgumentParser(description="Install FogBot's reviewed root-owned deployment helper.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--config", dest="config_source", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--helper-path", type=Path, default=Path("/usr/local/libexec/fogbot-deploy"))
    parser.add_argument("--config-destination", type=Path, default=Path("/etc/fogbot-deploy/config.json"))
    parser.add_argument("--python", dest="python_executable", default="/usr/bin/python3")
    parser.add_argument("--replace", action="store_true", help="explicitly replace existing reviewed targets")
    arguments = parser.parse_args(argv)
    try:
        install_helper(
            arguments.source_root,
            arguments.config_source,
            arguments.install_root,
            arguments.helper_path,
            arguments.config_destination,
            python_executable=arguments.python_executable,
            replace=arguments.replace,
        )
    except InstallationConfigError as error:
        print(f"installation_failed:{error}", file=sys.stderr)
        return 2
    print("installation_staged:helper source config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
