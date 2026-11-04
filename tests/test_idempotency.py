import threading

import pytest

from fts.errors import AlreadyCommitted, IdempotencyConflict
from fts.jobs.clock import FakeClock, SequenceIds
from fts.jobs.control import JobService
from tests.helpers import spec


def test_duplicate_register_returns_the_same_job(jobs):
    first = jobs.register(spec=spec(), idempotency_key="same", requested_by="kr", region="KR")
    claimed = jobs.claim(first.job["job_id"], "kr", "KR", "claim")
    second = jobs.register(spec=spec(), idempotency_key="same", requested_by="kr", region="KR")
    assert second.replayed
    assert second.job["job_id"] == first.job["job_id"]
    assert second.job["state"] == "LEASED"
    assert second.job["version"] == claimed.job["version"]
    assert len(jobs.store.scan("jobs")) == 1


def test_reused_key_with_a_different_body_conflicts(jobs):
    jobs.register(spec=spec(seed=1), idempotency_key="same", requested_by="kr", region="KR")
    with pytest.raises(IdempotencyConflict):
        jobs.register(spec=spec(seed=2), idempotency_key="same", requested_by="kr", region="KR")


def test_duplicate_commit_does_not_increment_commit_count(jobs):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", "claim")
    token = claimed.job["lease_token"]
    attempt_id = claimed.job["attempt_id"]
    jobs.start(job_id, token, "kr")
    jobs.record_results(job_id, token, attempt_id, {"value": "only"}, "record", "kr")
    first = jobs.commit(job_id, attempt_id, "commit-key", "kr")
    second = jobs.commit(job_id, attempt_id, "commit-key", "kr")
    third = jobs.commit(job_id, attempt_id, "commit-key", "kr")
    assert first.replayed is False
    assert second.replayed and third.replayed
    assert first.job["commit_count"] == second.job["commit_count"] == third.job["commit_count"] == 1
    assert [event["op"] for event in third.job["history"]].count("commit") == 1


def test_different_commit_key_is_rejected_after_success(jobs):
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", "claim")
    jobs.start(job_id, claimed.job["lease_token"], "kr")
    jobs.record_results(
        job_id,
        claimed.job["lease_token"],
        claimed.job["attempt_id"],
        {"value": "kept"},
        "record",
        "kr",
    )
    jobs.commit(job_id, claimed.job["attempt_id"], "first-key", "kr")
    with pytest.raises(AlreadyCommitted):
        jobs.commit(job_id, claimed.job["attempt_id"], "second-key", "kr")
    assert jobs.get(job_id)["commit_count"] == 1
    assert jobs.get(job_id)["committed_result"] == {"value": "kept"}


def test_file_backend_remembers_a_commit_across_processes(tmp_path):
    from fts.jobs.store import FileStore

    path = tmp_path / "state.json"
    clock = FakeClock()
    first_service = JobService(FileStore(path), clock, SequenceIds(), lease_ttl_s=30)
    registered = first_service.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = first_service.claim(job_id, "kr", "KR", "claim")
    first_service.start(job_id, claimed.job["lease_token"], "kr")
    first_service.record_results(
        job_id,
        claimed.job["lease_token"],
        claimed.job["attempt_id"],
        {"value": "persisted"},
        "record",
        "kr",
    )
    first_service.commit(job_id, claimed.job["attempt_id"], "commit-key", "kr")

    reopened = JobService(FileStore(path), clock, SequenceIds(), lease_ttl_s=30)
    replayed = reopened.commit(job_id, claimed.job["attempt_id"], "commit-key", "kr")
    assert replayed.replayed
    assert replayed.job["commit_count"] == 1
    assert replayed.job["committed_result"] == {"value": "persisted"}


def test_concurrent_commits_have_a_single_winner(store):
    clock = FakeClock()
    jobs = JobService(store, clock, SequenceIds(), lease_ttl_s=30)
    registered = jobs.register(spec=spec(), idempotency_key="reg", requested_by="kr", region="KR")
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "kr", "KR", "claim")
    token = claimed.job["lease_token"]
    attempt_id = claimed.job["attempt_id"]
    jobs.start(job_id, token, "kr")
    jobs.record_results(job_id, token, attempt_id, {"value": "one"}, "record", "kr")

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt(key: str) -> None:
        barrier.wait()
        try:
            jobs.commit(job_id, attempt_id, key, "kr")
            outcomes.append("ok")
        except AlreadyCommitted:
            outcomes.append("rejected")

    threads = [threading.Thread(target=attempt, args=(key,)) for key in ("key-a", "key-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["ok", "rejected"]
    assert jobs.get(job_id)["commit_count"] == 1
