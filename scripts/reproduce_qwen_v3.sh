#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo 'Usage: bash scripts/reproduce_qwen_v3.sh MODEL_DIR OUTPUT_DIR' >&2
  exit 1
fi
# Run with the pinned environment activated and this package installed.
model_dir=$(realpath -m "$1")
output_dir=$(realpath -m "$2")
python -I -m typo_math_audit.qwen_v3 acquire --model-dir "$model_dir"
python -I -m typo_math_audit.qwen_v3 run --phase pilot --model-dir "$model_dir" --out "$output_dir/pilot"
python -I -m typo_math_audit.qwen_v3 run --phase eval --model-dir "$model_dir" --out "$output_dir/eval" --pilot "$output_dir/pilot"
python -I -m typo_math_audit.qwen_v3 report "$output_dir/eval"
python scripts/offline_exec.py "$(command -v python)" -I -m typo_math_audit.qwen_v3 run --phase replay --model-dir "$model_dir" --out "$output_dir/replay" --pilot "$output_dir/pilot"
python scripts/check_qwen_v3.py --root "$output_dir" --model-dir "$model_dir" --require-replay
