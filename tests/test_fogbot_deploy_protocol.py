"""Tests for the isolated deployment authorization protocol."""

import importlib
import json
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


def test_submit_parser_accepts_only_the_exact_approved_grammar():
    """Catch a parser regression that accepts injected or malformed submit commands."""
    protocol = _protocol_module()

    parsed = protocol.parse_command(
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22"
    )

    assert parsed.sha == "0123456789abcdef0123456789abcdef01234567"
    assert parsed.run_id == 71
    assert parsed.run_attempt == 2
    assert parsed.repository_id == 22

    for command in (
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22 extra",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 22;id",
        "submit 0123456789abcdef0123456789abcdef01234567 0 2 22",
        "submit 0123456789abcdef0123456789abcdef01234567 71 2 -22",
        "status ABCDEF0123456789abcdef0123456789",
    ):
        with pytest.raises(protocol.CommandError):
            protocol.parse_command(command)


def test_operation_id_is_stable_and_strictly_lowercase_hex():
    """Catch an idempotency regression that makes a retry create another operation."""
    protocol = _protocol_module()
    request = protocol.SubmitRequest(
        sha="0123456789abcdef0123456789abcdef01234567",
        run_id=71,
        run_attempt=2,
        repository_id=22,
    )

    operation_id = protocol.operation_id_for(request)

    assert operation_id == protocol.operation_id_for(request)
    assert len(operation_id) == 32
    assert operation_id.isascii()
    assert operation_id.islower()
    assert all(character in "0123456789abcdef" for character in operation_id)


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
        protocol.SubmitRequest(request_sha or run_payload["head_sha"], 71, 2, 22)
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
    request = protocol.SubmitRequest("0123456789abcdef0123456789abcdef01234567", 71, 2, 22)
    operation_id = protocol.operation_id_for(request)
    record = state.OperationRecord.authorized(_verified_run(now), operation_id)
    store = state.OperationStore(tmp_path / "operations")

    saved, created = store.create_or_read(record)
    raw = json.loads((tmp_path / "operations" / f"{operation_id}.json").read_text(encoding="utf-8"))

    assert created is True
    assert saved.operation_id == operation_id
    assert raw["phase"] == "authorized"
    assert raw["target"] == {"repository_id": 22, "run_attempt": 2, "run_id": 71, "sha": request.sha}
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


def test_forced_command_replays_submit_without_relaunching_and_reports_status(tmp_path):
    """Catch replay behavior that starts two deployment transactions for one CI run."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    cli = _cli_module()
    state = _state_module()
    verifier = AcceptingVerifier(_verified_run(now))
    launcher = RecordingLauncher()
    handler = cli.ForcedCommandHandler(verifier, state.OperationStore(tmp_path / "operations"), launcher)
    command = "submit 0123456789abcdef0123456789abcdef01234567 71 2 22"

    first = handler.handle(command)
    second = handler.handle(command)
    operation_id = json.loads(first.stdout)["operation_id"]
    status = handler.handle(f"status {operation_id}")

    assert first.exit_code == 0
    assert first.stdout == second.stdout
    assert verifier.calls == 2
    assert launcher.operation_ids == [operation_id]
    assert json.loads(status.stdout)["phase"] == "authorized"


def test_forced_command_rejects_malformed_input_and_redacts_verifier_errors(tmp_path):
    """Catch a forced-command regression that exposes an exception or accepts shell syntax."""
    cli = _cli_module()
    state = _state_module()
    verifier_module = _verifier_module()

    class RejectingVerifier:
        def verify(self, request):
            raise verifier_module.VerificationError("workflow_mismatch")

    handler = cli.ForcedCommandHandler(RejectingVerifier(), state.OperationStore(tmp_path / "operations"), RecordingLauncher())

    malformed = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22; id")
    rejected = handler.handle("submit 0123456789abcdef0123456789abcdef01234567 71 2 22")

    assert malformed.exit_code == 2
    assert json.loads(malformed.stdout) == {"code": "invalid_command", "ok": False}
    assert rejected.exit_code == 3
    assert json.loads(rejected.stdout) == {"code": "workflow_mismatch", "ok": False}
    assert "exception" not in rejected.stdout
