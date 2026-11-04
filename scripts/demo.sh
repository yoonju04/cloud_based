#!/usr/bin/env bash
# One command for the local KR -> US handoff.
# Creates a virtualenv on first use, installs the pinned dependencies, runs the demo.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m fts demo
