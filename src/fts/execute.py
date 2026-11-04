"""Run an adapter and turn logs into package pieces.

Nothing in this module reads the discovery catalog. Callers pass a request
that already came from either the catalog (first run) or a package (everyone else).
"""

from __future__ import annotations

import json
from pathlib import Path

from fts.adapters.base import ExecutionAdapter, ExecutionRequest, SubmissionState
from fts.canonical import content_hash, normalize
from fts.domain.log import SimulationLog
from fts.domain.package import ArtifactRef
from fts.domain.scenario import apply_overrides, scenario_parameter_hash
from fts.errors import AdapterUnavailable
from fts.kpi.evaluator import compare_logs


def request_from_package(package, *, seed: int | None = None, overrides: dict[str, float] | None = None) -> ExecutionRequest:
    """Build a worker request from a handoff package and nothing else."""

    return ExecutionRequest(
        scenario_id=package.scenario.scenario_id,
        dataset_version=package.scenario.dataset_version,
        parameters=package.scenario.parameters,
        seed=package.environment.seed if seed is None else seed,
        simulator_version=package.environment.simulator_version,
        container_digest=package.environment.container_digest,
        models=list(package.models),
        kpi_rule_version=package.safety.kpi_rule_version,
        parameter_overrides=dict(overrides or {}),
    )


def run_request(adapter: ExecutionAdapter, request: ExecutionRequest) -> list[SimulationLog]:
    submission = adapter.submit(request)
    if submission.state != SubmissionState.SUCCEEDED:
        raise AdapterUnavailable(submission.detail)
    current = adapter.status(submission.submission_id)
    if current.state != SubmissionState.SUCCEEDED:
        raise AdapterUnavailable(current.detail)
    product = adapter.fetch_results(submission.submission_id)
    by_role = {log.model_role: log for log in product.logs}
    if set(by_role) != {"A", "B"}:
        raise AdapterUnavailable("worker did not return both model A and model B logs")
    return [by_role["A"], by_role["B"]]


def comparison_dict(log_a: SimulationLog, log_b: SimulationLog) -> dict:
    compared = compare_logs(log_a, log_b)
    return {
        "material": compared["material"],
        "reasons": [reason.value for reason in compared["reasons"]],
        "kpi_rule_version": compared["kpi_rule_version"],
        "model_a": compared["model_a"].model_dump(mode="json"),
        "model_b": compared["model_b"].model_dump(mode="json"),
        "kpi_fingerprint": compared["kpi_fingerprint"],
    }


def write_log(path: Path, log: SimulationLog, *, uri: str) -> ArtifactRef:
    payload = log.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalize(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return ArtifactRef(
        kind="log",
        uri=uri,
        content_hash=content_hash(payload),
        media_type="application/json",
        model_role=log.model_role,
    )


def effective_parameter_hash(package, overrides: dict[str, float]) -> str:
    return scenario_parameter_hash(apply_overrides(package.scenario.parameters, overrides))
