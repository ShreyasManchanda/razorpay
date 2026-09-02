"""Defensive pattern synthesis with validated, monotonic versioning."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from warden.detection.pattern_registry import (
    active_version,
    load_pattern_records,
    validate_records,
)


class ProposedPattern(BaseModel):
    pattern_name: str
    regex: str
    description: str
    tier: str = Field(default="imperative")
    source: str | None = None


PATTERNS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "patterns")


def load_patterns(version: str | None = None) -> list[dict]:
    """Load a validated pattern artifact (latest version by default)."""

    if version is None:
        version = active_version(PATTERNS_DIR)
    if version is None:
        return []
    return load_pattern_records(version, PATTERNS_DIR)


def save_patterns(patterns: list[dict], version: str):
    """Validate and atomically write a pattern artifact."""

    validated = validate_records(patterns)
    if not re.fullmatch(r"v[1-9]\d*", version):
        raise ValueError(f"Invalid pattern version: {version!r}")
    directory = Path(PATTERNS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{version}.json"
    fd, temporary = tempfile.mkstemp(prefix=f".{version}.", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(validated, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def next_version() -> str:
    latest = active_version(PATTERNS_DIR)
    if latest is None:
        return "v1"
    return f"v{int(latest[1:]) + 1}"


def synthesize_from_missed_attacks(missed_messages: list[str]) -> list[ProposedPattern]:
    """Derive conservative imperative patterns from missed attack text.

    This is intentionally deterministic and reviewable. It only emits patterns
    when a message contains an agent-directed imperative trigger, and captures a
    short context window to reduce broad keyword-only false positives.
    """

    patterns: list[ProposedPattern] = []
    triggers = re.compile(
        r"\b(?:must|shall|should|need(?:s)?\s+to|has\s+to|override|ignore|disregard)\b", re.IGNORECASE
    )
    for msg in missed_messages:
        text = str(msg).strip()
        match = triggers.search(text)
        if not match:
            continue
        words = re.findall(r"[\w'-]+", text.lower())
        trigger_index = next(
            (
                i
                for i, word in enumerate(words)
                if re.fullmatch(r"(?:must|shall|should|override|ignore|disregard)", word)
            ),
            None,
        )
        if trigger_index is None:
            # Handles multi-word forms such as "needs to" and "has to".
            trigger_index = max(0, len(words) // 2)
        context_words = words[max(0, trigger_index - 2) : min(len(words), trigger_index + 4)]
        if not context_words:
            continue
        escaped = r"\s+".join(re.escape(word) for word in context_words)
        digest = hashlib.sha256(escaped.encode("utf-8")).hexdigest()[:10]
        candidate = ProposedPattern(
            pattern_name=f"auto_pattern_{digest}",
            regex=rf"\b{escaped}\b",
            description=f"Auto-derived from missed attack containing '{match.group(0).lower()}'",
            tier="imperative",
            source="selfplay_missed_attack",
        )
        if all(candidate.regex != existing.regex for existing in patterns):
            patterns.append(candidate)
    return patterns


def version_bump(missed_messages: list[str], control_messages: list[str] | None = None) -> str | None:
    """Create the next registry version, preserving all prior patterns."""

    current_version = active_version(PATTERNS_DIR)
    current = load_patterns(current_version) if current_version else []
    new_patterns = synthesize_from_missed_attacks(missed_messages)
    controls = [str(message) for message in (control_messages or [])]
    # Candidate activation is gated by a simple frozen-control check. A
    # candidate that cannot match a miss or matches a known benign control is
    # retained only as a proposal in memory, never activated.
    if controls:
        accepted = []
        for candidate in new_patterns:
            compiled = re.compile(candidate.regex, re.IGNORECASE)
            if any(compiled.search(str(miss)) for miss in missed_messages) and not any(
                compiled.search(control) for control in controls
            ):
                accepted.append(candidate)
        new_patterns = accepted
    if not new_patterns:
        return None
    merged = list(current)
    known = {(item["pattern_name"], item["regex"], item.get("tier", "imperative")) for item in merged}
    for pattern in new_patterns:
        item = pattern.model_dump(exclude_none=True)
        key = (item["pattern_name"], item["regex"], item.get("tier", "imperative"))
        if key not in known and not any(
            item["regex"] == old["regex"] and item.get("tier") == old.get("tier") for old in merged
        ):
            merged.append(item)
            known.add(key)
    version = next_version()
    save_patterns(merged, version)
    return version
