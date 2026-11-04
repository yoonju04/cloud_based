"""External SIL adapter stub.

dSPACE or another existing SIL stack would sit behind this interface after
API and license access are confirmed. Those are unconfirmed, so the stub
does not pretend to call anything.
"""

from __future__ import annotations

from fts.adapters.base import ExecutionProduct, ExecutionRequest, Submission, SubmissionState
from fts.errors import AdapterUnavailable

_DETAIL = (
    "External SIL adapter is a proposal stub. Vendor API, license, and "
    "42dot's actual SIL supplier are unconfirmed. No remote call is made."
)


class ExternalSilAdapter:
    name = "external-sil"

    def submit(self, request: ExecutionRequest) -> Submission:
        del request
        return Submission(
            submission_id="external-sil-unavailable",
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
