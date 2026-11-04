"""What the receiving region is allowed to see: the package JSON.

This module must not import the discovery scenario catalog. A third party
with the JSON and this code should be able to rerun the failure.
"""

from __future__ import annotations

from pathlib import Path

from fts.adapters.replay import ReplayWorker
from fts.domain.package import (
    HandoffPackage,
    Ownership,
    RecordedVariant,
    ReproductionCheck,
    seal,
    verify_content_hash,
)
from fts.errors import PackageIntegrityError
from fts.execute import comparison_dict, effective_parameter_hash, request_from_package, run_request, write_log
from fts.jobs.control import JobService
from fts.verdict import verdict_after_remote


def load_package_json(package_json: str) -> HandoffPackage:
    package = HandoffPackage.model_validate_json(package_json)
    if not verify_content_hash(package):
        raise PackageIntegrityError("content hash does not match the package body")
    return package


def us_continue(
    package_json: str,
    *,
    evidence_dir: Path,
    uri_prefix: str,
    jobs: JobService,
) -> HandoffPackage:
    """Continue the handoff. ``package_json`` is the failure description."""

    incoming = load_package_json(package_json)
    if incoming.verdict.state != "Inconclusive":
        raise PackageIntegrityError("this walkthrough expects an open Inconclusive package from KR")
    worker = ReplayWorker()
    reproduction = _reproduction_job(
        incoming,
        evidence_dir=evidence_dir,
        uri_prefix=uri_prefix,
        jobs=jobs,
        worker=worker,
    )
    variant = _variant_job(
        incoming,
        evidence_dir=evidence_dir,
        uri_prefix=uri_prefix,
        jobs=jobs,
        worker=worker,
    )
    if not reproduction["matched"]:
        verdict = verdict_after_remote(reproduction_match=False, variant_material=None)
    else:
        verdict = verdict_after_remote(
            reproduction_match=True,
            variant_material=variant["material"],
        )
    repro_handed = jobs.handoff(
        reproduction["job_id"],
        "kr-validation",
        "KR",
        "us-repro-handoff",
        "us-validation",
    )
    variant_handed = jobs.handoff(
        variant["job_id"],
        "kr-validation",
        "KR",
        "us-variant-handoff",
        "us-validation",
    )
    del repro_handed
    package = HandoffPackage(
        schema_version="fts.handoff.v1",
        package_id="pkg-us-rainy-night-return",
        revision=incoming.revision + 1,
        parent_package_id=incoming.package_id,
        parent_content_hash=incoming.content_hash,
        created_at="2026-11-02T15:00:00Z",
        created_by="us-validation",
        region="US",
        claims=incoming.claims,
        models=list(incoming.models),
        scenario=incoming.scenario,
        environment=incoming.environment,
        safety=incoming.safety,
        observed_regression=incoming.observed_regression,
        artifacts=list(incoming.artifacts) + reproduction["artifacts"] + variant["artifacts"],
        root_cause=incoming.root_cause,
        recommended_next_tests=list(incoming.recommended_next_tests),
        recorded_variants=[variant["record"]],
        reproduction=ReproductionCheck(
            matched=reproduction["matched"],
            kpi_fingerprint=reproduction["kpi_fingerprint"],
            job_id=reproduction["job_id"],
            attempt_id=reproduction["attempt_id"],
        ),
        ownership=_ownership(
            variant_handed.job,
            idempotency_key="us-variant-commit",
            related_job_ids=[reproduction["job_id"]],
        ),
        verdict=verdict,
        content_hash=None,
    )
    return seal(package)


def _reproduction_job(incoming, *, evidence_dir: Path, uri_prefix: str, jobs: JobService, worker: ReplayWorker) -> dict:
    request = request_from_package(incoming)
    registered = jobs.register(
        spec=request.model_dump(mode="json"),
        idempotency_key="us-repro-register",
        requested_by="us-validation",
        region="US",
        parent_job_id=incoming.ownership.job_id,
        reproduces_package_hash=incoming.content_hash,
    )
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "us-validation", "US", "us-repro-claim")
    token = claimed.job["lease_token"]
    attempt_id = claimed.job["attempt_id"]
    jobs.heartbeat(job_id, token, "us-validation")
    jobs.start(job_id, token, "us-validation")
    logs = run_request(worker, request)
    artifacts = [
        write_log(evidence_dir / f"us_repro_model_{log.model_role.lower()}.json", log, uri=f"{uri_prefix}/logs/us_repro_model_{log.model_role.lower()}.json")
        for log in logs
    ]
    compared = comparison_dict(logs[0], logs[1])
    matched = compared["kpi_fingerprint"] == incoming.observed_regression.kpi_fingerprint
    body = {
        "kind": "reproduction",
        "matched": matched,
        "kpi_fingerprint": compared["kpi_fingerprint"],
        "model_a": compared["model_a"],
        "model_b": compared["model_b"],
    }
    jobs.record_results(job_id, token, attempt_id, body, "us-repro-record", "us-validation")
    committed = jobs.commit(job_id, attempt_id, "us-repro-commit", "us-validation")
    replayed = jobs.commit(job_id, attempt_id, "us-repro-commit", "us-validation")
    if not replayed.replayed or replayed.job["commit_count"] != 1 or committed.job["commit_count"] != 1:
        raise PackageIntegrityError("reproduction commit was not idempotent")
    return {
        "matched": matched,
        "kpi_fingerprint": compared["kpi_fingerprint"],
        "job_id": job_id,
        "attempt_id": attempt_id,
        "artifacts": artifacts,
    }


def _variant_job(incoming, *, evidence_dir: Path, uri_prefix: str, jobs: JobService, worker: ReplayWorker) -> dict:
    test = next(item for item in incoming.recommended_next_tests if item.test_id == "variant-pedestrian-speed-1.6")
    request = request_from_package(incoming, seed=test.seed, overrides=dict(test.parameter_overrides))
    registered = jobs.register(
        spec=request.model_dump(mode="json"),
        idempotency_key="us-variant-register",
        requested_by="us-validation",
        region="US",
        parent_job_id=incoming.ownership.job_id,
        reproduces_package_hash=incoming.content_hash,
    )
    job_id = registered.job["job_id"]
    claimed = jobs.claim(job_id, "us-validation", "US", "us-variant-claim")
    token = claimed.job["lease_token"]
    attempt_id = claimed.job["attempt_id"]
    jobs.heartbeat(job_id, token, "us-validation")
    jobs.start(job_id, token, "us-validation")
    logs = run_request(worker, request)
    artifacts = [
        write_log(
            evidence_dir / f"us_variant_model_{log.model_role.lower()}.json",
            log,
            uri=f"{uri_prefix}/logs/us_variant_model_{log.model_role.lower()}.json",
        )
        for log in logs
    ]
    compared = comparison_dict(logs[0], logs[1])
    parameter_hash = effective_parameter_hash(incoming, dict(test.parameter_overrides))
    record = RecordedVariant(
        test_id=test.test_id,
        seed=test.seed,
        parameter_overrides=dict(test.parameter_overrides),
        parameter_hash=parameter_hash,
        material=compared["material"],
        reasons=compared["reasons"],
        kpi_rule_version=compared["kpi_rule_version"],
        model_a=compared["model_a"],
        model_b=compared["model_b"],
        kpi_fingerprint=compared["kpi_fingerprint"],
        job_id=job_id,
        attempt_id=attempt_id,
        artifacts=artifacts,
    )
    jobs.record_results(
        job_id,
        token,
        attempt_id,
        record.model_dump(mode="json"),
        "us-variant-record",
        "us-validation",
    )
    committed = jobs.commit(job_id, attempt_id, "us-variant-commit", "us-validation")
    replayed = jobs.commit(job_id, attempt_id, "us-variant-commit", "us-validation")
    if not replayed.replayed or committed.job["commit_count"] != 1:
        raise PackageIntegrityError("variant commit was not idempotent")
    return {
        "material": compared["material"],
        "job_id": job_id,
        "record": record,
        "artifacts": artifacts,
    }


def _ownership(job: dict, *, idempotency_key: str, related_job_ids: list[str]) -> Ownership:
    return Ownership(
        owner=job["owner"],
        region=job["region"],
        job_id=job["job_id"],
        attempt_id=job["attempt_id"],
        state=job["state"],
        lease_token=job["lease_token"],
        lease_expires_at=None,
        idempotency_key=idempotency_key,
        next_owner=job.get("next_owner"),
        related_job_ids=related_job_ids,
    )

