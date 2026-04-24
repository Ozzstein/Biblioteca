from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(path: Path) -> str:
    """SHA-256 hash of file contents, prefixed with 'sha256:'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"
