from fts.domain.package import Verdict
from fts.extension.prioritizer import ReviewPriority, annotate, score_candidate
from fts.extension.questions import QUESTIONS
from fts.reproduce import simulate_package
from fts.walkthrough import run_walkthrough
import pytest
from pydantic import ValidationError


def test_review_priority_does_not_change_the_verdict(tmp_path):
    walk = run_walkthrough(evidence_dir=tmp_path / "logs", uri_prefix="repo://examples")
    verdict = walk.us_package.verdict
    before = verdict.model_dump(mode="json")
    logs = simulate_package(walk.us_package)
    priority = score_candidate(logs[1], walk.us_package.observed_regression.model_b)
    again = score_candidate(logs[1], walk.us_package.observed_regression.model_b)
    annotation = annotate(verdict, priority)

    assert priority.question_scores.keys() == {key for key, _prompt in QUESTIONS}
    assert priority.model_dump(mode="json") == again.model_dump(mode="json")
    assert annotation.verdict_state == verdict.state == "Confirmed"
    assert verdict.model_dump(mode="json") == before
    assert "suggestion:" not in walk.us_package.model_dump_json()
    assert priority.may_override_safety_verdict is False
    assert priority.trained_on == "synthetic_stand_in_not_driving_labels"


def test_override_flag_cannot_be_set():
    with pytest.raises(ValidationError):
        ReviewPriority(
            question_scores={"late_response": 1.0},
            ridge_priority=1.0,
            logistic_review_probability=0.5,
            synthetic_holdout_mae=0.0,
            trained_on="synthetic_stand_in_not_driving_labels",
            may_override_safety_verdict=True,
        )


def test_inconclusive_policy_keeps_follow_ups():
    verdict = Verdict(
        state="Inconclusive",
        rationale="still open",
        follow_up_tasks=[
            {
                "task_id": "followup-reproduce",
                "summary": "rerun from the package",
                "kind": "reproduce",
            }
        ],
    )
    assert verdict.follow_up_tasks[0].task_id == "followup-reproduce"
