"""Scenario parameters, synthetic model cards, and the hashes that pin them.

The replay worker has no neural-network weights. A synthetic behavior card
travels inside the package, and the checkpoint hash is the hash of that card.
Changing the card changes the hash, so the next team cannot silently retune it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from fts.canonical import content_hash
from fts.domain.base import ApiModel

SEED_OFFSET_FORMULA = "(seed % 5 - 2) * seed_offset_scale_m"
SYNTHETIC_CARD_NOTE = (
    "Synthetic behavior card standing in for a checkpoint that is not in this "
    "repository. Not a neural network and not a 42dot model."
)


def seed_offset_m(seed: int, scale: float) -> float:
    """Implementation of ``SEED_OFFSET_FORMULA``. Kept beside the string on purpose."""

    return (seed % 5 - 2) * scale


class ScenarioParameters(ApiModel):
    weather: Literal["rain"]
    time_of_day: Literal["night"]
    location_type: Literal["signalized_intersection"]
    dt_s: float = Field(gt=0, le=0.2)
    horizon_s: float = Field(gt=0, le=30)
    ego_initial_speed_mps: float = Field(gt=0, le=40)
    ego_initial_x_m: float
    ego_initial_y_m: float
    pedestrian_x_m: float
    pedestrian_initial_y_m: float
    pedestrian_speed_mps: float = Field(gt=0, le=5)
    occlusion_until_y_m: float
    lane_center_y_m: float
    lane_half_width_m: float = Field(gt=0, le=5)
    seed_offset_scale_m: float = Field(ge=0, le=1)
    seed_offset_formula: str

    @model_validator(mode="after")
    def _formula_is_the_implemented_one(self) -> ScenarioParameters:
        if self.seed_offset_formula != SEED_OFFSET_FORMULA:
            raise ValueError("seed_offset_formula does not match the worker implementation")
        if not (self.pedestrian_initial_y_m < self.occlusion_until_y_m):
            raise ValueError("pedestrian must start occluded, below occlusion_until_y_m")
        return self


def scenario_parameter_hash(parameters: ScenarioParameters) -> str:
    return content_hash(parameters.model_dump(mode="json"))


def apply_overrides(parameters: ScenarioParameters, overrides: dict[str, float]) -> ScenarioParameters:
    data = parameters.model_dump(mode="json")
    for key, value in overrides.items():
        if key not in data:
            raise ValueError(f"unknown scenario override: {key}")
        data[key] = value
    return ScenarioParameters.model_validate(data)


class SyntheticModelCard(ApiModel):
    reaction_delay_s: float = Field(gt=0, lt=10)
    brake_decel_mps2: float = Field(gt=0, le=12)
    swerve_lateral_accel_mps2: float = Field(ge=0, le=5)
    swerve_ttc_threshold_s: float = Field(gt=0, le=5)
    max_lateral_speed_mps: float = Field(gt=0, le=5)
    note: str


class ModelCheckpoint(ApiModel):
    role: Literal["A", "B"]
    display_name: str
    checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    synthetic_model_card: SyntheticModelCard

    @model_validator(mode="after")
    def _hash_matches_card(self) -> ModelCheckpoint:
        expected = model_checkpoint_hash(self.role, self.display_name, self.synthetic_model_card)
        if self.checkpoint_hash != expected:
            raise ValueError("checkpoint hash does not match the synthetic model card")
        return self


def model_checkpoint_hash(role: str, display_name: str, card: SyntheticModelCard) -> str:
    body = {
        "display_name": display_name,
        "poc_synthetic": True,
        "role": role,
        "synthetic_model_card": card.model_dump(mode="json"),
    }
    return content_hash(body)


def make_checkpoint(role: Literal["A", "B"], display_name: str, card: SyntheticModelCard) -> ModelCheckpoint:
    return ModelCheckpoint(
        role=role,
        display_name=display_name,
        checkpoint_hash=model_checkpoint_hash(role, display_name, card),
        synthetic_model_card=card,
    )
