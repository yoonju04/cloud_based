"""Illustrative review questions.

The proposal mentions an example bank of about 25 questions and names such as
Jev and Laya. Neither the count nor those models is confirmed. This module
uses eight deterministic questions so the pipeline can run offline. Scores
are concern in [0, 1]. They are not a second safety threshold.
"""

from __future__ import annotations

from fts.domain.kpi import KpiReport
from fts.domain.log import SimulationLog
from fts.kpi.rules import MIN_SAFE_DISTANCE_M

QUESTIONS: tuple[tuple[str, str], ...] = (
    ("late_response", "전환이 늦었는가?"),
    ("lane_departure", "차선을 이탈했는가?"),
    ("excessive_oscillation", "제어가 과도하게 진동했는가?"),
    ("close_approach", "보행자와의 거리가 너무 가까웠는가?"),
    ("collision", "충돌했는가?"),
    ("harsh_brake", "제동이 과도하게 급했는가?"),
    ("slow_after_occlusion", "가림 이후 반응이 늦었는가?"),
    ("missed_stop_before_crossing", "보행자 횡단 위치 이전에 멈추지 못했는가?"),
)


def question_scores(log: SimulationLog, report: KpiReport) -> dict[str, float]:
    stopped_short = _stopped_short(log)
    scores = {
        "late_response": _unit(report.reaction_time_s / 2.0),
        "lane_departure": 1.0 if report.lane_departure else 0.0,
        "excessive_oscillation": _unit(_oscillation_changes(log) / 5.0),
        "close_approach": 0.0
        if report.min_distance_m >= MIN_SAFE_DISTANCE_M
        else _unit((MIN_SAFE_DISTANCE_M - report.min_distance_m) / MIN_SAFE_DISTANCE_M),
        "collision": 1.0 if report.collision else 0.0,
        "harsh_brake": _unit(_max_decel(log) / 8.0),
        "slow_after_occlusion": _unit(report.reaction_time_s / 1.5),
        "missed_stop_before_crossing": 0.0 if stopped_short else 1.0,
    }
    return {key: scores[key] for key, _prompt in QUESTIONS}


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _oscillation_changes(log: SimulationLog) -> int:
    changes = 0
    previous = 0
    for earlier, later in zip(log.frames, log.frames[1:]):
        delta = later.ego_y_m - earlier.ego_y_m
        if abs(delta) < 1e-4:
            continue
        sign = 1 if delta > 0 else -1
        if previous != 0 and sign != previous:
            changes += 1
        previous = sign
    return changes


def _max_decel(log: SimulationLog) -> float:
    peak = 0.0
    for earlier, later in zip(log.frames, log.frames[1:]):
        dt = later.t_s - earlier.t_s
        if dt <= 0:
            continue
        peak = max(peak, (earlier.ego_speed_mps - later.ego_speed_mps) / dt)
    return peak


def _stopped_short(log: SimulationLog) -> bool:
    pedestrian_x = log.frames[0].pedestrian_x_m
    return any(
        frame.ego_speed_mps <= 0.05 and frame.ego_x_m < pedestrian_x - 1.0 for frame in log.frames
    )
