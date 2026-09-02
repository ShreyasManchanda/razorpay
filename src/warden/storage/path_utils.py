"""Safe identifiers and atomic JSON persistence helpers.

Transaction ids are used as filenames in the demo's file-backed stores. Keep
that boundary explicit so a value supplied by an HTTP path can never escape the
configured data directory.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_TX_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_tx_id(tx_id: str) -> str:
    if not isinstance(tx_id, str) or not _TX_ID_RE.fullmatch(tx_id):
        raise ValueError("transaction id must contain only letters, numbers, '.', '_' or '-' (max 128 characters)")
    return tx_id


def safe_json_path(base_dir: str | os.PathLike[str], tx_id: str) -> Path:
    return Path(base_dir).resolve() / f"{validate_tx_id(tx_id)}.json"


def atomic_json_dump(path: Path, value: Any) -> None:
    """Write JSON via a same-directory temporary file and atomic replace."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
