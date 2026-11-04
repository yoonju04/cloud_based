"""Scripted KR -> US handoff of the hypothetical rainy-night failure.

Korea may read the scenario catalog. The United States receives only the
sealed package JSON, then opens its own jobs on the shared control plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fts.adapters.base import not_evaluated_verdict
from fts.adapters.carla import CarlaWorker
from fts.adapters.external_sil import ExternalSilAdapter
from fts.adapters.replay import ReplayWorker
from fts.domain.package import (
    DISCLAIMER,
    Claims,
    ExecutionEnvironment,
    HandoffPackage,
    ObservedRegression,
    Ownership,
    RecommendedTest,
    RootCauseHypothesis,
    ScenarioRef,
    seal,
)
from fts.domain.scenario import scenario_parameter_hash
from fts.errors import PackageIntegrityError
from fts.execute import comparison_dict, run_request, write_log
from fts.extension.prioritizer import annotate, score_candidate, suggest_followups
from fts.jobs.clock import FakeClock, SequenceIds
from fts.jobs.control import JobService
from fts.jobs.store import MemoryStore
from fts.kpi.evaluator import evaluate_log
from fts.receive import us_continue
from fts.scenarios.rainy_night import SUMMARY_EN, SUMMARY_KO, discovery_request
from fts.verdict import verdict_after_discovery

KR_CREATED_AT = "2026-11-02T09:00:00Z"


@dataclass(frozen=True)
class Walkthrough:
    lines: list[str]
    kr_package: HandoffPackage
    us_package: HandoffPackage
    jobs: JobService


def run_walkthrough(*, evidence_dir: Path, uri_prefix: str) -> Walkthrough:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    jobs = JobService(MemoryStore(), FakeClock(), SequenceIds(), lease_ttl_s=3600.0)
    lines: list[str] = []

    def say(message: str) -> None:
        lines.append(message)

    say("질문: 한국 팀이 찾은 실패를, 미국 팀이 패키지만으로 재현할 수 있는가?")
    say("이 실행은 가상 시나리오다. 42dot 로그도, 측정된 성능 수치도 아니다.")
    carla = CarlaWorker().submit(discovery_request())
    external = ExternalSilAdapter().submit(discovery_request())
    say(f"CARLA 어댑터: {not_evaluated_verdict(carla.detail).state}. {carla.detail}")
    say(f"외부 SIL 어댑터: {not_evaluated_verdict(external.detail).state}. {external.detail}")

    kr_package = _korea_discovers(jobs, evidence_dir, uri_prefix, say)
    package_json = kr_package.model_dump_json()
    say("한국 측 파이썬 객체를 넘기지 않는다. 미국 팀의 입력은 패키지 JSON뿐이다.")
    us_package = us_continue(
        package_json,
        evidence_dir=evidence_dir,
        uri_prefix=uri_prefix,
        jobs=jobs,
    )
    _report_us(kr_package, us_package, say)
    return Walkthrough(lines=lines, kr_package=kr_package, us_package=us_package, jobs=jobs)


def _korea_discovers(jobs: JobService, evidence_dir: Path, uri_prefix: str, say) -> HandoffPackage:
    request = discovery_request()
    registered = jobs.register(
        spec=request.model_dump(mode="json"),
        idempotency_key="kr-register",
        requested_by="kr-validation",
        region="KR",
    )
    duplicate = jobs.register(
        spec=request.model_dump(mode="json"),
        idempotency_key="kr-register",
        requested_by="kr-validation",
        region="KR",
    )
    if not duplicate.replayed or duplicate.job["job_id"] != registered.job["job_id"]:
        raise PackageIntegrityError("duplicate KR registration created a second job")
    job_id = registered.job["job_id"]
    say(f"한국 작업 {job_id} 등록. 같은 멱등 키의 재전송은 새 작업을 만들지 않는다.")

    claimed = jobs.claim(job_id, "kr-validation", "KR", "kr-claim")
    token = claimed.job["lease_token"]
    attempt_id = claimed.job["attempt_id"]
    jobs.heartbeat(job_id, token, "kr-validation")
    jobs.start(job_id, token, "kr-validation")
    logs = run_request(ReplayWorker(), request)
    artifacts = [
        write_log(
            evidence_dir / f"kr_model_{log.model_role.lower()}.json",
            log,
            uri=f"{uri_prefix}/logs/kr_model_{log.model_role.lower()}.json",
        )
        for log in logs
    ]
    compared = comparison_dict(logs[0], logs[1])
    report_b = evaluate_log(logs[1])
    say(
        "모델 A는 충돌 없음, 차선 유지. "
        f"모델 B collision={report_b.collision}, "
        f"min_distance_m={report_b.min_distance_m}, "
        f"lane_departure={report_b.lane_departure}. "
        "이 값은 합성 재실행 출력이며 실험 결과가 아니다."
    )
    say(f"KPI fingerprint {compared['kpi_fingerprint']}")
    body = {"kind": "discovery", **compared, "artifacts": [item.model_dump(mode="json") for item in artifacts]}
    jobs.record_results(job_id, token, attempt_id, body, "kr-record", "kr-validation")
    committed = jobs.commit(job_id, attempt_id, "kr-commit", "kr-validation")
    replayed = jobs.commit(job_id, attempt_id, "kr-commit", "kr-validation")
    if not replayed.replayed or committed.job["commit_count"] != 1:
        raise PackageIntegrityError("KR commit was not idempotent")
    say(f"결과 확정 1회. 같은 키의 재전송 이후 commit_count={replayed.job['commit_count']}.")
    handed = jobs.handoff(job_id, "us-validation", "US", "kr-handoff", "kr-validation")
    package = seal(
        HandoffPackage(
            schema_version="fts.handoff.v1",
            package_id="pkg-kr-rainy-night-discovery",
            revision=1,
            parent_package_id=None,
            parent_content_hash=None,
            created_at=KR_CREATED_AT,
            created_by="kr-validation",
            region="KR",
            claims=Claims(
                hypothetical_scenario=True,
                real_42dot_data=False,
                measured_performance_claim=False,
                note=DISCLAIMER,
            ),
            models=list(request.models),
            scenario=ScenarioRef(
                scenario_id=request.scenario_id,
                dataset_version=request.dataset_version,
                summary_ko=SUMMARY_KO,
                summary_en=SUMMARY_EN,
                hypothetical=True,
                parameters=request.parameters,
                parameter_hash=scenario_parameter_hash(request.parameters),
            ),
            environment=ExecutionEnvironment(
                seed=request.seed,
                simulator_version=request.simulator_version,
                container_digest=request.container_digest,
            ),
            safety=request_safety(),
            observed_regression=ObservedRegression.model_validate(compared),
            artifacts=artifacts,
            root_cause=RootCauseHypothesis(
                statement=(
                    "가설(미확정): 후보 모델 B는 가림이 풀린 뒤 보행자에 대한 제동이 "
                    "베이스라인보다 늦다. Hypothesis (unconfirmed): candidate B brakes later "
                    "after the pedestrian leaves occlusion."
                ),
                confidence=0.35,
                confidence_is_calibrated=False,
                unconfirmed=[
                    "Perception delay, prediction delay, and planner delay are not separated.",
                    "The scene is synthetic. No 42dot log was used.",
                    "Rain, sensor noise, and occlusion duration were not swept.",
                    "The confidence value is an analyst label for this hypothetical, not a calibrated probability.",
                ],
            ),
            recommended_next_tests=[
                RecommendedTest(
                    test_id="variant-pedestrian-speed-1.6",
                    purpose_ko="보행자 속도를 1.6 m/s로 올려 가림 이후 여유가 더 짧은 경우를 본다.",
                    purpose_en="Raise pedestrian speed to 1.6 m/s so the post-occlusion margin is shorter.",
                    seed=request.seed,
                    parameter_overrides={"pedestrian_speed_mps": 1.6},
                    executable_from_package_alone=True,
                )
            ],
            recorded_variants=[],
            reproduction=None,
            ownership=Ownership(
                owner=handed.job["owner"],
                region=handed.job["region"],
                job_id=handed.job["job_id"],
                attempt_id=handed.job["attempt_id"],
                state=handed.job["state"],
                lease_token=None,
                lease_expires_at=None,
                idempotency_key="kr-commit",
                next_owner="us-validation",
                related_job_ids=[],
            ),
            verdict=verdict_after_discovery(material=compared["material"]),
            content_hash=None,
        )
    )
    say(f"패키지 봉인 {package.package_id} content_hash={package.content_hash}")
    say(f"판정 {package.verdict.state}. 후속 작업 {len(package.verdict.follow_up_tasks)}건이 패키지 안에 있다.")
    return package


def request_safety():
    from fts.domain.package import safety_profile

    return safety_profile()


def _report_us(kr_package: HandoffPackage, us_package: HandoffPackage, say) -> None:
    matched = us_package.reproduction is not None and us_package.reproduction.matched
    same_fingerprint = (
        us_package.reproduction is not None
        and us_package.observed_regression is not None
        and us_package.reproduction.kpi_fingerprint == kr_package.observed_regression.kpi_fingerprint
    )
    say("미국 재현 fingerprint " + ("일치" if matched and same_fingerprint else "불일치"))
    variant = us_package.recorded_variants[0]
    say(
        f"변형 시험 {variant.test_id} material={variant.material} "
        f"fingerprint={variant.kpi_fingerprint}"
    )
    say(f"돌려받은 판정: {us_package.verdict.state}. 소유 작업 상태 {us_package.ownership.state}.")
    say(f"부모 패키지 해시 {us_package.parent_content_hash}")
    # The extension sees the candidate log only after the verdict exists, and
    # annotate() returns a side object. It is not written back into the package.
    from fts.reproduce import simulate_package

    logs = simulate_package(us_package)
    priority = score_candidate(logs[1], us_package.observed_regression.model_b)
    annotation = annotate(us_package.verdict, priority)
    suggestions = suggest_followups(priority.question_scores)
    if annotation.verdict_state != us_package.verdict.state:
        raise PackageIntegrityError("review priority changed the safety verdict")
    say("--- 선택 확장: 검토 우선순위. 안전 판정을 바꾸지 않는다. ---")
    say(
        "Ridge/Logistic 점수는 합성 라벨에 맞춘 것이다. "
        f"ridge={priority.ridge_priority:.4f}, "
        f"logistic={priority.logistic_review_probability:.4f}. "
        "성능 지표로 인용하지 않는다."
    )
    say(f"확장 모듈 호출 뒤에도 판정은 {annotation.verdict_state}.")
    for suggestion in suggestions:
        say(suggestion)
    if us_package.verdict.state != "Confirmed" or not matched or not same_fingerprint:
        raise PackageIntegrityError("scripted handoff did not reproduce and confirm the synthetic failure")
    if any(suggestion in us_package.model_dump_json() for suggestion in suggestions):
        raise PackageIntegrityError("extension suggestions were written into the package")
