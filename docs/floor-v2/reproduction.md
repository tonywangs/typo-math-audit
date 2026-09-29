# Reproduce the separately frozen floor experiment

Keep the original experiment in `results/final`, `results/pilot`, and the other
historical directories intact. Version 2 lives in `results/floor-v2` and uses a
separate `typo-math-floor` CLI. Its immutable preregistration is packaged as
`src/typo_math_audit/assets/floor-v2-protocol.json`.

Use Linux x86_64, Python 3.12.3, and the exact pinned dependencies. Install the
project wheel with no dependency resolution after installing `requirements.lock`:

```bash
python3.12 -m venv /tmp/typo-floor-env
source /tmp/typo-floor-env/bin/activate
python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock
python -m pip install --no-deps --no-build-isolation .
```

Then one reproduction command downloads/verifies the public pinned model, runs
the pilot, applies the frozen gate and runs the preregistered replay. It runs the
held-out typo evaluation only if the gate passes:

```bash
bash scripts/reproduce_floor_v2.sh /tmp/typo-floor-model /tmp/typo-floor-reproduction
```

The model acquisition uses public HTTPS without account tokens. The model takes
about 273 MB outside the checkout. Allow roughly 1–2 GB of process memory. The
pilot budget is 30 minutes and the conditional final budget is three hours;
loading and downtime after interruption count. The replay has its own 30-minute
budget. A run cannot extend its original wall deadline by restarting. Exit 2
means checkpointed, interrupted or exhausted, and is never evidence of completion.
A complete negative pilot is a successful experiment and the wrapper exits 0
only after its replay matches. The wrapper's directory name `offline-replay`
describes local-files-only inference; kernel enforcement is an additional step
below. Reproduction creates scientific records and a gate decision. The checked-in
independent checker verifies the published summaries against the published run.

## Isolated installed CLI validation

The recorded replay uses a separate wheel installation with no source checkout
on Python's import path. To rebuild that isolation, download the pinned wheels
and one pip wheel into a wheelhouse, add the project wheel built by
`python -m build --wheel --no-isolation`, and use:

```bash
python3 scripts/offline_exec.py /path/to/bootstrap/python scripts/create_offline_env.py /path/to/wheelhouse /tmp/floor-offline-env
python3 scripts/offline_exec.py /tmp/floor-offline-env/bin/python -I -m typo_math_audit.floor_v2 run --model-dir /tmp/typo-floor-model --out /tmp/floor-offline-replay --replay
```

The inherited Linux seccomp guard refuses IPv4 and IPv6 sockets and verifies both
refusals before `exec`. It is an offline check, not a general-purpose sandbox.
The second command performs the failed-gate development replay: 42 distinct
questions, balanced across families, with formats assigned by question index
modulo three. If the gate passes instead, use `--phase eval --pilot PILOT` for
the preregistered 42 held-out question/condition pairs. The reference and replay
use different run hashes because their case inventories differ. Comparison checks
all scientific fields, ignoring only those run hashes, wall timing and dependent
record seals. Both run specifications must still independently audit.

## Verify published evidence

```bash
python3 scripts/check_artifacts.py
python -m pytest -q
python scripts/check_floor_v2.py --require-replay --model-dir /tmp/typo-floor-model
python scripts/check_floor_v2_recovery.py
```

The first check and independent count check (without `--model-dir`) do not need
model inference. The optional model argument retokenizes every prompt and decodes
every recorded completion using the verified tokenizer. The recovery check verifies
preserved real-model SIGTERM, torn-tail recovery and matching resumed records;
`--execute` is only for creating evidence in an absent recovery directory.
Prerecorded protocol/scorer tests are hash-frozen; later independent-checker tests
are separately identified in the test tree. Tests use fake engines except for the
explicitly recorded real-model experiment; they do not imply unrun model tests.
