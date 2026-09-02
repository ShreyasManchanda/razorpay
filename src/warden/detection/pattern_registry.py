"""Validated, versioned pattern registry used by the runtime scanners.

Pattern files are intentionally small JSON artifacts so they can be reviewed and
replayed.  The registry treats them as untrusted input: every record is checked
before it is exposed to detection code.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PATTERNS_DIR = Path(__file__).resolve().parents[3] / "patterns"
_VERSION_RE = re.compile(r"^v(?P<number>[1-9]\d*)$")
_ALLOWED_TIERS = {"imperative", "suspicious"}


@dataclass(frozen=True)
class PatternRecord:
    pattern_name: str
    regex: str
    description: str
    tier: str
    source: str | None = None
    synthesized_from: str | None = None

    @property
    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.regex, re.IGNORECASE)


def _version_number(version: str) -> int:
    match = _VERSION_RE.fullmatch(version)
    if not match:
        raise ValueError(f"Invalid pattern version: {version!r}")
    return int(match.group("number"))


def validate_records(records: Any) -> list[dict[str, Any]]:
    """Validate and normalize pattern records, raising on malformed input."""

    if not isinstance(records, list):
        raise ValueError("Pattern registry must contain a JSON list")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    regexes: set[tuple[str, str]] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise ValueError(f"Pattern {index} must be an object")
        name = raw.get("pattern_name")
        regex = raw.get("regex")
        description = raw.get("description", "")
        tier = raw.get("tier", "imperative")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
            raise ValueError(f"Pattern {index} has invalid pattern_name")
        if name in names:
            raise ValueError(f"Duplicate pattern_name: {name}")
        if not isinstance(regex, str) or not regex.strip() or len(regex) > 1000:
            raise ValueError(f"Pattern {name} has invalid regex")
        if not isinstance(description, str) or len(description) > 1000:
            raise ValueError(f"Pattern {name} has invalid description")
        if tier not in _ALLOWED_TIERS:
            raise ValueError(f"Pattern {name} has invalid tier: {tier!r}")
        try:
            re.compile(regex, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Pattern {name} does not compile: {exc}") from exc
        key = (regex, tier)
        if key in regexes:
            raise ValueError(f"Duplicate regex in pattern registry: {name}")
        names.add(name)
        regexes.add(key)
        item = {
            "pattern_name": name,
            "regex": regex,
            "description": description,
            "tier": tier,
        }
        if raw.get("source") is not None:
            item["source"] = str(raw["source"])
        if raw.get("synthesized_from") is not None:
            item["synthesized_from"] = str(raw["synthesized_from"])
        normalized.append(item)
    return normalized


def available_versions(patterns_dir: str | os.PathLike[str] | None = None) -> list[str]:
    directory = Path(patterns_dir or DEFAULT_PATTERNS_DIR)
    if not directory.exists():
        return []
    versions = []
    for path in directory.glob("v*.json"):
        version = path.stem
        if _VERSION_RE.fullmatch(version):
            versions.append(version)
    return sorted(versions, key=_version_number)


def active_version(patterns_dir: str | os.PathLike[str] | None = None) -> str | None:
    versions = available_versions(patterns_dir)
    return versions[-1] if versions else None


def load_pattern_records(
    version: str | None = None,
    patterns_dir: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    directory = Path(patterns_dir or DEFAULT_PATTERNS_DIR)
    chosen = version or active_version(directory)
    if chosen is None:
        return []
    _version_number(chosen)
    path = directory / f"{chosen}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as handle:
        return validate_records(json.load(handle))


def load_pattern_set(
    patterns_dir: str | os.PathLike[str] | None = None,
) -> tuple[str | None, list[PatternRecord]]:
    version = active_version(patterns_dir)
    records = load_pattern_records(version, patterns_dir) if version else []
    return version, [PatternRecord(**record) for record in records]
