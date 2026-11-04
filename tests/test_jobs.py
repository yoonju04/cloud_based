import pytest

from fts.errors import AlreadyCommitted, TransitionError
from fts.jobs.control import JobService
from fts.jobs.store import Condition, ConditionFailed
from tests.helpers import spec


def _to_pending(jobs: JobService, key: str = "reg"):
    registered = jobs.register(spec=spec(), idempotency_key=key, requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", f"{key}-claim")
    token = claimed.job["lease_token"]
    attempt_id = claimed.job["attempt_id"]
    jobs.start(job_id, token, "kr")
    jobs.record_results(job_id, token, attempt_id, {"value": "r1"}, f"{key}-record", "kr")
    return job_id, attempt_id


def test_happy_path_reaches_handed_off(jobs):
    job_id, attempt_id = _to_pending(jobs)
    committed = jobs.commit(job_id, attempt_id, "commit", "kr")
    assert committed.job["state"] == "COMMITTED"
    assert committed.job["commit_count"] == 1
    handed = jobs.handoff(job_id, "us", "US", "handoff", "kr")
    assert handed.job["state"] == "HANDED_OFF"
    assert handed.job["owner"] == "us"
    assert [event["to"] for event in handed.job["history"]] == [
        "QUEUED",
        "LEASED",
        "RUNNING",
        "RESULTS_PENDING",
        "COMMITTED",
        "HANDED_OFF",
    ]


@pytest.mark.parametrize(
    ("call", "message"),
    [
        ("commit", "cannot commit"),
        ("start", "live lease"),
        ("handoff", "cannot hand off"),
    ],
)
def test_illegal_transitions(jobs, call, message):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    with pytest.raises((TransitionError, Exception), match=message):
        if call == "commit":
            jobs.commit(job_id, "missing", "commit", "kr")
        elif call == "start":
            jobs.start(job_id, "missing-token", "kr")
        else:
            jobs.handoff(job_id, "us", "US", "handoff", "kr")


def test_stale_attempt_cannot_overwrite_a_commit(jobs, clock):
    job_id, first_attempt = _to_pending(jobs, "first")
    clock.advance(11)
    with pytest.raises(TransitionError):
        jobs.commit(job_id, first_attempt, "stale-commit", "kr")
    assert jobs.get(job_id)["commit_count"] == 0
    assert jobs.get(job_id)["state"] == "QUEUED"

    claimed = jobs.claim(job_id, "us", "US", "second-claim")
    token = claimed.job["lease_token"]
    second_attempt = claimed.job["attempt_id"]
    jobs.start(job_id, token, "us")
    jobs.record_results(job_id, token, second_attempt, {"value": "r2"}, "second-record", "us")
    committed = jobs.commit(job_id, second_attempt, "second-commit", "us")
    assert committed.job["committed_result"] == {"value": "r2"}
    with pytest.raises(AlreadyCommitted):
        jobs.commit(job_id, first_attempt, "stale-commit", "kr")
    assert jobs.get(job_id)["commit_count"] == 1
    assert jobs.get(job_id)["committed_result"] == {"value": "r2"}


def test_conditional_version_write_rejects_a_stale_update(store):
    store.put_item("jobs", {"job_id": "job-1", "version": 1, "state": "QUEUED"}, Condition(attribute_not_exists=("job_id",)))
    store.update_item(
        "jobs",
        {"job_id": "job-1"},
        {"version": 2, "state": "LEASED"},
        Condition(equals=(("version", 1), ("state", "QUEUED"))),
    )
    with pytest.raises(ConditionFailed):
        store.update_item(
            "jobs",
            {"job_id": "job-1"},
            {"version": 2, "state": "RUNNING"},
            Condition(equals=(("version", 1),)),
        )
    assert store.get_item("jobs", {"job_id": "job-1"})["state"] == "LEASED"


def test_retryable_failure_returns_to_queued_without_committing(jobs):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", "claim")
    failed = jobs.fail(
        job_id,
        claimed.job["lease_token"],
        claimed.job["attempt_id"],
        "worker exited",
        retryable=True,
        actor="kr",
    )
    assert failed["state"] == "QUEUED"
    assert failed["commit_count"] == 0
    assert claimed.job["attempt_id"] in failed["abandoned_attempts"]


def test_release_drops_the_lease(jobs):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", "claim")
    released = jobs.release(job_id, claimed.job["lease_token"], "kr")
    assert released["state"] == "QUEUED"
    assert released["lease_token"] is None
