import importlib.metadata
import platform
from pathlib import Path
from .common import ASSETS, canonical, digest, file_hash, read_json
from .dataset import DATA_SEED, FAMILIES, PROMPT, SYSTEM, dataset_hash
from .perturb import TYPO_SEED, EDITABLE, KEYBOARD, CONDITIONS, LEVELS, cases
from .dataset import generate
from .common import jsonl_bytes
from .inference import SETTINGS

CORE = ("common.py", "dataset.py", "perturb.py", "scoring.py", "model.py", "inference.py", "protocol.py", "runner.py", "audit.py", "analysis.py", "cli.py")
RUNTIME = tuple(read_json(ASSETS / "dependencies.json"))


def specification():
    return dict(schema=1, model_manifest_sha256=file_hash(ASSETS / "model.json"),
                source_sha256={name: file_hash(Path(__file__).parent / name) for name in CORE},
                python=platform.python_version(), dependencies={p: importlib.metadata.version(p) for p in RUNTIME},
                settings=SETTINGS, data_seed=DATA_SEED, typo_seed=TYPO_SEED,
                families=list(FAMILIES), dev_per_family=10, eval_per_family=70,
                prompt_template=PROMPT, system_prompt=SYSTEM,
                operand_range=[0,20], unique_unordered_pairs=True,
                eligible_words=sorted(EDITABLE), keyboard=KEYBOARD,
                levels=list(LEVELS), conditions=list(CONDITIONS),
                dataset_sha256={s:dataset_hash(s) for s in ("dev", "eval")},
                cases_sha256={s:digest(jsonl_bytes(list(cases(generate(s))))) for s in ("dev", "eval")},
                scoring="strip whitespace; whole ASCII signed integer only; truncated is always incorrect",
                order="question-major, family addition/subtraction/multiplication; clean then type then level",
                runtime_budget_seconds=18000,
                analysis=dict(bootstrap_seed=62103, bootstrap_replicates=10000,
                              unit="original question with all seven conditions", stratify="family",
                              confidence=0.95, interval="percentile; marginal, not multiplicity-adjusted",
                              primary="accuracy(condition) minus accuracy(clean)",
                              secondary="clean-correct to incorrect transition; invalid and truncation rates"))


def load_frozen():
    lock = read_json(ASSETS / "protocol.json")
    if lock["specification"] != specification():
        raise ValueError("Frozen protocol differs from current code, data, model manifest or environment")
    if lock["specification_sha256"] != digest(canonical(lock["specification"])):
        raise ValueError("Protocol hash mismatch")
    return lock
