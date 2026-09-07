import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export type Db = DatabaseSync;

export function openDb(dbPath: string): Db {
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new DatabaseSync(dbPath);
  db.exec("PRAGMA journal_mode = WAL;");
  db.exec("PRAGMA foreign_keys = ON;");
  migrate(db);
  return db;
}

export function migrate(db: Db): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS design_task (
      id            TEXT PRIMARY KEY,
      name          TEXT NOT NULL,
      user_id       TEXT,
      server        TEXT NOT NULL DEFAULT 'epcd-primary',
      session       TEXT NOT NULL,
      current_phase TEXT NOT NULL DEFAULT 'health',
      status        TEXT NOT NULL DEFAULT 'created',
      config_json   TEXT NOT NULL DEFAULT '{}',
      created_at    TEXT NOT NULL,
      updated_at    TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS phase_log (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id      TEXT NOT NULL,
      phase        TEXT NOT NULL,
      status       TEXT NOT NULL,
      payload_json TEXT,
      error_json   TEXT,
      started_at   TEXT,
      finished_at  TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_phase_log_task ON phase_log(task_id);

    -- 注意：不能叫 milestone —— epcd_agent store 在同库有同名表（不同字段）。
    CREATE TABLE IF NOT EXISTS design_milestone (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id       TEXT NOT NULL,
      code          TEXT NOT NULL,
      phase         TEXT NOT NULL,
      status        TEXT NOT NULL DEFAULT 'pending',
      snapshot_json TEXT,
      decided_at    TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_design_milestone_task ON design_milestone(task_id);
  `);
}