"""Ridge and logistic scores for review ordering.

The fit uses a fixed synthetic design matrix, not labeled driving data.
``annotate`` copies the verdict state out. It has no parameter that writes
a new verdict, and ``may_override_safety_verdict`` cannot be set true.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache
from typing import Literal

from pydantic import Field

from fts.domain.base import ApiModel
from fts.domain.kpi import KpiReport
from fts.domain.log import SimulationLog
from fts.domain.package import Verdict
from fts.extension.questions import QUESTIONS, question_scores


class ReviewPriority(ApiModel):
    question_scores: dict[str, float]
    ridge_priority: float
    logistic_review_probability: float
    synthetic_holdout_mae: float
    trained_on: Literal["synthetic_stand_in_not_driving_labels"]
    may_override_safety_verdict: Literal[False] = False


class ReviewAnnotation(ApiModel):
    verdict_state: str
    verdict_rationale: str
    follow_up_task_ids: list[str]
    priority: ReviewPriority
    note: str = Field(
        default="Priority is a review ordering hint. It is not a safety verdict."
    )


def score_candidate(log: SimulationLog, report: KpiReport) -> ReviewPriority:
    scores = question_scores(log, report)
    vector = [scores[key] for key, _prompt in QUESTIONS]
    ridge_w, logistic_w, logistic_b, holdout_mae = _fitted()
    return ReviewPriority(
        question_scores=scores,
        ridge_priority=_dot(ridge_w, vector),
        logistic_review_probability=_sigmoid(_dot(logistic_w, vector) + logistic_b),
        synthetic_holdout_mae=holdout_mae,
        trained_on="synthetic_stand_in_not_driving_labels",
        may_override_safety_verdict=False,
    )


def annotate(verdict: Verdict, priority: ReviewPriority) -> ReviewAnnotation:
    if priority.may_override_safety_verdict:
        raise ValueError("AI review priority must not override deterministic safety verdicts")
    return ReviewAnnotation(
        verdict_state=verdict.state,
        verdict_rationale=verdict.rationale,
        follow_up_task_ids=[task.task_id for task in verdict.follow_up_tasks],
        priority=priority,
    )


def suggest_followups(scores: dict[str, float]) -> list[str]:
    """Hints only. They are not follow-up tasks and are not written into the package."""

    notes: list[str] = []
    if scores.get("late_response", 0.0) >= 0.5:
        notes.append("suggestion: inspect occlusion-to-brake timing. Not a verdict task.")
    if scores.get("lane_departure", 0.0) >= 1.0:
        notes.append("suggestion: review the lateral reaction during the late brake. Not a verdict task.")
    if not notes:
        notes.append("suggestion: no extra review hint from the question scores. Not a verdict task.")
    return notes


@lru_cache(maxsize=1)
def _fitted() -> tuple[tuple[float, ...], tuple[float, ...], float, float]:
    features, ridge_labels, logistic_labels = _synthetic_rows()
    train_x, hold_x = features[:16], features[16:]
    train_y, hold_y = ridge_labels[:16], ridge_labels[16:]
    ridge_w = _fit_ridge(train_x, train_y, l2=1.0)
    holdout_mae = sum(abs(_dot(ridge_w, row) - label) for row, label in zip(hold_x, hold_y)) / len(hold_x)
    logistic_w, logistic_b = _fit_logistic(train_x, logistic_labels[:16], l2=0.1)
    return tuple(ridge_w), tuple(logistic_w), logistic_b, holdout_mae


def _synthetic_rows() -> tuple[list[list[float]], list[float], list[int]]:
    """Fixed stand-in labels so the math can execute. Not driving data."""

    generator = random.Random(0)
    true_w = [0.4, 0.7, 0.2, 0.5, 0.9, 0.1, 0.3, 0.6]
    features: list[list[float]] = []
    ridge_labels: list[float] = []
    logistic_labels: list[int] = []
    for _ in range(24):
        row = [generator.random() for _ in true_w]
        label = _dot(true_w, row) + 0.01 * (generator.random() - 0.5)
        features.append(row)
        ridge_labels.append(label)
        logistic_labels.append(1 if label >= 1.5 else 0)
    return features, ridge_labels, logistic_labels


def _fit_ridge(features: list[list[float]], labels: list[float], l2: float) -> list[float]:
    width = len(features[0])
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]
    for row, label in zip(features, labels):
        for i in range(width):
            xty[i] += row[i] * label
            for j in range(width):
                xtx[i][j] += row[i] * row[j]
    for i in range(width):
        xtx[i][i] += l2
    return _solve(xtx, xty)


def _fit_logistic(features: list[list[float]], labels: list[int], l2: float) -> tuple[list[float], float]:
    width = len(features[0])
    weights = [0.0 for _ in range(width)]
    bias = 0.0
    count = float(len(features))
    for _step in range(400):
        grad_w = [l2 * weight for weight in weights]
        grad_b = 0.0
        for row, label in zip(features, labels):
            error = _sigmoid(_dot(weights, row) + bias) - label
            grad_b += error
            for index, value in enumerate(row):
                grad_w[index] += error * value
        bias -= 0.2 * grad_b / count
        weights = [weight - 0.2 * grad / count for weight, grad in zip(weights, grad_w)]
    return weights, bias


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    rows = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(rows[row][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("ridge matrix is singular; increase l2")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        scale = rows[col][col]
        for column in range(col, size + 1):
            rows[col][column] /= scale
        for row in range(size):
            if row == col:
                continue
            factor = rows[row][col]
            for column in range(col, size + 1):
                rows[row][column] -= factor * rows[col][column]
    return [rows[index][size] for index in range(size)]


def _dot(weights: tuple[float, ...] | list[float], row: list[float]) -> float:
    return sum(weight * value for weight, value in zip(weights, row))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)
