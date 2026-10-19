# Qwen replacement study (v3)

## Motivation and prior evidence

The original objective is to measure effects of typo type and frequency on small
LLM arithmetic performance. Neither the historical format floor nor the failed
v2 extraction gate answers it. Replace only the model and fix one of the already
defined v2 prompts, retaining the arithmetic task, conservative scorer, and edits.
This is a separate experiment; historical artifacts and scores are unchanged.

Before any Qwen inference, select the public Apache-2.0
[Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/7ae557604adf67be50417f59c2c2f167def9a775/README.md)
revision `7ae557604adf67be50417f59c2c2f167def9a775`.
Its documented 0.49B parameters fit this CPU host. Its model card motivates a
mathematics/instruction-following test, not an assumption of baseline success.
Use its chat template with the existing `You are a helpful assistant.` system
message. No prompt search, retry sampling, constrained decoding, or answer repair.

[PromptRobust](https://arxiv.org/abs/2306.04528) and
[Reasoning Robustness of LLMs to Adversarial Typographical Errors](https://arxiv.org/abs/2411.05345)
already study prompt perturbation and reasoning robustness. This is a small
reproducible controlled experiment, with no claim of a novel attack or benchmark.
These primary sources and the model card were inspected on 2026-10-19.

## Fixed inputs and gate

Reuse the v2 42 clean development questions (14 per family) and the still-unrun
210 reserved evaluation questions (70 per family); they are disjoint unordered
family/operand identities, also disjoint from historical v1 questions. v2
observations motivated model replacement, so development results are not a
held-out generalization estimate. The reserved evaluation answers have not been
used to choose any Qwen configuration. Question IDs and edit seeds remain v2
identities to preserve the exact intervention.

One fixed user format:

```
Please carefully calculate the following simple arithmetic problem below.
{expression}
Reply with only the integer answer. No explanation.
```

Run all 42 development inputs once. Proceed only with at least 34/42 correct
(80%) and 38/42 extracted (90%), using the existing v2 whole-response scorer.
No alternative format or model is attempted in this frozen study if the gate
fails. A failed gate is a blocker for the original goal. Pilot budget: 1,800
elapsed seconds, including loading and resume downtime. Evaluation budget:
10,800 elapsed seconds under the same rule. Interrupted or incomplete experiments
are retained and not called delivered.

Evaluation: all 210 questions, each with clean and six typo conditions, 1,470
actual completions. Adjacent transposition, single-character deletion, and
horizontal QWERTY-neighbor substitution at 20% and 40% of five eligible optional
words (one and two edits). Rates over all words are also reported. Numbers,
operators, and answer instructions are protected. Conditions are in fixed
question-major order, clean then type then rate, with fresh model context for
each generation. No inference cache shared between cases. Same v1 perturbation
algorithm and seed 83171; high-rate edits contain low-rate edits for each type.

## Inference and scoring

CPU float32, one intra/inter-op thread, eager attention, MKLDNN disabled,
deterministic algorithms, seed 1907, batch size one, greedy decoding, one beam,
KV cache within a generation, max 64 new tokens, tokenizer EOS sole normal stop.
Pin model files by SHA-256, runtime packages by exact versions, all transitive
project source, protocol, and exact input bytes before the first pilot response.
Use local files only in inference and no remote code. No weights enter Git.

Reuse v2 `score_response`: whole signed integer, `Answer: N`, `The answer is N`,
or the exact input equation, with the documented whitespace/period allowances;
no arbitrary number search. Extraction is gold-independent. All invalid and
truncated responses count as incorrect. Report strict integer correctness,
extraction, arithmetic accuracy among all assigned questions, and truncation
separately. Stop signals discard partial generations and checkpoint completed
rows. Resume must validate protocol, inputs, and all completed rows first.

## Analysis fixed before inference

Primary: six paired accuracy changes (typo minus clean). Secondary: three paired
high-minus-low rate changes within typo type, transitions from clean correctness,
extraction and strict compliance, and accuracy by task family. Use the existing
family-stratified question-cluster percentile bootstrap, 10,000 resamples, seed
62103, marginal 95% intervals. All variants of a question stay together. Report
raw counts and no significance stars or multiple-testing claims. Also report
Wilson 95% intervals for clean accuracy and clean-correct break proportions:
bootstrap intervals can degenerate at a floor/ceiling. Wilson intervals are
binomial descriptive approximations and do not capture template uncertainty.
A zero observed effect is not proof of equivalence or immunity.

All conclusions concern these fixed optional-word edits, this model and simple
English arithmetic only. They do not concern word problems, corrupted numbers,
human typo distributions, harder reasoning, other prompts, or larger models.
Synthetic arithmetic is intentional in the original task; the public pretrained
model is the real inference input. Training-data contamination is unknown.

## Completion and reproduction

Required: passing development gate, complete paired evaluation, raw completions
and token IDs, effect sizes with uncertainty, readable result and runnable launch
instructions. Validate the exact rendered prompts/tokenization by replaying the
first two evaluation questions per family across all seven conditions (42
responses) in a separately installed offline process. Audit every stored row,
regenerate scores and inputs, independently recompute analysis, and test
cancellation/recovery and corruption rejection. A fresh read-only reviewer checks
the original acceptance criteria. Failed checks must be resolved or reported.
