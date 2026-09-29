"""Explicit acquisition; inference only opens hash-verified local files."""
from pathlib import Path
import os
import urllib.request
from .common import ASSETS, read_json, file_hash


def verify_model(root):
    root = Path(root)
    manifest = read_json(ASSETS / "model.json")
    for name, entry in manifest["files"].items():
        path = root / name
        if not path.is_file() or path.stat().st_size != entry["bytes"] or file_hash(path) != entry["sha256"]:
            raise ValueError(f"Model artifact missing or corrupt: {name}")
    return manifest


def acquire(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = read_json(ASSETS / "model.json")
    for name, entry in manifest["files"].items():
        path = root / name
        if path.exists() and file_hash(path) == entry["sha256"]:
            continue
        url = f"https://huggingface.co/{manifest['repo_id']}/resolve/{manifest['revision']}/{name}"
        tmp = path.with_suffix(path.suffix + ".partial")
        with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as f:
            while chunk := response.read(1024 * 1024):
                f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
        if tmp.stat().st_size != entry["bytes"] or file_hash(tmp) != entry["sha256"]:
            tmp.unlink()
            raise ValueError(f"Downloaded hash mismatch: {name}")
        tmp.replace(path)
    return verify_model(root)
