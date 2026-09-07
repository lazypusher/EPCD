import type { Db } from "./db.js";

export interface AuditRow {
  id: number;
  user_id: string | null;
  username: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail_json: string | null;
  created_at: string;
}

export interface UserRow {
  id: string;
  username: string;
  role: string;
  created_at: string;
}

export function recordAudit(
  db: Db,
  opts: {
    userId?: string;
    username?: string;
    action: string;
    targetType?: string;
    targetId?: string;
    detail?: unknown;
  }
): void {
  db.prepare(
    `INSERT INTO audit_log (user_id, username, action, target_type, target_id, detail_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).run(
    opts.userId ?? null,
    opts.username ?? null,
    opts.action,
    opts.targetType ?? null,
    opts.targetId ?? null,
    opts.detail === undefined ? null : JSON.stringify(opts.detail),
    new Date().toISOString()
  );
}

export function listAudit(db: Db, limit = 200): AuditRow[] {
  return db
    .prepare("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?")
    .all(limit) as unknown as AuditRow[];
}

export function listUsers(db: Db): UserRow[] {
  return db
    .prepare("SELECT id, username, role, created_at FROM app_user ORDER BY created_at")
    .all() as unknown as UserRow[];
}

export function setUserRole(db: Db, userId: string, role: "user" | "admin"): boolean {
  const res = db.prepare("UPDATE app_user SET role = ? WHERE id = ?").run(role, userId);
  return res.changes > 0;
}