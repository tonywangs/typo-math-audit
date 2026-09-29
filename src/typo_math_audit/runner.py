"""One writer, durable records, validated prefix resume, bounded cancellation."""
from __future__ import annotations
import fcntl
import json
import os
import platform
import resource
import signal
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from .common import (canonical, digest, file_hash, jsonl_bytes, read_json,
                     seal, check_seal, utcnow, write_json)
from .dataset import generate
from .perturb import cases
from .scoring import score
from .model import verify_model
from .protocol import specification, load_frozen


@contextmanager
def writer_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "run.lockfile").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ValueError("Another writer owns this output directory") from e
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def validate_record(row, case, protocol_hash):
    check_seal(row)
    if row["protocol_sha256"] != protocol_hash:
        raise ValueError("Result belongs to a different protocol")
    for key, value in case.items():
        if row.get(key) != value:
            raise ValueError(f"Case mismatch: {key}")
    expected = score(row["completion"], case["answer"], row["truncated"])
    if any(row[k] != v for k, v in expected.items()):
        raise ValueError("Scoring mismatch")
    if row["rendered_prompt_sha256"] != digest(row["rendered_prompt"]):
        raise ValueError("Rendered input hash mismatch")
    if row["input_token_sha256"] != digest(canonical(row["input_token_ids"])):
        raise ValueError("Token hash mismatch")
    if row["input_tokens"] != len(row["input_token_ids"]) or row["output_tokens"] != len(row["output_token_ids"]):
        raise ValueError("Token count mismatch")
    if not (0 <= row["elapsed_seconds"] < 18000):
        raise ValueError("Invalid timing")


def recover_records(path, expected, protocol_hash):
    """Only a non-newline tail may be dropped; complete damaged rows fail closed."""
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        boundary = data.rfind(b"\n") + 1
        tail = data[boundary:]
        # Preserve evidence of the discarded bytes outside the scoring table.
        write_json(path.parent / f"recovery-{time.time_ns()}.json",
                   dict(utc=utcnow(), discarded_tail_hex=tail.hex(), sha256=digest(tail)))
        with path.open("r+b") as f:
            f.truncate(boundary)
            f.flush()
            os.fsync(f.fileno())
        data = data[:boundary]
    rows = [json.loads(line) for line in data.splitlines()]
    if len(rows) > len(expected):
        raise ValueError("Too many result records")
    for row, case in zip(rows, expected):
        validate_record(row, case, protocol_hash)
    return rows


def environment():
    cpu = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                    if line.startswith("model name")), cpu)
    return dict(python=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
                cpu_model=cpu, logical_cpus=os.cpu_count(),
                peak_rss_unit="KiB on Linux; process high-water mark including model loading")


def run(root, model_dir, split="eval", pilot=False, limit=None, engine_factory=None):
    root = Path(root)
    if pilot and split != "dev":
        raise ValueError("Pilot may only use development data")
    start = time.perf_counter()
    started_utc = utcnow()
    spec = specification() if pilot else load_frozen()["specification"]
    protocol_hash = digest(canonical(spec))
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    with writer_lock(root):
        verify_model(model_dir)
        questions = generate(split)
        expected = list(cases(questions))
        payload = dict(protocol_sha256=protocol_hash, split=split, pilot=pilot,
                       expected_records=len(expected), specification=spec)
        config_path = root / "run.json"
        if config_path.exists():
            old = read_json(config_path)
            if any(old.get(k) != v for k, v in payload.items()):
                raise ValueError("Cannot resume with different run configuration")
            anchor = old["created_utc"]
        else:
            anchor = started_utc
            write_json(config_path, dict(payload, created_utc=anchor))
        for name, content in (("questions.jsonl", jsonl_bytes(questions)),
                              ("cases.jsonl", jsonl_bytes(expected))):
            path = root / name
            if path.exists() and path.read_bytes() != content:
                raise ValueError(f"Input artifact mismatch: {name}")
            path.write_bytes(content)
        output = root / "outputs.jsonl"
        records = recover_records(output, expected, protocol_hash)
        if len(records) == len(expected):
            print(f"Already complete: {len(records)} verified records", flush=True)
            return 0
        deadline = datetime.fromisoformat(anchor).timestamp() + spec["runtime_budget_seconds"]
        cancelled = False
        def handler(signum, frame):
            nonlocal cancelled
            cancelled = True
        def stop():
            return cancelled or time.time() >= deadline
        previous = {s: signal.signal(s, handler) for s in (signal.SIGINT, signal.SIGTERM)}
        before = len(records)
        state = "error"
        error = None
        try:
            if stop():
                state = "budget_exhausted"
                return 2
            if engine_factory is None:
                from .inference import Engine
                engine_factory = Engine
            load_start = time.perf_counter()
            engine = engine_factory(str(model_dir))
            load_seconds = time.perf_counter() - load_start
            with output.open("ab") as f:
                for case in expected[before:]:
                    if stop():
                        raise InterruptedError("Cancelled or runtime budget exhausted")
                    result = engine.run(case, stop)
                    if stop():
                        raise InterruptedError("Cancelled before commit")
                    row = seal(dict(case, protocol_sha256=protocol_hash, **result))
                    validate_record(row, case, protocol_hash)
                    f.write(jsonl_bytes([row]))
                    f.flush()
                    os.fsync(f.fileno())
                    records.append(row)
                    if len(records) % 35 == 0:
                        print(f"{len(records)}/{len(expected)} durable records", flush=True)
                    if limit is not None and len(records)-before >= limit:
                        break
            state = "complete" if len(records) == len(expected) else "checkpoint"
            return 0 if state == "complete" else 2
        except InterruptedError:
            state = "cancelled" if cancelled else "budget_exhausted"
            return 2
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            for s, old_handler in previous.items():
                signal.signal(s, old_handler)
            summary = dict(started_utc=started_utc, finished_utc=utcnow(), state=state,
                           error=error, protocol_sha256=protocol_hash,
                           completed_before=before, completed_after=len(records),
                           new_records=len(records)-before, expected_records=len(expected),
                           wall_seconds=time.perf_counter()-start,
                           model_load_seconds=locals().get("load_seconds"),
                           peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           environment=environment(),
                           artifact_bytes={p.name:p.stat().st_size for p in root.iterdir()
                                           if p.is_file() and p.suffix in (".json", ".jsonl")})
            write_json(root / f"session-{time.time_ns()}.json", summary)
            write_json(root / "status.json", dict(state=state, completed=len(records), expected=len(expected)))
