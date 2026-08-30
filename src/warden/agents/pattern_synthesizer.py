import json
import os
import re

from pydantic import BaseModel


class ProposedPattern(BaseModel):
    pattern_name: str
    regex: str
    description: str


PATTERNS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "patterns")


def load_patterns(version: str = "v1") -> list[dict]:
    path = os.path.join(PATTERNS_DIR, f"{version}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save_patterns(patterns: list[dict], version: str):
    os.makedirs(PATTERNS_DIR, exist_ok=True)
    path = os.path.join(PATTERNS_DIR, f"{version}.json")
    with open(path, "w") as f:
        json.dump(patterns, f, indent=2)


def next_version() -> str:
    if not os.path.exists(PATTERNS_DIR):
        return "v1"
    versions = [f for f in os.listdir(PATTERNS_DIR) if re.match(r"v\d+\.json", f)]
    if not versions:
        return "v1"
    latest = max(int(re.findall(r"\d+", v)[0]) for v in versions)
    return f"v{latest + 1}"


def synthesize_from_missed_attacks(missed_messages: list[str]) -> list[ProposedPattern]:
    """Hand-authored fallback (per spec §17): derive regexes from what was missed.
    A full LLM-based synthesizer is a stretch goal."""
    patterns = []
    for msg in missed_messages:
        # Look for common imperative structures
        words = msg.lower().split()
        for i, w in enumerate(words):
            if w in ("must", "shall", "override", "ignore"):
                context = " ".join(words[max(0, i - 2) : i + 3])
                escaped = re.escape(context).replace(r"\ ", r"\s+")
                patterns.append(
                    ProposedPattern(
                        pattern_name=f"auto_pattern_{len(patterns) + 1}",
                        regex=escaped,
                        description=f"Auto-derived from missed attack containing '{w}'",
                    )
                )
                break
    return patterns


def version_bump(missed_messages: list[str]) -> str:
    current = load_patterns("v1")  # always read from v1 as base
    new_patterns = synthesize_from_missed_attacks(missed_messages)
    merged = current + [p.model_dump() for p in new_patterns]
    version = next_version()
    save_patterns(merged, version)
    return version
