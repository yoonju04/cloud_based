"""Deterministic KPI evaluation.

Same log in, same report out. The pass/fail rules live in ``fts.kpi.rules``
and are re-checked when a package is loaded, so a later edit to the prose
cannot quietly change the verdict.
"""

from __future__ import annotations

import math

from fts.domain.kpi import KpiReport, fingerprint_reports, reasons_for
from fts.domain.log import SimulationLog
from fts.errors import EnvironmentMismatch
from fts.kpi.rules import BRAKE_ONSET_DELTA_MPS, COLLISION_DISTANCE_M, RULE_VERSION


def _round(value: float) -> float:
    return round(value, 6)


def evaluate_log(log: SimulationLog) -> KpiReport:
    if log.kpi_rule_version != RULE_VERSION:
        raise EnvironmentMismatch(
            f"log rule version {log.kpi_rule_version} does not match {RULE_VERSION}"
        )
    frames = log.frames
    lane_half_width = frames[0].lane_half_width_m
    min_distance = min(
        math.hypot(frame.ego_x_m - frame.pedestrian_x_m, frame.ego_y_m - frame.pedestrian_y_m)
        for frame in frames
    )
    max_offset = max(abs(frame.ego_y_m - frame.lane_center_y_m) for frame in frames)
    min_distance = _round(min_distance)
    max_offset = _round(max_offset)
    initial_speed = frames[0].ego_speed_mps
    reaction: float | None = None
    for frame in frames:
        if frame.ego_speed_mps < initial_speed - BRAKE_ONSET_DELTA_MPS:
            reaction = _round(frame.t_s - log.pedestrian_visible_t_s)
            break
    if reaction is None:
        reaction = _round(frames[-1].t_s - log.pedestrian_visible_t_s)
    return KpiReport(
        collision=min_distance < COLLISION_DISTANCE_M,
        min_distance_m=min_distance,
        lane_departure=max_offset > lane_half_width,
        max_lane_offset_m=max_offset,
        reaction_time_s=reaction,
    )


def compare_logs(log_a: SimulationLog, log_b: SimulationLog) -> dict:
    """Compare baseline A with candidate B and return the regression block fields."""

    if log_a.model_role != "A" or log_b.model_role != "B":
        raise EnvironmentMismatch("compare_logs expects model A then model B")
    if log_a.kpi_rule_version != log_b.kpi_rule_version:
        raise EnvironmentMismatch("the two logs were stamped with different KPI rule versions")
    report_a = evaluate_log(log_a)
    report_b = evaluate_log(log_b)
    reasons = reasons_for(report_a, report_b)
    return {
        "material": bool(reasons),
        "reasons": reasons,
        "kpi_rule_version": log_a.kpi_rule_version,
        "model_a": report_a,
        "model_b": report_b,
        "kpi_fingerprint": fingerprint_reports(log_a.kpi_rule_version, report_a, report_b),
    }
