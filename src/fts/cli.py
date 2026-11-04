"""Command line. ``python -m fts demo`` is the local walkthrough."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fts import NORTH_STAR, __version__
from fts.canonical import normalize
from fts.domain.package import HandoffPackage
from fts.reproduce import check_package
from fts.walkthrough import run_walkthrough


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fts", description=NORTH_STAR)
    parser.add_argument("--version", action="version", version=f"fts {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Run the hypothetical KR to US handoff locally")
    demo.add_argument("--out", default="var/demo", help="Directory for this run's JSON artifacts")

    repro = sub.add_parser("repro", help="Reproduce a package file with no extra context")
    repro.add_argument("package", type=Path)

    sub.add_parser("generate-examples", help="Rewrite examples/ from the scripted walkthrough")
    sub.add_parser("export-schema", help="Rewrite schema/handoff.package.v1.schema.json")

    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo(Path(args.out))
    if args.command == "repro":
        return _repro(args.package)
    if args.command == "generate-examples":
        return _generate_examples(Path.cwd())
    if args.command == "export-schema":
        return _export_schema(Path.cwd() / "schema" / "handoff.package.v1.schema.json")
    return 2


def _demo(out_dir: Path) -> int:
    result = run_walkthrough(evidence_dir=out_dir / "logs", uri_prefix=f"repo://{out_dir.as_posix()}")
    handoff = out_dir / "handoff"
    handoff.mkdir(parents=True, exist_ok=True)
    kr_path = handoff / "kr_discovery.json"
    us_path = handoff / "us_return.json"
    kr_path.write_text(_dump(result.kr_package), encoding="utf-8")
    us_path.write_text(_dump(result.us_package), encoding="utf-8")
    for line in result.lines:
        print(line)
    kr_check = check_package(kr_path)
    us_check = check_package(us_path)
    print(f"제3자 재현 검사 {kr_path}: {'통과' if kr_check.ok else '실패'}")
    print(f"제3자 재현 검사 {us_path}: {'통과' if us_check.ok else '실패'}")
    if result.us_package.verdict.state != "Confirmed" or not kr_check.ok or not us_check.ok:
        print("데모가 패키지 재현에 실패했다.", file=sys.stderr)
        return 1
    print("로컬 데모가 끝났다. 수치는 이 가상 장면의 재실행이며, 측정된 성능이 아니다.")
    return 0


def _repro(path: Path) -> int:
    report = check_package(path)
    print(f"package_id={report.package_id}")
    print(f"content_hash={report.content_hash}")
    print(f"fingerprint_match={report.fingerprint_match}")
    print(f"variant_matches={report.variant_matches}")
    for note in report.artifact_notes:
        print(note)
    print(report.detail)
    return 0 if report.ok else 1


def _generate_examples(root: Path) -> int:
    result = run_walkthrough(evidence_dir=root / "examples" / "logs", uri_prefix="repo://examples")
    handoff = root / "examples" / "handoff"
    handoff.mkdir(parents=True, exist_ok=True)
    (handoff / "kr_discovery.json").write_text(_dump(result.kr_package), encoding="utf-8")
    (handoff / "us_return.json").write_text(_dump(result.us_package), encoding="utf-8")
    print(result.kr_package.content_hash)
    print(result.us_package.content_hash)
    return 0


def _export_schema(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = HandoffPackage.model_json_schema()
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)
    return 0


def _dump(package: HandoffPackage) -> str:
    return json.dumps(normalize(package.model_dump(mode="json")), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
