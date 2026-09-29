"""Synthetic instances; independent counting oracle checks direct arithmetic."""
import random
from .common import digest, jsonl_bytes

FAMILIES = ("addition", "subtraction", "multiplication")
SYMBOLS = {"addition": "+", "subtraction": "-", "multiplication": "*"}
DATA_SEED = 20260929
PROMPT = ("Please carefully calculate the following simple arithmetic problem below.\n"
          "{expression}\nReply with only the integer answer.")
SYSTEM = "You are a helpful assistant."


def oracle(family, a, b):
    # Count explicitly constructed objects; do not reuse the arithmetic operators
    # under test. Small operand bounds make enumeration cheap and exact.
    if family == "addition":
        return len(list(range(a)) + list(range(b)))
    if family == "subtraction":
        return len(list(range(a))[b:])
    if family == "multiplication":
        return len([(i, j) for i in range(a) for j in range(b)])
    raise ValueError(family)


def generate(split):
    if split not in ("dev", "eval"):
        raise ValueError("split must be dev or eval")
    rows = []
    for fi, family in enumerate(FAMILIES):
        pairs = [(a, b) for a in range(21) for b in range(a, 21)]
        random.Random(DATA_SEED + fi).shuffle(pairs)
        selected = pairs[:10] if split == "dev" else pairs[10:80]
        for i, (a, b) in enumerate(selected):
            if family == "subtraction":
                a, b = b, a
            answer = {"addition": lambda: a + b,
                      "subtraction": lambda: a - b,
                      "multiplication": lambda: a * b}[family]()
            independent = oracle(family, a, b)
            if answer != independent:
                raise ValueError("Oracle disagreement")
            expression = f"{a} {SYMBOLS[family]} {b}"
            text = PROMPT.format(expression=expression)
            rows.append(dict(question_id=f"{split}-{family}-{i:03d}", split=split,
                             family=family, operands=[a, b], expression=expression,
                             answer=answer, oracle_answer=independent, prompt=text,
                             prompt_sha256=digest(text)))
    return rows


def dataset_hash(split):
    return digest(jsonl_bytes(generate(split)))
