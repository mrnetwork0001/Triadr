"""
Triadr - `.env` loading, dependency-free.

The engine promises to run on a bare Python 3.11+ with nothing installed, so
this is a small stdlib parser rather than python-dotenv. Existing environment
variables always win over the file, matching dotenv's default behaviour.

Every entry point calls `load_env()` first: main.py, server.py, the MCP stdio
server and the scripts. Without it, credentials placed in .env are invisible
and every app silently falls back to SIMULATED mode - which is exactly the
failure a live demo must not have.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent


def parse_env(text: str) -> Dict[str, str]:
    """Parse KEY=VALUE lines. Supports comments, blank lines, `export KEY=`,
    and single/double-quoted values. Deliberately no interpolation."""
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            # Strip a trailing inline comment on unquoted values.
            hash_at = value.find(" #")
            if hash_at != -1:
                value = value[:hash_at].rstrip()
        out[key] = value
    return out


def load_env(path: Optional[Path] = None, *, override: bool = False) -> Dict[str, str]:
    """Load `.env` (default: repo root) into os.environ. Returns what was applied."""
    target = path or ROOT / ".env"
    if not target.exists():
        return {}
    applied: Dict[str, str] = {}
    for key, value in parse_env(target.read_text(encoding="utf-8")).items():
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
