# Pilot interpretation

The completed development pilot accepted **0/30 clean responses** and 0/30 in
each perturbation condition under the declared whole-integer scorer. Clean
responses comprised 13 format-invalid completions and 17 completions that hit the
24-token cap. All 210 actual model completions are preserved in
[outputs.jsonl](outputs.jsonl); none were replaced with estimates.

This is a floor effect in an arithmetic-plus-format task, not evidence that the
model cannot perform any arithmetic. For example, `dev-addition-001:clean`
responded `17 + 17 = 34`, which contains correct arithmetic but violates the
whole-integer output rule. Other outputs began explanatory prose and ran out of
allowed tokens. These failure modes make the strict accuracy endpoint poorly
suited to measuring a further loss in mathematical ability in this configuration.

The frozen evaluation retains the same template, scorer, 24-token limit and
inference settings. A zero clean-correct denominator makes the conditional
clean-correct-to-incorrect rate undefined; it is stored as null. A degenerate
bootstrap interval at zero for an observed accuracy difference is not an
equivalence result or evidence of real-world typo robustness.
