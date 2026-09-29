# Rationale and sources

Reviewed 2026-09-29 before the new pilot. The historical raw outputs include
`4 + 9 = 13`, rejected by the integer-only scorer, and incomplete explanatory
sentences at the 24-token cap. That supports testing explicit output forms,
a longer cap, and a conservative equation-aware scorer, while retaining the
old scores unchanged. A rejected response need not be arithmetically wrong;
a number somewhere in an explanation need not be the model's final answer.

The [pinned model card](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/blob/12fd25f77366fa6b3b4b768ec3050bf629380bac/README.md)
uses chat-template generation and cautions about logical errors. The new study
retains that interface; it does not assume GSM8K scores transfer to this dataset.
[LightEval's extraction implementation](https://github.com/huggingface/lighteval/blob/main/src/lighteval/metrics/utils/extractive_match_utils.py)
uses configurable number/expression extraction patterns and prioritization. Our
whole-response whitelist is substantially narrower: it declines broad prose
extraction and treats ambiguity as a measurable failure. No code was copied.

[PromptRobust](https://arxiv.org/abs/2306.04528v5) evaluates adversarial prompts
at multiple textual levels and tasks. [Gan et al.](https://arxiv.org/abs/2411.05345v1)
study adversarial typographical attacks on reasoning, with selected edits and
reasoning datasets. Our fixed optional-word perturbations and tiny arithmetic
model are not replications of those studies. A usable clean baseline is needed
before a null paired result can say anything about this narrower intervention.
This experiment contributes reproducible diagnostic evidence, not a new attack,
new extraction algorithm, or general benchmark ranking.
