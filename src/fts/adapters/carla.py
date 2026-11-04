"""CARLA worker stub.

The proposal names CARLA as the PoC simulator. This class keeps the adapter
interface and refuses to invent a trajectory. Nothing is launched.
"""

from __future__ import annotations

from fts.adapters.base import ExecutionProduct, ExecutionRequest, Submission, SubmissionState
from fts.errors import AdapterUnavailable

_DETAIL = (
    "CARLA worker is a proposal stub. No CARLA process is launched and no "
    "log is synthesized. Use the replay adapter for the local walkthrough."
)


class CarlaWorker:
    name = "carla"

    def submit(self, request: ExecutionRequest) -> Submission:
        del request
        return Submission(
            submission_id="carla-unavailable",
            state=SubmissionState.UNAVAILABLE,
            detail=_DETAIL,
        )

    def status(self, submission_id: str) -> Submission:
        return Submission(
            submission_id=submission_id,
            state=SubmissionState.UNAVAILABLE,
            detail=_DETAIL,
        )

    def fetch_results(self, submission_id: str) -> ExecutionProduct:
        raise AdapterUnavailable(_DETAIL)
