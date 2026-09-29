# Reproduction and artifacts

## Files

Each run directory includes:

| File | Meaning |
|---|---|
| `run.json` | Complete run configuration, protocol digest, split and initial UTC start |
| `questions.jsonl` | Original questions, operands, direct answers and independent oracle answers |
| `cases.jsonl` | Seven prompts per question with edit spans and realized rates |
| `outputs.jsonl` | Actual completions, input/output token IDs, hashes, timings, termination flags and scores |
| `session-*.json` | Structured experiment metadata: runtime, environment, process peak RSS and completion status |
| `status.json` | Latest invocation state; use `audit` to check actual output completeness |
| `summary.json` | Paired statistics, uncertainty intervals, denominators and artifact sizes |
| `report.md` | Readable tables and limitations |

`record_sha256` is SHA-256 of compact, key-sorted, UTF-8 JSON for every field
except itself. JSONL files end every committed record with a newline. Input
hashes include exact whitespace. Prompt hashes refer to user text; rendered-prompt
hashes include chat-template special tokens and system text. Input-token hashes
cover canonical JSON arrays. Output token IDs include EOS if emitted; the raw
completion retains decoded special tokens. The score parses the version with
special tokens removed.

`artifacts.json` covers the publishable tree, excluding itself. `check_artifacts.py`
checks the inventory and rejects files over 10 MiB, trees over 32 MiB or over
1,000 files, unwanted logs, model files and wheel files. To seal a deliberately
changed release, run `python3 scripts/check_artifacts.py --seal`; ordinary
verification never overwrites the manifest. The scientific code and protocol
must still match their pre-evaluation freeze.

## Installed offline replay

The replay must not import an editable source checkout or fetch dependencies on
demand. First, while online, download the locked dependency wheels, build the
project wheel after protocol freeze, and place it beside them:

```bash
python -m pip download --dest /tmp/typo-wheelhouse \
  --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock pip==25.0.1
python -m build --wheel --no-isolation --outdir /tmp/typo-wheelhouse
```

With model files already acquired, install into a new virtual environment under
a Linux x86_64 seccomp filter that denies IPv4 and IPv6 socket creation. The
helper bootstraps pip from the acquired wheel; it does not require network access
or the system `ensurepip` module:

```bash
python3 scripts/offline_exec.py /usr/bin/python3 \
  scripts/create_offline_env.py /tmp/typo-wheelhouse /tmp/typo-offline-env
```

Then, from outside the source checkout, run the installed entry point under the
same guard. Use absolute paths to the helper, model directory and output:

```bash
python3 /absolute/checkout/scripts/offline_exec.py \
  /tmp/typo-offline-env/bin/typo-math-audit run \
  --model-dir /tmp/typo-audit-model --out /tmp/typo-offline-output
```

The guard positively tests that AF_INET and AF_INET6 sockets fail with permission
denied, sets Hugging Face offline flags, and execs the target so the kernel filter
is inherited. It is a reproducibility check, not a general-purpose security
sandbox: local UNIX sockets and preexisting descriptors are not blocked. The
model is loaded from a hash-verified local directory with remote code disabled.
`create_offline_env.py` checks that the package import originates in its new venv,
removes PYTHONPATH/PYTHONHOME for installation subprocesses, and uses no system
site packages. Dependency versions and source hashes are checked by the runner.

Compare the completed replay with the original:

```bash
typo-math-audit compare results/final /tmp/typo-offline-output
```

A replay may have different timestamps and durations. All scientific row fields,
including raw text, parsed results and exact token IDs, must match. The checked-in
`results/offline-replay` directory preserves actual replay evidence; it is not a
copy of the original output.

## Interpretation and operational limits

The 24-token cap bounds generation work per example. The five-hour runtime budget
includes verification and model loading and is anchored to the first run start.
Resume after that deadline is rejected; start a new directory for a new run.
SIGINT/SIGTERM metadata captures recorded invocation time. SIGKILL or machine loss
may omit the final session timing. Surviving committed rows are validated on
resume; file fsync is not a filesystem-wide transaction or a guarantee against
hardware power loss. The
reported peak RSS is the Linux process high-water mark, not total system memory
or an isolated model-weights measurement. It includes initialization/imports.

The dependency lock is version-pinned rather than a cross-platform environment
specification. Exact greedy reproducibility is checked on one CPU architecture
and numerical stack. Different processors or package builds are not certified.
Never describe partial or estimated outputs as completed measurements.

## Recovery test with the actual model

The separate [recovery-check evidence](../results/recovery-check/verification.json)
records a SIGTERM after one actual completion, an intentionally torn trailing
JSON record, and a resumed seven-completion checkpoint. The committed prefix
remained identical, and all seven scientific rows matched the original pilot,
including token IDs. This ran through the installed CLI with the kernel offline
guard. It is a bounded integration test, not an additional evaluation sample.

To rerun it without changing checked-in evidence:

```bash
python3 scripts/check_recovery.py \
  --cli /tmp/typo-offline-env/bin/typo-math-audit \
  --model-dir /tmp/typo-audit-model --reference results/pilot
```

It uses a fresh temporary directory and removes it after a successful check.
`python scripts/check_statistics.py` recomputes all stored scientific summaries
and bootstrap intervals without overwriting reports or timing metadata.

The original evaluation and offline replay were run concurrently on this shared
CPU host, with a short recovery check during their opening phase. Their recorded
wall times therefore include resource contention. They are actual execution
costs for these invocations, not isolated model throughput benchmarks. Each
process uses the frozen one-thread numerical settings; concurrent scheduling
changes timings but is not intended to change generated tokens.
