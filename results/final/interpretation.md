# Result: the strict endpoint is at its floor

All **1,470/1,470 planned model completions** were generated and retained for
210 held-out arithmetic questions. Strict accuracy was **0/210 (0%) in every
condition**, including clean input. The experiment completed, but this
configuration does **not** provide a useful accuracy-based ranking of typo
robustness.

The clean condition had 85/210 format-invalid responses and 125/210 truncated
responses. No clean answer passed the whole-integer rule. For example,
`eval-addition-002:clean` produced `15 + 19 = 34`, with oracle answer 34: correct
arithmetic in an output format the frozen scorer rejects. Other responses began
explanations and exhausted the 24-token budget. Thus zero strict accuracy must
not be paraphrased as “the model cannot do arithmetic.”

All six paired accuracy differences were zero percentage points, with empirical
question-bootstrap intervals [0, 0]. Because every strict correctness indicator
was zero, resampling cannot create variability in that endpoint. These degenerate
intervals are **not equivalence evidence**, and do not establish that typos have
no effect. There were zero clean-correct cases; the conditional
clean-correct-to-incorrect transition rate is undefined, stored as null rather
than zero. The report displays its count and denominator as 0/0.

The observed termination categories did differ:

| Condition | Format-invalid / 210 | Truncated / 210 |
|---|---:|---:|
| Clean | 85 | 125 |
| Transposition, 20% eligible words | 133 | 77 |
| Transposition, 40% eligible words | 154 | 56 |
| Deletion, 20% eligible words | 128 | 82 |
| Deletion, 40% eligible words | 146 | 64 |
| Keyboard substitution, 20% eligible words | 127 | 83 |
| Keyboard substitution, 40% eligible words | 141 | 69 |

These are descriptive counts under the fixed generation cap. Fewer truncated
responses did not produce any accepted answers and should not be described as
better mathematical reasoning. The exact completions remain available for
inspection in [outputs.jsonl](outputs.jsonl); the frozen scoring rule was not
changed to recover convenient answers from those texts.

The original evaluation took **7,974.280 seconds** of measured invocation wall
time (about 2 hours 13 minutes), including model loading and verification. Peak
process RSS was **1,115,104 KiB** (about 1.06 GiB). It shared the CPU host with the
independently installed replay, so these are observed execution costs, not
isolated throughput measurements.

The [generated report](report.md) contains the paired tables, family counts,
realized corruption rates and limitations. The [machine-readable summary](summary.json)
also preserves accuracy intervals, all four paired cells, transition
probabilities, token counts, timings and artifact sizes. The immutable source and
settings freeze precedes all held-out generation. Development and evaluation use
disjoint instances but share a template; no conclusions are justified about
other templates, difficult mathematics, story understanding, larger models or
human typo distributions.
