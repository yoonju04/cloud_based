"""The single draft KPI rule set shipped with this PoC.

Thresholds are part of the handoff contract. Changing a number without
changing ``RULE_VERSION`` is a bug: packages name the version, and the
evaluator refuses a version it does not implement.
"""

RULE_VERSION = "kpi-rules-2026.11-draft"
PROFILE_ID = "safety-profile-hypothetical-urban-v1"

# Point-mass stand-in. This is not a vehicle-body polygon.
COLLISION_DISTANCE_M = 0.75
MIN_SAFE_DISTANCE_M = 1.5
MATERIAL_DISTANCE_DROP_M = 0.5

# A brake is "observed" once speed falls this far below the first sample.
BRAKE_ONSET_DELTA_MPS = 0.05
