# Related work and scope

Sources reviewed 2026-09-29. This experiment claims neither a new attack nor a
reproduction of the published benchmark scores.

- [PromptRobust, Zhu et al.](https://arxiv.org/abs/2306.04528v5) evaluates adversarial
  prompts at character, word, sentence and semantic levels, across multiple tasks.
  Its [PromptBench implementation](https://github.com/microsoftarchive/promptbench)
  supplies a broader evaluation framework. Our fixed random edits are not selected
  against a model loss and do not reproduce those attacks or their task suite.
- [MulTypo, Zhao et al., ACL 2026](https://aclanthology.org/2026.acl-long.729/)
  studies multilingual typing noise across several tasks and models. Its
  [public implementation](https://github.com/cisnlp/multypo) includes keyboard
  layouts, operation mixtures and exclusions. We inspected
  [core.py at ecd72d1](https://github.com/cisnlp/multypo/blob/ecd72d1927bec8e4bb3b3d09dcccc04dadeef28d/core.py):
  it weights word/character choices, distinguishes horizontal/vertical neighbors,
  and constrains transpositions by hand. Our sampler instead uses uniform
  optional-word selection, only horizontal US-QWERTY neighbors, and adjacent
  unequal-character swaps. These simplifications are transparent interventions,
  not validated models of human typing. No source code was copied.
- [Reasoning Robustness of LLMs to Adversarial Typographical Errors,
  Gan et al.](https://arxiv.org/html/2411.05345v1) introduces ATA and R²ATA, using
  model-guided typo selection and established reasoning datasets. Here there is
  no adversarial search, no chain-of-thought requirement, and no GSM8K, BBH or MMLU
  evaluation. The arithmetic expressions are deliberately much simpler.
- The [SmolLM2-135M-Instruct model card](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/blob/12fd25f77366fa6b3b4b768ec3050bf629380bac/README.md)
  describes an English instruction model and warns of factual/logical errors.
  It reports weak GSM8K performance under its own evaluation configuration;
  those numbers are not directly comparable to this synthetic, zero-shot,
  CPU float32 experiment. We use the documented chat-template interface but
  replace sampling with bounded greedy decoding.

The useful deliverable is an inspectable chain from exact question and edit to
model completion, score, paired comparison and offline replay. Holding the
expression and answer instruction intact isolates a narrow form of surrounding
text corruption. It does not estimate robustness to errors in names, quantities,
negation, operators, story relationships or answer-bearing terms.
