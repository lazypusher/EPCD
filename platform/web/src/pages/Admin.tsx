import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button, Pill } from "@deepseek-ai/dsh-client-ui-primitives";
import { api } from "../api/client";

const cell: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 10px",
  borderBottom: "1px solid var(--dsw-border, #eee)",
};

export function Admin() {
  const qc = useQueryClient();
  const usersQ = useQuery({ queryKey: ["admin", "users"], queryFn: api.adminUsers });
  const auditQ = useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => api.adminAudit(200),
  });

  const setRoleMut = useMutation({
    mutationFn: (args: { id: string; role: "user" | "admin" }) =>
      api.adminSetRole(args.id, args.role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <div style={{ padding: 24, maxWidth: 920 }}>
      <Link to="/">← 返回</Link>
      <h1>管理后台</h1>

      <section style={{ margin: "16px 0" }}>
        <h3>用户</h3>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={cell}>用户名</th>
              <th style={cell}>角色</th>
              <th style={cell}>注册时间</th>
              <th style={cell}>操作</th>
            </tr>
          </thead>
          <tbody>
            {usersQ.data?.users.map((u) => (
              <tr key={u.id}>
                <td style={cell}>{u.username}</td>
                <td style={cell}>
                  <Pill active={u.role === "admin"}>{u.role === "admin" ? "管理员" : "用户"}</Pill>
                </td>
                <td style={cell}>{new Date(u.created_at).toLocaleString()}</td>
                <td style={cell}>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={setRoleMut.isPending || u.username === "admin"}
                    onClick={() =>
                      setRoleMut.mutate({ id: u.id, role: u.role === "admin" ? "user" : "admin" })
                    }
                  >
                    {u.role === "admin" ? "降为用户" : "升为管理员"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {setRoleMut.isError && (
          <p style={{ color: "var(--dsw-danger, red)" }}>{(setRoleMut.error as Error).message}</p>
        )}
      </section>

      <section style={{ margin: "16px 0" }}>
        <h3>审计日志</h3>
        <ul style={{ listStyle: "none", padding: 0 }}>
          {auditQ.data?.events.map((e) => (
            <li key={e.id} style={{ ...cell, display: "flex", gap: 10, fontFamily: "monospace", fontSize: 13 }}>
              <span style={{ color: "var(--dsw-text-tertiary, #888)" }}>
                {new Date(e.created_at).toLocaleString()}
              </span>
              <span>{e.username ?? "-"}</span>
              <span style={{ color: "var(--dsw-text-strong, #000)" }}>{e.action}</span>
              <span style={{ color: "var(--dsw-text-tertiary, #888)" }}>
                {e.target_type ?? ""} {e.target_id ? String(e.target_id).slice(0, 8) : ""}
              </span>
            </li>
          ))}
        </ul>
        {auditQ.data?.events.length === 0 && <p>暂无审计记录。</p>}
      </section>
    </div>
  );
}