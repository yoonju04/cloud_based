"""KPI reports embedded in a handoff package.

Reason codes are recomputed from the numbers. A package cannot claim
"new collision" unless model B's report shows a collision and model A's
does not, under the thresholds in ``fts.kpi.rules``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from fts.canonical import content_hash
from fts.domain.base import ApiModel
from fts.kpi.rules import (
    COLLISION_DISTANCE_M,
    MATERIAL_DISTANCE_DROP_M,
    MIN_SAFE_DISTANCE_M,
    RULE_VERSION,
)


class ReasonCode(str, Enum):
    NEW_COLLISION = "new_collision"
    NEW_LANE_DEPARTURE = "new_lane_departure"
    MIN_DISTANCE_DROP = "min_distance_drop"


class KpiReport(ApiModel):
    collision: bool
    min_distance_m: float
    lane_departure: bool
    max_lane_offset_m: float
    reaction_time_s: float


def reasons_for(model_a: KpiReport, model_b: KpiReport) -> list[ReasonCode]:
    """Pre-declared material-regression rules. Any one code is material."""

    reasons: list[ReasonCode] = []
    if model_b.collision and not model_a.collision:
        reasons.append(ReasonCode.NEW_COLLISION)
    if model_b.lane_departure and not model_a.lane_departure:
        reasons.append(ReasonCode.NEW_LANE_DEPARTURE)
    drop = model_a.min_distance_m - model_b.min_distance_m
    if drop > MATERIAL_DISTANCE_DROP_M and model_b.min_distance_m < MIN_SAFE_DISTANCE_M:
        reasons.append(ReasonCode.MIN_DISTANCE_DROP)
    return reasons


def fingerprint_reports(rule_version: str, model_a: KpiReport, model_b: KpiReport) -> str:
    """Hash of the numeric comparison. Prose is not part of the fingerprint."""

    body = {
        "kpi_rule_version": rule_version,
        "thresholds": {
            "collision_distance_m": COLLISION_DISTANCE_M,
            "min_safe_distance_m": MIN_SAFE_DISTANCE_M,
            "material_distance_drop_m": MATERIAL_DISTANCE_DROP_M,
        },
        "model_a": model_a.model_dump(mode="json"),
        "model_b": model_b.model_dump(mode="json"),
    }
    return content_hash(body)


class ObservedRegression(ApiModel):
    material: bool
    reasons: list[ReasonCode]
    kpi_rule_version: str
    model_a: KpiReport
    model_b: KpiReport
    kpi_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _matches_rules(self) -> ObservedRegression:
        if self.kpi_rule_version != RULE_VERSION:
            raise ValueError(f"unsupported kpi rule version: {self.kpi_rule_version}")
        expected_reasons = reasons_for(self.model_a, self.model_b)
        if list(self.reasons) != expected_reasons:
            raise ValueError("reason codes do not match the KPI reports under the pre-declared rules")
        if self.material != bool(expected_reasons):
            raise ValueError("material flag does not match reason codes")
        expected_fp = fingerprint_reports(self.kpi_rule_version, self.model_a, self.model_b)
        if self.kpi_fingerprint != expected_fp:
            raise ValueError("kpi fingerprint does not match model A/B reports")
        return self
