# A usable extraction baseline was not established

**Decision: fail the preregistered development gate. No new typo evaluation was
run, and this experiment makes no inference about typo robustness.** All 126
planned development completions finished within the 30-minute pilot budget.

| Requested format | Correct / 42 | Extracted / 42 | Strictly compliant / 42 | Strictly correct / 42 | Truncated |
| --- | ---: | ---: | ---: | ---: | ---: |
| Integer only | 15 (35.7%) | 29 (69.0%) | 0 | 0 | 0 |
| Answer label | 12 (28.6%) | 26 (61.9%) | 0 | 0 | 0 |
| Completed equation with example | 1 (2.4%) | 11 (26.2%) | 11 | 1 | 0 |

Passing required **both** at least 11 correct and at least 34 extracted answers
out of 42 for a format. The first two configurations cleared the arithmetic
threshold but every configuration missed the extraction threshold. No format was
selected. The 210 separately reserved held-out questions remain unqueried; their
inputs and frozen hash are preserved for split verification, not presented as
experimental results. No paired typo effects or uncertainty intervals are reported
because the gate did not authorize that experiment.

## What failed

The new 64-token cap produced no truncated development outputs. Nevertheless,
the model frequently returned extra text, repeated an answer, or copied the
formatting example. Whole-response extraction deliberately rejects these cases.
Among unambiguously extracted answers, 14 integer-request, 14 label-request, and
10 equation-request responses were arithmetically wrong. The remaining 13, 16,
and 31 responses respectively failed the extraction grammar; those failures
must not all be described as incorrect arithmetic.

Examples are directly inspectable in [pilot/outputs.jsonl](pilot/outputs.jsonl):

- `v2-dev-addition-000:clean:integer` returned `2 + 7 = 11`: an unambiguous
  equation with incorrect arithmetic. It also violates the requested integer format.
- `v2-dev-addition-001:clean:integer` returned `2 + 8 = 10` followed by
  `The answer is 10.` This is understandable and internally consistent, but
  outside the preregistered whole-response whitelist. It is not evidence that
  the model cannot solve that arithmetic problem.
- `v2-dev-addition-005:clean:integer` explained the calculation and consistently
  gave 29 for 8 + 11: both unsupported format and visibly incorrect arithmetic.
- `v2-dev-addition-001:clean:label` gave a correct equation followed by a request
  for the user's preferred format and several numbers/expressions. Broadly
  taking the last number would be an unreliable final-answer rule.
- `v2-dev-addition-000:clean:equation` gave the wrong equation `2 + 7 = 11`
  and then the demonstration `21 + 1 = 22`. There are two equation results
  with different roles; neither is accepted by the frozen whole-response rule.

The scorer's `potentially_ambiguous` flag means unsupported text with multiple
numeric tokens, **not** a validated judgment that a human finds the answer
ambiguous. It includes consistent repetitions as well as competing expressions.
These examples provide qualitative diagnosis only and never change any score.
Changing the grammar to accept these outputs after seeing them would require a
new frozen experiment and fresh development/evaluation instances.

## Historical floor remains unchanged

The historical study reported strict accuracy of 0/210 in each condition.
Its development pilot had 127 format-invalid and 83 truncated records; its final
run had 914 format-invalid and 556 truncated records. Those original scores,
completions, protocols, reports and interpretations remain byte-for-byte intact.

A separately labeled post-hoc diagnostic in
[historical-diagnosis.json](historical-diagnosis.json) applies only the new
whole-response grammar to classify old text. Of 1,470 historical final records,
315 contain a matching whole-response answer that is arithmetically correct,
203 contain a matching whole-response answer that is wrong, 396 are unsupported
and nontruncated, and 556 are truncated and not assessed. These are diagnostic
counts across all old conditions, **not replacement scores or a new typo analysis**.
The original strict scorer was doing what its protocol required; the experiment
had a measurement floor that prevented the intended robustness interpretation.

The new development accuracy cannot be read as a causal improvement over the
historical clean accuracy: the questions, prompts, token cap and extraction rule
all differ. This study establishes failure of these three frozen configurations
to meet the operational gate, not failure of every possible prompting strategy
or every reasonable human answer interpretation.

## Reproduction and limits

The pilot took **484.733 seconds** including model loading, with peak process
RSS **1,112,032 KiB**. Exact timing, environment, token counts and model/source/input
hashes are in the run metadata and [summary.json](summary.json). It used the same
pinned 135M model, Python 3.12.3, CPU float32, one intra/inter-op thread, eager
attention, greedy decoding and seed 1907. Recorded host CPU label: `DO-Regular`;
Linux x86_64, kernel 6.8.0-124-generic. Child validation overlapped part of the
pilot, so wall times are descriptive rather than a controlled speed comparison.

The separate installed CLI replayed all **42** preregistered distinct development
question/condition pairs under a verified kernel network guard. Every scientific
field matched the pilot, excluding only timing, dependent seals and the documented
subset run hash. The tokenizer audit reproduced every saved prompt token sequence
and decoded completion in both runs. Real-model SIGTERM stopped without committing
a partial answer; recovery preserved the first durable record, archived an injected
torn tail, and reproduced the next record exactly. The deliberately partial
recovery run is separate from the complete 42-record replay.

The independently computed summaries, strict-vs-extracted distinction, protected
perturbation tests, historical hashes and exact split disjointness can be verified
without generating new completions. See [reproduction instructions](../../docs/floor-v2/reproduction.md)
and the [preregistered design](../../docs/floor-v2/protocol.md).

This is a small development-only result for one model and one arithmetic domain.
The narrow grammar can reject semantically clear answers, and the model can
produce valid-looking equations with wrong arithmetic. The demonstration condition
also changes instructional content, so the design does not isolate individual
prompt features. There is no independent human adjudication of all prose answers.
Hashes protect against accidental changes, not deliberate falsification or an
externally authenticated preregistration. Generalization to other models, broader
answer grammars, natural typing mistakes or real word problems is unmeasured.
