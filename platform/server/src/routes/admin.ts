import type { FastifyInstance } from "fastify";
import type { Db } from "../db.js";
import { requireAdmin } from "../auth.js";
import { listAudit, listUsers, setUserRole } from "../audit.js";

export async function adminRoutes(app: FastifyInstance, db: Db): Promise<void> {
  app.addHook("preHandler", requireAdmin(db));

  app.get("/api/admin/users", async () => ({ ok: true, users: listUsers(db) }));

  app.put("/api/admin/users/:id/role", async (req, reply) => {
    const { id } = req.params as { id: string };
    const body = (req.body ?? {}) as { role?: string };
    if (!body.role || !["user", "admin"].includes(body.role)) {
      return reply.code(400).send({ ok: false, error: { message: "role must be user|admin" } });
    }
    if (!setUserRole(db, id, body.role as "user" | "admin")) {
      return reply.code(404).send({ ok: false, error: { message: "user not found" } });
    }
    return { ok: true };
  });

  app.get("/api/admin/audit", async (req) => {
    const q = (req.query ?? {}) as { limit?: string };
    const limit = Math.min(Number(q.limit) || 200, 1000);
    return { ok: true, events: listAudit(db, limit) };
  });
}