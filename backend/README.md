# epcd-agent

EPCD 器件设计 Agent 平台的后端核心（计划 1 + 计划 2 交付物）：在 LLM 之外、可独立
测试的确定性执行层，加上供 Claude Code / Claude Agent SDK 调用的单一 CLI 入口。
设计依据见 `../../docs/superpowers/specs/2026-08-17-epcd-agent-platform-design.md`，
CLI 接口契约见 `../../agent-demo-command-flow_release.md`（epcd-response/v1，
其中 §4.9–4.15 已按真实环境实测校正）。

## 架构一句话

Agentic trunk + deterministic island：主 Agent（计划 2 用 Claude Code 驱动，计划 3
换 Claude Agent SDK）负责对话与决策；本包提供 LLM 不调度、只消费结果的"岛"——

- **工具层**（`tools/`）：对 epcd-cli 的子进程封装。所有 `--project` / `--instance-id`
  从 Session Store 注入（LLM 永不提供 id）；写操作成功后自动记账（硬规则 3）。
- **优化控制器**（`optimizer/`）：Optuna TPE 驱动的迭代评测循环，自带预算、
  同 requestId 重试/接回、崩溃恢复、连续失败暂停上报。
- **平台工具**（`platform/`）：`optimization_start/status/cancel`（跨进程可取消的
  优化任务）与 `artifact_view`（job 产物卡片 + 本地/远端拉取）。
- **单一 CLI 入口**（`cli.py`）：全部 12 个工具经 stdin-JSON / stdout 单行 JSON /
  退出码 0/1/2 暴露，与 epcd-cli 自身调用纪律同构，计划 3 的 SDK 可直接复用。

## 目录

```
src/epcd_agent/
  envelope.py        epcd-response/v1 信封解析（容忍 stdout 前置噪声行）
  exitcodes.py       退出码 → 分类（agent_retryable / needs_decision / blocking / transient ...）
  cli_client.py      EpcdCli 子进程客户端（UTF-8 JSON stdin，超时/执行失败兜底）
  cli.py             单一 CLI 入口：python -m epcd_agent.cli <tool>（12 工具注册表）
  store.py           SessionStore：SQLite，LLM 之外的唯一事实源
  tools/base.py      ToolResult / ToolContext / id 注入 / digest 前置条件
  tools/read.py      epcd_health / epcd_template / epcd_formula / epcd_job
  tools/write.py     epcd_project / epcd_device / epcd_run（含记账）
  tools/config.py    epcd_config：schema/get/patch/apply-result（digest 自动刷新重试一次）
  optimizer/space.py       config schema → ParamSpec/ParsedSpace（嵌套分组/字符串数值适配）
  optimizer/controller.py  OptimizationController + Budget/Report/PausedError + cost 回退
  platform/optimize_tools.py  optimization_start/status/cancel（Store 持久化，跨进程取消）
  platform/artifact_view.py   artifact_view（GDS/版图/SNP 卡片；ssh base64 拉取远端产物）
skills/
  device-design-flow/  编排 skill：4.1~4.15 + M1~M4 里程碑（与 .claude/skills 同步）
demo/
  headless_flow.py     无 LLM 的 P0 全流程（4.1~4.15 + M1~M4 里程碑），人工冒烟入口
  smoke_remote_ssh.py  远程 SSH 通道冒烟脚本
  probe_run_contract*.py  真实服务器 run/job/apply-result 契约探针（计划 2）
tests/               全部基于场景驱动的 mock epcd-cli（mock_cli.py），不依赖真实环境
```

## 单一 CLI 入口（计划 2）

```bash
./.venv/Scripts/python -m epcd_agent.cli [--server NAME | --ssh HOST --pkg PKG] \
    [--db PATH --session NAME] <tool>
```

- **工具参数**：stdin 一个 UTF-8 JSON 对象；**输出**：stdout 恰好一行
  `{"ok": bool, "data": ..., "error": {"type","message"} | null}`；
  **退出码**：0 成功 / 1 业务失败（结构化输出仍在 stdout）/ 2 用法错误。
- `--ssh` 与 `--pkg` 必须成对出现（远程模式）；都省略则本地直调 `epcd-cli`。
- `--server NAME` 从 `servers.json` 读 `{ssh, pkg}` 一键注入（`--ssh`/`--pkg` 显式值优先）；
  未命中或文件缺失 → 退出码 2（USAGE）。

| 子命令 | 说明 |
| --- | --- |
| `epcd_health` | 健康检查（无参数） |
| `epcd_template` | 模板 list/describe |
| `epcd_project` | 工程 init/describe/validate |
| `epcd_device` | 器件实例 add/describe |
| `epcd_config` | 配置 schema/get/patch/apply-result（digest 自动注入） |
| `epcd_formula` | 公式库查询 |
| `epcd_run` | 提交仿真/综合任务（候选参数经 stdin） |
| `epcd_job` | job get/result/cancel（仅 `--id`，服务端自持上下文） |
| `optimization_start` | 启动 TPE 迭代优化任务（parameter_schema + 预算） |
| `optimization_status` | 查询优化任务进度/报告 |
| `optimization_cancel` | 跨进程请求取消优化任务 |
| `artifact_view` | 取 job 产物卡片并按需拉取文件到 fetch_dir |

环境变量（均可被同名命令行参数覆盖）：

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `EPCD_AGENT_DB` | Session Store SQLite 路径 | `epcd-agent-session.sqlite3` |
| `EPCD_AGENT_SESSION` | 会话名 | `default` |
| `EPCD_SSH_HOST` | 远程主机（如 `zhubo@192.168.20.243`） | 无（本地模式） |
| `EPCD_PKG_ROOT` | 远端 EPCD 包根（如 `/package/eda9cube-...`） | 无 |
| `EPCD_SERVER` | 服务器别名（`servers.json` 里的 key，注入 ssh+pkg） | 无 |
| `EPCD_SERVERS_FILE` | 服务器配置文件路径 | `servers.json` |

## 测试

```bash
./.venv/Scripts/python -m pytest tests -q    # Windows
.venv/bin/python -m pytest tests -q          # POSIX
```

当前 120 个用例全绿，覆盖信封解析、退出码、客户端、Store、工具层、优化器、
平台工具（optimization_*/artifact_view）、CLI 入口与端到端流程。

## 远程执行（EPCD 服务器不在本机时）

`EpcdCli` 的命令前缀可配置，远程部署**零代码改动**。CLI 入口的远程模式：

```bash
python -m epcd_agent.cli --ssh zhubo@192.168.20.243 \
  --pkg /package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default \
  epcd_health
```

- stdin JSON（`--input -`）经 ssh 管道透传，已用远端替身脚本验证（`demo/smoke_remote_ssh.py`）。
- 必须使用免密公钥登录（`-o BatchMode=yes`）；本机到
  `zhubo@192.168.20.243` 的免密已就绪。
- 所有路径类参数（`--work-dir` 等）按**远端**路径理解。
- `artifact_view` 远端产物经 `ssh base64 -w0` 拉回本地 fetch_dir。

### 实测环境差异（2026-08-20，服务器 build 0.1.0）

远端命令需先 source 包内环境脚本（不在默认 PATH）：
`ssh <host> "source <pkg>/user.bashrc.ePCD >/dev/null 2>&1; epcd-cli ..."`。
与 release 文档契约的实测差异（均已在代码中兼容，并已校正回 release 文档，
原错误内容以 HTML 注释保留）：

1. `project init` 响应为 `data.path`（文档为 `data.project`），且无
   `created`/`technologyDigest`/`warnings` 字段 → 工具层按 `project` 优先、
   `path` 兜底记账。
2. CLI 会在 stdout 的 envelope 之前泄漏求解器 `Warning:` 行 →
   `parse_envelope` 自首个 `{` 恢复解析。
3. `device-template describe` 的 `builtInMetrics` 为对象数组
   （key/tagName/default/weight/formula），`parameterSchema` 为
   basic/opt/synth 分组嵌套结构；边界先后出现过两种格式——旧 build 把数值边界
   以字符串给出（`minimum`/`maximum`/`step`/`enabled`/`suffix`），当前 build 用
   数值 `minimum`/`maximum` + `multipleOf`（离散步进）+ `x-epcd-enabled`/
   `x-epcd-locked`/`x-epcd-suffix` 布尔/枚举。`optimizer/space.py` 的
   `parse_real_parameter_schema`/`parse_synth_targets` 两种都适配，且
   `x-epcd-locked` 参数不进优化空间（如 adv_simple_inductor 锁定 trackSpace）。
4. `project device add` 响应无 `created`/`name`/`folderName`/`templateId`，
   `instanceId` 为时间戳形式字符串，附带 `config`（epcd-device/v1 骨架）。
5. `config schema` 的 `schema` 是 epcd-device/v1 配置默认值骨架，不是
   带类型/边界的 JSON Schema；参数边界只能取自模板 `parameterSchema`。
   `config schema --path /sweeps` 触发 INTERNAL_ERROR（退出码 8），已规避。
6. `run` 响应无 `configDigestUsed`；`job get/result/cancel` 仅接受 `--id`
   （无 `--project`/`--instance-id`）。
7. `job result` 为完整 `epcd-job/v1` 快照：**无顶层 `objectiveCost`** →
   `controller.cost_from_result` 回退到 targetValues（逐项 objectiveCost →
   relativeDeviation → satisfied 0/1）；`status=="succeeded"` 可能携带
   `warnings:[{code:"SIMULATION_FAILED",...}]`，编排层必须检查
   warnings/targetValues（release §4.12）。
8. `config patch`：`synthesisTargets` 持久化（读回字符串化，frequency 变为
   `{"mode":"point","freq":...}`）；`simulation.sweeps` **不持久化**
   （changed:true 但 digest 不变、读回空）；**顶层 `sweeps`** 持久化，条目形状
   `{enabled,type,start,stop,step,points}`，start/stop/step 为带单位字符串。
9. 未决异常：`config patch` 写 `device.parameters` 与 `config apply-result`
   均返回 applied/changed:true 但 digest 不变、读回无值；候选参数生效路径以
   `run --input` 为准。
10. **EM 求解器许可证阻断**：包内许可证文件 DAEMON 行为占位符
    `PATH_NINECUBE`，emsolver 报 "Flexnet license file does not exist" →
    仿真 succeeded 但 warnings 携带 SIMULATION_FAILED、无 targetValues。
    修复路径：`/home/zhubo/ninecube-fixed.lic`（修正 DAEMON 路径 + 端口 27001）
    + 以 zhubo 启动 lmgrd + `NINECUBE_LICENSE_FILE=27001@localhost`
    （见 `demo/start_ninelic.sh`；§4.15 实测状态注记）。

## 计划 2 边界

已完成：单一 CLI 入口、platform 工具（optimization_*/artifact_view）、
device-design-flow 编排 skill、真实环境契约适配与 release 校正、
Claude Code 驱动的 M1–M4 端到端冒烟验收（见 `docs/plan2-real-run-report.md`）。

属计划 3：Claude Agent SDK 接入（替换 Claude Code，AskUserQuestion 拦截、
session 映射、milestone 记账）、WebSocket/SSE 与 Web 前端。
