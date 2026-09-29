"""Strict, predeclared scoring: no search for convenient numbers in prose."""
import re


def score(text, answer, truncated=False):
    stripped = text.strip()
    valid = re.fullmatch(r"[+-]?[0-9]+", stripped) is not None
    parsed = int(stripped) if valid and len(stripped) < 100 else None
    status = "truncated" if truncated else ("valid" if parsed is not None else "invalid_format")
    return dict(parsed_answer=parsed, status=status,
                correct=status == "valid" and parsed == answer)
