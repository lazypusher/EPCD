import type { MilestoneDecision, MilestoneCode, TaskContext } from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await resp.json().catch(() => null);
  if (!resp.ok && body && "error" in body) {
    const err = body as { error?: { message?: string } };
    throw new Error(err.error?.message ?? `HTTP ${resp.status}`);
  }
  return body as T;
}

export interface TaskListItem {
  task: TaskContext;
}

export const api = {
  listTasks: () =>
    request<{ ok: boolean; tasks: { id: string; name: string; server: string; current_phase: string; status: string; created_at: string }[] }>(
      "/api/tasks"
    ),

  createTask: (opts: { name: string; server?: string; config?: Record<string, unknown> }) =>
    request<{ ok: boolean; task: TaskContext }>("/api/tasks", {
      method: "POST",
      body: JSON.stringify(opts),
    }),

  getTask: (id: string) =>
    request<{ ok: boolean } & TaskContext>(`/api/tasks/${id}`),

  startTask: (id: string) =>
    request<{ ok: boolean } & TaskContext>(`/api/tasks/${id}/start`, {
      method: "POST",
      body: "{}",
    }),

  confirmMilestone: (
    id: string,
    code: MilestoneCode,
    decision: MilestoneDecision,
    config?: Record<string, unknown>
  ) =>
    request<{ ok: boolean } & TaskContext>(`/api/tasks/${id}/milestones/${code}`, {
      method: "POST",
      body: JSON.stringify({ decision, config }),
    }),
};