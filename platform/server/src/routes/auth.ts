import type { FastifyInstance } from "fastify";
import type { Db } from "../db.js";
import { createUser, getUserByToken, issueToken, verifyLogin, type AppUser } from "../auth.js";
import { recordAudit } from "../audit.js";

interface AuthBody {
  username?: string;
  password?: string;
}

export async function authRoutes(app: FastifyInstance, db: Db): Promise<void> {
  app.post("/api/auth/register", async (req, reply) => {
    const { username, password } = (req.body ?? {}) as AuthBody;
    if (!username || !password) {
      return reply.code(400).send({ ok: false, error: { message: "用户名和密码必填" } });
    }
    const r = createUser(db, username, password);
    if (r.error) return reply.code(409).send({ ok: false, error: { message: r.error } });
    const token = issueToken(db, r.user!.id);
    recordAudit(db, { userId: r.user!.id, username: r.user!.username, action: "auth.register" });
    return { ok: true, token, user: r.user };
  });

  app.post("/api/auth/login", async (req, reply) => {
    const { username, password } = (req.body ?? {}) as AuthBody;
    const r = verifyLogin(db, username ?? "", password ?? "");
    if (r.error) return reply.code(401).send({ ok: false, error: { message: r.error } });
    const token = issueToken(db, r.user!.id);
    recordAudit(db, { userId: r.user!.id, username: r.user!.username, action: "auth.login" });
    return { ok: true, token, user: r.user };
  });

  app.get("/api/auth/me", async (req) => {
    const auth = req.headers.authorization ?? "";
    const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
    const user: AppUser | null = token ? getUserByToken(db, token) : null;
    return { ok: true, user };
  });
}