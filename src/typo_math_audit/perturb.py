"""Seeded nested perturbations, restricted to an explicit optional-word allowlist."""
import math
import random
import re
from .common import digest

TYPO_SEED = 83171
EDITABLE = frozenset({"please", "carefully", "following", "simple", "below"})
KINDS = ("transpose", "delete", "keyboard")
LEVELS = (0.2, 0.4)
CONDITIONS = ("clean",) + tuple(f"{k}-{int(p*100)}" for k in KINDS for p in LEVELS)
# Horizontal neighbors only, symmetric, fixed US QWERTY letter rows.
# Deliberately not a model of empirical human typing frequencies.
KEYBOARD = {}
for row in ("qwertyuiop", "asdfghjkl", "zxcvbnm"):
    for i, c in enumerate(row):
        KEYBOARD[c] = row[max(0, i-1):i] + row[i+1:i+2]


def apply_edits(text, edits):
    result = text
    end = 0
    for e in sorted(edits, key=lambda e: e["start"]):
        if e["start"] < end or text[e["start"]:e["end"]] != e["before"]:
            raise ValueError("Overlapping or invalid edit")
        end = e["end"]
    for e in sorted(edits, key=lambda e: e["start"], reverse=True):
        result = result[:e["start"]] + e["after"] + result[e["end"]:]
    return result


def perturb(question, kind="clean", level=0.0):
    text = question["prompt"]
    words = list(re.finditer(r"[A-Za-z]+", text))
    eligible = [m for m in words if m.group().lower() in EDITABLE]
    edits = []
    if kind != "clean":
        if kind not in KINDS or level not in LEVELS:
            raise ValueError("Unknown perturbation")
        seed = int(digest(f"{TYPO_SEED}:{question['question_id']}:{kind}"), 16)
        rng = random.Random(seed)
        rng.shuffle(eligible)
        # Same ordering and RNG stream at both levels => nested edits.
        for m in eligible[:math.ceil(level * len(eligible))]:
            word = m.group()
            positions = [i for i in range(len(word)-1) if word[i] != word[i+1]] if kind == "transpose" else list(range(len(word)))
            if not positions:
                continue
            i = rng.choice(positions)
            old = word[i:i+2] if kind == "transpose" else word[i]
            if kind == "transpose":
                new = old[::-1]
            elif kind == "delete":
                new = ""
            else:
                new = rng.choice(KEYBOARD[old.lower()])
                if old.isupper():
                    new = new.upper()
            edits.append(dict(start=m.start()+i, end=m.start()+i+len(old),
                              before=old, after=new, word_start=m.start(),
                              word_end=m.end(), original_word=word))
    altered = apply_edits(text, edits)
    condition = "clean" if kind == "clean" else f"{kind}-{int(level*100)}"
    return dict(case_id=f"{question['question_id']}:{condition}",
                question_id=question["question_id"], family=question["family"],
                condition=condition, answer=question["answer"], prompt=altered,
                prompt_sha256=digest(altered), clean_prompt_sha256=digest(text),
                edits=sorted(edits, key=lambda e: e["start"]),
                target_eligible_word_rate=level, eligible_words=len(eligible),
                total_words=len(words), changed_words=len(edits),
                realized_eligible_word_rate=len(edits)/len(eligible) if eligible else 0,
                realized_all_word_rate=len(edits)/len(words) if words else 0,
                character_edit_operations=len(edits),
                touched_original_characters=sum(e["end"]-e["start"] for e in edits),
                unchanged=altered == text,
                possible_meaning_change=bool(edits),
                semantic_review="unreviewed_optional_word_edits" if edits else "unchanged")


def cases(questions):
    for q in questions:
        yield perturb(q)
        for kind in KINDS:
            for level in LEVELS:
                yield perturb(q, kind, level)
