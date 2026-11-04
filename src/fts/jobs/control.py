"""Job state machine, leases, and idempotent commits.

States
------
QUEUED -> LEASED -> RUNNING -> RESULTS_PENDING -> COMMITTED -> HANDED_OFF

LEASED, RUNNING, and RESULTS_PENDING return to QUEUED when the lease
expires or the holder releases it. A retryable failure also returns to
QUEUED. A non-retryable failure ends in FAILED.

The commit transition is the one that must not happen twice. It is a
conditional write on ``commit_count == 0`` plus an idempotency key.
A duplicate delivery of the same key returns the committed job and does
not increment ``commit_count``. A different key, or a stale attempt whose
lease already expired, cannot overwrite the committed result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fts.canonical import content_hash
from fts.errors import AlreadyCommitted, IdempotencyConflict, LeaseError, TransitionError
from fts.jobs.clock import Clock
from fts.jobs.store import Condition, ConditionFailed, DynamoShape

ACTIVE_LEASE_STATES = {"LEASED", "RUNNING", "RESULTS_PENDING"}
TERMINAL_STATES = {"HANDED_OFF", "FAILED"}


@dataclass(frozen=True)
class JobResult:
    job: dict[str, Any]
    replayed: bool


class JobService:
    def __init__(
        self,
        store: DynamoShape,
        clock: Clock,
        ids: Callable[[str], str],
        lease_ttl_s: float = 30.0,
    ) -> None:
        self.store = store
        self.clock = clock
        self.ids = ids
        self.lease_ttl_s = lease_ttl_s

    def get(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_item("jobs", {"job_id": job_id})
        if job is None:
            raise TransitionError(f"unknown job {job_id}")
        return job

    def register(
        self,
        *,
        spec: dict[str, Any],
        idempotency_key: str,
        requested_by: str,
        region: str,
        parent_job_id: str | None = None,
        reproduces_package_hash: str | None = None,
    ) -> JobResult:
        request_hash = content_hash(
            {
                "operation": "register",
                "spec": spec,
                "requested_by": requested_by,
                "region": region,
                "parent_job_id": parent_job_id,
                "reproduces_package_hash": reproduces_package_hash,
            }
        )
        replay = self._begin(idempotency_key, "register", request_hash)
        if replay is not None:
            return JobResult(replay, replayed=True)
        job_id = self.ids("job")
        now = self.clock.now()
        job = {
            "job_id": job_id,
            "state": "QUEUED",
            "owner": None,
            "region": None,
            "requested_by": requested_by,
            "requested_region": region,
            "lease_token": None,
            "lease_expires_at": None,
            "attempt_id": None,
            "attempt_count": 0,
            "abandoned_attempts": [],
            "pending_result": None,
            "pending_idempotency_key": None,
            "committed_result": None,
            "committed_idempotency_key": None,
            "commit_count": 0,
            "version": 1,
            "spec": spec,
            "parent_job_id": parent_job_id,
            "reproduces_package_hash": reproduces_package_hash,
            "logical_key": logical_key(spec),
            "register_idempotency_key": idempotency_key,
            "history": [
                _event(now, None, "QUEUED", "register", requested_by, None),
            ],
        }
        try:
            self.store.put_item("jobs", job, Condition(attribute_not_exists=("job_id",)))
        except ConditionFailed as exc:
            raise TransitionError(f"job id {job_id} already exists") from exc
        self._remember(idempotency_key, "register", request_hash, job_id)
        return JobResult(self.get(job_id), replayed=False)

    def claim(self, job_id: str, owner: str, region: str, idempotency_key: str) -> JobResult:
        request_hash = content_hash(
            {"operation": "claim", "job_id": job_id, "owner": owner, "region": region}
        )
        replay = self._begin(idempotency_key, "claim", request_hash)
        if replay is not None:
            return JobResult(replay, replayed=True)
        self.expire_due()
        job = self.get(job_id)
        if job["state"] != "QUEUED":
            raise TransitionError(f"cannot claim from {job['state']}")
        attempt_id = self.ids("attempt")
        lease_token = self.ids("lease")
        now = self.clock.now()
        updated = self._transition(
            job,
            new_state="LEASED",
            op="claim",
            actor=owner,
            changes={
                "owner": owner,
                "region": region,
                "lease_token": lease_token,
                "lease_expires_at": now + self.lease_ttl_s,
                "attempt_id": attempt_id,
                "attempt_count": job["attempt_count"] + 1,
                "pending_result": None,
                "pending_idempotency_key": None,
            },
        )
        self._remember(idempotency_key, "claim", request_hash, job_id)
        return JobResult(updated, replayed=False)

    def heartbeat(self, job_id: str, lease_token: str, actor: str) -> dict[str, Any]:
        self.expire_due()
        job = self._require_lease(job_id, lease_token)
        now = self.clock.now()
        return self._transition(
            job,
            new_state=job["state"],
            op="heartbeat",
            actor=actor,
            changes={"lease_expires_at": now + self.lease_ttl_s},
            extra_equals=(("lease_token", lease_token),),
            extra_greater=(("lease_expires_at", now),),
        )

    def start(self, job_id: str, lease_token: str, actor: str) -> dict[str, Any]:
        self.expire_due()
        job = self._require_lease(job_id, lease_token)
        if job["state"] == "RUNNING" and job["lease_token"] == lease_token:
            return job
        if job["state"] != "LEASED":
            raise TransitionError(f"cannot start from {job['state']}")
        now = self.clock.now()
        return self._transition(
            job,
            new_state="RUNNING",
            op="start",
            actor=actor,
            changes={},
            extra_equals=(("lease_token", lease_token),),
            extra_greater=(("lease_expires_at", now),),
        )

    def record_results(
        self,
        job_id: str,
        lease_token: str,
        attempt_id: str,
        result: dict[str, Any],
        idempotency_key: str,
        actor: str,
    ) -> JobResult:
        request_hash = content_hash(
            {
                "operation": "record_results",
                "job_id": job_id,
                "attempt_id": attempt_id,
                "result": result,
            }
        )
        replay = self._begin(idempotency_key, "record_results", request_hash)
        if replay is not None:
            return JobResult(replay, replayed=True)
        self.expire_due()
        job = self._require_lease(job_id, lease_token)
        if job["attempt_id"] != attempt_id:
            raise LeaseError("attempt id does not match the live lease")
        if job["state"] != "RUNNING":
            raise TransitionError(f"cannot record results from {job['state']}")
        now = self.clock.now()
        updated = self._transition(
            job,
            new_state="RESULTS_PENDING",
            op="record_results",
            actor=actor,
            changes={
                "pending_result": result,
                "pending_idempotency_key": idempotency_key,
            },
            extra_equals=(("lease_token", lease_token), ("attempt_id", attempt_id)),
            extra_greater=(("lease_expires_at", now),),
        )
        self._remember(idempotency_key, "record_results", request_hash, job_id)
        return JobResult(updated, replayed=False)

    def commit(self, job_id: str, attempt_id: str, idempotency_key: str, actor: str) -> JobResult:
        """Commit the pending result once.

        Same idempotency key: return the existing commit.
        Different key after a commit: ``AlreadyCommitted``.
        Expired attempt: the conditional write fails and nothing is committed.
        """

        request_hash = content_hash(
            {"operation": "commit", "job_id": job_id, "attempt_id": attempt_id}
        )
        replay = self._begin(idempotency_key, "commit", request_hash)
        if replay is not None:
            return JobResult(replay, replayed=True)
        self.expire_due()
        job = self.get(job_id)
        if job["commit_count"] > 0:
            return self._commit_collision(job, idempotency_key, request_hash)
        if job["state"] != "RESULTS_PENDING" or job["attempt_id"] != attempt_id:
            raise TransitionError(
                f"cannot commit from {job['state']} attempt {job['attempt_id']}"
            )
        if job["pending_result"] is None:
            raise TransitionError("no pending result to commit")
        now = self.clock.now()
        try:
            updated = self._transition(
                job,
                new_state="COMMITTED",
                op="commit",
                actor=actor,
                changes={
                    "committed_result": job["pending_result"],
                    "committed_idempotency_key": idempotency_key,
                    "commit_count": 1,
                    "lease_token": None,
                    "lease_expires_at": None,
                    "owner": job["owner"],
                },
                extra_equals=(
                    ("attempt_id", attempt_id),
                    ("commit_count", 0),
                ),
                extra_greater=(("lease_expires_at", now),),
            )
        except TransitionError:
            current = self.get(job_id)
            if current["commit_count"] > 0:
                return self._commit_collision(current, idempotency_key, request_hash)
            raise
        self._remember(idempotency_key, "commit", request_hash, job_id)
        return JobResult(updated, replayed=False)

    def fail(
        self,
        job_id: str,
        lease_token: str,
        attempt_id: str,
        reason: str,
        *,
        retryable: bool,
        actor: str,
    ) -> dict[str, Any]:
        self.expire_due()
        job = self._require_lease(job_id, lease_token)
        if job["attempt_id"] != attempt_id:
            raise LeaseError("attempt id does not match the live lease")
        if job["state"] not in {"LEASED", "RUNNING", "RESULTS_PENDING"}:
            raise TransitionError(f"cannot fail from {job['state']}")
        if retryable:
            abandoned = list(job["abandoned_attempts"]) + [attempt_id]
            return self._transition(
                job,
                new_state="QUEUED",
                op="fail_retryable",
                actor=actor,
                changes={
                    "owner": None,
                    "region": None,
                    "lease_token": None,
                    "lease_expires_at": None,
                    "attempt_id": None,
                    "pending_result": None,
                    "pending_idempotency_key": None,
                    "abandoned_attempts": abandoned,
                    "last_error": reason,
                },
            )
        return self._transition(
            job,
            new_state="FAILED",
            op="fail",
            actor=actor,
            changes={
                "lease_token": None,
                "lease_expires_at": None,
                "last_error": reason,
            },
        )

    def release(self, job_id: str, lease_token: str, actor: str) -> dict[str, Any]:
        self.expire_due()
        job = self._require_lease(job_id, lease_token)
        if job["state"] not in ACTIVE_LEASE_STATES:
            raise TransitionError(f"cannot release from {job['state']}")
        abandoned = list(job["abandoned_attempts"])
        if job["attempt_id"] is not None:
            abandoned.append(job["attempt_id"])
        return self._transition(
            job,
            new_state="QUEUED",
            op="release",
            actor=actor,
            changes={
                "owner": None,
                "region": None,
                "lease_token": None,
                "lease_expires_at": None,
                "attempt_id": None,
                "pending_result": None,
                "pending_idempotency_key": None,
                "abandoned_attempts": abandoned,
            },
        )

    def handoff(self, job_id: str, to_owner: str, to_region: str, idempotency_key: str, actor: str) -> JobResult:
        request_hash = content_hash(
            {
                "operation": "handoff",
                "job_id": job_id,
                "to_owner": to_owner,
                "to_region": to_region,
            }
        )
        replay = self._begin(idempotency_key, "handoff", request_hash)
        if replay is not None:
            return JobResult(replay, replayed=True)
        job = self.get(job_id)
        if job["state"] != "COMMITTED":
            raise TransitionError(f"cannot hand off from {job['state']}")
        updated = self._transition(
            job,
            new_state="HANDED_OFF",
            op="handoff",
            actor=actor,
            changes={
                "owner": to_owner,
                "region": to_region,
                "next_owner": to_owner,
            },
        )
        self._remember(idempotency_key, "handoff", request_hash, job_id)
        return JobResult(updated, replayed=False)

    def expire_due(self) -> list[str]:
        now = self.clock.now()
        expired: list[str] = []
        for job in self.store.scan("jobs"):
            if job["state"] not in ACTIVE_LEASE_STATES:
                continue
            lease_expires_at = job.get("lease_expires_at")
            if lease_expires_at is None or float(lease_expires_at) > now:
                continue
            try:
                self._expire(job)
            except TransitionError:
                continue
            expired.append(job["job_id"])
        return expired

    def _expire(self, job: dict[str, Any]) -> dict[str, Any]:
        abandoned = list(job["abandoned_attempts"])
        if job.get("attempt_id"):
            abandoned.append(job["attempt_id"])
        return self._transition(
            job,
            new_state="QUEUED",
            op="lease_expired",
            actor="control-plane",
            changes={
                "owner": None,
                "region": None,
                "lease_token": None,
                "lease_expires_at": None,
                "attempt_id": None,
                "pending_result": None,
                "pending_idempotency_key": None,
                "abandoned_attempts": abandoned,
            },
        )

    def _require_lease(self, job_id: str, lease_token: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["state"] not in ACTIVE_LEASE_STATES or job.get("lease_token") != lease_token:
            raise LeaseError("lease token does not match a live lease, or the lease has expired")
        if job.get("lease_expires_at") is None or float(job["lease_expires_at"]) <= self.clock.now():
            raise LeaseError("lease expired")
        return job

    def _transition(
        self,
        job: dict[str, Any],
        *,
        new_state: str,
        op: str,
        actor: str,
        changes: dict[str, Any],
        extra_equals: tuple[tuple[str, Any], ...] = (),
        extra_greater: tuple[tuple[str, float], ...] = (),
    ) -> dict[str, Any]:
        now = self.clock.now()
        attempt_id = changes.get("attempt_id", job.get("attempt_id"))
        merged = {
            "state": new_state,
            "version": job["version"] + 1,
            "history": list(job["history"])
            + [_event(now, job["state"], new_state, op, actor, attempt_id)],
        }
        merged.update(changes)
        condition = Condition(
            equals=(("version", job["version"]), ("state", job["state"]), *extra_equals),
            greater_than=extra_greater,
        )
        try:
            return self.store.update_item("jobs", {"job_id": job["job_id"]}, merged, condition)
        except ConditionFailed as exc:
            raise TransitionError(f"{op} lost a conditional write on {job['job_id']}") from exc

    def _begin(self, key: str, operation: str, request_hash: str) -> dict[str, Any] | None:
        current = self.store.get_item("idempotency", {"idempotency_key": key})
        if current is None:
            return None
        if current["operation"] != operation or current["request_hash"] != request_hash:
            raise IdempotencyConflict(f"idempotency key {key} was already used for a different request")
        return self.get(current["job_id"])

    def _remember(self, key: str, operation: str, request_hash: str, job_id: str) -> None:
        item = {
            "idempotency_key": key,
            "operation": operation,
            "request_hash": request_hash,
            "job_id": job_id,
        }
        try:
            self.store.put_item(
                "idempotency",
                item,
                Condition(attribute_not_exists=("idempotency_key",)),
            )
        except ConditionFailed as exc:
            current = exc.item
            if (
                current
                and current.get("operation") == operation
                and current.get("request_hash") == request_hash
                and current.get("job_id") == job_id
            ):
                return
            raise IdempotencyConflict(f"idempotency key {key} conflicted during write") from exc

    def _commit_collision(self, job: dict[str, Any], idempotency_key: str, request_hash: str) -> JobResult:
        if job.get("committed_idempotency_key") == idempotency_key:
            self._remember(idempotency_key, "commit", request_hash, job["job_id"])
            return JobResult(job, replayed=True)
        raise AlreadyCommitted(
            f"job {job['job_id']} already committed under {job.get('committed_idempotency_key')}"
        )


def logical_key(spec: dict[str, Any]) -> str:
    """Identity of a run. Informational: it does not collapse two jobs into one."""

    models = spec.get("models", [])
    body = {
        "scenario_id": spec.get("scenario_id"),
        "dataset_version": spec.get("dataset_version"),
        "parameters": spec.get("parameters"),
        "seed": spec.get("seed"),
        "simulator_version": spec.get("simulator_version"),
        "container_digest": spec.get("container_digest"),
        "models": [
            {"role": model.get("role"), "checkpoint_hash": model.get("checkpoint_hash")}
            for model in models
        ],
        "kpi_rule_version": spec.get("kpi_rule_version"),
        "parameter_overrides": spec.get("parameter_overrides") or {},
    }
    return content_hash(body)


def _event(at: float, previous: str | None, new_state: str, op: str, actor: str, attempt_id: str | None) -> dict:
    return {
        "at": at,
        "from": previous,
        "to": new_state,
        "op": op,
        "actor": actor,
        "attempt_id": attempt_id,
    }
