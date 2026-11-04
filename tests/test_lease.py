import pytest

from fts.errors import LeaseError
from tests.helpers import spec


def test_heartbeat_extends_until_the_lease_expires(jobs, clock):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", "claim")
    token = claimed.job["lease_token"]
    first_expiry = claimed.job["lease_expires_at"]

    clock.advance(9)
    extended = jobs.heartbeat(job_id, token, "kr")
    assert extended["lease_expires_at"] > first_expiry

    clock.advance(10)
    with pytest.raises(LeaseError):
        jobs.heartbeat(job_id, token, "kr")
    assert jobs.get(job_id)["state"] == "QUEUED"
    assert jobs.get(job_id)["lease_token"] is None


def test_wrong_token_cannot_heartbeat(jobs):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    jobs.claim(job_id, "kr", "KR", "claim")
    with pytest.raises(LeaseError):
        jobs.heartbeat(job_id, "someone-elses-token", "kr")


def test_other_owner_claims_after_expiry_and_the_old_token_cannot_start(jobs, clock):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    first = jobs.claim(job_id, "kr-validation", "KR", "claim-kr")
    clock.advance(10)
    expired = jobs.expire_due()
    assert job_id in expired

    second = jobs.claim(job_id, "us-validation", "US", "claim-us")
    assert second.job["owner"] == "us-validation"
    assert second.job["lease_token"] != first.job["lease_token"]
    with pytest.raises(LeaseError):
        jobs.start(job_id, first.job["lease_token"], "kr-validation")
    started = jobs.start(job_id, second.job["lease_token"], "us-validation")
    assert started["state"] == "RUNNING"
    assert started["attempt_id"] == second.job["attempt_id"]
