"""Unified run-artifact path resolution.

All transient + deliverable artifacts share a single root — ``<repo_root>/runs``
— and are partitioned per task (one directory per session). Resolution is
independent of the *process cwd*, so the run dir never depends on where the
agent happened to be invoked from (fixes artefacts leaking into ``backend/``
when the caller spawned with ``cwd=backend``).
"""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Locate the repository root (the directory containing ``backend/``).

    Resolution order (most robust first):

    1. ``EPCD_REPO_ROOT`` env override (deployments that relocate the checkout).
    2. Walk up from this file's real location (``backend/src/epcd_agent/paths.py``)
       until a directory containing a ``backend/`` subdirectory is found.
    3. Fall back to the resolved ``process.cwd()`` (tests / odd layouts still
       resolve to somewhere writable).
    """
    env = os.environ.get("EPCD_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "backend").is_dir():
            return parent
    return Path.cwd().resolve()


def runs_root() -> Path:
    """Unified run-artifact root: ``<repo_root>/runs`` (created lazily)."""
    root = repo_root() / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_segment(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (name or ""))
    return safe or "default"


def task_run_dir(session_id: str) -> Path:
    """Per-task artifact directory ``runs/<session>`` (created lazily)."""
    path = runs_root() / _safe_segment(session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    """Default session-store path: ``runs/epcd-agent-session.sqlite3``.

    A single audit DB shared across sessions (rows carry the session id); the
    file lives at the run root so it never lands in ``backend/``.
    """
    return runs_root() / "epcd-agent-session.sqlite3"