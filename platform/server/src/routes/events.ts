import type { FastifyInstance } from "fastify";
import type { Db } from "../db.js";
import { requireAuth, type AppUser } from "../auth.js";
import { recordAudit } from "../audit.js";
import { loadConfig } from "../epcd/bridge.js";
import { taskContext } from "../tasks/machine.js";
import {
  getOptimizationSnapshot,
  handleOptimizationPhase,
  requestCancel,
} from "../tasks/optimizer.js";
import { getTask } from "../tasks/store.js";

export async function eventRoutes(app: FastifyInstance, db: Db): Promise<void> {
  const config = loadConfig();
  app.addHook("preHandler", requireAuth(db));

  // 每 1s 拉取任务上下文；若在优化中则顺带推进状态机（轮询 optimization_task）
  async function snapshot(id: string) {
    const task = getTask(db, id);
    if (task && task.status === "optimizing") {
      await handleOptimizationPhase(db, config, task);
    }
    const ctx = taskContext(db, id);
    let optimization: unknown = null;
    if (ctx && task) {
      const cfg = JSON.parse((task.config_json ?? "{}") as string);
      const t = cfg.optimizationTaskId as string | undefined;
      if (t) optimization = getOptimizationSnapshot(db, task.session, t);
    }
    return { ...ctx, optimization };
  }

  app.get("/api/tasks/:id/events", async (req, reply) => {
    const { id } = req.params as { id: string };

    reply.raw.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    reply.raw.write(": connected\n\n");

    const send = (event: string, data: unknown) => {
      reply.raw.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    };

    const timer = setInterval(async () => {
      try {
        const snap = await snapshot(id);
        send("status", snap);
      } catch (err) {
        send("error", { message: String(err) });
      }
    }, 1000);

    req.raw.on("close", () => clearInterval(timer));
  });

  app.post("/api/tasks/:id/optimization/cancel", async (req, reply) => {
    const { id } = req.params as { id: string };
    const task = getTask(db, id);
    if (!task) return reply.code(404).send({ ok: false, error: { message: "task not found" } });
    const cfg = (JSON.parse(task.config_json ?? "{}") as Record<string, unknown>) ?? {};
    const epcdTaskId = cfg.optimizationTaskId as string | undefined;
    if (!epcdTaskId) {
      return reply.code(400).send({ ok: false, error: { message: "no active optimization" } });
    }
    requestCancel(db, task.session, epcdTaskId);
    const user = (req as { user?: AppUser }).user!;
    recordAudit(db, {
      userId: user.id,
      username: user.username,
      action: "optimization.cancel",
      targetType: "task",
      targetId: id,
      detail: { taskId: epcdTaskId },
    });
    return { ok: true, cancelRequested: true, taskId: epcdTaskId };
  });
}