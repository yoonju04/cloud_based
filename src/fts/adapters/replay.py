"""Local deterministic replay worker.

This is the executable stand-in for a SIL worker. It is a point-mass
kinematic scene, not a vehicle dynamics model and not CARLA. Given the
same request it returns the same logs.
"""

from __future__ import annotations

import hashlib

from fts.adapters.base import ExecutionProduct, ExecutionRequest, Submission, SubmissionState
from fts.canonical import canonicalize, content_hash
from fts.domain.log import Frame, SimulationLog
from fts.domain.scenario import ScenarioParameters, apply_overrides, seed_offset_m
from fts.errors import AdapterUnavailable, EnvironmentMismatch
from fts.kpi.rules import RULE_VERSION

SIMULATOR_VERSION = "fts-replay-0.1.0"
# Not an image digest from a registry. It pins this worker implementation.
CONTAINER_DIGEST = "sha256:" + hashlib.sha256(
    b"fts-replay-worker-poc-0.1.0-not-a-published-image"
).hexdigest()


class ReplayWorker:
    name = "replay"

    def __init__(self) -> None:
        self._products: dict[str, ExecutionProduct] = {}

    def submit(self, request: ExecutionRequest) -> Submission:
        self._check_environment(request)
        submission_id = "replay-" + content_hash(request.model_dump(mode="json"))
        if submission_id not in self._products:
            self._products[submission_id] = self._execute(submission_id, request)
        return Submission(
            submission_id=submission_id,
            state=SubmissionState.SUCCEEDED,
            detail="deterministic replay completed locally",
        )

    def status(self, submission_id: str) -> Submission:
        if submission_id not in self._products:
            raise AdapterUnavailable(f"unknown replay submission {submission_id}")
        return Submission(
            submission_id=submission_id,
            state=SubmissionState.SUCCEEDED,
            detail="deterministic replay completed locally",
        )

    def fetch_results(self, submission_id: str) -> ExecutionProduct:
        try:
            return self._products[submission_id]
        except KeyError as exc:
            raise AdapterUnavailable(f"unknown replay submission {submission_id}") from exc

    def _check_environment(self, request: ExecutionRequest) -> None:
        if request.simulator_version != SIMULATOR_VERSION:
            raise EnvironmentMismatch(
                f"simulator version {request.simulator_version} != {SIMULATOR_VERSION}"
            )
        if request.container_digest != CONTAINER_DIGEST:
            raise EnvironmentMismatch("container digest does not match this replay worker")
        if request.kpi_rule_version != RULE_VERSION:
            raise EnvironmentMismatch(
                f"kpi rule version {request.kpi_rule_version} != {RULE_VERSION}"
            )
        roles = [model.role for model in request.models]
        if roles != ["A", "B"]:
            raise EnvironmentMismatch("replay requests must carry model A then model B")

    def _execute(self, submission_id: str, request: ExecutionRequest) -> ExecutionProduct:
        parameters = apply_overrides(request.parameters, request.parameter_overrides)
        logs = [
            _simulate(request, parameters, model.role, model.checkpoint_hash, model.synthetic_model_card)
            for model in request.models
        ]
        # Touch canonical bytes so a bug in float handling fails here, not later.
        canonicalize([log.model_dump(mode="json") for log in logs])
        return ExecutionProduct(submission_id=submission_id, logs=logs)


def _simulate(request, parameters: ScenarioParameters, role, checkpoint_hash, card) -> SimulationLog:
    dt = parameters.dt_s
    steps = int(round(parameters.horizon_s / dt))
    offset = round(seed_offset_m(request.seed, parameters.seed_offset_scale_m), 6)
    pedestrian_x = round(parameters.pedestrian_x_m + offset, 6)
    visible_t = round(
        (parameters.occlusion_until_y_m - parameters.pedestrian_initial_y_m) / parameters.pedestrian_speed_mps,
        6,
    )
    brake_at = round(visible_t + card.reaction_delay_s, 6)
    ego_x = parameters.ego_initial_x_m
    ego_y = parameters.ego_initial_y_m
    speed = parameters.ego_initial_speed_mps
    lateral_speed = 0.0
    frames: list[Frame] = []
    for index in range(steps + 1):
        t = round(index * dt, 6)
        pedestrian_y = round(parameters.pedestrian_initial_y_m + parameters.pedestrian_speed_mps * t, 6)
        frames.append(
            Frame(
                t_s=t,
                ego_x_m=ego_x,
                ego_y_m=ego_y,
                ego_speed_mps=speed,
                pedestrian_x_m=pedestrian_x,
                pedestrian_y_m=pedestrian_y,
                lane_center_y_m=parameters.lane_center_y_m,
                lane_half_width_m=parameters.lane_half_width_m,
            )
        )
        if t >= brake_at:
            speed = round(max(0.0, speed - card.brake_decel_mps2 * dt), 6)
        if speed <= 0.0:
            lateral_speed = 0.0
        closing = pedestrian_x - ego_x
        ttc = closing / speed if speed > 0.3 and closing > 0 else 999.0
        if (
            t >= brake_at
            and ttc < card.swerve_ttc_threshold_s
            and card.swerve_lateral_accel_mps2 > 0
            and speed > 1.0
        ):
            lateral_speed = round(
                min(card.max_lateral_speed_mps, lateral_speed + card.swerve_lateral_accel_mps2 * dt),
                6,
            )
        ego_x = round(ego_x + speed * dt, 6)
        ego_y = round(ego_y + lateral_speed * dt, 6)
    return SimulationLog(
        scenario_id=request.scenario_id,
        dataset_version=request.dataset_version,
        seed=request.seed,
        simulator_version=request.simulator_version,
        container_digest=request.container_digest,
        model_role=role,
        checkpoint_hash=checkpoint_hash,
        kpi_rule_version=request.kpi_rule_version,
        pedestrian_visible_t_s=visible_t,
        frames=frames,
    )
