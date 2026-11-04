"""Metric definitions from the proposal.

These functions are the formulas only. This module does not contain
measured rates, costs, or durations, and it refuses to fill a missing
cost component with a made-up number.
"""

from __future__ import annotations


def _rate(numerator: int, denominator: int, name: str) -> float:
    if numerator < 0 or denominator < 0:
        raise ValueError(f"{name} counts must be non-negative")
    if numerator > denominator:
        raise ValueError(f"{name} numerator cannot exceed the denominator")
    if denominator == 0:
        raise ValueError(f"{name} is undefined when the denominator is 0")
    return numerator / denominator


def reproduction_success_rate(*, successful_reruns: int, rerun_attempts: int) -> float:
    """재현 성공률 = 목표 조건 재실행 성공 수 / 총 재현 시도 수."""

    return _rate(successful_reruns, rerun_attempts, "reproduction success rate")


def duplicate_commit_rate(*, duplicate_commits: int, committed_results: int) -> float:
    """중복 결과 확정률 = 동일 논리 Job의 중복 확정 수 / 전체 확정 결과 수."""

    return _rate(duplicate_commits, committed_results, "duplicate commit rate")


def omitted_task_rate(*, omitted_tasks: int, handoff_tasks: int) -> float:
    """작업 누락률 = 미등록·미승계 후속 작업 수 / 전체 인계 대상 작업 수."""

    return _rate(omitted_tasks, handoff_tasks, "omitted task rate")


def handoff_completion_seconds(*, package_committed_at: float, next_team_started_at: float) -> float:
    """인계 완료 시간(초) = 다음 팀의 첫 유효 실행 시작 − 이전 팀의 패키지 확정."""

    delta = next_team_started_at - package_committed_at
    if delta < 0:
        raise ValueError("next team start is earlier than package commit")
    return delta


def regression_close_seconds(*, failure_observed_at: float, verdict_committed_at: float) -> float:
    """회귀 검증 완료 시간(초) = 판정 확정 − 실패 발견."""

    delta = verdict_committed_at - failure_observed_at
    if delta < 0:
        raise ValueError("verdict commit is earlier than failure observation")
    return delta


def operating_cost(
    *,
    worker_compute: float | None,
    storage: float | None,
    data_movement: float | None,
    control_plane: float | None,
) -> float | None:
    """운영 비용 = Worker 계산 + 스토리지 + 데이터 이동 + 관리 서비스.

    Returns None when any component is unknown. Missing prices are not estimated.
    """

    parts = (worker_compute, storage, data_movement, control_plane)
    if any(part is None for part in parts):
        return None
    if any(part < 0 for part in parts):
        raise ValueError("cost components must be non-negative")
    return float(sum(parts))
