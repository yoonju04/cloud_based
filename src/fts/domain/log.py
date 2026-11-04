"""Deterministic simulation log. The evaluator reads only this object."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from fts.domain.base import ApiModel


class Frame(ApiModel):
    t_s: float
    ego_x_m: float
    ego_y_m: float
    ego_speed_mps: float
    pedestrian_x_m: float
    pedestrian_y_m: float
    lane_center_y_m: float
    lane_half_width_m: float


class SimulationLog(ApiModel):
    scenario_id: str
    dataset_version: str
    seed: int
    simulator_version: str
    container_digest: str
    model_role: Literal["A", "B"]
    checkpoint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kpi_rule_version: str
    pedestrian_visible_t_s: float
    frames: list[Frame] = Field(min_length=2)
