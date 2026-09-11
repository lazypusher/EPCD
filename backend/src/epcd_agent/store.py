"""Design Session Store: single source of truth outside the LLM (design doc section 9)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
    session_id     TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    model_config   TEXT
);
CREATE TABLE IF NOT EXISTS instance (
    session_id    TEXT NOT NULL,
    instance_id   TEXT NOT NULL,
    project_dir   TEXT NOT NULL,
    template_id   TEXT,
    name          TEXT,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, instance_id)
);
CREATE TABLE IF NOT EXISTS job (
    session_id      TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    request_id      TEXT,
    task_type       TEXT,
    status          TEXT,
    parameters      TEXT,
    objective_cost  REAL,
    started_at      TEXT,
    finished_at     TEXT,
    PRIMARY KEY (session_id, job_id)
);
CREATE TABLE IF NOT EXISTS optimization_task (
    session_id   TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    status       TEXT NOT NULL,
    budget       TEXT,
    consumed     TEXT,
    best_job_id  TEXT,
    rounds       TEXT,
    PRIMARY KEY (session_id, task_id)
);
CREATE TABLE IF NOT EXISTS milestone (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    choice       TEXT NOT NULL,
    snapshot     TEXT,
    recorded_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_info (
    session_id          TEXT PRIMARY KEY,
    project_dir         TEXT NOT NULL,
    lib_name            TEXT,
    technology_digest   TEXT
);
CREATE TABLE IF NOT EXISTS kv_state (
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT,
    PRIMARY KEY (session_id, key)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def _loads(text: str | None) -> Any:
    return None if text is None else json.loads(text)


class SessionStore:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- session ---------------------------------------------------------
    def create_session(self, session_id: str, model_config: dict | None = None) -> None:
        self._conn.execute(
            "INSERT INTO session (session_id, created_at, model_config) VALUES (?, ?, ?)",
            (session_id, _utc_now(), _dumps(model_config)),
        )
        self._conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM session WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "model_config": _loads(row["model_config"]),
        }

    # -- project ---------------------------------------------------------
    def set_project(self, session_id: str, project_dir: str,
                    lib_name: str | None = None, technology_digest: str | None = None) -> None:
        self._conn.execute(
            """INSERT INTO project_info (session_id, project_dir, lib_name, technology_digest)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 project_dir = excluded.project_dir,
                 lib_name = excluded.lib_name,
                 technology_digest = excluded.technology_digest""",
            (session_id, project_dir, lib_name, technology_digest),
        )
        self._conn.commit()

    def get_project(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM project_info WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "project_dir": row["project_dir"],
            "lib_name": row["lib_name"],
            "technology_digest": row["technology_digest"],
        }

    # -- instance --------------------------------------------------------
    def upsert_instance(self, session_id: str, instance_id: str, *,
                        template_id: str | None, name: str | None, project_dir: str) -> None:
        self._conn.execute(
            """INSERT INTO instance (session_id, instance_id, project_dir, template_id, name, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, instance_id) DO UPDATE SET
                 project_dir = excluded.project_dir,
                 template_id = excluded.template_id,
                 name = excluded.name""",
            (session_id, instance_id, project_dir, template_id, name, _utc_now()),
        )
        self._conn.commit()

    def set_active_instance(self, session_id: str, instance_id: str) -> None:
        self.set_state(session_id, "active_instance_id", instance_id)

    def get_active_instance(self, session_id: str) -> dict | None:
        instance_id = self.get_state(session_id, "active_instance_id")
        if not instance_id:
            return None
        row = self._conn.execute(
            "SELECT * FROM instance WHERE session_id = ? AND instance_id = ?",
            (session_id, instance_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "instance_id": row["instance_id"],
            "template_id": row["template_id"],
            "name": row["name"],
            "project_dir": row["project_dir"],
            "config_digest": self.get_config_digest(session_id),
        }

    # -- config digest ----------------------------------------------------
    def set_config_digest(self, session_id: str, digest: str) -> None:
        self.set_state(session_id, "config_digest", digest)

    def get_config_digest(self, session_id: str) -> str | None:
        return self.get_state(session_id, "config_digest")

    # -- jobs -------------------------------------------------------------
    def add_job(self, session_id: str, job_id: str, *, request_id: str | None,
                task_type: str, status: str, parameters: dict | None = None) -> None:
        self._conn.execute(
            """INSERT INTO job (session_id, job_id, request_id, task_type, status, parameters)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, job_id, request_id, task_type, status, _dumps(parameters)),
        )
        self._conn.commit()

    def update_job(self, session_id: str, job_id: str, *, status: str | None = None,
                   objective_cost: float | None = None,
                   started_at: str | None = None, finished_at: str | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if objective_cost is not None:
            fields.append("objective_cost = ?")
            values.append(objective_cost)
        if started_at is not None:
            fields.append("started_at = ?")
            values.append(started_at)
        if finished_at is not None:
            fields.append("finished_at = ?")
            values.append(finished_at)
        if not fields:
            return
        values.extend([session_id, job_id])
        self._conn.execute(
            f"UPDATE job SET {', '.join(fields)} WHERE session_id = ? AND job_id = ?", values
        )
        self._conn.commit()

    def _job_row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "job_id": row["job_id"],
            "request_id": row["request_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "parameters": _loads(row["parameters"]),
            "objective_cost": row["objective_cost"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def get_job(self, session_id: str, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM job WHERE session_id = ? AND job_id = ?", (session_id, job_id)
        ).fetchone()
        return self._job_row(row)

    def list_jobs(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM job WHERE session_id = ? ORDER BY rowid", (session_id,)
        ).fetchall()
        return [self._job_row(r) for r in rows]

    def find_job_by_request(self, session_id: str, request_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM job WHERE session_id = ? AND request_id = ? ORDER BY rowid LIMIT 1",
            (session_id, request_id),
        ).fetchone()
        return self._job_row(row)

    # -- optimization tasks -----------------------------------------------
    def create_optimization(self, session_id: str, task_id: str, budget: dict) -> None:
        self._conn.execute(
            """INSERT INTO optimization_task (session_id, task_id, status, budget)
               VALUES (?, ?, 'pending', ?)""",
            (session_id, task_id, _dumps(budget)),
        )
        self._conn.commit()

    def update_optimization(self, session_id: str, task_id: str, *, status: str | None = None,
                            best_job_id: str | None = None, rounds: list | None = None,
                            consumed: dict | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if best_job_id is not None:
            fields.append("best_job_id = ?")
            values.append(best_job_id)
        if rounds is not None:
            fields.append("rounds = ?")
            values.append(_dumps(rounds))
        if consumed is not None:
            fields.append("consumed = ?")
            values.append(_dumps(consumed))
        if not fields:
            return
        values.extend([session_id, task_id])
        self._conn.execute(
            f"UPDATE optimization_task SET {', '.join(fields)} WHERE session_id = ? AND task_id = ?",
            values,
        )
        self._conn.commit()

    def get_optimization(self, session_id: str, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM optimization_task WHERE session_id = ? AND task_id = ?",
            (session_id, task_id),
        ).fetchone()
        return self._optimization_row(row)

    def list_optimizations(self, session_id: str) -> list[dict]:
        """All optimization tasks for a session, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM optimization_task WHERE session_id = ? "
            "ORDER BY CAST(substr(task_id, 5) AS INTEGER)",
            (session_id,),
        ).fetchall()
        return [self._optimization_row(r) for r in rows]

    def latest_optimization(self, session_id: str,
                            *, prefer_running: bool = False) -> dict | None:
        """Newest optimization task for a session.

        ``prefer_running=True`` returns the newest *running/pending* task if one
        exists, else falls back to the newest overall — so status polling can
        find the in-flight task without knowing its ``task_id`` in advance
        (``optimization_start`` blocks for the whole TPE loop and only exposes
        ``task_id`` on return, so callers cannot obtain it up front).
        """
        order = "ORDER BY CAST(substr(task_id, 5) AS INTEGER) DESC"
        if prefer_running:
            row = self._conn.execute(
                "SELECT * FROM optimization_task WHERE session_id = ? "
                f"AND status IN ('pending', 'running') {order} LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is not None:
                return self._optimization_row(row)
        row = self._conn.execute(
            "SELECT * FROM optimization_task WHERE session_id = ? "
            f"{order} LIMIT 1",
            (session_id,),
        ).fetchone()
        return self._optimization_row(row)

    def _optimization_row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "budget": _loads(row["budget"]),
            "consumed": _loads(row["consumed"]),
            "best_job_id": row["best_job_id"],
            "rounds": _loads(row["rounds"]),
        }

    # -- milestones ---------------------------------------------------------
    def record_milestone(self, session_id: str, name: str, choice: str,
                         snapshot: dict | None = None) -> None:
        self._conn.execute(
            "INSERT INTO milestone (session_id, name, choice, snapshot, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, name, choice, _dumps(snapshot), _utc_now()),
        )
        self._conn.commit()

    def list_milestones(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM milestone WHERE session_id = ? ORDER BY id", (session_id,)
        ).fetchall()
        return [
            {
                "name": r["name"],
                "choice": r["choice"],
                "snapshot": _loads(r["snapshot"]),
                "recorded_at": r["recorded_at"],
            }
            for r in rows
        ]

    # -- generic kv state ----------------------------------------------------
    def set_state(self, session_id: str, key: str, value: Any) -> None:
        self._conn.execute(
            """INSERT INTO kv_state (session_id, key, value) VALUES (?, ?, ?)
               ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value""",
            (session_id, key, _dumps(value)),
        )
        self._conn.commit()

    def get_state(self, session_id: str, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM kv_state WHERE session_id = ? AND key = ?", (session_id, key)
        ).fetchone()
        if row is None:
            return default
        return _loads(row["value"])
