import type { FastifyInstance } from "fastify";
import type { Db } from "../db.js";
import { requireAuth, type AppUser } from "../auth.js";
import { loadConfig, runEpcdTool, type EpcdTool } from "../epcd/bridge.js";
import {
  confirmMilestone,
  startTask,
  taskContext,
  type EpcdBridge,
} from "../tasks/machine.js";
import {
  createTask,
  getTask,
  listTasks,
  type TaskRow,
} from "../tasks/store.js";
import type { MilestoneDecision } from "../tasks/phases.js";

export async function taskRoutes(app: FastifyInstance, db: Db): Promise<void> {
  const config = loadConfig();

  const bridgeFor = (task: TaskRow): EpcdBridge => (tool: EpcdTool, input?: unknown) =>
    runEpcdTool(
      { tool, input, server: task.server, session: task.session },
      config
    );

  // 所有 /api/tasks* 需要登录（Bearer token）
  app.addHook("preHandler", requireAuth(db));

  app.post("/api/tasks", async (req, reply) => {
    const body = (req.body ?? {}) as {
      name?: string;
      server?: string;
      config?: Record<string, unknown>;
    };
    if (!body.name) {
      return reply.code(400).send({ ok: false, error: { message: "name required" } });
    }
    const user = (req as { user?: AppUser }).user!;
    const task = createTask(db, {
      name: body.name,
      server: body.server ?? config.defaultServer,
      config: body.config ?? {},
      userId: user.id,
    });
    return { ok: true, task: taskContext(db, task.id) };
  });

  app.get("/api/tasks", async (req) => {
    const user = (req as { user?: AppUser }).user!;
    return { ok: true, tasks: listTasks(db, user.id, user.role === "admin") };
  });

  app.get("/api/tasks/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    const ctx = taskContext(db, id);
    if (!ctx) return reply.code(404).send({ ok: false, error: { message: "task not found" } });
    return { ok: true, ...ctx };
  });

  app.post("/api/tasks/:id/start", async (req, reply) => {
    const { id } = req.params as { id: string };
    const task = getTask(db, id);
    if (!task) return reply.code(404).send({ ok: false, error: { message: "task not found" } });
    const started = await startTask(db, bridgeFor(task), config, task.id);
    return { ok: true, ...taskContext(db, started.id) };
  });

  app.post("/api/tasks/:id/milestones/:code", async (req, reply) => {
    const { id, code } = req.params as { id: string; code: string };
    const task = getTask(db, id);
    if (!task) return reply.code(404).send({ ok: false, error: { message: "task not found" } });
    const body = (req.body ?? {}) as {
      decision?: MilestoneDecision;
      config?: Record<string, unknown>;
    };
    if (!body.decision || !["approve", "modify", "abort"].includes(body.decision)) {
      return reply.code(400).send({
        ok: false,
        error: { message: "decision must be approve|modify|abort" },
      });
    }
    try {
      const next = await confirmMilestone(
        db,
        bridgeFor(task),
        config,
        task.id,
        code,
        body.decision,
        body.config
      );
      return { ok: true, ...taskContext(db, next.id) };
    } catch (err) {
      return reply.code(400).send({ ok: false, error: { message: String(err) } });
    }
  });
}