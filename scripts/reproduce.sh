#!/usr/bin/env bash
# Usage: bash scripts/reproduce.sh MODEL_DIRECTORY NEW_OUTPUT_DIRECTORY
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/reproduce.sh MODEL_DIRECTORY NEW_OUTPUT_DIRECTORY' >&2
  exit 1
fi
# Dependencies must already be installed from requirements.lock, and the project
# installed normally (not necessarily editable). Acquisition is the only network step.
typo-math-audit acquire --model-dir "$1"
typo-math-audit run --model-dir "$1" --out "$2"
typo-math-audit audit --run "$2"
typo-math-audit report --run "$2"
