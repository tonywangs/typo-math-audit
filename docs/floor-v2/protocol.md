# Floor recovery experiment, version 2

This is a separate experiment, not a replacement scoring of the historical study.
The historical dataset, protocol, outputs, scores and interpretation remain intact.
The objective is to decide whether a bounded prompt intervention supplies a usable
baseline for a subsequent typo study. No novelty is claimed.

## Design fixed before development inference

Use the same hash-pinned SmolLM2-135M-Instruct revision and dependency lock as v1.
CPU float32, eager attention, one intra/inter-op thread, MKLDNN disabled,
deterministic algorithms, seed 1907, greedy decoding, batch size one, cache enabled.
Increase the output cap from 24 to 64 tokens; EOS remains the sole normal stop.
No constrained decoding, retries, answer repair, or selection from sampled answers.
The system message remains `You are a helpful assistant.`

Exactly three user prompt formats share this prefix:

```
Please carefully calculate the following simple arithmetic problem below.
{expression}
```

Their suffixes, in fixed order, are:

1. `Reply with only the integer answer. No explanation.`
2. `Reply in this format: Answer: <integer>. No explanation.`
3. `Write only the completed equation, like 21 + 1 = 22. No explanation.`

The third is a single demonstration of output form outside the operand range;
it is not a development or evaluation question. This pilot tests pragmatic
configurations, not a factorial estimate of separate prompt and length effects.

Each family uses unordered operand pairs in 0..20 (subtraction larger first).
Exclude the union of both historical splits, shuffle the remaining pairs with
seed 20260930 + family index, take 14 development and the next 70 evaluation
pairs. Family is part of instance identity. This gives 42 new development and
210 reserved evaluation questions. Check both ordered expressions and unordered
family/pair identities. Verify arithmetic with the old independent counting oracle.

Pilot: clean prompts only, question-major then the three formats, 126 completions.
Budget: 1,800 elapsed seconds, including model loading and any resume downtime,
starting when the run metadata is created. Preserve incomplete runs; an incomplete
pilot fails the gate. Never add formats or extend the budget based on outcomes.

## Scoring and selection

Strip leading/trailing whitespace. Accept only these whole-response grammars:
ASCII signed integer; `Answer: N` or `The answer is N` (case-insensitive, optional
final period); or the exact input equation `a op b = N` (optional final period,
whitespace around tokens, ASCII digits, literal operator). No prose number search,
LaTeX, markdown, decimal numbers, thousands separators, multiple answers, repeated
labels, or mismatched left-hand sides. Integers are limited to 9 digits.
A complete integer, label, or equation is *unambiguous extraction* even if wrong.
Truncated responses always fail extraction and accuracy; potential pre-truncation
parses are preserved separately. Strict compliance means a nontruncated response
matches the requested format (integer, `Answer: N`, or exact equation).
Accuracy is correct unambiguous extraction divided by all assigned questions,
including invalid/truncated outputs in the denominator. Strict correctness is
reported separately. Invalid text with multiple standalone numeric tokens is
flagged as potentially ambiguous, not asserted to have multiple semantic answers.
Other invalid text is an unsupported format, not automatically wrong arithmetic.

A configuration passes only with >=25% accuracy AND >=80% extraction on all 42
questions (at least 11 correct and 34 extracted). Among passing configurations,
select greatest number correct, then greatest extraction, then fixed format order.
No passing format: stop, publish the floor diagnosis, decline to infer typo
robustness. Development success is selection-biased, not a held-out estimate.

If the gate passes, freeze the selected configuration, source hashes, exact
held-out inputs, model/environment and scoring protocol before evaluation.
Run 210 questions with clean plus all six existing typo conditions, reusing the
v1 perturbation algorithm. Preserve expressions, answer instructions, edit locations
and realized rates. Final inference budget: 10,800 elapsed seconds including
loading and resume downtime. No evaluation-dependent retuning. Reuse the v1
question-clustered family-stratified percentile bootstrap (10,000 resamples, seed
62103); report paired accuracy changes, extraction, strict compliance, truncation,
and clean-correct flips. If evaluation remains incomplete, label it incomplete.

## Validation fixed before inference

Replay subset: if the gate fails, all 14 development questions per family, each replayed in one format
chosen by its within-family index modulo 3 (42 distinct clean question/condition
pairs, stratified by family and spread 5/5/4 across formats in each family). If it passes,
the first 2 evaluation questions per family across all 7 conditions (42 pairs).
Replay uses a separately wheel-installed CLI, isolated Python import path and the
existing kernel guard denying Internet sockets. Compare every scientific record
field except elapsed timing and its dependent record hash. No model file goes in
Git. Test cancellation, torn-record recovery, complete-record corruption rejection,
scoring adversaries, disjointness and protected perturbations. Independently
recompute counts using a separate implementation. Scientific run metadata may be
stored under results; agent transcripts, operational handoffs and control reports
must stay outside this repository.

Hash this document, all new inference/scoring/data source, historical inputs,
model manifest, dependencies and test fixtures into `floor-v2-protocol.json`
before the first pilot completion. Timestamp and verify it at every invocation.
