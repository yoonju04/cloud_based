"""Execution adapters. Replay runs locally. CARLA and external SIL are stubs."""

from fts.adapters.carla import CarlaWorker
from fts.adapters.external_sil import ExternalSilAdapter
from fts.adapters.replay import CONTAINER_DIGEST, SIMULATOR_VERSION, ReplayWorker

__all__ = [
    "CONTAINER_DIGEST",
    "CarlaWorker",
    "ExternalSilAdapter",
    "ReplayWorker",
    "SIMULATOR_VERSION",
]
