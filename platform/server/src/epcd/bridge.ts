import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// EPCD 工具名单（与 backend/src/epcd_agent/cli.py 的 default_registry 一一对应）
// ---------------------------------------------------------------------------
export const EPCD_TOOLS = [
  "epcd_health",
  "epcd_template",
  "epcd_project",
  "epcd_device",
  "epcd_config",
  "epcd_formula",
  "epcd_run",
  "epcd_job",
  "optimization_start",
  "optimization_status",
  "optimization_cancel",
  "artifact_view",
] as const;

export type EpcdTool = (typeof EPCD_TOOLS)[number];

export function isEpcdTool(v: string): v is EpcdTool {
  return (EPCD_TOOLS as readonly string[]).includes(v);
}

// 工具名 -> REST 子路径（挂在 /api/epcd 之下）
export const TOOL_ROUTES: Record<EpcdTool, string> = {
  epcd_health: "/health",
  epcd_template: "/template",
  epcd_project: "/project",
  epcd_device: "/device",
  epcd_config: "/config",
  epcd_formula: "/formula",
  epcd_run: "/run",
  epcd_job: "/job",
  optimization_start: "/optimization/start",
  optimization_status: "/optimization/status",
  optimization_cancel: "/optimization/cancel",
  artifact_view: "/artifact/view",
};

// ---------------------------------------------------------------------------
// 配置解析：backend 目录、本地 python、会话 db、默认服务器
// ---------------------------------------------------------------------------
export interface EpcdConfig {
  backendDir: string;
  python: string;
  dbPath: string;
  defaultServer: string;
  artifactsDir: string;
  // 可选的 LLM 辅助建议（OpenAI-compatible，缺省走规则建议）
  llmBaseUrl?: string;
  llmKey?: string;
  llmModel?: string;
}

export function loadConfig(): EpcdConfig {
  const here = path.dirname(fileURLToPath(import.meta.url)); // .../platform/server/src/epcd
  const repoRoot = path.resolve(here, "..", "..", "..", ".."); // EPCD/
  const backendDir =
    process.env.EPCD_BACKEND_DIR ?? path.join(repoRoot, "backend");
  const python =
    process.env.EPCD_PYTHON ??
    path.join(
      backendDir,
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python"
    );
  const dbPath =
    process.env.EPCD_DB ??
    path.join(repoRoot, "platform", "server", "data", "epcd-platform.sqlite3");
  const defaultServer = process.env.EPCD_SERVER ?? "epcd-primary";
  const artifactsDir =
    process.env.EPCD_ARTIFACTS ??
    path.join(repoRoot, "platform", "server", "data", "artifacts");
  return {
    backendDir,
    python,
    dbPath,
    defaultServer,
    artifactsDir,
    llmBaseUrl: process.env.EPCD_LLM_BASE_URL,
    llmKey: process.env.EPCD_LLM_API_KEY,
    llmModel: process.env.EPCD_LLM_MODEL ?? "deepseek-chat",
  };
}

// 全局共享服务器池：读 backend/servers.json（admin 维护，运行时不变更）
export interface ServerEntry {
  name: string;
  ssh?: string;
  pkg?: string;
}

export function loadServers(config: EpcdConfig): ServerEntry[] {
  const file = path.join(config.backendDir, "servers.json");
  try {
    const json = JSON.parse(readFileSync(file, "utf8")) as {
      servers?: Record<string, { ssh?: string; pkg?: string }>;
    };
    return Object.entries(json.servers ?? {}).map(([name, v]) => ({
      name,
      ssh: v.ssh,
      pkg: v.pkg,
    }));
  } catch {
    return [{ name: config.defaultServer }];
  }
}

// ---------------------------------------------------------------------------
// spawn `python -m epcd_agent.cli`：stdin 一个 JSON 对象，stdout 一行 JSON
// ---------------------------------------------------------------------------
export interface EpcdInvokeParams {
  tool: EpcdTool;
  input?: unknown;
  server?: string;
  session?: string;
  ssh?: string;
  pkg?: string;
}

export interface EpcdResult {
  exitCode: number;
  ok: boolean;
  data: unknown;
  error: { type?: string; code?: string; message?: string } | null;
  raw: string;
  stderr: string;
}

export function runEpcdTool(
  params: EpcdInvokeParams,
  config: EpcdConfig
): Promise<EpcdResult> {
  const args = ["-m", "epcd_agent.cli"];
  if (params.server ?? config.defaultServer) {
    args.push("--server", params.server ?? config.defaultServer);
  }
  if (params.ssh) args.push("--ssh", params.ssh);
  if (params.pkg) args.push("--pkg", params.pkg);
  args.push("--db", config.dbPath);
  args.push("--session", params.session ?? "default");
  args.push(params.tool);

  return new Promise((resolve, reject) => {
    const child = spawn(config.python, args, {
      cwd: config.backendDir,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (err) => reject(err));

    child.on("close", (code) => {
      const exitCode = code ?? 1;
      const raw = stdout.trim();
      let parsed: Record<string, unknown> | null = null;
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = null;
      }
      resolve({
        exitCode,
        ok: parsed?.ok === true,
        data: parsed?.data ?? null,
        error: (parsed?.error as EpcdResult["error"]) ?? null,
        raw,
        stderr: stderr.trim(),
      });
    });

    child.stdin.write(JSON.stringify(params.input ?? {}));
    child.stdin.end();
  });
}