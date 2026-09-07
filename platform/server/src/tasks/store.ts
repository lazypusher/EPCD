import { randomUUID } from "node:crypto";
import type { Db } from "../db.js";
import { MILESTONES, type Phase } from "./phases.js";

export type TaskStatus =
  | "created"
  | "running"
  | "optimizing"
  | "awaiting_confirmation"
  | "confirmed"
  | "delivered"
  | "failed"
  | "aborted";

export interface TaskRow {
  id: string;
  name: string;
  user_id: string | null;
  server: string;
  session: string;
  current_phase: Phase | string;
  status: TaskStatus | string;
  config_json: string;
  created_at: string;
  updated_at: string;
}

export interface PhaseLogRow {
  id: number;
  task_id: string;
  phase: string;
  status: string;
  payload_json: string | null;
  error_json: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface MilestoneRow {
  id: number;
  task_id: string;
  code: string;
  phase: string;
  status: string;
  snapshot_json: string | null;
  decided_at: string | null;
}

function now(): string {
  return new Date().toISOString();
}

export function createTask(
  db: Db,
  opts: { name: string; server: string; config?: unknown; userId?: string }
): TaskRow {
  const id = randomUUID();
  const session = `task-${id.slice(0, 8)}`;
  const ts = now();
  db.prepare(
    `INSERT INTO design_task
       (id, name, user_id, server, session, current_phase, status, config_json, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 'health', 'created', ?, ?, ?)`
  ).run(
    id,
    opts.name,
    opts.userId ?? null,
    opts.server,
    session,
    JSON.stringify(opts.config ?? {}),
    ts,
    ts
  );

  // 初始化 4 个里程碑
  const ins = db.prepare(
    `INSERT INTO design_milestone (task_id, code, phase, status) VALUES (?, ?, ?, 'pending')`
  );
  for (const m of MILESTONES) ins.run(id, m.code, m.phase);

  return getTask(db, id)!;
}

export function getTask(db: Db, id: string): TaskRow | undefined {
  return db.prepare(`SELECT * FROM design_task WHERE id = ?`).get(id) as unknown as
    | TaskRow
    | undefined;
}

export function listTasks(db: Db, userId?: string, includeAll = false): TaskRow[] {
  if (userId && !includeAll) {
    return db
      .prepare(`SELECT * FROM design_task WHERE user_id = ? ORDER BY created_at DESC`)
      .all(userId) as unknown as TaskRow[];
  }
  return db
    .prepare(`SELECT * FROM design_task ORDER BY created_at DESC`)
    .all() as unknown as TaskRow[];
}

export function updateTask(
  db: Db,
  id: string,
  patch: Partial<Pick<TaskRow, "current_phase" | "status" | "config_json" | "name" | "server">>
): void {
  const fields: string[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const vals: any[] = [];
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined) continue;
    fields.push(`${k} = ?`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vals.push(v as any);
  }
  if (fields.length === 0) return;
  fields.push("updated_at = ?");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vals.push(now() as any, id as any);
  db.prepare(`UPDATE design_task SET ${fields.join(", ")} WHERE id = ?`).run(...vals);
}

export function patchTaskConfig(db: Db, id: string, config: unknown): void {
  updateTask(db, id, { config_json: JSON.stringify(config) });
}

export function logPhase(
  db: Db,
  taskId: string,
  phase: string,
  status: string,
  payload?: unknown,
  error?: unknown
): void {
  db.prepare(
    `INSERT INTO phase_log (task_id, phase, status, payload_json, error_json, started_at, finished_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).run(
    taskId,
    phase,
    status,
    payload === undefined ? null : JSON.stringify(payload),
    error === undefined ? null : JSON.stringify(error),
    now(),
    now()
  );
}

export function getPhaseLogs(db: Db, taskId: string): PhaseLogRow[] {
  return db
    .prepare(`SELECT * FROM phase_log WHERE task_id = ? ORDER BY id ASC`)
    .all(taskId) as unknown as PhaseLogRow[];
}

export function getMilestones(db: Db, taskId: string): MilestoneRow[] {
  return db
    .prepare(`SELECT * FROM design_milestone WHERE task_id = ? ORDER BY id ASC`)
    .all(taskId) as unknown as MilestoneRow[];
}

export function updateMilestone(
  db: Db,
  taskId: string,
  code: string,
  status: string,
  snapshot?: unknown
): void {
  db.prepare(
    `UPDATE design_milestone SET status = ?, snapshot_json = ?, decided_at = ?
      WHERE task_id = ? AND code = ?`
  ).run(
    status,
    snapshot === undefined ? null : JSON.stringify(snapshot),
    now(),
    taskId,
    code
  );
}

export function getTaskWithContext(db: Db, taskId: string) {
  const task = getTask(db, taskId);
  if (!task) return undefined;
  return {
    task,
    config: safeJsonParse(task.config_json),
    phases: getPhaseLogs(db, taskId).map((p) => ({
      phase: p.phase,
      status: p.status,
      payload: safeJsonParse(p.payload_json ?? undefined),
      error: safeJsonParse(p.error_json ?? undefined),
      startedAt: p.started_at,
      finishedAt: p.finished_at,
    })),
    milestones: getMilestones(db, taskId).map((m) => ({
      code: m.code,
      phase: m.phase,
      status: m.status,
      snapshot: safeJsonParse(m.snapshot_json ?? undefined),
      decidedAt: m.decided_at,
    })),
  };
}

function safeJsonParse(s?: string): unknown {
  if (!s) return undefined;
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}