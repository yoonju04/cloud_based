import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fts.canonical import content_hash
from fts.cli import _dump
from fts.domain.package import HandoffPackage, Verdict, seal, verify_content_hash
from fts.walkthrough import run_walkthrough

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "handoff.package.v1.schema.json"


@pytest.fixture(scope="module")
def sealed_packages(tmp_path_factory):
    out = tmp_path_factory.mktemp("pkg")
    return run_walkthrough(evidence_dir=out / "logs", uri_prefix="repo://examples")


def test_content_hash_ignores_its_own_field_and_key_order(sealed_packages):
    package = sealed_packages.kr_package
    assert verify_content_hash(package)
    assert seal(package).content_hash == package.content_hash

    body = package.model_dump(mode="json")
    body.pop("content_hash")
    reversed_body = json.loads(json.dumps(body))
    reversed_body = {key: reversed_body[key] for key in reversed(list(reversed_body))}
    assert content_hash(body) == content_hash(reversed_body) == package.content_hash


def test_tamper_breaks_the_hash_until_reseal(sealed_packages):
    body = sealed_packages.kr_package.model_dump(mode="json")
    body["root_cause"]["statement"] = "tampered hypothesis"
    tampered = HandoffPackage.model_validate(body)
    assert not verify_content_hash(tampered)
    resealed = seal(tampered)
    assert verify_content_hash(resealed)
    assert resealed.content_hash != sealed_packages.kr_package.content_hash


def test_json_roundtrip_keeps_the_hash(sealed_packages):
    text = _dump(sealed_packages.us_package)
    loaded = HandoffPackage.model_validate_json(text)
    assert verify_content_hash(loaded)
    assert loaded.content_hash == sealed_packages.us_package.content_hash
    assert loaded.parent_content_hash == sealed_packages.kr_package.content_hash


def test_inconclusive_without_follow_up_is_rejected():
    with pytest.raises(ValidationError, match="follow-up"):
        Verdict(state="Inconclusive", rationale="open", follow_up_tasks=[])


def test_claims_cannot_pretend_this_is_real_42dot_data(sealed_packages):
    body = sealed_packages.kr_package.model_dump(mode="json")
    body["claims"]["real_42dot_data"] = True
    body["content_hash"] = None
    with pytest.raises(ValidationError):
        HandoffPackage.model_validate(body)


def test_confirmed_requires_a_matching_reproduction(sealed_packages):
    body = sealed_packages.kr_package.model_dump(mode="json")
    body["verdict"] = {"state": "Confirmed", "rationale": "too early", "follow_up_tasks": []}
    body["content_hash"] = None
    with pytest.raises(ValidationError, match="Confirmed"):
        HandoffPackage.model_validate(body)


def test_not_evaluated_rejects_invented_kpis(sealed_packages):
    body = sealed_packages.kr_package.model_dump(mode="json")
    body["verdict"] = {
        "state": "Not Evaluated",
        "rationale": "adapter unavailable",
        "follow_up_tasks": [],
    }
    body["content_hash"] = None
    with pytest.raises(ValidationError, match="Not Evaluated"):
        HandoffPackage.model_validate(body)


def test_models_must_be_baseline_then_candidate(sealed_packages):
    body = sealed_packages.kr_package.model_dump(mode="json")
    body["models"] = list(reversed(body["models"]))
    body["content_hash"] = None
    with pytest.raises(ValidationError, match="baseline A"):
        HandoffPackage.model_validate(body)


def test_schema_file_matches_the_pydantic_model():
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == HandoffPackage.model_json_schema()
    encoded = json.dumps(committed)
    for state in ("Confirmed", "No Material Regression", "Inconclusive", "Not Evaluated"):
        assert state in encoded


def test_committed_examples_match_a_fresh_walkthrough(tmp_path):
    fresh = run_walkthrough(evidence_dir=tmp_path / "logs", uri_prefix="repo://examples")
    kr_path = ROOT / "examples" / "handoff" / "kr_discovery.json"
    us_path = ROOT / "examples" / "handoff" / "us_return.json"
    assert kr_path.read_text(encoding="utf-8") == _dump(fresh.kr_package)
    assert us_path.read_text(encoding="utf-8") == _dump(fresh.us_package)
