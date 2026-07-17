from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(target: Path, content: bytes) -> None:
    """Durably stage bytes beside the target, then atomically replace it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            _ = handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _ = temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(target: Path, content: str) -> None:
    atomic_write_bytes(target, content.encode("utf-8"))
