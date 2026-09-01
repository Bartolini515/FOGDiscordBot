"""Immutable, externally supplied trust configuration for deployment approval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class DeploymentConfig:
    """Trusted GitHub and activation-boundary values, installed outside releases."""

    repository_owner: str
    repository_name: str
    repository_id: int
    head_repository_id: int
    workflow_id: int
    workflow_path: str
    main_branch: str
    minimum_activation_run_id: int
    activation_timestamp: datetime
    max_run_age: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if not self.repository_owner or not self.repository_name or not self.main_branch:
            raise ValueError("invalid_repository_configuration")
        if self.workflow_path != ".github/workflows/ci.yml":
            raise ValueError("invalid_workflow_configuration")
        if any(
            value <= 0
            for value in (
                self.repository_id,
                self.head_repository_id,
                self.workflow_id,
                self.minimum_activation_run_id,
            )
        ):
            raise ValueError("invalid_numeric_configuration")
        if self.activation_timestamp.tzinfo is None or self.max_run_age <= timedelta(0):
            raise ValueError("invalid_time_configuration")
