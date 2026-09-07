---
name: epcd-agent-flow
description: EPCD 元器件设计 Agent 端到端全流程编排（含 M1~M4 里程碑确认）。用户用自然语言发起器件设计（如"帮我设计一个 2.4GHz 下 L≈10nH、Q>20 的电感"）时使用。核心流程走 epcd_agent 确定性后端（pwsh 调用），运维/传输/多服务器走 dsh-ssh 工具。
---

# EPCD Agent Flow

在 `epcd-cli` 之上编排一套完整的器件设计流程：健康检查 → 建工程 → 选模板 →
实例化 → 配置目标 → 迭代优化 → 写回最优 → 最终仿真 → 产物交付。本 skill 是
**流程编排配方**，不含器件领域知识（模板边界见 `references/`）。

## 架构定位：两大工具通道

| 通道 | 工具 | 用在哪 |
| --- | --- | --- |
| **确定性后端**（首选） | `epcd_agent.cli`（经本机 `pwsh` 调用；内含 epcd-cli SSH 子进程、信封解析、退出码分类、SQLite 记账、Optuna TPE 优化控制器） | 全部 P0 流程工具（health/template/project/device/config/formula/run/job）、优化闭环（optimization_start/status/cancel）、artifact_view |
| **SSH 基础设施** | `dsh-ssh` 工具（`ssh_list`/`ssh_exec`/`ssh_upload`/`ssh_download`/`ssh_tunnel`/`ssh_cluster`） | 多服务器发现与选择、远程运维调试（许可证/日志/清目录）、工艺文件上传、产物批量拉取、集群冒烟 |

**规则**：凡是"EPCD 领域语义"（信封解析、digest 记账、优化闭环）一律走
`epcd_agent.cli`，它有 120+ 单测保障、读取结构化字段、绝不手搓 `epcd-cli` 原文。
`dsh-ssh` 只做"连接、上/下载、运维 shell"，不承担 EPCD 契约解析。

## 服务器预置

EPCD 服务器经 `~/.ssh/config`（标准源）+ `dsh-ssh` 导入派生。当前环境：

| 项 | 值 |
| --- | --- |
| 主机别名 | `epcd-primary`（`~/.ssh/config` 与 `dsh-ssh` 均已配置：HostName 192.168.20.243 / User zhubo / IdentityFile ~/.ssh/id_ed25519） |
| EPCD 包根 | `/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default` |
| 工艺基线 | `demo_revised.ptxt`（终审版；原始 `demo.ptxt` 因衬底/金属损耗过高 L/Q 恒负，已弃用） |
| 许可证 | `NINECUBE_LICENSE_FILE=2048@192.168.20.109`（远端 `~/.epcd-env`，`epcd_agent.cli` 前缀自动 source） |
| 认证 | 免密 `id_ed25519`（实测 `ssh epcd-primary` 直连成功） |

主机/包根**项目可配置**：`epcd-agent/servers.json` 维护 `别名 → {ssh, pkg}`，用
`epcd_agent.cli --server <别名>` 一键注入（见下方调用范式）。一次性覆盖用 `--ssh`/`--pkg`
（`--ssh` 同样接受 `~/.ssh/config` 别名）或环境变量 `EPCD_SSH_HOST`/`EPCD_PKG_ROOT`
（**两者必须成对**）。
多服务器：在 `servers.json` 加条目 + `dsh-ssh` 加主机；用 `ssh_list` 按
`environment`/`tags` 过滤选择目标。

## epcd_agent.cli 调用范式（本机 pwsh）

工作目录 `epcd-agent/`，所有参数经 **stdin 一个 UTF-8 JSON 对象**，stdout 恰好一行
JSON，退出码 0 成功 / 1 业务失败（结构化错误仍在 stdout）/ 2 用法错误：

```powershell
$in = '{"action":"init","work_dir":"/home/zhubo/epcd-runs/<器件名>","technology":"/home/zhubo/demo_revised.ptxt"}'
$in | .\.venv\Scripts\python.exe -m epcd_agent.cli `
  --server epcd-primary `
  --db <本地db路径> --session <会话名> epcd_project
```

> `--server epcd-primary` 从 `epcd-agent/servers.json` 读 `{ssh, pkg}`（主机/包根单一来源，
> 已实测通）。等价显式写法：`--ssh epcd-primary --pkg /package/...`（`--ssh` 接受
> `~/.ssh/config` 别名）。服务器名/配置文件也可经环境变量 `EPCD_SERVER` /
> `EPCD_SERVERS_FILE` 注入；`--server` 未命中/文件缺失 → 退出码 2（USAGE）。

12 个工具：`epcd_health` / `epcd_template` / `epcd_project` / `epcd_device` /
`epcd_config` / `epcd_formula` / `epcd_run` / `epcd_job` / `optimization_start` /
`optimization_status` / `optimization_cancel` / `artifact_view`。

`--db` 用项目工作区内的持久化 SQLite（如 `epcd-agent-session.sqlite3`），会话名
`--session` 按设计任务隔离（单一事实源，审计 + 恢复）。

## 阶段流程

1. **健康检查（自主）**：`epcd_health`。`data.status=="degraded"` 时解释原因并停。
2. **建工程（自主）**：`epcd_project` init（`work_dir` 远端路径 + `technology` 工艺文件）；
   随后 describe + validate。
3. **选型（自主 + M1 确认）**：优先用本地对比表 `references/inductor-templates-comparison.md`
   （9 个电感/tcoil 模板的 opt 边界、synth 默认目标、指标族），仅未覆盖信息才回退
   `epcd_template` list/describe。向用户展示候选，**用 `ask_user_question` 做 M1**
   （选定模板 + 实例名；批准/换一个/终止）。批准后 `epcd_device` add。
4. **目标与仿真配置（M2 确认）**：`epcd_config` schema/get 取骨架与 digest；
   按模板 synth 组 suffix+default 构造 synthesisTargets。**评分目标由 objectives 直接
   生效**（metric 用模板族名：`Inductance Value(nH)`→L、`Min Q Factor`→Q、`Max Size(um)`→size，
   `targetValue` 写数值）。**不需 customMetrics 注入**；真要自定义公式才放
   `/synthesisTargets/customMetrics`（勿与内置同名，否则 `CUSTOM_METRIC_CONFLICT`）。
   扫频按目标推导：point 目标不配扫频；range 目标顶层 sweep 覆盖 range；模板 EM 必须
   sweep 时（stack 家族）用最小覆盖带宽。sweep patch 放 JSON **顶层** `{"sweeps":[...]}`。
   把指标/频点/比较/权重/扫频/预算（默认 max_rounds=3、startup_trials=3）合并成一张
   **`ask_user_question` M2 确认卡**。批准后 `epcd_config` patch（objectives 与 sweeps
   分开提交，每次用最新 digest，`--if-match` 由工具自动注入）。
5. **迭代优化（自主，预算内）**：`optimization_start` **用 pwsh `run_in_background` 后台
   启动**（它在单进程里阻塞跑完整 TPE 循环，几分钟量级；跨进程取消经 Store SQLite
   `kv_state`，与本进程无关）。stdin 传 `parameter_schema`（**用 live `config schema` 的
   `device.parameters.opt` 构造**，不用 describe 原样——describe 的 opt 为空会坠入 22 维
   addinParams 兜底空间，L/Q 恒定无优化信号）、`initial_candidates`（1~2 组起点）、预算。
   前台轮询 `optimization_status`（读 SQLite，跨进程安全）；喊停 `optimization_cancel`
   （写 cancel 标志，控制器每轮 cancel_probe 检查）；后台 job 结束用 `job_output` 收报告。
   `OPTIMIZATION_PAUSED` 时读 `data.errors`/`category` 诊断并询问用户；
   succeeded+warnings+空 targetValues 是失败轮，控制器按 FAIL 处理让 TPE 规避，不暂停。
6. **写回（M3 确认）**：报告 best cost / 各指标达成（`ask_user_question` M3），批准后
   `epcd_config` apply-result（jobId=best_job_id）。
7. **最终仿真（M4 确认）**：`ask_user_question` M4 批准后 `epcd_run` final：不带候选输入、
   `request_id="final-<best-job-id>"`。**验收口径**：读最终 job 的 `targetValues`，核对每条
   `targetValue == 配置 objectives 值`，`satisfied` 判达标，`parametersUsed` 应含写回几何。
8. **交付**：`artifact_view`（带 fetch_dir）取最终 job 产物卡片；或 `ssh_download` 批量拉取
   GDS/版图/SNP/目标值/图表；向用户汇报路径。

## 硬规则

- 里程碑 M1~M4 必须 `ask_user_question` 确认，三选项语义：批准 / 修改后批准 / 终止，
  每次确认的选项与理由在验收报告留痕。
- id/digest/jobId 永远取自工具响应，绝不从路径或名字推测。
- 分支只看 `ok`/`error.type`/退出码；`error.message` 只给用户看，绝不程序分支。
- `job result` 的 `status=="succeeded"` 不等于仿真成功：必须检查 `warnings`（如
  `SIMULATION_FAILED`）与 `targetValues` 非空才算真成功。
- 候选信封（血泪教训）：手动 `epcd_run` 候选的 input_obj 必带
  `{"schemaVersion":"epcd-candidate/v1","parameters":{...}}`；只传 `{"parameters":{...}}`
  会被服务端静默忽略、跑默认几何。优化控制器内部已带正确信封。
- objectives patch 格式（冒烟实测）：`synthesisTargets` 需含 `frequencyMode:"points"`；
  每条 objective 的 `frequency` 用 `{"mode":"point","value":2.4,"unit":"GHz"}`（`value` 是
  **数字**）、`targetValue` 是**数字**、`weight` 是**整数 1~10**、`comparison` ∈
  `equal|greater-than|less-than`。用字符串/缺 `frequencyMode` 会依次报
  `INVALID_OBJECTIVE_TARGET`/`INVALID_OBJECTIVE_WEIGHT`/`INVALID_FREQUENCY`。
- `epcd_run` final：`wait=true` 时**不要**传 `timeout_seconds`（服务端 `TIMEOUT_WITH_WAIT`；
  timeout 仅异步提交 wait=false 可用）。
- 同一调用自纠上限 2 次；退出码语义见 release §2/§10。
- 预算：MVP 冒烟 max_rounds=3、startup_trials=3；生产按模板推荐（简单电感 ~10 轮、
  几何受限 stack 家族 ≥20 轮），见 `references/tpe-tuning-9template-20260903.md`。
- 提交前本地跑 `./.venv/Scripts/python -m pytest tests -q`，全绿再交付改动。