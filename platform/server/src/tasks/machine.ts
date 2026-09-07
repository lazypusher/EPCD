import type { EpcdConfig, EpcdResult, EpcdTool } from "../epcd/bridge.js";
import type { Db } from "../db.js";
import { handleOptimizationPhase } from "./optimizer.js";
import {
  MILESTONE_BY_CODE,
  MILESTONES,
  PHASE_AFTER,
  type MilestoneDecision,
  type Phase,
} from "./phases.js";
import {
  getTask,
  getTaskWithContext,
  logPhase,
  patchTaskConfig,
  updateMilestone,
  updateTask,
  type TaskRow,
} from "./store.js";

export type EpcdBridge = (tool: EpcdTool, input?: unknown) => Promise<EpcdResult>;

// 每个阶段调用的工具 + 从 config 取 input 的键
const PHASE_TOOL: Record<Phase, { tool: EpcdTool; inputKey: string }> = {
  health: { tool: "epcd_health", inputKey: "healthInput" },
  project: { tool: "epcd_project", inputKey: "projectInput" },
  template: { tool: "epcd_template", inputKey: "templateInput" },
  objectives: { tool: "epcd_config", inputKey: "objectivesInput" },
  optimization: { tool: "optimization_start", inputKey: "optimizationInput" },
  apply: { tool: "epcd_config", inputKey: "applyInput" },
  final: { tool: "epcd_run", inputKey: "finalInput" },
  deliver: { tool: "artifact_view", inputKey: "deliverInput" },
};

function parseTaskConfig(task: TaskRow): Record<string, unknown> {
  try {
    return JSON.parse(task.config_json);
  } catch {
    return {};
  }
}

interface PhaseOutcome {
  ok: boolean;
  payload?: unknown;
  error?: unknown;
}

async function executePhase(
  db: Db,
  task: TaskRow,
  phase: Phase,
  bridge: EpcdBridge
): Promise<PhaseOutcome> {
  const { tool, inputKey } = PHASE_TOOL[phase];
  const config = parseTaskConfig(task);
  const input = config[inputKey] ?? {};
  logPhase(db, task.id, phase, "running", input);
  const r = await bridge(tool, input);
  if (r.ok) {
    return { ok: true, payload: r.data };
  }
  return { ok: false, error: r.error ?? { message: r.raw || "tool failed" } };
}

// 从当前阶段推进，直到里程碑暂停 / 完成 / 失败
async function advance(
  db: Db,
  bridge: EpcdBridge,
  task: TaskRow,
  epcdConfig: EpcdConfig
): Promise<TaskRow> {
  let current = task;
  while (true) {
    const phase = current.current_phase as Phase;

    if (phase === "deliver") {
      updateTask(db, current.id, { status: "delivered" });
      return getTask(db, current.id)!;
    }

    // optimization 阶段：后台 spawn，完成后轮询推进到 apply
    if (phase === "optimization") {
      const { advanced, task: next } = await handleOptimizationPhase(db, epcdConfig, current);
      if (!advanced) return next; // 仍在后台运行（status=optimizing）
      current = next; // 已完成，立即进入 apply
      continue;
    }

    const outcome = await executePhase(db, current, phase, bridge);

    if (!outcome.ok) {
      logPhase(db, current.id, phase, "failed", undefined, outcome.error);
      updateTask(db, current.id, { status: "failed" });
      return getTask(db, current.id)!;
    }

    logPhase(db, current.id, phase, "succeeded", outcome.payload);

    const ms = MILESTONES.find((m) => m.phase === phase);
    if (ms) {
      updateMilestone(db, current.id, ms.code, "awaiting", outcome.payload);
      updateTask(db, current.id, { status: "awaiting_confirmation" });
      return getTask(db, current.id)!;
    }

    const next = PHASE_AFTER[phase];
    if (next === null) {
      updateTask(db, current.id, { status: "delivered" });
      return getTask(db, current.id)!;
    }
    updateTask(db, current.id, { current_phase: next, status: "running" });
    current = getTask(db, current.id)!;
  }
}

export function startTask(
  db: Db,
  bridge: EpcdBridge,
  epcdConfig: EpcdConfig,
  taskId: string
): Promise<TaskRow> {
  updateTask(db, taskId, { status: "running" });
  return advance(db, bridge, getTask(db, taskId)!, epcdConfig);
}

export async function confirmMilestone(
  db: Db,
  bridge: EpcdBridge,
  epcdConfig: EpcdConfig,
  taskId: string,
  code: string,
  decision: MilestoneDecision,
  modifiedConfig?: Record<string, unknown>
): Promise<TaskRow> {
  const task = getTask(db, taskId);
  if (!task) throw new Error(`task not found: ${taskId}`);
  const ms = (MILESTONE_BY_CODE as Record<string, (typeof MILESTONES)[number]>)[code];
  if (!ms) throw new Error(`unknown milestone: ${code}`);

  switch (decision) {
    case "approve": {
      updateMilestone(db, taskId, code, "approved");
      const next = PHASE_AFTER[ms.phase];
      if (next === null) {
        updateTask(db, taskId, { status: "delivered" });
        return getTask(db, taskId)!;
      }
      updateTask(db, taskId, { current_phase: next, status: "running" });
      return advance(db, bridge, getTask(db, taskId)!, epcdConfig);
    }
    case "modify": {
      updateMilestone(db, taskId, code, "modified", modifiedConfig ?? null);
      if (modifiedConfig) {
        const merged = { ...parseTaskConfig(task), ...modifiedConfig };
        patchTaskConfig(db, taskId, merged);
      }
      // 回到该里程碑阶段重做，重新输出并再次暂停确认
      updateTask(db, taskId, { current_phase: ms.phase, status: "running" });
      return advance(db, bridge, getTask(db, taskId)!, epcdConfig);
    }
    case "abort": {
      updateMilestone(db, taskId, code, "aborted");
      updateTask(db, taskId, { status: "aborted" });
      return getTask(db, taskId)!;
    }
  }
}

export function taskContext(db: Db, taskId: string) {
  return getTaskWithContext(db, taskId);
}