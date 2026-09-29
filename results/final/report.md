# Frozen evaluation: arithmetic typo audit

210 complete original questions; 1470/1470 actual completions. Excluded incomplete questions: 0.

Accuracy uses strict whole-integer responses. Invalid format and truncated responses count as incorrect. Delta is corrupted minus clean accuracy; positive values are improvements.

| Condition | Correct / N | Accuracy | Delta (percentage points), 95% CI | Clean correct → incorrect / clean correct | Incorrect → correct | Invalid | Truncated |
|---|---:|---:|---:|---:|---:|---:|---:|
| clean | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 85 | 125 |
| transpose-20 | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 133 | 77 |
| transpose-40 | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 154 | 56 |
| delete-20 | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 128 | 82 |
| delete-40 | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 146 | 64 |
| keyboard-20 | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 127 | 83 |
| keyboard-40 | 0/210 | 0.00% | +0.00 [+0.00, +0.00] | 0/0 | 0 | 141 | 69 |

Intervals use 10,000 bootstrap samples of original questions, stratified by task family. All seven variants stay together. These are marginal intervals without multiplicity correction, not evidence about other templates, models, or human typing distributions. Accuracy and conditional transition intervals are in summary.json.

## Task families

| Condition | Addition | Subtraction | Multiplication |
|---|---:|---:|---:|
| clean | 0/70 | 0/70 | 0/70 |
| transpose-20 | 0/70 | 0/70 | 0/70 |
| transpose-40 | 0/70 | 0/70 | 0/70 |
| delete-20 | 0/70 | 0/70 | 0/70 |
| delete-40 | 0/70 | 0/70 | 0/70 |
| keyboard-20 | 0/70 | 0/70 | 0/70 |
| keyboard-40 | 0/70 | 0/70 | 0/70 |

## Realized perturbations

| Condition | Eligible-word rate | All-word rate | Unchanged / N | Possible meaning change / N | Mean input tokens |
|---|---:|---:|---:|---:|---:|
| clean | 0.0% | 0.00% | 210/210 | 0/210 | 45.04 |
| transpose-20 | 20.0% | 6.67% | 0/210 | 210/210 | 46.98 |
| transpose-40 | 40.0% | 13.33% | 0/210 | 210/210 | 48.90 |
| delete-20 | 20.0% | 6.67% | 0/210 | 210/210 | 46.21 |
| delete-40 | 40.0% | 13.33% | 0/210 | 210/210 | 47.42 |
| keyboard-20 | 20.0% | 6.67% | 0/210 | 210/210 | 46.68 |
| keyboard-40 | 40.0% | 13.33% | 0/210 | 210/210 | 48.36 |

All edited variants are conservatively flagged for possible meaning changes; this is an unreviewed risk flag, not a measured semantic failure. Numbers, operators and the answer instruction are untouched. Offsets refer to the original user prompt.

## Runtime and artifacts

Recorded invocation time: 7974.280 seconds across 1 sessions. Peak process RSS: 1115104 KiB (Linux high-water mark). Per-case times, token IDs, exact rendered prompts, completions, hashes and scoring evidence are in outputs.jsonl. Environment and loading time are in session-*.json. File sizes are listed in summary.json; model weights are stored separately.

## Limits

One 135M-parameter model, one prompt template, English, operands 0–20, and three single-operation families. Development and evaluation arithmetic instances are disjoint, but share templates and operand ranges; training-data contamination cannot be ruled out. Five optional scaffold words are eligible for one or two edits, so this is a mild, protected-input intervention. It does not measure story comprehension, difficult mathematics, larger-model behavior, adversarial attacks, or realistic human-error distributions. Strict scoring mixes arithmetic success with instruction-format compliance. The 24-token cap may censor correct answers in longer explanations; no post-hoc answer extraction or generation retuning is used. Clean-first order and shared templates limit timing and uncertainty interpretations. Poor accuracy, zero changes, and improvements are all retained. Deterministic replay is tested on the recorded environment; different hardware or numerical libraries may differ.
