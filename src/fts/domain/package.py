"""Validation Handoff Package, schema version fts.handoff.v1.

The sealed JSON file is the only explanation the next team is supposed to need.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from fts.canonical import content_hash
from fts.domain.base import ApiModel
from fts.domain.kpi import KpiReport, ObservedRegression, ReasonCode, fingerprint_reports, reasons_for
from fts.domain.scenario import (
    ModelCheckpoint,
    ScenarioParameters,
    apply_overrides,
    scenario_parameter_hash,
)
from fts.kpi.rules import (
    COLLISION_DISTANCE_M,
    MATERIAL_DISTANCE_DROP_M,
    MIN_SAFE_DISTANCE_M,
    PROFILE_ID,
    RULE_VERSION,
)

SCHEMA_VERSION = "fts.handoff.v1"
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA256 = r"^[a-f0-9]{64}$"
_DIGEST = r"^sha256:[a-f0-9]{64}$"

DISCLAIMER = (
    "Hypothetical course scenario. Not a real 42dot incident, log, model, "
    "or measured performance result. Unconfirmed items remain unconfirmed."
)


class Claims(ApiModel):
    hypothetical_scenario: Literal[True]
    real_42dot_data: Literal[False]
    measured_performance_claim: Literal[False]
    note: str


class ExecutionEnvironment(ApiModel):
    seed: int
    simulator_version: str
    container_digest: str = Field(pattern=_DIGEST)


class SafetyProfile(ApiModel):
    profile_id: Literal["safety-profile-hypothetical-urban-v1"]
    kpi_rule_version: Literal["kpi-rules-2026.11-draft"]
    collision_distance_m: float
    min_safe_distance_m: float
    material_distance_drop_m: float

    @model_validator(mode="after")
    def _echoes_the_implemented_rules(self) -> SafetyProfile:
        expected = {
            "profile_id": PROFILE_ID,
            "kpi_rule_version": RULE_VERSION,
            "collision_distance_m": COLLISION_DISTANCE_M,
            "min_safe_distance_m": MIN_SAFE_DISTANCE_M,
            "material_distance_drop_m": MATERIAL_DISTANCE_DROP_M,
        }
        if self.model_dump(mode="json") != expected:
            raise ValueError("safety profile does not match the stated KPI rule version")
        return self


def safety_profile() -> SafetyProfile:
    return SafetyProfile(
        profile_id=PROFILE_ID,
        kpi_rule_version=RULE_VERSION,
        collision_distance_m=COLLISION_DISTANCE_M,
        min_safe_distance_m=MIN_SAFE_DISTANCE_M,
        material_distance_drop_m=MATERIAL_DISTANCE_DROP_M,
    )


class ScenarioRef(ApiModel):
    scenario_id: str
    dataset_version: str
    summary_ko: str
    summary_en: str
    hypothetical: Literal[True]
    parameters: ScenarioParameters
    parameter_hash: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def _hash_matches_parameters(self) -> ScenarioRef:
        if self.parameter_hash != scenario_parameter_hash(self.parameters):
            raise ValueError("scenario parameter hash mismatch")
        return self


class ArtifactRef(ApiModel):
    kind: Literal["log"]
    uri: str
    content_hash: str = Field(pattern=_SHA256)
    media_type: Literal["application/json"] = "application/json"
    model_role: Literal["A", "B"]


class RootCauseHypothesis(ApiModel):
    statement: str
    confidence: float = Field(ge=0, le=1)
    confidence_is_calibrated: Literal[False]
    unconfirmed: list[str] = Field(min_length=1)


class RecommendedTest(ApiModel):
    test_id: str
    purpose_ko: str
    purpose_en: str
    seed: int
    parameter_overrides: dict[str, float]
    executable_from_package_alone: Literal[True] = True


class FollowUpTask(ApiModel):
    task_id: str
    summary: str
    kind: Literal["reproduce", "variant", "review"]
    recommended_test_id: str | None = None


class Verdict(ApiModel):
    """One of the four end states from the proposal.

    ``Inconclusive`` is rejected unless ``follow_up_tasks`` is non-empty.
    ``Confirmed`` means the regression reproduced under the pre-declared
    rules. It does not mean the root-cause hypothesis was proven.
    """

    state: Literal[
        "Confirmed",
        "No Material Regression",
        "Inconclusive",
        "Not Evaluated",
    ]
    rationale: str = Field(min_length=1)
    follow_up_tasks: list[FollowUpTask] = Field(default_factory=list)

    @model_validator(mode="after")
    def _inconclusive_keeps_work(self) -> Verdict:
        if self.state == "Inconclusive" and len(self.follow_up_tasks) < 1:
            raise ValueError("Inconclusive verdicts must carry at least one follow-up task")
        return self


class Ownership(ApiModel):
    owner: str
    region: Literal["KR", "US"]
    job_id: str
    attempt_id: str
    state: str
    lease_token: str | None = None
    lease_expires_at: str | None = None
    idempotency_key: str
    next_owner: str | None = None
    related_job_ids: list[str] = Field(default_factory=list)


class ReproductionCheck(ApiModel):
    matched: bool
    kpi_fingerprint: str = Field(pattern=_SHA256)
    job_id: str
    attempt_id: str


class RecordedVariant(ApiModel):
    test_id: str
    seed: int
    parameter_overrides: dict[str, float]
    parameter_hash: str = Field(pattern=_SHA256)
    material: bool
    reasons: list[ReasonCode]
    kpi_rule_version: str
    model_a: KpiReport
    model_b: KpiReport
    kpi_fingerprint: str = Field(pattern=_SHA256)
    job_id: str
    attempt_id: str
    artifacts: list[ArtifactRef]

    @model_validator(mode="after")
    def _numbers_match_the_fingerprint(self) -> RecordedVariant:
        if self.kpi_rule_version != RULE_VERSION:
            raise ValueError("variant uses an unknown kpi rule version")
        expected_reasons = reasons_for(self.model_a, self.model_b)
        if list(self.reasons) != expected_reasons:
            raise ValueError("variant reason codes do not match its KPI reports")
        if self.material != bool(self.reasons):
            raise ValueError("variant material flag does not match reason codes")
        expected = fingerprint_reports(self.kpi_rule_version, self.model_a, self.model_b)
        if self.kpi_fingerprint != expected:
            raise ValueError("variant kpi fingerprint mismatch")
        return self


class HandoffPackage(ApiModel):
    schema_version: Literal["fts.handoff.v1"]
    package_id: str
    revision: int = Field(ge=1)
    parent_package_id: str | None = None
    parent_content_hash: str | None = Field(default=None, pattern=_SHA256)
    created_at: str
    created_by: str
    region: Literal["KR", "US"]
    claims: Claims
    models: list[ModelCheckpoint]
    scenario: ScenarioRef
    environment: ExecutionEnvironment
    safety: SafetyProfile
    observed_regression: ObservedRegression | None
    artifacts: list[ArtifactRef]
    root_cause: RootCauseHypothesis
    recommended_next_tests: list[RecommendedTest]
    recorded_variants: list[RecordedVariant] = Field(default_factory=list)
    reproduction: ReproductionCheck | None = None
    ownership: Ownership
    verdict: Verdict
    content_hash: str | None = Field(default=None, pattern=_SHA256)

    @model_validator(mode="after")
    def _contract(self) -> HandoffPackage:
        if not _TIMESTAMP.match(self.created_at):
            raise ValueError("created_at must be an explicit UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
        roles = [model.role for model in self.models]
        if roles != ["A", "B"]:
            raise ValueError("models must be baseline A followed by candidate B")
        if (self.parent_content_hash is None) != (self.parent_package_id is None):
            raise ValueError("parent package id and parent content hash must be set together")
        if self.revision == 1 and self.parent_content_hash is not None:
            raise ValueError("revision 1 cannot name a parent package")
        if self.revision > 1 and self.parent_content_hash is None:
            raise ValueError("later revisions must name the parent content hash")
        if self.ownership.lease_expires_at is not None and not _TIMESTAMP.match(
            self.ownership.lease_expires_at
        ):
            raise ValueError("lease_expires_at must be an explicit UTC timestamp or null")

        recommended = {test.test_id: test for test in self.recommended_next_tests}
        for task in self.verdict.follow_up_tasks:
            if task.recommended_test_id is not None and task.recommended_test_id not in recommended:
                raise ValueError(f"follow-up task references unknown test {task.recommended_test_id}")

        state = self.verdict.state
        if state == "Not Evaluated":
            if self.observed_regression is not None or self.artifacts or self.recorded_variants:
                raise ValueError("Not Evaluated must not carry KPI results, logs, or variant results")
        elif self.observed_regression is None:
            raise ValueError("this verdict requires an observed regression block")

        if (
            state == "No Material Regression"
            and self.observed_regression is not None
            and self.observed_regression.material
        ):
            raise ValueError("No Material Regression contradicts a material regression block")
        if state == "Confirmed":
            if self.reproduction is None or not self.reproduction.matched:
                raise ValueError("Confirmed requires a matching reproduction check")
            if not self.recorded_variants:
                raise ValueError("Confirmed requires the recorded follow-up variant")

        if self.reproduction is not None and self.reproduction.matched:
            if self.observed_regression is None:
                raise ValueError("a matched reproduction needs the original regression block")
            if self.reproduction.kpi_fingerprint != self.observed_regression.kpi_fingerprint:
                raise ValueError("matched reproduction fingerprint differs from the observed regression")

        for variant in self.recorded_variants:
            test = recommended.get(variant.test_id)
            if test is None:
                raise ValueError(f"recorded variant {variant.test_id} was not a recommended test")
            effective = apply_overrides(self.scenario.parameters, variant.parameter_overrides)
            if scenario_parameter_hash(effective) != variant.parameter_hash:
                raise ValueError("variant parameter hash does not match the parent scenario plus overrides")
            if variant.seed != test.seed:
                raise ValueError("variant seed does not match the recommended test")
            if variant.parameter_overrides != test.parameter_overrides:
                raise ValueError("variant overrides do not match the recommended test")
        return self


def package_body(package: HandoffPackage) -> dict:
    """JSON object that the content hash covers. The hash field itself is omitted."""

    return package.model_dump(mode="json", exclude={"content_hash"})


def compute_content_hash(package: HandoffPackage) -> str:
    return content_hash(package_body(package))


def seal(package: HandoffPackage) -> HandoffPackage:
    """Return a copy whose ``content_hash`` matches the canonical body."""

    dumped = package_body(package)
    dumped["content_hash"] = content_hash(dumped)
    return HandoffPackage.model_validate(dumped)


def verify_content_hash(package: HandoffPackage) -> bool:
    if package.content_hash is None:
        return False
    return package.content_hash == compute_content_hash(package)
