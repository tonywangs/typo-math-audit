"""Offline scientific integrity checks; does not execute a model."""
from pathlib import Path
from .common import canonical, digest, file_hash, jsonl_bytes, read_json, read_jsonl
from .dataset import generate
from .perturb import cases, CONDITIONS, apply_edits
from .runner import validate_record


def audit_run(root, allow_partial=False):
    root = Path(root)
    config = read_json(root / "run.json")
    if config["protocol_sha256"] != digest(canonical(config["specification"])):
        raise ValueError("Run protocol hash mismatch")
    questions = generate(config["split"])
    expected = list(cases(questions))
    for name, rows in (("questions.jsonl", questions), ("cases.jsonl", expected)):
        if (root / name).read_bytes() != jsonl_bytes(rows):
            raise ValueError(f"Artifact does not match deterministic regeneration: {name}")
    output = root / "outputs.jsonl"
    data = output.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("Uncommitted output tail; resume runner to recover")
    records = read_jsonl(output)
    if len(records) > len(expected) or (not allow_partial and len(records) != len(expected)):
        raise ValueError(f"Incomplete or extra outputs: {len(records)}/{len(expected)}")
    for row, case in zip(records, expected):
        validate_record(row, case, config["protocol_sha256"])
    if config["specification"]["dataset_sha256"][config["split"]] != file_hash(root / "questions.jsonl"):
        raise ValueError("Frozen dataset hash mismatch")
    if config["specification"]["cases_sha256"][config["split"]] != file_hash(root / "cases.jsonl"):
        raise ValueError("Frozen case hash mismatch")
    return dict(records=len(records), expected_records=len(expected), complete=len(records)==len(expected),
                outputs_sha256=file_hash(output), questions_sha256=file_hash(root / "questions.jsonl"),
                cases_sha256=file_hash(root / "cases.jsonl"), protocol_sha256=config["protocol_sha256"])


def compare_runs(reference, replay):
    a = audit_run(reference, True)
    b = audit_run(replay, True)
    if a["protocol_sha256"] != b["protocol_sha256"]:
        raise ValueError("Replay uses different protocol")
    original = {r["case_id"]:r for r in read_jsonl(Path(reference)/"outputs.jsonl")}
    replayed = read_jsonl(Path(replay)/"outputs.jsonl")
    if not replayed:
        raise ValueError("Empty replay")
    exclude = {"record_sha256", "elapsed_seconds"}
    for row in replayed:
        expected = original.get(row["case_id"])
        if expected is None or {k:v for k,v in row.items() if k not in exclude} != {k:v for k,v in expected.items() if k not in exclude}:
            raise ValueError(f"Deterministic replay differs: {row['case_id']}")
    return dict(matched_records=len(replayed), reference_records=len(original),
                exact_fields="all except per-case elapsed_seconds and dependent record_sha256",
                protocol_sha256=a["protocol_sha256"])
