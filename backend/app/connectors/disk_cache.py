"""Tiny JSON-on-disk cache for slow-changing API responses.

Survives uvicorn reloads and restarts (unlike the in-memory pipeline cache), so
season stats are fetched about once a day instead of on every restart — and a
stale copy can stand in when the source is down.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"


def cache_path(namespace: str, endpoint: str, params: dict[str, Any] | None) -> Path:
    key = json.dumps([endpoint, sorted((params or {}).items())], default=str)
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    name = endpoint.strip("/").replace("/", "_") or "root"
    return CACHE_DIR / namespace / f"{name}_{digest}.json"


def read(path: Path, max_age_seconds: float | None) -> Any | None:
    """Cached payload, or None if missing/corrupt/older than max_age (None = any age)."""
    try:
        if max_age_seconds is not None and time.time() - path.stat().st_mtime > max_age_seconds:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def age_hours(path: Path) -> float | None:
    try:
        return (time.time() - path.stat().st_mtime) / 3600
    except OSError:
        return None


def write(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        logger.warning(f"Disk cache write failed for {path.name}: {e}")
