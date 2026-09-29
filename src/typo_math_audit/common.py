from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    with tmp.open("w") as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def jsonl_bytes(rows):
    return ("".join(canonical(r) + "\n" for r in rows)).encode()


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def seal(row):
    return dict(row, record_sha256=digest(canonical(row)))


def check_seal(row):
    body = {k: v for k, v in row.items() if k != "record_sha256"}
    if row.get("record_sha256") != digest(canonical(body)):
        raise ValueError("Record integrity mismatch")
