# EPCD 配置重构：平铺 multi-config（最终落地清单）

> 状态：**定稿待执行**。四项决策已确认：① 文件名 `epcd-configs.json`、放项目内；② 项目级
> （`active` 属项目，[EPCD 配置] tab 也是项目级）；③ 一刀切（不保留 `--server`/`--ssh`/`--pkg`
> 兼容别名）；④ 扩展 `/api/epcd-config`。

## 0. 目标形态

```json
// <项目根>/epcd-configs.json
{
  "active": "zhubo-prod",
  "configs": {
    "zhubo-prod": {
      "host": "192.168.20.243",
      "port": 22,
      "user": "zhubo",
      "identityFile": "~/.ssh/id_rsa_epcdB",
      "pkg": "/package/eda9cube-...-default",
      "technology": "/home/zhubo/demo_revised.ptxt",
      "workDirRoot": "/home/zhubo/epcd-runs"
    },
    "zhubo-test": { "...": "..." }
  }
}
```

- 平铺，无 servers/profiles 层级；一份 config = 一组完整属性（连接 + pkg + 工艺 + 工作目录）。
- `active` 一键切换；`configs` 增删改；字段可自由扩展（未来加 timeout/solver/license 等）。

## 1. 关键约束（已核实，决定实现方式）

- 后端 `python -m epcd_agent.cli` 的 **cwd = `backend/`**（`bridge.ts`/`epcd-ui-persist` 均以
  `backendDir` 为 cwd，非项目根）。
- 因此后端**不能用相对 cwd 找到项目内的 `epcd-configs.json`**。必须由上游（DSH 宿主）把
  「config 文件绝对路径」或「解析后的整套字段」显式传给后端。

落地采用：**DSH 宿主层（面板/`epcd_cli` 工具）读项目内 `epcd-configs.json`，按 active 解析出
整套字段，显式传给后端**。后端新增 `--config-file <abs>`（或 `--config-json <json>`）接收，
自身**不再**维护 `servers.json` 解析。

## 2. 后端改动（backend/src/epcd_agent/cli.py）

1. 删除 `--server` / `--servers-file` / `--ssh` / `--pkg` / `--host` / `--user` / `--port` /
   `--identity-file` 这一整套（一刀切）；**新增** `--config-file <abs路径>`（读 `epcd-configs.json`）
   或 `--config <name>` + `--configs-file <abs路径>`。
2. `_apply_server` 改为 `_apply_config`：从 `epcd-configs.json` 读 `active` + `configs[active]`，
   平铺解析 `host/port/user/identityFile/pkg/technology/workDirRoot`。
3. `build_argv_prefix` 保持「`-F` temp 空 config + `-o/-i` 显式连接」不变（上轮已解耦）。
4. `_build_ctx` / `ToolContext`：ssh_connect 不变；新增把 `technology`/`workDirRoot` 暴露出来
   （或仍由上游传 `epcd_project init`，见 §3）。

## 3. DSH 宿主层改动（bridge.ts + epcd-ui-persist）

- `bridge.ts`：删 `loadServers`（读 servers.json）、`ServerEntry`；`runEpcdTool` 增加读项目内
  `epcd-configs.json`、按 active 解析、把 `--config-file`（或解析后字段）传给 python。
- `epcd-ui-persist/lib/index.js`：`CONFIG_FIELDS` 从 `["ssh","pkg","technology","workDirRoot"]`
  改为 configs 模型的字段集；`/api/epcd-config` 扩展为
  `action = get | list | save | delete | activate`（get=当前 active 整套字段，list=configs key 列表，
  save=写/新建某 config，delete=删某 config，activate=切 active）。
- 删除旧 `servers.json` 的读取路径与 `epcd-config-defaults.json` 的迁移逻辑（一刀切；保留一段
  「首次迁移旧文件 → 新 configs」的一次性代码即可，或直接手写新文件）。

## 4. skill / 前端面板改动

- `SKILL.md`：`server` 参数语义改为 `config`/`active`；「切环境」说明改为「切 active」；
  移除 servers.json/epcd-config.json 双文件描述，统一为 `epcd-configs.json`。
- 面板 `[EPCD 配置]` tab：顶部「配置」下拉（configs key）+ 新建/修改/删除/切换；字段平铺
  （host/port/user/identityFile/pkg/technology/workDirRoot）；切换即写 active（项目级）。

## 5. 迁移（一次性，一刀切）

- 把现 `backend/servers.json` 的 `epcd-primary.ssh{host,user,port,identityFile}` + `pkg`，
  与 `epcd-config.json` 的 `technology`/`workDirRoot`，合并为项目内 `epcd-configs.json` 的
  `configs["zhubo-prod"]`，`active="zhubo-prod"`。
- 删除 `backend/servers.json`、`epcd-config.json`（或归档）。

## 6. 验收清单

- [ ] `python -m epcd_agent.cli --config-file <abs> epcd_health` 返回 ok（ssh 走 temp 空 config + `-o/-i`）。
- [ ] 面板 `[EPCD 配置]` 能列出 configs、增删改、切换 active 且后端即时生效。
- [ ] `epcd_project init` 用的 technology/workDirRoot 来自 active config。
- [ ] 两个 config 切换后，`host/user/pkg/technology/workDirRoot` 整套联动。
- [ ] 旧文件已删/归档，无 `--server`/`--ssh`/`--pkg` 残留引用。

## 7. 已定决策（A、B）

- **A（已定）**：后端接收 `--config-file <绝对路径>`，后端**自己读** `epcd-configs.json` 并解析。
- **B（已定）**：`technology`/`workDirRoot` 由后端从 active config **自动带出**。精确语义：
  - 自动带出的是配置里的**原始值** `technology` 与 `workDirRoot`（存进 `ToolContext`）；
  - `work_dir`（含「器件名」这一 skill 层语义的派生值）仍由 skill 用 `workDirRoot + 器件名` 拼好
    传给 `epcd_project init`——器件名生成职责**不下沉到后端**。
  - 因此 `epcd_project init` 在缺 `technology` 入参时回落 `ctx.technology`；`work_dir` 仍要求传入
    （skill 拼好），但 skill 不再需要手填 `technology`，只填 `work_dir`。

## 8. 最终落地清单（backend → bridge → 面板 → skill）

### 8.1 backend（`backend/src/epcd_agent/cli.py` + `tools/*`）

1. 删除 `--server/--servers-file/--ssh/--pkg/--host/--user/--port/--identity-file`（一刀切）。
2. 新增 `--config-file <abs>`；`_apply_config(args, config_file)` 读 `epcd-configs.json` →
   取 `active` → `configs[active]` 平铺字段 host/port/user/identityFile/pkg/technology/workDirRoot。
3. `build_argv_prefix` 不变（`-F` temp 空 config + `-o/-i`）；目标参数用「config 名」作占位标签。
4. `ToolContext` 增加 `technology`、`workDirRoot`（来自 active config），`_build_ctx` 注入。
5. `epcd_project init`：`technology=None` 时回落 `ctx.technology`；`work_dir` 仍必填（skill 拼好）。
6. `epcd_config`（MCP 宿主 ≠ 后端 config 工具）后续由 bridge 层读 configs，不落在后端。

### 8.2 bridge（`platform/server/src/epcd/bridge.ts`）

7. 删 `loadServers`/`ServerEntry`；`runEpcdTool` 增加「定位项目 cwd → 读 `<cwd>/epcd-configs.json`
   → 传 `--config-file <abs>`」。
8. `EpcdInvokeParams`：`server` → `configFile`（或由 server 名映射到 project 文件路径）。

### 8.3 面板（`plugins/epcd-ui-persist/lib/*`）

9. `/api/epcd-config` 扩展 `action = get|list|save|delete|activate`：
   get=当前 active 整套字段；list=configs key；save=写/新建某 config；delete=删；activate=切 active。
10. `[EPCD 配置]` tab：配置下拉 + 新建/修改/删除/切换；字段平铺 7 项。

### 8.4 skill（`.dsh/skills/epcd-agent-flow/*`）

11. `SKILL.md`：`server`/双文件 描述改为 `epcd-configs.json` + `active`；`epcd_project init` 只传
    `work_dir`（technology 自动带出）；「切环境」= 切 active。
12. 删除旧 `servers.json` / `epcd-config.json` 引用。

### 8.5 迁移（一次性）

13. 旧 `servers.json`+`epcd-config.json` 合并为项目内 `epcd-configs.json`（含 `configs` 一份 +
    `active`），删除旧两文件。

## 9. 验收清单

- [ ] `python -m epcd_agent.cli --config-file <abs> epcd_health` ok（ssh 走 temp 空 config）。
- [ ] `epcd_project init` 只传 `work_dir` 即可，technology 自动带出。
- [ ] 面板能 list/增删改/切换 config，切 active 后 host/user/pkg/technology/workDirRoot 全套联动。
- [ ] 旧 `--server/--ssh/--pkg` 无残留、无返回 usage error。
- [ ] 两个 config 切换后，后端 `epcd_health`/`epcd_project` 走各自 connection 均 ok。