from pathlib import Path

import pytest

from fts.adapters.base import SubmissionState, not_evaluated_verdict
from fts.adapters.carla import CarlaWorker
from fts.adapters.external_sil import ExternalSilAdapter
from fts.adapters.replay import ReplayWorker
from fts.canonical import content_hash
from fts.errors import AdapterUnavailable
from fts.execute import comparison_dict, run_request
from fts.kpi.evaluator import evaluate_log
from fts.jobs.clock import FakeClock, SequenceIds
from fts.jobs.control import JobService
from fts.jobs.store import MemoryStore
from fts.receive import us_continue
from fts.reproduce import check_package
from fts.scenarios.rainy_night import discovery_request
from fts.walkthrough import run_walkthrough

ROOT = Path(__file__).resolve().parents[1]


def test_replay_is_deterministic_and_the_candidate_regresses():
    request = discovery_request()
    first = run_request(ReplayWorker(), request)
    second = run_request(ReplayWorker(), request)
    assert content_hash([log.model_dump(mode="json") for log in first]) == content_hash(
        [log.model_dump(mode="json") for log in second]
    )
    report_a = evaluate_log(first[0])
    report_b = evaluate_log(first[1])
    assert report_a.collision is False
    assert report_a.lane_departure is False
    assert report_a.min_distance_m >= 1.5
    compared = comparison_dict(first[0], first[1])
    assert compared["material"] is True
    assert "new_collision" in compared["reasons"]
    assert "new_lane_departure" in compared["reasons"]
    assert report_b.collision is True

    shifted = request.model_copy(update={"seed": request.seed + 1})
    shifted_compared = comparison_dict(*run_request(ReplayWorker(), shifted))
    assert shifted_compared["kpi_fingerprint"] != compared["kpi_fingerprint"]


def test_receiving_region_does_not_read_the_discovery_catalog(tmp_path, monkeypatch):
    import fts.receive as receive
    import fts.reproduce as reproduce
    import fts.scenarios.rainy_night as catalog

    for module in (receive, reproduce):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "rainy_night" not in source
        assert "scenarios" not in source

    walk = run_walkthrough(evidence_dir=tmp_path / "logs", uri_prefix="repo://tmp")
    package_json = walk.kr_package.model_dump_json()

    def explode():
        raise AssertionError("discovery catalog was consulted during US continuation")

    monkeypatch.setattr(catalog, "discovery_request", explode)
    fresh_jobs = JobService(MemoryStore(), FakeClock(), SequenceIds(), lease_ttl_s=3600)
    continued = us_continue(
        package_json,
        evidence_dir=tmp_path / "us",
        uri_prefix="repo://tmp-us",
        jobs=fresh_jobs,
    )
    assert continued.reproduction is not None
    assert continued.reproduction.matched
    assert continued.verdict.state == "Confirmed"
    assert continued.observed_regression.kpi_fingerprint == walk.kr_package.observed_regression.kpi_fingerprint


def test_committed_packages_reproduce_for_a_third_party():
    kr = check_package(ROOT / "examples" / "handoff" / "kr_discovery.json")
    us = check_package(ROOT / "examples" / "handoff" / "us_return.json")
    assert kr.ok and kr.fingerprint_match
    assert us.ok and us.fingerprint_match and us.variant_matches == [True]
    assert any(note.startswith("matched ") for note in kr.artifact_notes)
    assert any(note.startswith("matched ") for note in us.artifact_notes)


def test_stubs_do_not_invent_logs():
    request = discovery_request()
    for adapter in (CarlaWorker(), ExternalSilAdapter()):
        submission = adapter.submit(request)
        assert submission.state is SubmissionState.UNAVAILABLE
        verdict = not_evaluated_verdict(submission.detail)
        assert verdict.state == "Not Evaluated"
        with pytest.raises(AdapterUnavailable):
            adapter.fetch_results(submission.submission_id)
