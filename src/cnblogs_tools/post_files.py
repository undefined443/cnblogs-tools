"""Read and persist local post baselines."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


def read_post(path: Path) -> str:
    """Read a post without normalizing body line endings."""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def digest(content: str) -> str:
    """Return a content hash for detecting local edits."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def save_snapshot(output_dir: Path, snapshot: dict[str, Any]) -> None:
    """Atomically persist the complete export baseline."""
    target = output_dir / ".backup.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def parse_post(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML front matter without changing the post body."""
    match = re.fullmatch(r"---\r?\n(.*?)^---[ \t]*\r?\n(.*)", content, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError("Invalid YAML front matter.")
    return yaml.safe_load(match[1]), match[2]
