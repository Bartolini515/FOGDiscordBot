"""Public GitHub API verification for a requested deployment run."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Protocol, cast
from urllib.request import Request, urlopen

from .config import DeploymentConfig
from .protocol import SHA_PATTERN, SubmitRequest


PUBLIC_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class HttpTransport(Protocol):
    """Minimal injected public-API transport with no credential input."""

    def __call__(self, url: str, timeout: float) -> Mapping[str, Any]: ...


class VerificationError(ValueError):
    """A controlled diagnostic code for an untrusted deployment request."""

    def __init__(self, diagnostic_code: str) -> None:
        super().__init__(diagnostic_code)
        self.diagnostic_code = diagnostic_code


@dataclass(frozen=True, slots=True)
class VerifiedRun:
    """The deployment target that has passed all independently repeatable checks."""

    repository_id: int
    run_id: int
    run_attempt: int
    sha: str
    verified_at: datetime


def public_github_get(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Mapping[str, Any]:
    """Fetch JSON only from the public GitHub API with a bounded timeout."""
    if not url.startswith(f"{PUBLIC_API_BASE}/"):
        raise ValueError("invalid_public_api_url")
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "fogbot-deploy"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - host is constrained above
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("invalid_public_api_response")
    return cast(Mapping[str, Any], payload)


class GitHubRunVerifier:
    """Validate one exact workflow run against the trusted current main ref."""

    def __init__(
        self,
        config: DeploymentConfig,
        transport: HttpTransport = public_github_get,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._config = config
        self._transport = transport
        self._now = now
        self._timeout = timeout

    def verify(self, request: SubmitRequest) -> VerifiedRun:
        """Independently revalidate a submitted target; safe to call before stopping."""
        if request.repository_id != self._config.repository_id:
            raise VerificationError("repository_mismatch")
        if not SHA_PATTERN.fullmatch(request.sha):
            raise VerificationError("head_sha_mismatch")
        if request.run_id < self._config.minimum_activation_run_id:
            raise VerificationError("minimum_run_id")

        run = self._get_run(request.run_id)
        self._require_equal(run.get("id"), request.run_id, "run_id_mismatch")
        self._require_equal(run.get("run_attempt"), request.run_attempt, "run_attempt_mismatch")
        self._require_equal(run.get("head_sha"), request.sha, "head_sha_mismatch")
        self._require_equal(run.get("event"), "push", "event_mismatch")
        self._require_equal(run.get("head_branch"), self._config.main_branch, "branch_mismatch")
        self._require_equal(run.get("status"), "completed", "status_mismatch")
        self._require_equal(run.get("conclusion"), "success", "conclusion_mismatch")
        self._require_equal(self._nested_id(run, "repository"), self._config.repository_id, "repository_mismatch")
        self._require_equal(
            self._nested_id(run, "head_repository"), self._config.head_repository_id, "head_repository_mismatch"
        )
        self._require_equal(run.get("workflow_id"), self._config.workflow_id, "workflow_mismatch")
        self._require_equal(run.get("path"), self._config.workflow_path, "workflow_mismatch")
        created_at = self._parse_timestamp(run.get("created_at"))
        now = self._now()
        if now.tzinfo is None:
            raise VerificationError("clock_invalid")
        if created_at < self._config.activation_timestamp:
            raise VerificationError("activation_timestamp")
        if now.astimezone(UTC) - created_at > self._config.max_run_age:
            raise VerificationError("stale_run")

        main_sha = self._get_current_main_sha()
        self._require_equal(main_sha, request.sha, "current_main_mismatch")
        return VerifiedRun(
            repository_id=request.repository_id,
            run_id=request.run_id,
            run_attempt=request.run_attempt,
            sha=request.sha,
            verified_at=now.astimezone(UTC),
        )

    def _get_run(self, run_id: int) -> Mapping[str, Any]:
        return self._transport(
            f"{PUBLIC_API_BASE}/repos/{self._config.repository_owner}/{self._config.repository_name}/actions/runs/{run_id}",
            self._timeout,
        )

    def _get_current_main_sha(self) -> Any:
        response = self._transport(
            f"{PUBLIC_API_BASE}/repos/{self._config.repository_owner}/{self._config.repository_name}/git/ref/heads/{self._config.main_branch}",
            self._timeout,
        )
        reference = response.get("object")
        if not isinstance(reference, Mapping):
            raise VerificationError("current_main_mismatch")
        return reference.get("sha")

    @staticmethod
    def _nested_id(payload: Mapping[str, Any], field: str) -> Any:
        value = payload.get(field)
        return value.get("id") if isinstance(value, Mapping) else None

    @staticmethod
    def _require_equal(actual: Any, expected: Any, diagnostic_code: str) -> None:
        if actual != expected:
            raise VerificationError(diagnostic_code)

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if not isinstance(value, str):
            raise VerificationError("timestamp_invalid")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise VerificationError("timestamp_invalid") from error
        if parsed.tzinfo is None:
            raise VerificationError("timestamp_invalid")
        return parsed.astimezone(UTC)
