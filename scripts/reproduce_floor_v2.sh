#!/usr/bin/env bash
# Uses the installed frozen CLI. Both arguments point outside the checkout.
set -euo pipefail
if [[ $# != 2 ]]; then
  echo 'Usage: reproduce_floor_v2.sh MODEL_DIR OUTPUT_ROOT' >&2
  exit 1
fi
model_dir=$1
output_root=$2
mkdir -p "$output_root"
typo-math-audit acquire --model-dir "$model_dir"
typo-math-floor run --model-dir "$model_dir" --out "$output_root/pilot"
typo-math-floor audit --run "$output_root/pilot"
typo-math-floor gate --run "$output_root/pilot" > "$output_root/gate.json.partial"
mv "$output_root/gate.json.partial" "$output_root/gate.json"
selection=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["selected"] or "FAIL")' "$output_root/gate.json")
if [[ $selection == FAIL ]]; then
  echo 'Completed negative gate: no typo-robustness inference is authorized.'
  typo-math-floor run --model-dir "$model_dir" --out "$output_root/offline-replay" --replay
  typo-math-floor compare "$output_root/pilot" "$output_root/offline-replay"
else
  typo-math-floor run --model-dir "$model_dir" --out "$output_root/final" --phase eval --pilot "$output_root/pilot"
  typo-math-floor audit --run "$output_root/final"
  typo-math-floor run --model-dir "$model_dir" --out "$output_root/offline-replay" --phase eval --pilot "$output_root/pilot" --replay
  typo-math-floor compare "$output_root/final" "$output_root/offline-replay"
fi
