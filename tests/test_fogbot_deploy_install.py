"""Tests for the manual, root-owned FogBot deployment helper installer."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest


def _installer_module():
    try:
        return importlib.import_module("deployment.server.install.installer")
    except ModuleNotFoundError:
        pytest.fail("deployment helper installer has not been implemented")


def _config() -> dict[str, object]:
    root = Path("C:/opt/fogbot") if os.name == "nt" else Path("/opt/fogbot")
    state = Path("C:/var/lib/fogbot") if os.name == "nt" else Path("/var/lib/fogbot")
    return {
        "github": {
            "repository_owner": "example-owner",
            "repository_name": "example-repository",
            "repository_id": 22,
            "head_repository_id": 22,
            "workflow_id": 71,
            "workflow_path": ".github/workflows/ci.yml",
            "main_branch": "main",
            "minimum_activation_run_id": 70,
            "activation_timestamp": "2026-08-30T10:00:00+00:00",
            "max_run_age_seconds": 86400,
        },
        "layout": {
            "releases": str(root / "releases"),
            "source_repository": str(root / "source"),
            "shared": str(root / "shared"),
            "state": str(state),
            "operations": str(state / "operations"),
            "backups": str(state / "backups"),
            "configuration": str(root / "shared" / "configuration.json"),
            "database": str(root / "shared" / "db" / "bot.db"),
            "readiness": str(state / "runtime" / "ready.json"),
            "instance_lock": str(state / "runtime" / "instance.lock"),
            "sha_marker": str(state / "current.sha"),
            "minimum_free_bytes": 536870912,
        },
        "health_policy": {
            "stop_timeout_seconds": 180,
            "startup_timeout_seconds": 60,
            "observation_window_seconds": 30,
        },
    }


def test_validate_config_accepts_only_non_secret_deployment_configuration():
    installer = _installer_module()

    validated = installer.validate_config(_config())

    assert validated["github"]["workflow_path"] == ".github/workflows/ci.yml"
    assert Path(validated["layout"]["configuration"]).is_absolute()


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["github"].update(workflow_path=".github/workflows/other.yml"),
        lambda value: value["github"].update(repository_id=0),
        lambda value: value["github"].update(activation_timestamp="2026-08-30"),
        lambda value: value["layout"].update(releases="releases"),
        lambda value: value["layout"].update(configuration=str(Path("C:/opt/fogbot/.env") if os.name == "nt" else Path("/opt/fogbot/.env"))),
        lambda value: value["layout"].update(database=str((Path("C:/opt/fogbot") if os.name == "nt" else Path("/opt/fogbot")) / "db" / "bot.db")),
        lambda value: value["layout"].update(releases=str(Path("C:/opt/fogbot/releases/../unsafe") if os.name == "nt" else Path("/opt/fogbot/releases/../unsafe"))),
    ],
)
def test_validate_config_rejects_invalid_or_sensitive_layout(change):
    installer = _installer_module()
    value = _config()
    change(value)

    with pytest.raises(installer.InstallationConfigError):
        installer.validate_config(value)


def test_render_helper_is_fixed_path_python_entrypoint_without_shell_interpolation(tmp_path: Path):
    installer = _installer_module()
    source = tmp_path / "source"
    config = tmp_path / "config.json"

    rendered = installer.render_helper(source, config)

    assert "entrypoint import" in rendered
    assert source.as_posix() in rendered
    assert config.as_posix() in rendered
    assert "shell=True" not in rendered
    assert "SSH_ORIGINAL_COMMAND" not in rendered
    assert "sys.argv[1:]" in rendered


def test_render_helper_rejects_untrusted_paths(tmp_path: Path):
    installer = _installer_module()

    with pytest.raises(installer.InstallationConfigError):
        installer.render_helper(tmp_path / "source" / "../source", tmp_path / "config.json")

    with pytest.raises(installer.InstallationConfigError):
        installer.render_helper(tmp_path / "source", Path("config.json"))


def test_install_helper_copies_only_deployment_package_and_writes_private_wrapper(tmp_path: Path):
    installer = _installer_module()
    source = tmp_path / "source"
    (source / "deployment" / "server" / "fogbot_deploy").mkdir(parents=True)
    (source / "deployment" / "__init__.py").write_text("", encoding="utf-8")
    (source / "deployment" / "server" / "__init__.py").write_text("", encoding="utf-8")
    (source / "deployment" / "server" / "fogbot_deploy" / "entrypoint.py").write_text("", encoding="utf-8")
    (source / ".env").write_text("DO NOT COPY", encoding="utf-8")
    config_source = tmp_path / "deployment-config.json"
    config_source.write_text(json.dumps(_config()), encoding="utf-8")
    install_root = tmp_path / "installed-source"
    helper = tmp_path / "usr" / "local" / "libexec" / "fogbot-deploy"
    config_destination = tmp_path / "etc" / "fogbot-deploy" / "config.json"

    installer.install_helper(source, config_source, install_root, helper, config_destination)

    assert (install_root / "deployment" / "server" / "fogbot_deploy" / "entrypoint.py").is_file()
    assert not (install_root / ".env").exists()
    assert helper.is_file()
    assert "entrypoint import" in helper.read_text(encoding="utf-8")
    installed_config = json.loads(config_destination.read_text(encoding="utf-8"))
    assert installed_config["github"] == _config()["github"]
    assert installed_config["layout"] == _config()["layout"]
    assert installed_config["policy"] == {
        "stop_timeout_seconds": 180,
        "startup_timeout_seconds": 60,
        "health_timeout_seconds": 30,
        "health_poll_seconds": 1,
    }


def test_install_helper_rejects_source_with_symlink(tmp_path: Path):
    installer = _installer_module()
    source = tmp_path / "source"
    package = source / "deployment" / "server" / "fogbot_deploy"
    package.mkdir(parents=True)
    (source / "deployment" / "__init__.py").write_text("", encoding="utf-8")
    (source / "deployment" / "server" / "__init__.py").write_text("", encoding="utf-8")
    (package / "entrypoint.py").write_text("", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    try:
        (package / "unsafe.py").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")

    config_source = tmp_path / "config.json"
    config_source.write_text(json.dumps(_config()), encoding="utf-8")

    with pytest.raises(installer.InstallationConfigError):
        installer.install_helper(
            source,
            config_source,
            tmp_path / "installed-source",
            tmp_path / "helper",
            tmp_path / "installed-config.json",
        )
