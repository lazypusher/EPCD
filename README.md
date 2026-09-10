# EPCD 器件设计 Agent 平台

电子元器件（片上电感）自动化设计平台。前端复用 DeepSeek Harness（DSH）的
视觉令牌与 primitives，后端通过 Node HTTP 桥 spawn `python -m epcd_agent.cli`
（确定性后端，保持不变）。

## 架构

```
EPCD/
├─ backend/            # epcd_agent 确定性后端（python，保持不变）
│  ├─ servers.json     # 全局服务器池（ssh 别名 + pkg 路径）
│  ├─ pyproject.toml   # PEP 621 项目元数据（setuptools 构建，uv 管理环境）
│  ├─ .python-version  # 固定 Python 3.13
│  ├─ uv.lock          # uv 锁文件（依赖版本可复现）
│  └─ .venv/           # uv 管理的 python 3.13 虚拟环境（uv sync 生成）
└─ platform/           # npm workspaces
   ├─ server/          # @epcd/server — Fastify 5 + TypeScript (NodeNext/ESM) + node:sqlite
   └─ web/             # @epcd/web — Vite + React 18 + dsh-client-ui-primitives
```

## 8 阶段状态机

`health → project → template(M1) → objectives(M2) → optimization → apply(M3) → final(M4) → deliver`

- M1 模板选定 / M2 目标配置 / M3 最优参数写回 / M4 最终仿真，每个里程碑需**确认**（批准/修改/终止）。
- `optimization_start` 阻塞整轮 TPE，平台将其 spawn 为后台进程，直接读同一 SQLite
  （`optimization_task`/`job`/`kv_state`）轮询进度，前端用 SSE 实时看板 + 取消。

## 后端 Python 环境（uv）

`backend/` 的 Python 环境用 [uv](https://docs.astral.sh/uv/) 管理，锁定在 Python 3.13：

```bash
cd backend
uv sync          # 按 uv.lock 创建/更新 .venv，安装 epcd-agent（optuna 等依赖）
```

- 首次运行需先装 uv：`curl -LsSf https://astral.sh/uv/install.sh | sh`（或 `pip install uv`）。
- 服务器系统 Python 可能是 3.9（低于 requires-python>=3.10），uv 会自动下载并管理 3.13。
- `epcd_agent.cli` 由 DSH 宿主（`epcd_cli` 工具）spawn `backend/.venv/{bin/python,Scripts/python.exe}` 执行，
  因此只要 `.venv` 由 `uv sync` 就绪即可，无需全局 Python。
- 依赖变更后：改 `pyproject.toml` → `uv lock`（更新锁）→ `uv sync`（应用到环境）。

## 启动

```bash
npm install                                              # 根目录，安装两个 workspace
npm run dev --workspace @epcd/server                     # 后端 :4100
npm run dev --workspace @epcd/web                        # 前端 :5173（/api 代理到 4100）
```

生产构建：`npm run build`，然后 `node dist/index.js`（`platform/server`，PORT/HOST 可选）。

环境变量：`EPCD_SERVER`（默认服务器）、`EPCD_DB`（SQLite 路径）、
`EPCD_BACKEND_DIR`/`EPCD_PYTHON`、`EPCD_ARTIFACTS`（产物缓存目录）、
`EPCD_LLM_BASE_URL`/`EPCD_LLM_API_KEY`/`EPCD_LLM_MODEL`（可选 LLM 不达标建议；缺省走规则建议）。

## 鉴权

轻量鉴权（Bearer token，bcryptjs）。首次启动自动创建默认管理员
`admin / admin123`（请尽快修改）。普通用户只能看自己的任务；管理员可进入
「管理后台」查看用户/角色/审计日志。

## 关键说明

- 平台表名用 `design_task`/`phase_log`/`design_milestone`/`app_user`/`auth_token`/`audit_log`，
  避免与 `epcd_agent` 在同库的 `session`/`instance`/`job`/`optimization_task`/`milestone`/`kv_state` 冲突。
- 后端 `epcd_agent` 目录**保持不变**（仅目录重命名），所有工具通过 stdin JSON → stdout 单行 JSON 调用。