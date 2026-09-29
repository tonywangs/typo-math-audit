# Experiment method

## Design

The full machine-readable protocol is shipped as
`src/typo_math_audit/assets/protocol.json`. It is created only after the completed
development pilot and checked before every evaluation run. It binds source
hashes, model-file hashes, dependency versions, Python version, datasets,
perturbations, inference settings, scoring, uncertainty estimates and a five-hour
per-run budget. Freeze time and pilot output hash establish the recorded ordering;
this is a local freeze, not an externally timestamped preregistration.

For each of addition, subtraction and multiplication, generate the 231 unordered
pairs from integers 0–20, shuffle with Python's seeded RNG (seed 20260929 plus
family index), take the first ten for development and the next seventy for
evaluation. Subtraction orders operands to keep answers nonnegative. Addition and
multiplication use ascending operand order, so they are not representative of
arbitrary arithmetic questions. There are 30 development and 210 evaluation
instances. An instance is its family and unordered operand pair. No instance
crosses splits; template and operand distributions are shared. Independent
oracles count concatenated lists, remaining list entries, or Cartesian-product
entries and must match the direct arithmetic calculation.

All questions use this user template, preceded by the model's chat template with
system text `You are a helpful assistant.`:

```text
Please carefully calculate the following simple arithmetic problem below.
{a} {operator} {b}
Reply with only the integer answer.
```

Only `Please`, `carefully`, `following`, `simple`, and `below` are eligible. Numbers,
operators, the mathematical instruction and the entire answer instruction are
protected. There are no personal names in the generated questions; the allowlist
also protects other words such as names in invariant tests. General name
recognition is not implemented. This is not an arbitrary-text typo service.

## Perturbations

Each original question has clean plus six conditions: adjacent transposition,
character deletion, and horizontal US-QWERTY neighbor substitution, each at 20%
and 40% of eligible words. Uniformly shuffle the five eligible word occurrences
and edit the first one or two. Choose one character position per selected word;
swaps choose an adjacent pair with unequal characters. Deletions remove one
character; substitutions choose an immediate neighbor in `qwertyuiop`,
`asdfghjkl`, or `zxcvbnm` and preserve that character's case. A swap involving
initial capitalization can move it. The per-question/type seed is SHA-256 of
`83171:{question_id}:{type}`, interpreted as an integer. Low-level edits are nested
inside the high level for that type; different types use independent seeds.

Rates are 1/5 and 2/5 of eligible words, but 1/15 and 2/15 of all alphabetic words.
They are not character corruption probabilities. Every edit stores original user
prompt offsets, before/after text, word boundaries and original word. We record
changed words, character operations and touched original characters separately.
The same edit can make a valid but unintended word; every changed variant is
conservatively marked `possible_meaning_change=true`, with no claim of manual
semantic validation. Ineligible or unchangeable inputs retain unchanged variants
rather than silently dropping them. The frozen generated dataset has five
eligible words for every question.

## Model and scoring

The model revision and eight file hashes are in `assets/model.json`. Weights are
never tracked. Acquisition uses revision-specific public HTTPS URLs, validates
SHA-256 and size, then renames each complete file. Inference uses local files
only, disables remote model code, and checks all hashes before loading.

Inference is CPU float32, one intra-op and one inter-op thread, eager attention,
MKLDNN disabled, evaluation mode, no gradient computation, greedy decoding,
one beam, KV cache, one example at a time, 24 new tokens, fixed seed 1907 and
PyTorch deterministic algorithms. The upstream chat template is hash-pinned with
the tokenizer. A fresh GenerationConfig prevents upstream sampling defaults from
leaking into the experiment. Library defaults are fixed by the dependency lock.
The order is family, question, clean, then each typo type at low and high level.
It is fixed rather than randomized; do not interpret timing differences causally.

Strip surrounding whitespace and require the entire decoded response to match
`[+-]?[0-9]+`. An integer equal to the oracle answer is correct only if not
truncated. Prose, equations, multiple numbers, decimals, Unicode digits and empty
responses are invalid. Leading zeros and explicit plus signs are accepted. EOS
is removed for parsing but retained in `raw_completion` and output token IDs.
Hitting 24 tokens without EOS is truncated and always incorrect, even if the
prefix looks like a correct integer. Invalid and truncated rates are reported
separately. This intentionally measures arithmetic-plus-format compliance.

## Paired analysis

For each condition report correct/N, accuracy, corrupted minus clean accuracy,
and the four cells of the paired correctness table. Clean-correct→incorrect is
reported both over N and as a conditional rate over the clean-correct count in
machine-readable results; a zero clean-correct denominator yields null, not zero.
Accuracy differences may be negative, zero or positive.

Use 10,000 bootstrap resamples with NumPy seed 62103, resampling original
questions within family and keeping all seven variants of each question together.
Report marginal percentile 95% intervals, without multiple-comparison correction.
These intervals do not measure uncertainty across templates, models or typo
mechanisms. They should not be read as confirmatory significance tests. With
`--allow-partial`, analysis explicitly excludes incomplete clusters and reports
how many records were excluded; complete reporting rejects missing output.

## Durability and reproducibility

The runner uses a single-writer OS lock, immutable run metadata and validated
input regeneration. Each output has a canonical JSON SHA-256 seal; it is flushed
and fsynced after generation. Resume verifies the full ordered prefix, including
recomputed scores and input hashes. A non-newline final tail is preserved as hex
in a recovery JSON file and discarded; damaged complete records fail closed.
SIGINT/SIGTERM are checked between generated tokens and before record commit.
An interrupted completion is retried, not counted as a failed answer. Session
metadata records interruption status and process peak RSS. SIGKILL cannot record
its final session timings, a documented recovery limitation.

The wall budget is anchored to the first invocation's UTC start, so a paused
run does not silently receive a fresh allowance. To reproduce later, use a new
output directory. Timestamps and timings are expected to differ; scientific
fields and token IDs are compared exactly in deterministic replay. A hash is an
integrity check, not an authenticated signature. Different hardware/software
may produce different numerical outcomes even with greedy decoding.
