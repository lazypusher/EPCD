export type Phase =
  | "health"
  | "project"
  | "template"
  | "objectives"
  | "optimization"
  | "apply"
  | "final"
  | "deliver";

export type TaskStatus =
  | "created"
  | "running"
  | "awaiting_confirmation"
  | "confirmed"
  | "delivered"
  | "failed"
  | "aborted";

export type MilestoneCode = "M1" | "M2" | "M3" | "M4";
export type MilestoneDecision = "approve" | "modify" | "abort";
export type MilestoneStatus = "pending" | "awaiting" | "approved" | "modified" | "aborted";

export interface Task {
  id: string;
  name: string;
  user_id: string | null;
  server: string;
  session: string;
  current_phase: Phase;
  status: TaskStatus;
  config_json: string;
  created_at: string;
  updated_at: string;
}

export interface PhaseLog {
  phase: Phase;
  status: "running" | "succeeded" | "failed";
  payload?: unknown;
  error?: unknown;
  startedAt?: string;
  finishedAt?: string;
}

export interface Milestone {
  code: MilestoneCode;
  phase: Phase;
  status: MilestoneStatus;
  snapshot?: unknown;
  decidedAt?: string;
}

export interface TaskContext {
  task: Task;
  config: Record<string, unknown>;
  phases: PhaseLog[];
  milestones: Milestone[];
}

export const PHASE_LABELS: Record<Phase, string> = {
  health: "健康检查",
  project: "建工程",
  template: "选模板",
  objectives: "配置目标",
  optimization: "迭代优化",
  apply: "写回最优",
  final: "最终仿真",
  deliver: "产物交付",
};

export const PHASE_ORDER: Phase[] = [
  "health",
  "project",
  "template",
  "objectives",
  "optimization",
  "apply",
  "final",
  "deliver",
];