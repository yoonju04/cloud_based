"""Common submit / status / fetch-results surface for every worker."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import Field

from fts.domain.base import ApiModel
from fts.domain.log import SimulationLog
from fts.domain.package import Verdict
from fts.domain.scenario import ModelCheckpoint, ScenarioParameters


class SubmissionState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class ExecutionRequest(ApiModel):
    scenario_id: str
    dataset_version: str
    parameters: ScenarioParameters
    seed: int
    simulator_version: str
    container_digest: str
    models: list[ModelCheckpoint] = Field(min_length=2, max_length=2)
    kpi_rule_version: str
    parameter_overrides: dict[str, float] = Field(default_factory=dict)


class Submission(ApiModel):
    submission_id: str
    state: SubmissionState
    detail: str


class ExecutionProduct(ApiModel):
    submission_id: str
    logs: list[SimulationLog]


class ExecutionAdapter(Protocol):
    """The control plane talks to CARLA, an external SIL, or replay through this."""

    name: str

    def submit(self, request: ExecutionRequest) -> Submission:
        """Accept a run. Unavailable adapters must not invent a log."""

    def status(self, submission_id: str) -> Submission:
        """Return the latest status for a submission id."""

    def fetch_results(self, submission_id: str) -> ExecutionProduct:
        """Return logs for a succeeded submission."""


def not_evaluated_verdict(detail: str) -> Verdict:
    return Verdict(
        state="Not Evaluated",
        rationale=detail,
        follow_up_tasks=[],
    )
