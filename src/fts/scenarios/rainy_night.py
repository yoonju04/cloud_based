"""Hypothetical rainy-night intersection. Discovery side only.

The numbers are a synthetic scene built for the course walkthrough. They are
not a reconstruction of a 42dot drive, and they are not a measured failure rate.
"""

from __future__ import annotations

from fts.adapters.base import ExecutionRequest
from fts.adapters.replay import CONTAINER_DIGEST, SIMULATOR_VERSION
from fts.domain.package import safety_profile
from fts.domain.scenario import (
    SEED_OFFSET_FORMULA,
    SYNTHETIC_CARD_NOTE,
    ScenarioParameters,
    SyntheticModelCard,
    make_checkpoint,
    scenario_parameter_hash,
)

SCENARIO_ID = "hypothetical-rainy-night-intersection-pedestrian"
DATASET_VERSION = "2026.11.02-hypothetical"
SEED = 20261102

SUMMARY_KO = (
    "가상 사례: 비 오는 밤, 신호가 있는 교차로에서 가려져 있던 보행자가 차선으로 들어온다. "
    "실제 42dot 사고나 로그가 아니다."
)
SUMMARY_EN = (
    "Hypothetical: at a signalized intersection on a rainy night, a pedestrian who was "
    "occluded steps into the ego lane. Not a real 42dot incident or log."
)


def scenario_parameters() -> ScenarioParameters:
    return ScenarioParameters(
        weather="rain",
        time_of_day="night",
        location_type="signalized_intersection",
        dt_s=0.05,
        horizon_s=8.0,
        ego_initial_speed_mps=12.0,
        ego_initial_x_m=0.0,
        ego_initial_y_m=0.0,
        pedestrian_x_m=54.0,
        pedestrian_initial_y_m=-7.0,
        pedestrian_speed_mps=1.5,
        occlusion_until_y_m=-3.0,
        lane_center_y_m=0.0,
        lane_half_width_m=1.75,
        seed_offset_scale_m=0.01,
        seed_offset_formula=SEED_OFFSET_FORMULA,
    )


def model_checkpoints():
    baseline = make_checkpoint(
        "A",
        "hypothetical-baseline-A",
        SyntheticModelCard(
            reaction_delay_s=0.40,
            brake_decel_mps2=6.0,
            swerve_lateral_accel_mps2=0.0,
            swerve_ttc_threshold_s=1.2,
            max_lateral_speed_mps=3.0,
            note=SYNTHETIC_CARD_NOTE,
        ),
    )
    candidate = make_checkpoint(
        "B",
        "hypothetical-candidate-B",
        SyntheticModelCard(
            reaction_delay_s=1.30,
            brake_decel_mps2=6.0,
            swerve_lateral_accel_mps2=2.2,
            swerve_ttc_threshold_s=1.0,
            max_lateral_speed_mps=3.0,
            note=SYNTHETIC_CARD_NOTE,
        ),
    )
    return [baseline, candidate]


def discovery_request() -> ExecutionRequest:
    """Initial KR request. After this is sealed, the catalog is not an input."""

    parameters = scenario_parameters()
    # Hash is checked so a drift in the catalog fails before a package is sealed.
    scenario_parameter_hash(parameters)
    safety_profile()
    return ExecutionRequest(
        scenario_id=SCENARIO_ID,
        dataset_version=DATASET_VERSION,
        parameters=parameters,
        seed=SEED,
        simulator_version=SIMULATOR_VERSION,
        container_digest=CONTAINER_DIGEST,
        models=model_checkpoints(),
        kpi_rule_version=safety_profile().kpi_rule_version,
        parameter_overrides={},
    )
