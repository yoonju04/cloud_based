"""Third-party reproducibility check.

The checker reads a package file, builds the worker request from that file,
and compares KPI fingerprints. It does not open the discovery catalog.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from fts.adapters.replay import ReplayWorker
from fts.canonical import content_hash
from fts.domain.log import SimulationLog
from fts.domain.package import HandoffPackage, verify_content_hash
from fts.errors import PackageIntegrityError
from fts.execute import comparison_dict, request_from_package, run_request
from fts.receive import load_package_json


@dataclass
class ReproReport:
    ok: bool
    package_id: str
    content_hash: str
    fingerprint_match: bool
    variant_matches: list[bool] = field(default_factory=list)
    artifact_notes: list[str] = field(default_factory=list)
    detail: str = ""


def simulate_package(package: HandoffPackage) -> list[SimulationLog]:
    return run_request(ReplayWorker(), request_from_package(package))


def check_package(path: Path, search_roots: list[Path] | None = None) -> ReproReport:
    package = load_package_json(path.read_text(encoding="utf-8"))
    if not verify_content_hash(package):
        raise PackageIntegrityError("content hash mismatch")
    if package.observed_regression is None:
        raise PackageIntegrityError("package has no regression block to reproduce")
    compared = comparison_dict(*simulate_package(package))
    fingerprint_match = compared["kpi_fingerprint"] == package.observed_regression.kpi_fingerprint
    material_match = compared["material"] == package.observed_regression.material
    variant_matches: list[bool] = []
    for variant in package.recorded_variants:
        request = request_from_package(
            package,
            seed=variant.seed,
            overrides=dict(variant.parameter_overrides),
        )
        variant_compared = comparison_dict(*run_request(ReplayWorker(), request))
        variant_matches.append(
            variant_compared["kpi_fingerprint"] == variant.kpi_fingerprint
            and variant_compared["material"] == variant.material
        )
    artifact_notes = _check_artifacts(package, search_roots or [Path.cwd(), *path.parents])
    ok = fingerprint_match and material_match and all(variant_matches)
    detail = "reproduced from the package" if ok else "package claims did not match a fresh run"
    return ReproReport(
        ok=ok,
        package_id=package.package_id,
        content_hash=package.content_hash or "",
        fingerprint_match=fingerprint_match,
        variant_matches=variant_matches,
        artifact_notes=artifact_notes,
        detail=detail,
    )


def _check_artifacts(package: HandoffPackage, search_roots: list[Path]) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    artifacts = list(package.artifacts)
    for variant in package.recorded_variants:
        artifacts.extend(variant.artifacts)
    for artifact in artifacts:
        if artifact.uri in seen:
            continue
        seen.add(artifact.uri)
        if not artifact.uri.startswith("repo://"):
            notes.append(f"skip {artifact.uri}")
            continue
        relative = artifact.uri.removeprefix("repo://")
        matched = False
        for root in search_roots:
            candidate = root / relative
            if not candidate.is_file():
                continue
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            actual = content_hash(payload)
            if actual != artifact.content_hash:
                raise PackageIntegrityError(f"on-disk log hash mismatch for {artifact.uri}")
            notes.append(f"matched {artifact.uri}")
            matched = True
            break
        if not matched:
            notes.append(f"file-not-local {artifact.uri}")
    return notes
