"""Follow-the-sun SIL validation control plane, course PoC.

The repository is organized around one question. A failure found by one
regional team has to be reproducible by another regional team from the
handoff package alone, with the root-cause hypothesis and the next
validation step still attached.
"""

__version__ = "0.1.0"

NORTH_STAR = (
    "Can a failure in an autonomous-driving model found by one regional team "
    "be reproduced by another regional team without any extra explanation, "
    "root-caused, and carried into the next validation step?"
)

NORTH_STAR_KO = (
    "한 지역 팀이 발견한 자율주행 모델의 실패를, 다른 지역 팀이 추가 설명 없이 "
    "재현하고, 원인 가설을 유지한 채, 다음 검증 단계로 넘길 수 있는가?"
)
