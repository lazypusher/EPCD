import type { MilestoneDecision, MilestoneCode, TaskContext } from "../types";
import { clearAuth, getToken } from "../auth";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const resp = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (resp.status === 401 && !path.startsWith("/api/auth/")) {
    clearAuth();
    window.location.href = "/login";
    throw new Error("未登录或登录已过期");
  }
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

  cancelOptimization: (id: string) =>
    request<{ ok: boolean; cancelRequested: boolean; taskId: string }>(
      `/api/tasks/${id}/optimization/cancel`,
      { method: "POST", body: "{}" }
    ),

  getDelivery: (id: string) => request<{ ok: boolean } & import("../types").Delivery>(
    `/api/tasks/${id}/delivery`
  ),

  artifactUrl: (id: string, file: string) =>
    `/api/tasks/${id}/artifacts/${encodeURIComponent(file)}`,

  login: (username: string, password: string) =>
    request<{ ok: boolean; token?: string; user?: { id: string; username: string; role: string } }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) }
    ),

  register: (username: string, password: string) =>
    request<{ ok: boolean; token?: string; user?: { id: string; username: string; role: string } }>(
      "/api/auth/register",
      { method: "POST", body: JSON.stringify({ username, password }) }
    ),

  me: () => request<{ ok: boolean; user: { id: string; username: string; role: string } | null }>(
    "/api/auth/me"
  ),

  listServers: () =>
    request<{ ok: boolean; servers: { name: string; ssh?: string; pkg?: string }[] }>(
      "/api/servers"
    ),

  getAdvice: (id: string) =>
    request<{ ok: boolean; source: "llm" | "rule"; advice: string[]; unmet: unknown[] }>(
      `/api/tasks/${id}/advice`
    ),
};