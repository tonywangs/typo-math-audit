# typo-math-audit

A reproducible CPU experiment measuring how controlled spelling errors affect
SmolLM2-135M-Instruct's responses to simple arithmetic expressions. It preserves
exact prompts, edits, token IDs, completions, strict scores and paired uncertainty.
It is a deliberately narrow experiment, not a new robustness benchmark.

**Observed result:** 0/210 strict correct responses in the clean condition and
in each of the six typo conditions. This is a format/truncation floor, not
evidence of typo robustness. All 1,470 planned evaluations were actually run.
Read the [result interpretation](results/final/interpretation.md) alongside the
accuracy tables. A separately wheel-installed CLI reproduced all 1,470
scientific output records exactly with IPv4/IPv6 socket creation blocked.
The 35-test suite and real-model cancellation/recovery check also passed.

## Read the evidence

- [Frozen evaluation report](results/final/report.md)
- [Development pilot](results/pilot/report.md)
- [Method and limitations](docs/method.md)
- [Related research and implementations](docs/related-work.md)
- [Frozen protocol](src/typo_math_audit/assets/protocol.json)
- [Model revision and file hashes](src/typo_math_audit/assets/model.json)

There are 210 held-out questions (70 each for addition, subtraction and
multiplication), each evaluated clean and under six typo conditions: transposition,
deletion and keyboard-neighbor substitution, at 20% and 40% of **eligible words**.
Only five optional words can be edited; the rates over all prompt words are 6.67%
and 13.33%. Numbers, operators and answer instructions are protected. Development
and evaluation instances are disjoint, but use the same template and operand range.

The score requires a whole-integer response and treats invalid or truncated
outputs as incorrect. It measures arithmetic **and format compliance**. Poor
baseline accuracy, unchanged scores and improvements are valid results. Read the
report before interpreting any accuracy change as mathematical robustness.

## Setup and reproduce

The reference environment is Linux x86_64, Python **3.12.3**, CPU-only PyTorch.
The frozen runner checks exact dependency and Python versions; other platforms
need a separately versioned experiment, not an unnoticed change to this one.
Model files total about 273 MB and stay outside the repository. Allow roughly
1–2 GB of process memory; measured runtime and peak RSS are in the report.
No GPU, paid inference or account token is used.

```bash
python3.12 -m venv /tmp/typo-audit-env
source /tmp/typo-audit-env/bin/activate
python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock
python -m pip install --no-deps --no-build-isolation .
```

With that environment activated, one command acquires and verifies the pinned
model, runs all 1,470 evaluations, audits the artifacts and writes the report:

```bash
bash scripts/reproduce.sh /tmp/typo-audit-model /tmp/typo-audit-reproduction
```

Use a new output directory for a new experiment. Repeating the same command
resumes a validated prefix if its five-hour wall budget has not expired. A
completed directory is verified rather than regenerated. Nothing is downloaded
by `run`; only `acquire` accesses the network, and it skips hash-valid local files.
For an entirely offline inference command after acquisition:

```bash
typo-math-audit run --model-dir /tmp/typo-audit-model --out /tmp/typo-audit-offline
```

Exit 0 means complete; exit 2 means checkpointed, cancelled or budget-exhausted;
exit 1 means an input/configuration error. SIGINT or SIGTERM stops between tokens
without scoring a partial answer. `--limit 7` makes a seven-completion checkpoint
for a short smoke test. `audit` normally rejects incomplete runs; exploratory
`report --allow-partial` explicitly excludes incomplete question clusters.

## Verify without rerunning the model

```bash
python3 scripts/check_artifacts.py
python -m pytest -q
typo-math-audit audit --run results/final
typo-math-audit compare results/final results/offline-replay
```

The first command needs only the Python standard library and Git. It checks the
release inventory, SHA-256 hashes, frozen sources, exact regenerated questions
and edits, independently recomputed scores, and complete paired output. Tests
exercise the oracle, splits, perturbation invariants, parsing, known paired
statistics, model hashes, single-writer locking, cancellation, recovery and
corruption rejection. The replay comparison ignores only timings and the record
hash that depends on timings.

[Reproduction details](docs/reproduction.md) explain the separately installed,
kernel-enforced offline replay. Model weights, wheels and virtual environments
are intentionally excluded from the tracked tree. Artifact SHA-256 checks detect
accidental corruption; they are not an authenticated signature.
