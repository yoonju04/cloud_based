"""Formula checks. The integers below are arithmetic fixtures, not measurements."""

import pytest

from fts.metrics import (
    duplicate_commit_rate,
    handoff_completion_seconds,
    omitted_task_rate,
    operating_cost,
    regression_close_seconds,
    reproduction_success_rate,
)


def test_rates_match_the_proposal_definitions():
    assert reproduction_success_rate(successful_reruns=1, rerun_attempts=4) == 0.25
    assert duplicate_commit_rate(duplicate_commits=0, committed_results=5) == 0.0
    assert omitted_task_rate(omitted_tasks=1, handoff_tasks=4) == 0.25


def test_rates_are_undefined_without_a_denominator():
    with pytest.raises(ValueError):
        reproduction_success_rate(successful_reruns=0, rerun_attempts=0)


def test_durations_reject_a_reversed_interval():
    assert handoff_completion_seconds(package_committed_at=10, next_team_started_at=16) == 6
    assert regression_close_seconds(failure_observed_at=3, verdict_committed_at=9) == 6
    with pytest.raises(ValueError):
        handoff_completion_seconds(package_committed_at=16, next_team_started_at=10)


def test_operating_cost_stays_unknown_when_a_component_is_missing():
    assert (
        operating_cost(worker_compute=1, storage=2, data_movement=3, control_plane=4) == 10
    )
    assert (
        operating_cost(worker_compute=1, storage=None, data_movement=3, control_plane=4) is None
    )
