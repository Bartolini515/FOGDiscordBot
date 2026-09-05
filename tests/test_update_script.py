from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from datetime import date

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "update.sh"


def _bash() -> str:
    candidates = [shutil.which("bash")]
    if os.name == "nt":
        candidates.append(r"C:\Program Files\Git\usr\bin\bash.exe")
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    pytest.skip("bash is required to exercise scripts/update.sh")


def _msys_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    drive, tail = os.path.splitdrive(str(resolved))
    return f"/{drive.rstrip(':').lower()}{tail.replace(os.sep, '/')}"


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _prepare_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    shutil.copy2(SCRIPT, repo / "scripts" / "update.sh")
    (repo / ".gitignore").write_text("configuration.json\n", encoding="utf-8")
    (repo / "configuration.json").write_text(
        json.dumps(
            {
                "technical_info": {"version": "1.0.0", "last_updated": "2026-01-01"},
                "other": {"preserved": True},
            }
        ),
        encoding="utf-8",
    )

    remote = tmp_path / "remote.git"
    _run_git(tmp_path, "init", "--bare", str(remote))
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "add", ".gitignore", "scripts/update.sh")
    _run_git(repo, "commit", "-m", "Initial test commit")
    _run_git(repo, "remote", "add", "origin", str(remote))
    _run_git(repo, "push", "-u", "origin", "main")

    upstream = tmp_path / "upstream"
    _run_git(tmp_path, "clone", "--branch", "main", str(remote), str(upstream))
    _run_git(upstream, "config", "user.email", "test@example.invalid")
    _run_git(upstream, "config", "user.name", "Test User")
    (upstream / "pulled-release-marker").write_text("latest\n", encoding="utf-8")
    _run_git(upstream, "add", "pulled-release-marker")
    _run_git(upstream, "commit", "-m", "Release marker")
    _run_git(upstream, "push")

    commands = tmp_path / "commands"
    commands.mkdir()
    state = tmp_path / "service.state"
    state.write_text("active\n", encoding="utf-8")
    log = tmp_path / "systemctl.log"
    _write_executable(
        commands / "sudo",
        "#!/usr/bin/env bash\nexec \"$@\"\n",
    )
    _write_executable(
        commands / "systemctl",
        f'''#!/usr/bin/env bash
set -eu
state={_msys_path(state)!r}
log={_msys_path(log)!r}
printf '%s\\n' "$*" >> "$log"
case "$1" in
  stop)
    if [[ "${{FAKE_KEEP_ACTIVE:-0}}" != 1 ]]; then
      printf 'inactive\\n' > "$state"
    fi
    ;;
  is-active)
    cat "$state"
    [[ $(cat "$state") == inactive ]]
    ;;
  start)
    printf 'active\\n' > "$state"
    ;;
  *)
    exit 2
    ;;
esac
''',
    )
    return repo, commands, log


def _python_command() -> str:
    executable = Path(sys.executable).resolve()
    return _msys_path(executable)


def _run_update(
    repo: Path,
    commands: Path,
    input_text: str,
    **environment_overrides: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if os.name == "nt":
        environment["PATH"] = f"{_msys_path(commands)}:/usr/bin:/bin:/cmd"
    else:
        environment["PATH"] = f"{commands}{os.pathsep}{environment.get('PATH', '')}"
    environment["FOGBOT_PYTHON_BIN"] = _python_command()
    environment.update(environment_overrides)
    return subprocess.run(
        [_bash(), str(repo / "scripts" / "update.sh")],
        cwd=repo,
        env=environment,
        input=input_text,
        capture_output=True,
        text=True,
    )


def test_update_script_stops_updates_and_starts_service(tmp_path: Path) -> None:
    repo, commands, log = _prepare_repo(tmp_path)

    result = _run_update(repo, commands, "1.23.45\n")

    assert result.returncode == 0, result.stderr + result.stdout
    configuration = json.loads((repo / "configuration.json").read_text(encoding="utf-8"))
    assert configuration["technical_info"] == {
        "version": "1.23.45",
        "last_updated": date.today().isoformat(),
    }
    assert configuration["other"] == {"preserved": True}
    assert (repo / "pulled-release-marker").read_text(encoding="utf-8") == "latest\n"
    assert log.read_text(encoding="utf-8").splitlines() == [
        "stop fogbot.service",
        "is-active fogbot.service",
        "start fogbot.service",
        "is-active fogbot.service",
    ]


def test_update_script_does_not_stop_service_with_dirty_worktree(tmp_path: Path) -> None:
    repo, commands, log = _prepare_repo(tmp_path)
    (repo / "tracked-change.txt").write_text("local change\n", encoding="utf-8")

    result = _run_update(repo, commands, "1.23.45\n")

    assert result.returncode != 0
    assert "worktree contains local changes" in result.stderr
    assert not log.exists()


def test_update_script_leaves_service_stopped_when_stop_times_out(tmp_path: Path) -> None:
    repo, commands, log = _prepare_repo(tmp_path)

    result = _run_update(
        repo,
        commands,
        "1.23.45\n",
        FOGBOT_STOP_TIMEOUT_SECONDS="1",
        FAKE_KEEP_ACTIVE="1",
    )

    assert result.returncode != 0
    assert "did not become inactive" in result.stderr
    assert "start fogbot.service" not in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("version", ["1.2", "1.2.3.4", "v1.2.3", "01.2.3", "1.2.3-rc.1"])
def test_update_script_rejects_non_core_major_minor_version(tmp_path: Path, version: str) -> None:
    repo, commands, log = _prepare_repo(tmp_path)

    result = _run_update(repo, commands, version + "\n")

    assert result.returncode != 0
    configuration = json.loads((repo / "configuration.json").read_text(encoding="utf-8"))
    assert configuration["technical_info"] == {
        "version": "1.0.0",
        "last_updated": "2026-01-01",
    }
    assert log.read_text(encoding="utf-8").splitlines() == [
        "stop fogbot.service",
        "is-active fogbot.service",
    ]
