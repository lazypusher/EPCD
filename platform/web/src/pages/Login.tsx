import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@deepseek-ai/dsh-client-ui-primitives";
import { api } from "../api/client";
import { setAuth } from "../auth";

export function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!username || !password) {
      setError("请输入用户名和密码");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r =
        mode === "login"
          ? await api.login(username, password)
          : await api.register(username, password);
      if (r.ok && r.token && r.user) {
        setAuth(r.token, r.user);
        navigate("/");
      } else {
        setError("认证失败");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 10px",
    fontSize: 14,
    marginBottom: 10,
    borderRadius: 6,
    border: "1px solid var(--dsw-border, #ccc)",
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--dsw-surface-1, #f5f5f5)",
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        style={{
          width: 320,
          padding: 28,
          borderRadius: 12,
          border: "1px solid var(--dsw-border, #ccc)",
          background: "var(--dsw-surface, #fff)",
        }}
      >
        <h2 style={{ marginTop: 0 }}>EPCD 器件设计平台</h2>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="用户名"
          style={inputStyle}
          autoFocus
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="密码"
          style={inputStyle}
        />
        <Button variant="primary" onClick={submit} disabled={busy}>
          {busy ? "处理中…" : mode === "login" ? "登录" : "注册"}
        </Button>

        <button
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          style={{ background: "none", border: "none", cursor: "pointer", marginTop: 12, fontSize: 13 }}
        >
          {mode === "login" ? "没有账号？注册" : "已有账号？登录"}
        </button>

        {error && <p style={{ color: "var(--dsw-danger, red)", fontSize: 13 }}>{error}</p>}
        <p style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)", marginBottom: 0 }}>
          默认管理员：admin / admin123
        </p>
      </form>
    </div>
  );
}