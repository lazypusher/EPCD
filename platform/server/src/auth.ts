import { randomUUID } from "node:crypto";
import bcrypt from "bcryptjs";
import type { Db } from "./db.js";

export interface AppUser {
  id: string;
  username: string;
  role: string;
}

export function hashPassword(pw: string): string {
  return bcrypt.hashSync(pw, 10);
}

export function verifyPassword(pw: string, hash: string): boolean {
  return bcrypt.compareSync(pw, hash);
}

export function createUser(
  db: Db,
  username: string,
  password: string,
  role: "user" | "admin" = "user"
): { user?: AppUser; error?: string } {
  const existing = db
    .prepare("SELECT id FROM app_user WHERE username = ?")
    .get(username) as { id: string } | undefined;
  if (existing) return { error: "用户名已存在" };
  const id = randomUUID();
  db.prepare(
    "INSERT INTO app_user (id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)"
  ).run(id, username, hashPassword(password), role, new Date().toISOString());
  return { user: { id, username, role } };
}

export function verifyLogin(
  db: Db,
  username: string,
  password: string
): { user?: AppUser; error?: string } {
  const row = db
    .prepare("SELECT * FROM app_user WHERE username = ?")
    .get(username) as { id: string; username: string; role: string; password_hash: string } | undefined;
  if (!row || !verifyPassword(password, row.password_hash)) {
    return { error: "用户名或密码错误" };
  }
  return { user: { id: row.id, username: row.username, role: row.role } };
}

export function issueToken(db: Db, userId: string): string {
  const token = randomUUID();
  db.prepare("INSERT INTO auth_token (token, user_id, created_at) VALUES (?, ?, ?)").run(
    token,
    userId,
    new Date().toISOString()
  );
  return token;
}

export function getUserByToken(db: Db, token: string): AppUser | null {
  const row = db
    .prepare(
      `SELECT u.id, u.username, u.role
         FROM auth_token t JOIN app_user u ON u.id = t.user_id
        WHERE t.token = ?`
    )
    .get(token) as { id: string; username: string; role: string } | undefined;
  if (!row) return null;
  return { id: row.id, username: row.username, role: row.role };
}

// 轻量鉴权中间件：校验 Bearer token，附加 req.user
function extractToken(req: unknown): string {
  const r = req as { headers: Record<string, string | undefined>; query?: unknown };
  const auth = r.headers.authorization ?? "";
  const q = r.query as { token?: string } | undefined;
  const fromHeader = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  return fromHeader || (typeof q?.token === "string" ? q.token : "");
}

export function requireAuth(db: Db) {
  return async (req: unknown, reply: { code: (n: number) => { send: (b: unknown) => unknown } }) => {
    const r = req as { user?: AppUser };
    const user = getUserByToken(db, extractToken(req));
    if (!user) {
      return reply.code(401).send({ ok: false, error: { message: "未登录或 token 失效" } });
    }
    r.user = user;
    return undefined;
  };
}

// 管理员中间件：校验 token + admin 角色
export function requireAdmin(db: Db) {
  return async (req: unknown, reply: { code: (n: number) => { send: (b: unknown) => unknown } }) => {
    const r = req as { user?: AppUser };
    const user = getUserByToken(db, extractToken(req));
    if (!user) {
      return reply.code(401).send({ ok: false, error: { message: "未登录或 token 失效" } });
    }
    if (user.role !== "admin") {
      return reply.code(403).send({ ok: false, error: { message: "需要管理员权限" } });
    }
    r.user = user;
    return undefined;
  };
}

export function ensureAdmin(db: Db): void {
  const n = db.prepare("SELECT count(*) AS c FROM app_user").get() as { c: number };
  if (n.c === 0) {
    createUser(db, "admin", "admin123", "admin");
    console.log("[auth] 已创建默认管理员 admin / admin123（请尽快修改）");
  }
}