"""Tests for the isolated deployment authorization protocol."""

import importlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest


def _protocol_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.protocol")
    except ModuleNotFoundError:
        pytest.fail("deployment authorization protocol has not been implemented")


def _verifier_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.verifier")
    except ModuleNotFoundError:
        pytest.fail("GitHub deployment verifier has not been implemented")


def _config_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.config")
    except ModuleNotFoundError:
        pytest.fail("deployment verifier configuration has not been implemented")


def _state_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.state")
    except ModuleNotFoundError:
        pytest.fail("durable operation state has not been implemented")


def _cli_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.cli")
    except ModuleNotFoundError:
        pytest.fail("forced command CLI has not been implemented")


def _metadata_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.metadata")
    except ModuleNotFoundError:
        pytest.fail("deployment metadata reader has not been implemented")


def test_submit_parser_accepts_only_the_exact_approved_grammar():
    """Catch a parser regression that accepts injected or malformed submit commands."""
    protocol = _protocol_module()

    parsed = protocol.parse_command(
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11"
    )

    assert parsed.sha == "0123456789abcdef0123456789abcdef01234567"
    assert parsed.run_id == 71
    assert parsed.run_attempt == 2
    assert parsed.repository_id == 22
    assert parsed.version == "1.2.11"
    assert isinstance(protocol.parse_command("current"), protocol.CurrentRequest)

    for command in (
        "current extra",
        " submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11 extra",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11;id",
        "submit 0123456789abcdef0123456789abcdef01234567 0 2 22 1.2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 -22 1.2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 v1.2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 01.2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.02.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.011",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 ١.٢.٣",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11-rc1",
        "status ABCDEF0123456789abcdef0123456789",
    ):
        with pytest.raises(protocol.CommandError):
            protocol.parse_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "submit 0123456789abcdef0123456789abcdef01234567 " + "9" * 20 + " 2 22 1.2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 " + "1" * 10 + ".2.11",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 " + "1" * 500,
    ],
)
def test_submit_parser_rejects_excessive_numeric_and_version_tokens(command):
    """Catch a resource-exhaustion regression that accepts oversized identity fields."""
    protocol = _protocol_module()

    with pytest.raises(protocol.CommandError, match="invalid_command"):
        protocol.parse_command(command)


def test_submit_parser_converts_huge_integer_failures_to_controlled_errors():
    """Catch a parser regression that lets Python integer limits escape the forced-command boundary."""
    protocol = _protocol_module()
    command = "submit 0123456789abcdef0123456789abcdef01234567 " + "9" * 5000 + " 2 22 1.2.11"

    with pytest.raises(protocol.CommandError, match="invalid_command"):
        protocol.parse_command(command)


def test_operation_id_is_stable_and_strictly_lowercase_hex():
    """Catch an idempotency regression that makes a retry create another operation."""
    protocol = _protocol_module()
    request = protocol.SubmitRequest(
        sha="0123456789abcdef0123456789abcdef01234567",
        run_id=71,
        run_attempt=2,
        repository_id=22,
        version="1.2.11",
    )

    operation_id = protocol.operation_id_for(request)

    assert operation_id == protocol.operation_id_for(request)
    assert len(operation_id) == 32
    assert operation_id.isascii()
    assert operation_id.islower()
    assert all(character in "0123456789abcdef" for character in operation_id)


def test_operation_id_changes_when_only_operator_version_changes():
    """Catch a replay regression that aliases deployments with different declared versions."""
    protocol = _protocol_module()
    common = {
        "sha": "0123456789abcdef0123456789abcdef01234567",
        "run_id": 71,
        "run_attempt": 2,
        "repository_id": 22,
    }

    first = protocol.operation_id_for(protocol.SubmitRequest(**common, version="1.2.11"))
    second = protocol.operation_id_for(protocol.SubmitRequest(**common, version="1.2.12"))

    assert first != second


class FakeHttp:
    """Fake public-API boundary retaining the requested endpoints."""

    def __init__(self, responses):
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float):
        self.urls.append(url)
        return self.responses[url]


def _deployment_config(now: datetime):
    config = _config_module()
    return config.DeploymentConfig(
        repository_owner="example-owner",
        repository_name="example-repository",
        repository_id=22,
        head_repository_id=22,
        workflow_id=71,
        workflow_path=".github/workflows/ci.yml",
        main_branch="main",
        minimum_activation_run_id=70,
        activation_timestamp=now - timedelta(hours=2),
        max_run_age=timedelta(hours=24),
    )


def _run_payload(now: datetime, **changes):
    payload = {
        "id": 71,
        "run_attempt": 2,
        "head_sha": "0123456789abcdef0123456789abcdef01234567",
        "event": "push",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "repository": {"id": 22},
        "head_repository": {"id": 22},
        "workflow_id": 71,
        "path": ".github/workflows/ci.yml",
        "created_at": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    }
    payload.update(changes)
    return payload


def _verify(run_payload, now: datetime, *, request_sha=None, main_sha=None, activation_timestamp=None):
    verifier = _verifier_module()
    protocol = _protocol_module()
    config = _deployment_config(now)
    if activation_timestamp is not None:
        config = replace(config, activation_timestamp=activation_timestamp)
    run_url = "https://api.github.com/repos/example-owner/example-repository/actions/runs/71"
    main_url = "https://api.github.com/repos/example-owner/example-repository/git/ref/heads/main"
    http = FakeHttp({run_url: run_payload, main_url: {"object": {"sha": main_sha or run_payload["head_sha"]}}})
    checked = verifier.GitHubRunVerifier(config, http, now=lambda: now).verify(
        protocol.SubmitRequest(request_sha or run_payload["head_sha"], 71, 2, 22, "1.2.11")
    )
    return checked, http


def test_verifier_requires_exact_run_and_current_main_identity():
    """Catch a substitution regression that authorizes a different commit than main."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    checked, http = _verify(_run_payload(now), now)

    assert checked.sha == "0123456789abcdef0123456789abcdef01234567"
    assert http.urls == [
        "https://api.github.com/repos/example-owner/example-repository/actions/runs/71",
        "https://api.github.com/repos/example-owner/example-repository/git/ref/heads/main",
    ]

    verifier = _verifier_module()
    with pytest.raises(verifier.VerificationError, match="current_main_mismatch"):
        _verify(_run_payload(now), now, main_sha="abcdef0123456789abcdef0123456789abcdef01")


@pytest.mark.parametrize(
    ("changes", "diagnostic"),
    [
        ({"event": "pull_request"}, "event_mismatch"),
        ({"head_repository": {"id": 23}}, "head_repository_mismatch"),
        ({"workflow_id": 72}, "workflow_mismatch"),
        ({"id": 69}, "run_id_mismatch"),
    ],
)
def test_verifier_rejects_unapproved_run_provenance(changes, diagnostic):
    """Catch authorization regressions for stale, forked, PR, wrong-workflow, or old runs."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    verifier = _verifier_module()

    with pytest.raises(verifier.VerificationError, match=diagnostic):
        _verify(_run_payload(now, **changes), now)


def test_verifier_rejects_stale_and_pre_activation_requests():
    """Catch a rollback regression that permits stale or pre-activation CI evidence."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    verifier = _verifier_module()

    with pytest.raises(verifier.VerificationError, match="stale_run"):
        _verify(
            _run_payload(now, created_at="2026-08-28T11:00:00Z"),
            now,
            activation_timestamp=now - timedelta(days=3),
        )


def _verified_run(now: datetime):
    verifier = _verifier_module()
    return verifier.VerifiedRun(
        repository_id=22,
        run_id=71,
        run_attempt=2,
        sha="0123456789abcdef0123456789abcdef01234567",
        verified_at=now,
    )


def test_operation_store_creates_an_atomic_redacted_json_record(tmp_path):
    """Catch a state regression that loses durable identity or serializes error/log text."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    state = _state_module()
    protocol = _protocol_module()
    request = protocol.SubmitRequest("0123456789abcdef0123456789abcdef01234567", 71, 2, 22, "1.2.11")
    operation_id = protocol.operation_id_for(request)
    record = state.OperationRecord.authorized(_verified_run(now), operation_id, request.version)
    store = state.OperationStore(tmp_path / "operations")

    saved, created = store.create_or_read(record)
    raw = json.loads((tmp_path / "operations" / f"{operation_id}.json").read_text(encoding="utf-8"))

    assert created is True
    assert saved.operation_id == operation_id
    assert raw["phase"] == "authorized"
    assert raw["target"] == {
        "repository_id": 22,
        "run_attempt": 2,
        "run_id": 71,
        "sha": request.sha,
        "target_version": "1.2.11",
    }
    assert raw["diagnostic_code"] == "authorized"
    assert "error" not in raw
    assert "log" not in raw
    assert store.read(operation_id) == saved


class RecordingLauncher:
    def __init__(self):
        self.operation_ids: list[str] = []

    def start(self, record):
        self.operation_ids.append(record.operation_id)


class AcceptingVerifier:
    def __init__(self, verified):
        self.verified = verified
        self.calls = 0

    def verify(self, request):
        self.calls += 1
        return self.verified


class FixedMetadataReader:
    def __init__(self, version="1.2.11", last_updated="2026-08-20"):
        self.version = version
        self.last_updated = last_updated

    def read(self):
        metadata = _metadata_module()
        return metadata.CurrentMetadata(self.version, self.last_updated)


def test_forced_command_replays_submit_without_relaunching_and_reports_status(tmp_path):
    """Catch replay behavior that starts two deployment transactions for one CI run."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    cli = _cli_module()
    state = _state_module()
    verifier = AcceptingVerifier(_verified_run(now))
    launcher = RecordingLauncher()
    handler = cli.ForcedCommandHandler(
        verifier, state.OperationStore(tmp_path / "operations"), launcher, FixedMetadataReader()
    )
    command = "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11"

    first = handler.handle(command)
    second = handler.handle(command)
    operation_id = json.loads(first.stdout)["operation_id"]
    status = handler.handle(f"status {operation_id}")

    assert first.exit_code == 0
    assert first.stdout == second.stdout
    assert verifier.calls == 2
    assert launcher.operation_ids == [operation_id]
    assert json.loads(status.stdout)["phase"] == "authorized"


def test_forced_command_uses_version_as_replay_identity_and_persists_it(tmp_path):
    """Catch a replay regression that reuses the operation of a different target version."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    cli = _cli_module()
    state = _state_module()
    launcher = RecordingLauncher()
    handler = cli.ForcedCommandHandler(
        AcceptingVerifier(_verified_run(now)), state.OperationStore(tmp_path / "operations"), launcher, FixedMetadataReader()
    )

    initial = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11")
    replay = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11")
    changed = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.12")

    assert initial.stdout == replay.stdout
    assert json.loads(initial.stdout)["operation_id"] != json.loads(changed.stdout)["operation_id"]
    assert len(launcher.operation_ids) == 2
    first_target = json.loads(
        (tmp_path / "operations" / f"{json.loads(initial.stdout)['operation_id']}.json").read_text(encoding="utf-8")
    )["target"]
    assert first_target["target_version"] == "1.2.11"


def test_current_returns_only_redacted_version_metadata(tmp_path):
    """Catch a current-command regression that exposes full production configuration."""
    metadata = _metadata_module()
    cli = _cli_module()
    state = _state_module()
    config_path = tmp_path / "configuration.json"
    config_path.write_text(
        json.dumps(
            {
                "technical_info": {"version": "1.2.11", "last_updated": "2026-08-20"},
                "discord_token": "not-returned",
                "channels": {"internal": 1},
            }
        ),
        encoding="utf-8",
    )
    handler = cli.ForcedCommandHandler(
        AcceptingVerifier(_verified_run(datetime(2026, 8, 30, tzinfo=UTC))),
        state.OperationStore(tmp_path / "operations"),
        RecordingLauncher(),
        metadata.ProductionMetadataReader(config_path),
    )

    response = handler.handle("current")

    assert response.exit_code == 0
    assert json.loads(response.stdout) == {"ok": True, "version": "1.2.11", "last_updated": "2026-08-20"}
    assert "not-returned" not in response.stdout
    assert str(config_path) not in response.stdout


@pytest.mark.parametrize(
    "content",
    [
        "{",
        json.dumps({"technical_info": {"version": "01.2.11", "last_updated": "2026-08-20"}}),
        json.dumps({"technical_info": {"version": "١.٢.٣", "last_updated": "2026-08-20"}}),
        json.dumps({"technical_info": {"version": "1.2.11", "last_updated": "2026-02-30"}}),
        json.dumps({"technical_info": {"version": 12, "last_updated": "2026-08-20"}}),
    ],
)
def test_current_redacts_missing_or_invalid_configuration(tmp_path, content):
    """Catch a metadata-reader regression that leaks invalid configuration details."""
    metadata = _metadata_module()
    cli = _cli_module()
    state = _state_module()
    config_path = tmp_path / "configuration.json"
    config_path.write_text(content, encoding="utf-8")
    handler = cli.ForcedCommandHandler(
        AcceptingVerifier(_verified_run(datetime(2026, 8, 30, tzinfo=UTC))),
        state.OperationStore(tmp_path / "operations"),
        RecordingLauncher(),
        metadata.ProductionMetadataReader(config_path),
    )

    response = handler.handle("current")

    assert response.exit_code == 4
    assert json.loads(response.stdout) == {"code": "configuration_unavailable", "ok": False}
    assert str(config_path) not in response.stdout


def test_current_rejects_missing_oversized_and_non_regular_configuration(tmp_path):
    """Catch a metadata-reader regression that accepts unsafe configuration inputs."""
    metadata = _metadata_module()
    cli = _cli_module()
    state = _state_module()
    missing = metadata.ProductionMetadataReader(tmp_path / "missing.json")
    oversized_path = tmp_path / "oversized.json"
    oversized_path.write_bytes(b"x" * (metadata.MAXIMUM_CONFIGURATION_BYTES + 1))
    oversized = metadata.ProductionMetadataReader(oversized_path)
    directory = metadata.ProductionMetadataReader(tmp_path)

    for reader in (missing, oversized, directory):
        handler = cli.ForcedCommandHandler(
            AcceptingVerifier(_verified_run(datetime(2026, 8, 30, tzinfo=UTC))),
            state.OperationStore(tmp_path / "operations"),
            RecordingLauncher(),
            reader,
        )
        response = handler.handle("current")

        assert response.exit_code == 4
        assert json.loads(response.stdout) == {"code": "configuration_unavailable", "ok": False}


def test_metadata_reader_rejects_path_replacement_before_opening_descriptor(tmp_path, monkeypatch):
    """Catch a TOCTOU regression that follows a symlink swapped in after path inspection."""
    metadata = _metadata_module()
    configuration_path = tmp_path / "configuration.json"
    replacement_path = tmp_path / "replacement.json"
    configuration_path.write_text(
        json.dumps({"technical_info": {"version": "1.2.11", "last_updated": "2026-08-20"}}), encoding="utf-8"
    )
    replacement_path.write_text(
        json.dumps({"technical_info": {"version": "9.9.9", "last_updated": "2026-08-21"}}), encoding="utf-8"
    )
    original_open = os.open

    def replace_path_then_open(path, flags, mode=0o777):
        if os.fspath(path) == os.fspath(configuration_path):
            configuration_path.unlink()
            try:
                configuration_path.symlink_to(replacement_path)
            except OSError as error:
                pytest.skip(f"symlink replacement is unavailable: {error.winerror}")
        return original_open(path, flags, mode)

    monkeypatch.setattr(os, "open", replace_path_then_open)

    with pytest.raises(metadata.MetadataError, match="configuration_unavailable"):
        metadata.ProductionMetadataReader(configuration_path).read()


def test_repository_does_not_contain_a_github_cd_workflow():
    """Catch scope drift that reintroduces prohibited automatic deployment automation."""
    from pathlib import Path

    assert not Path(".github/workflows/cd.yml").exists()


def test_forced_command_rejects_malformed_input_and_redacts_verifier_errors(tmp_path):
    """Catch a forced-command regression that exposes an exception or accepts shell syntax."""
    cli = _cli_module()
    state = _state_module()
    verifier_module = _verifier_module()

    class RejectingVerifier:
        def verify(self, request):
            raise verifier_module.VerificationError("workflow_mismatch")

    handler = cli.ForcedCommandHandler(
        RejectingVerifier(), state.OperationStore(tmp_path / "operations"), RecordingLauncher(), FixedMetadataReader()
    )

    malformed = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11; id")
    rejected = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22 1.2.11")

    assert malformed.exit_code == 2
    assert json.loads(malformed.stdout) == {"code": "invalid_command", "ok": False}
    assert rejected.exit_code == 3
    assert json.loads(rejected.stdout) == {"code": "workflow_mismatch", "ok": False}
    assert "exception" not in rejected.stdout
