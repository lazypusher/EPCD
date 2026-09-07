import { spawn, type ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import type { Db } from "../db.js";
import type { EpcdConfig } from "../epcd/bridge.js";
import { logPhase, patchTaskConfig, updateTask, type TaskRow } from "./store.js";

// ---------------------------------------------------------------------------
// optimization_start 阻塞整轮 TPE。这里把它 spawn 成独立后台进程，server 直接读
// 同一 SQLite（optimization_task / job / kv_state 表）轮询进度，不依赖子进程
// stdout（跨进程状态都在 db 里）。
// ---------------------------------------------------------------------------

export const optimizerEvents = new EventEmitter();

interface OptimizationJob {
  designTaskId: string;
  epcdTaskId: string;
  child: ChildProcess;
  closed: boolean;
  exitCode: number | null;
  report?: unknown;
  outputRaw?: string;
}

const jobs = new Map<string, OptimizationJob>();

export interface OptimizationSnapshot {
  epcdTaskId: string;
  status: string;
  bestJobId?: string;
  rounds?: unknown[];
  consumed?: unknown;
  jobCount: number;
}

function safeParse(s: string | null | undefined): unknown {
  if (!s) return undefined;
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

// task_id = opt-(该 session 的 job 行数 + 1)，与 epcd_agent 一致
export function predictTaskId(db: Db, session: string): string {
  const row = db
    .prepare("SELECT count(*) AS c FROM job WHERE session_id = ?")
    .get(session) as { c: number };
  return `opt-${row.c + 1}`;
}

export function getOptimizationSnapshot(
  db: Db,
  session: string,
  epcdTaskId: string
): OptimizationSnapshot | null {
  const row = db
    .prepare(
      "SELECT * FROM optimization_task WHERE session_id = ? AND task_id = ?"
    )
    .get(session, epcdTaskId) as
    | Record<string, unknown>
    | undefined;
  if (!row) return null;
  const jc = db
    .prepare("SELECT count(*) AS c FROM job WHERE session_id = ?")
    .get(session) as { c: number };
  return {
    epcdTaskId: row.task_id as string,
    status: row.status as string,
    bestJobId: (row.best_job_id as string) ?? undefined,
    rounds: (safeParse(row.rounds as string) as unknown[]) ?? undefined,
    consumed: safeParse(row.consumed as string) as unknown,
    jobCount: jc.c,
  };
}

export function launchOptimization(
  db: Db,
  config: EpcdConfig,
  task: TaskRow,
  input: unknown
): OptimizationJob {
  const epcdTaskId = predictTaskId(db, task.session);
  const args = [
    "-m",
    "epcd_agent.cli",
    "--server",
    task.server,
    "--db",
    config.dbPath,
    "--session",
    task.session,
    "optimization_start",
  ];
  const child = spawn(config.python, args, {
    cwd: config.backendDir,
    windowsHide: true,
  });

  const job: OptimizationJob = {
    designTaskId: task.id,
    epcdTaskId,
    child,
    closed: false,
    exitCode: null,
  };
  jobs.set(task.id, job);

  let out = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (d) => (out += d));
  child.on("close", (code) => {
    job.closed = true;
    job.exitCode = code;
    job.outputRaw = out.trim();
    try {
      const parsed = JSON.parse(out.trim());
      job.report = parsed.data?.report ?? parsed.data;
    } catch {
      job.report = undefined;
    }
    optimizerEvents.emit("optimization-closed", task.id, job);
  });
  child.on("error", (err) => {
    job.closed = true;
    optimizerEvents.emit("optimization-error", task.id, err);
  });

  child.stdin.write(JSON.stringify(input));
  child.stdin.end();

  return job;
}

export function requestCancel(db: Db, session: string, epcdTaskId: string): void {
  db.prepare(
    `INSERT INTO kv_state (session_id, key, value) VALUES (?, ?, 'true')
     ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value`
  ).run(session, `opt-cancel:${epcdTaskId}`);
}

export function isCancelRequested(
  db: Db,
  session: string,
  epcdTaskId: string
): boolean {
  const row = db
    .prepare("SELECT value FROM kv_state WHERE session_id = ? AND key = ?")
    .get(session, `opt-cancel:${epcdTaskId}`) as { value: string } | undefined;
  return row?.value === "true";
}

export function getJob(designTaskId: string): OptimizationJob | undefined {
  return jobs.get(designTaskId);
}

// machine.ts 的 optimization 阶段处理器：首次 launch，之后轮询完成态。
// 返回 true 表示已推进到下一阶段（apply），false 表示仍在后台运行/已失败标记。
export async function handleOptimizationPhase(
  db: Db,
  config: EpcdConfig,
  task: TaskRow
): Promise<{ advanced: boolean; task: TaskRow }> {
  const cfg = safeParse(task.config_json) as Record<string, unknown>;
  const epcdTaskId = cfg.optimizationTaskId as string | undefined;

  if (!epcdTaskId) {
    const input = cfg.optimizationInput ?? {};
    const job = launchOptimization(db, config, task, input);
    patchTaskConfig(db, task.id, { ...cfg, optimizationTaskId: job.epcdTaskId });
    logPhase(db, task.id, "optimization", "running", { task_id: job.epcdTaskId });
    updateTask(db, task.id, { status: "optimizing" });
    return { advanced: false, task: getTaskForId(db, task.id) };
  }

  const snap = getOptimizationSnapshot(db, task.session, epcdTaskId);
  const job = jobs.get(task.id);

  if (snap?.status === "finished") {
    const report = job?.report ?? { best_job_id: snap.bestJobId, rounds: snap.rounds };
    logPhase(db, task.id, "optimization", "succeeded", { task_id: epcdTaskId, report });
    // 把 best_parameters 注入 config.applyInput，供 apply 阶段写回
    const bestParams = (report as { best_parameters?: unknown })?.best_parameters;
    const nextCfg = { ...cfg };
    if (bestParams !== undefined) {
      nextCfg.applyInput = bestParams;
    }
    patchTaskConfig(db, task.id, nextCfg);
    updateTask(db, task.id, { current_phase: "apply", status: "running" });
    return { advanced: true, task: getTaskForId(db, task.id) };
  }

  if (snap?.status === "paused") {
    logPhase(db, task.id, "optimization", "failed", undefined, {
      code: "OPTIMIZATION_PAUSED",
      cancel_requested: isCancelRequested(db, task.session, epcdTaskId),
    });
    updateTask(db, task.id, { status: "failed" });
    return { advanced: false, task: getTaskForId(db, task.id) };
  }

  // pending / 首次未入库：仍在后台
  return { advanced: false, task };
}

function getTaskForId(db: Db, id: string): TaskRow {
  return db.prepare("SELECT * FROM design_task WHERE id = ?").get(id) as unknown as TaskRow;
}