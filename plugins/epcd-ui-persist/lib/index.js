// EPCD UI persistent plugin — NODE half (host).
//
// Registered model tools + client-rendered toolviews / views:
//   epcd_status     — echo the TPE optimization summary (progress bar toolview)
//   epcd_artifacts  — read local artifact files into a gallery (toolview + view tab)
//   epcd_config     — read/write the PROJECT-level EPCD config (model-facing data)
//
// Host HTTP routes (consumed by the client view tabs):
//   GET  /api/epcd-gallery?session=<id>  — last delivered artifacts for a session
//   GET  /api/epcd-config?session=<id>   — effective config = project over default
//   POST /api/epcd-config                 — save project config (+ path history cache)
//
// Config model:
//   defaults : profiles/epcd/data/epcd-config-defaults.json  (the baseline values)
//   project  : <cwd>/epcd-config.json                        (per-project override)
//   cache    : profiles/epcd/data/epcd-config-cache.json      (per-field path history)
//   effective = defaults overlaid by project, field-by-field.

import { defineTool } from "@deepseek-ai/dsh-tools";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join, dirname, basename, resolve } from "node:path";
import { homedir } from "node:os";
import { spawn } from "node:child_process";

export const name = "epcd-ui-host";
export const inject = ["tools", "webServer", "agents"];

const dshHome = process.env.DSH_HOME || join(homedir(), ".dsh");
const dataDir = join(dshHome, "profiles", "epcd", "data");
const galleryDir = join(dataDir, "gallery");
const cachePath = join(dataDir, "epcd-config-cache.json");

const CONFIG_FIELDS = ["host", "port", "user", "identityFile", "pkg", "technology", "workDirRoot"];
const CONFIG_LABELS = {
  host: "主机地址",
  port: "SSH 端口",
  user: "用户名",
  identityFile: "密钥文件",
  pkg: "EPCD 包根",
  technology: "工艺文件",
  workDirRoot: "工作目录根"
};

function jsonBlock(value) {
  return [{ type: "text", text: JSON.stringify(value) }];
}

// ── epcd_cli：进程直调 python -m epcd_agent.cli（不经过 pwsh/bash）──────────
// 与 platform/server/src/epcd/bridge.ts 的 runEpcdTool 同构：Node spawn 直调
// 后端 python，stdin 一个 JSON 对象、stdout 一行 JSON、退出码 0/1/2。

// 12 个后端工具（与 backend/src/epcd_agent/cli.py 的 default_registry 一一对应）。
const EPCD_TOOLS = [
  "epcd_health", "epcd_template", "epcd_project", "epcd_device",
  "epcd_config", "epcd_formula", "epcd_run", "epcd_job",
  "optimization_start", "optimization_status", "optimization_cancel",
  "artifact_view",
];

// 定位 backend 目录：优先环境变量，否则假定会话 cwd 是仓库根（backend/ 子目录）。
function resolveBackendDir() {
  if (process.env.EPCD_BACKEND_DIR) return resolve(process.env.EPCD_BACKEND_DIR);
  return resolve(process.cwd(), "backend");
}

// 定位 python：优先环境变量，否则 backend/.venv 下按平台选 python.exe / python。
function resolvePython(backendDir) {
  if (process.env.EPCD_PYTHON) return resolve(process.env.EPCD_PYTHON);
  const exe = process.platform === "win32" ? "Scripts/python.exe" : "bin/python";
  return join(backendDir, ".venv", exe);
}

// 后台任务用的超时（秒）；optimization_start 会阻塞整轮 TPE，需更长。
const EPCD_CLI_TIMEOUT_MS = Number(process.env.EPCD_CLI_TIMEOUT_MS) || 600000;

function runEpcdCli({ tool, input, cwd, session }) {
  const backendDir = resolveBackendDir();
  const python = resolvePython(backendDir);
  const args = ["-m", "epcd_agent.cli"];
  // 一刀切：后端只认 --config-file（项目内 epcd-configs.json 的绝对路径）。
  const configFile = process.env.EPCD_CONFIG_FILE
    || (cwd ? join(cwd, "epcd-configs.json") : null);
  if (configFile) args.push("--config-file", configFile);
  if (session) args.push("--session", session);
  args.push(tool);

  return new Promise((resolve_) => {
    let child;
    try {
      child = spawn(python, args, {
        cwd: backendDir,
        windowsHide: true,
      });
    } catch (err) {
      resolve_({ ok: false, error: { type: "SPAWN", message: String(err) } });
      return;
    }
    let stdout = "";
    let stderr = "";
    let settle = false;
    const timer = setTimeout(() => {
      if (settle) return;
      settle = true;
      try { child.kill(); } catch { /* ignore */ }
      resolve_({ ok: false, timedOut: true, error: { type: "TIMEOUT", message: `epcd_cli timeout after ${EPCD_CLI_TIMEOUT_MS}ms` } });
    }, EPCD_CLI_TIMEOUT_MS);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (d) => { stdout += d; });
    child.stderr.on("data", (d) => { stderr += d; });
    child.on("error", (err) => {
      if (settle) return;
      settle = true;
      clearTimeout(timer);
      resolve_({ ok: false, error: { type: "SPAWN_ERROR", message: String(err) } });
    });
    child.on("close", (code) => {
      if (settle) return;
      settle = true;
      clearTimeout(timer);
      const raw = stdout.trim();
      let parsed = null;
      try { parsed = JSON.parse(raw); } catch { parsed = null; }
      resolve_({
        ok: parsed?.ok === true,
        exitCode: code ?? 1,
        data: parsed?.data ?? null,
        error: parsed?.error ?? null,
        stdout: raw,
        stderr: stderr.trim(),
        parseError: parsed === null && raw !== "" ? "non-JSON stdout" : null,
      });
    });

    child.stdin.write(JSON.stringify(input ?? {}));
    child.stdin.end();
  });
}

function readJson(path, fallback) {
  try {
    if (existsSync(path)) return JSON.parse(readFileSync(path, "utf8"));
  } catch (e) {
    /* fall through */
  }
  return fallback;
}

function writeJson(path, data) {
  try {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify(data, null, 2), "utf8");
    return true;
  } catch (e) {
    return false;
  }
}

function safeSessionId(id) {
  return String(id || "").replace(/[^A-Za-z0-9._-]/g, "").slice(0, 128);
}

function sessionIdOf(exec) {
  try {
    const a = exec && exec.agent;
    if (!a) return null;
    if (typeof a.id === "string" && a.id) return a.id;
    return null;
  } catch (e) {
    return null;
  }
}

function cwdOfAgent(agent) {
  try {
    const cwd = agent && agent.session && agent.session.header ? agent.session.header.cwd : null;
    return typeof cwd === "string" && cwd ? cwd : null;
  } catch (e) {
    return null;
  }
}

// ── config model（epcd-configs.json：平铺 multi-config）────────────────────
// 结构：{ "active": "<name>", "configs": { "<name>": {host,port,user,
//        identityFile,pkg,technology,workDirRoot}, ... } }

function readCache() {
  const c = readJson(cachePath, null);
  const out = {};
  for (const f of CONFIG_FIELDS) {
    out[f] = c && Array.isArray(c[f]) ? c[f].filter((v) => typeof v === "string" && v) : [];
  }
  return out;
}

function updateCache(config) {
  const cache = readCache();
  let changed = false;
  for (const f of CONFIG_FIELDS) {
    const v = config && typeof config[f] === "string" && config[f].trim() ? config[f].trim() : "";
    if (!v) continue;
    const arr = cache[f] || [];
    const idx = arr.indexOf(v);
    if (idx >= 0) arr.splice(idx, 1);
    arr.unshift(v);
    cache[f] = arr.slice(0, 20);
    changed = true;
  }
  if (changed) writeJson(cachePath, cache);
  return cache;
}

function configsPath(cwd) {
  return join(cwd, "epcd-configs.json");
}

function readConfigs(cwd) {
  if (!cwd) return { active: null, configs: {} };
  const d = readJson(configsPath(cwd), null);
  if (!d || typeof d !== "object") return { active: null, configs: {} };
  return {
    active: typeof d.active === "string" ? d.active : null,
    configs: d.configs && typeof d.configs === "object" ? d.configs : {},
  };
}

function writeConfigs(cwd, active, configs) {
  if (!cwd) return { ok: false, error: "无法定位当前项目目录（会话缺 cwd）" };
  if (!writeJson(configsPath(cwd), { active, configs })) {
    return { ok: false, error: "写入 " + configsPath(cwd) + " 失败" };
  }
  return { ok: true };
}

function getActiveConfig(cwd) {
  const { active, configs } = readConfigs(cwd);
  const cfg = active && configs[active];
  return cfg && typeof cfg === "object" ? cfg : {};
}

function listConfigs(cwd) {
  return Object.keys(readConfigs(cwd).configs);
}

function saveConfig(cwd, name, fields) {
  if (!cwd) return { ok: false, error: "无法定位当前项目目录（会话缺 cwd）" };
  if (!name || typeof name !== "string" || !name.trim()) {
    return { ok: false, error: "配置名不能为空" };
  }
  name = name.trim();
  const { active, configs } = readConfigs(cwd);
  const cur = configs[name] && typeof configs[name] === "object" ? configs[name] : {};
  const next = {};
  for (const f of CONFIG_FIELDS) {
    const raw = fields && fields[f];
    // string 字段去首尾空白；number 字段（port）按原样保留（后端 port 支持 str | int）。
    const v = typeof raw === "string" ? raw.trim() : (typeof raw === "number" && Number.isFinite(raw) ? raw : "");
    if (v !== "" && v !== undefined && v !== null) next[f] = v;
    else if (cur[f] !== undefined && cur[f] !== null) next[f] = cur[f];
  }
  configs[name] = next;
  const out = writeConfigs(cwd, active || name, configs);
  if (out.ok) updateCache(next);
  return out;
}

function deleteConfig(cwd, name) {
  if (!cwd) return { ok: false, error: "无法定位当前项目目录（会话缺 cwd）" };
  const { active, configs } = readConfigs(cwd);
  if (!(name in configs)) return { ok: false, error: "配置不存在：" + name };
  if (active === name) return { ok: false, error: "不能删除当前激活的配置" };
  delete configs[name];
  return writeConfigs(cwd, active, configs);
}

function activateConfig(cwd, name) {
  if (!cwd) return { ok: false, error: "无法定位当前项目目录（会话缺 cwd）" };
  const { configs } = readConfigs(cwd);
  if (!(name in configs)) return { ok: false, error: "配置不存在：" + name };
  return writeConfigs(cwd, name, configs);
}

function getEffective(cwd) {
  const { active, configs } = readConfigs(cwd);
  const cache = readCache();
  return {
    cwd: cwd || null,
    active,
    configs,
    list: Object.keys(configs),
    activeConfig: active && configs[active] ? configs[active] : {},
    cache,
    labels: CONFIG_LABELS,
    fields: CONFIG_FIELDS,
  };
}

// ── artifacts ──────────────────────────────────────────────────────────────

function materialize(f) {
  const path = f && typeof f.path === "string" ? f.path : "";
  const kind = f && typeof f.kind === "string" ? f.kind : "text";
  const label = (f && f.label) || basename(path || kind) || kind;
  const entry = { path, kind, label };
  if (!path) {
    entry.error = "missing path";
    return entry;
  }
  try {
    if (kind === "image") {
      const buf = readFileSync(path);
      entry.image = "data:image/png;base64," + buf.toString("base64");
    } else if (kind === "gds") {
      entry.kind = "gds";
    } else {
      const text = readFileSync(path, "utf8");
      entry.text = text.length > 20000 ? text.slice(0, 20000) + "\n...(截断)" : text;
    }
  } catch (e) {
    entry.error = String((e && e.message) || e);
  }
  return entry;
}

function galleryPath(sessionId) {
  return join(galleryDir, safeSessionId(sessionId) + ".json");
}

function persistGallery(sessionId, files) {
  const id = safeSessionId(sessionId);
  if (!id) return;
  try {
    mkdirSync(galleryDir, { recursive: true });
    writeFileSync(
      galleryPath(id),
      JSON.stringify({ sessionId: id, files, ts: Date.now() }),
      "utf8"
    );
  } catch (e) {
    /* non-fatal */
  }
}

function loadGallery(sessionId) {
  const id = safeSessionId(sessionId);
  if (!id) return null;
  try {
    if (!existsSync(galleryPath(id))) return null;
    return JSON.parse(readFileSync(galleryPath(id), "utf8"));
  } catch (e) {
    return null;
  }
}

// ── apply ──────────────────────────────────────────────────────────────────

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: "epcd_status",
    description: "把 TPE 优化进度渲染成进度条。传你刚从优化状态里读到的汇总字段。",
    parameters: {
      task_id: { type: "string", description: "优化任务 id，如 opt-17" },
      status: { type: "string", description: "running | finished | paused | canceled" },
      total_rounds: { type: "number", required: true, description: "预算 max_rounds" },
      done_rounds: { type: "number", required: true, description: "已完成轮数" },
      best_cost: { type: "number", description: "当前最优 cost（越小越好）" },
      rounds: {
        type: "array",
        description: "每轮 cost 序列（可选）",
        items: {
          type: "object",
          additionalProperties: true,
          properties: {
            round_no: { type: "number" },
            cost: { type: "number" },
            status: { type: "string" }
          }
        }
      }
    },
    execute: async (args) => ({
      progress: {
        task_id: args.task_id ?? null,
        status: args.status ?? "running",
        total_rounds: args.total_rounds,
        done_rounds: args.done_rounds,
        best_cost: typeof args.best_cost === "number" ? args.best_cost : null,
        rounds: Array.isArray(args.rounds) ? args.rounds : []
      }
    }),
    output: {
      schema: { type: "object", additionalProperties: true },
      render: (_args, value) => jsonBlock(value)
    }
  }));

  ctx.tools.register(defineTool({
    name: "epcd_artifacts",
    description: "把已交付的器件产物（版图预览 PNG、S 参数 S2P、GDS、目标值 JSON/文本）渲染成图库；多张版图预览（top/iso/side）会合并成三视图切换。传本机绝对路径 + kind。",
    parameters: {
      files: {
        type: "array",
        required: true,
        description: "产物文件数组",
        items: {
          type: "object",
          additionalProperties: true,
          properties: {
            path: { type: "string", description: "本机绝对路径" },
            kind: { type: "string", description: "image | text | s2p | json | gds", enum: ["image", "text", "s2p", "json", "gds"] },
            label: { type: "string", description: "展示标签" }
          }
        }
      }
    },
    execute: async (args, exec) => {
      const files = Array.isArray(args.files) ? args.files : [];
      const out = files.map(materialize);
      const sid = sessionIdOf(exec);
      if (sid) {
        persistGallery(
          sid,
          files
            .filter((f) => f && typeof f.path === "string" && f.path.length > 0)
            .map((f) => ({ path: f.path, kind: f.kind || "text", label: f.label || "" }))
        );
      }
      return { artifacts: out };
    },
    output: {
      schema: { type: "object", additionalProperties: true },
      render: (_args, value) => jsonBlock(value)
    }
  }));

  ctx.tools.register(defineTool({
    name: "epcd_config",
    description: "读/写 EPCD 项目配置（epcd-configs.json：平铺 multi-config）。action=get 返回当前 active config + 配置列表；action=list 返回所有配置名；action=save 新建/修改某配置；action=delete 删除某配置；action=activate 切换 active。",
    parameters: {
      action: { type: "string", required: true, enum: ["get", "list", "save", "delete", "activate"], description: "get/list/save/delete/activate" },
      name: { type: "string", description: "配置名（save/delete/activate 必填）" },
      config: {
        type: "object",
        additionalProperties: true,
        description: "action=save 时写入的字段（host/port/user/identityFile/pkg/technology/workDirRoot）",
        properties: {
          host: { type: "string" },
          port: { oneOf: [{ type: "string" }, { type: "number" }] },
          user: { type: "string" },
          identityFile: { type: "string" },
          pkg: { type: "string" },
          technology: { type: "string" },
          workDirRoot: { type: "string" }
        }
      }
    },
    execute: async (args, exec) => {
      const cwd = cwdOfAgent(exec && exec.agent);
      switch (args.action) {
        case "list":
          return { cwd, list: listConfigs(cwd) };
        case "save": {
          const r = saveConfig(cwd, args.name, args.config || {});
          return { ...r, ...getEffective(cwd) };
        }
        case "delete": {
          const r = deleteConfig(cwd, args.name);
          return { ...r, ...getEffective(cwd) };
        }
        case "activate": {
          const r = activateConfig(cwd, args.name);
          return { ...r, ...getEffective(cwd) };
        }
        default:
          return { ...getEffective(cwd), present: Boolean(cwd) };
      }
    },
    output: {
      schema: { type: "object", additionalProperties: true },
      render: (_args, value) => jsonBlock(value)
    }
  }));

  // epcd_cli：进程直调 python -m epcd_agent.cli，绕过 pwsh/bash（跨平台）。
  ctx.tools.register(defineTool({
    name: "epcd_cli",
    description: "直接调用 EPCD 确定性后端（python -m epcd_agent.cli），不经过 shell。参数 tool 是后端工具名：epcd_health / epcd_template / epcd_project / epcd_device / epcd_config / epcd_formula / epcd_run / epcd_job / optimization_start / optimization_status / optimization_cancel / artifact_view。input 是传给该工具的 JSON 对象（stdin 一个对象）。optimization_start 会阻塞整轮 TPE，超时约 10 分钟。",
    parameters: {
      tool: {
        type: "string",
        required: true,
        enum: EPCD_TOOLS,
        description: "后端工具名（12 选 1）"
      },
      input: {
        type: "object",
        additionalProperties: true,
        description: "传给后端工具的参数字典（stdin JSON）"
      },
      session: {
        type: "string",
        description: "会话名（可选，省略用 default）"
      }
    },
    execute: async (args, exec) => runEpcdCli({
      tool: args.tool,
      input: args.input ?? {},
      cwd: cwdOfAgent(exec && exec.agent),
      session: args.session ?? null,
    }),
    output: {
      schema: { type: "object", additionalProperties: true },
      render: (_args, value) => jsonBlock(value)
    }
  }));

  // Gallery route for the "产物图库" view tab.
  ctx.webServer.register({
    kind: "exact",
    path: "/api/epcd-gallery",
    handler: (req, res) => {
      try {
        const url = new URL(req.url || "/", "http://localhost");
        const sessionId = safeSessionId(url.searchParams.get("session") || "");
        const ledger = loadGallery(sessionId);
        res.statusCode = 200;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.setHeader("Cache-Control", "no-store");
        res.end(JSON.stringify(
          ledger
            ? { sessionId: ledger.sessionId, ts: ledger.ts, artifacts: (Array.isArray(ledger.files) ? ledger.files : []).map(materialize) }
            : { sessionId, ts: null, artifacts: [] }
        ));
      } catch (e) {
        res.statusCode = 500;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: String((e && e.message) || e) }));
      }
    }
  });

  // Config route for the "EPCD 配置" view tab.
  ctx.webServer.register({
    kind: "exact",
    path: "/api/epcd-config",
    handler: (req, res) => {
      const send = (code, body) => {
        res.statusCode = code;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.setHeader("Cache-Control", "no-store");
        res.end(JSON.stringify(body));
      };
      try {
        const url = new URL(req.url || "/", "http://localhost");
        const sessionId = safeSessionId(url.searchParams.get("session") || "");
        const agent = ctx.agents ? ctx.agents.get(sessionId) : undefined;
        const cwd = cwdOfAgent(agent) || url.searchParams.get("cwd") || null;
        if (req.method === "POST") {
          let body = "";
          req.on("data", (chunk) => { body += chunk; });
          req.on("end", () => {
            try {
              const parsed = body ? JSON.parse(body) : {};
              const s = parsed.session ? safeSessionId(parsed.session) : sessionId;
              const a2 = ctx.agents ? ctx.agents.get(s) : undefined;
              const c2 = cwdOfAgent(a2) || parsed.cwd || cwd;
              let r;
              switch (parsed.action) {
                case "save":
                  r = saveConfig(c2, parsed.name, parsed.config || {});
                  break;
                case "delete":
                  r = deleteConfig(c2, parsed.name);
                  break;
                case "activate":
                  r = activateConfig(c2, parsed.name);
                  break;
                default:
                  r = { ok: false, error: "unknown action (save|delete|activate)" };
              }
              send(r.ok ? 200 : 400, { ...r, ...getEffective(c2) });
            } catch (e) {
              send(500, { ok: false, error: String((e && e.message) || e) });
            }
          });
          return;
        }
        // GET：支持 ?action=list 只回配置名列表；否则返回完整 effective。
        if (url.searchParams.get("action") === "list") {
          send(200, { ok: true, cwd, list: listConfigs(cwd) });
        } else {
          send(200, getEffective(cwd));
        }
      } catch (e) {
        send(500, { ok: false, error: String((e && e.message) || e) });
      }
    }
  });
}