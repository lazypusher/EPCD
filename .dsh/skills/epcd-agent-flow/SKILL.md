---
name: epcd-agent-flow
description: EPCD 元器件设计 Agent 端到端全流程编排（含 M1~M4 里程碑确认）。用户用自然语言发起器件设计（如"帮我设计一个 2.4GHz 下 L≈10nH、Q>20 的电感"）时使用。chat 式交互：器件名/工作路径自动生成，服务器与工艺文件读全局配置（~/.dsh/epcd-config.json），里程碑用 ask_user_question 确认卡。核心流程走 epcd_agent 确定性后端（pwsh 调用），运维/传输走 dsh-ssh 工具。
---

# EPCD Agent Flow

在 `epcd-cli` 之上编排一套完整的器件设计流程：健康检查 → 建工程 → 选模板 →
实例化 → 配置目标 → 迭代优化 → 写回最优 → 最终仿真 → 产物交付。本 skill 是
**流程编排配方**，不含器件领域知识（模板边界见 `references/`）。

## 全局配置（用户唯一需要手动维护的输入）

**所有服务器/工艺/路径都读全局配置，绝不硬编码、也绝不在每次设计时问用户。**
配置存于 `~/.dsh/epcd-config.json`（UTF-8 JSON）：

| 字段 | 含义 |
| --- | --- |
| `ssh` | SSH 服务器别名（`~/.ssh/config` 的 Host，含 HostName/User/IdentityFile；也支持直接 host） |
| `pkg` | EPCD 包根（远端绝对路径） |
| `technology` | 工艺文件（远端绝对路径，如 `demo_revised.ptxt`） |
| `workDirRoot` | 器件工作目录根（远端，`/…/epcd-runs`） |

流程入口读该文件：
- **缺失/字段不全** → 用 `ask_user_question` 只问缺失的 `ssh`/`pkg`/`technology`/`workDirRoot`，写回该文件后再继续（一次性）。
- **用户说「改全局配置 / 换服务器 / 换工艺 / 连另一台服务器」** → 更新该文件对应字段，再从第 1 阶段跑。
- `servers.json` 仍是服务器池（`别名 → {ssh, pkg}`），但全局配置的 `ssh`/`pkg` 为默认目标，二者保持一致即可。

## 自动命名（器件名/路径/实例名，用户不必手动填）

- **器件名**：从用户自然语言提取关键参数自动生成，如「2.4GHz 下 L≈10nH 电感」→ `ind-2p4g-10nh`；无法提取时按 `ind-001`、`ind-002`…全局递增（依据 `workDirRoot` 下已有目录）。
- **work_dir** = `<workDirRoot>/<器件名>`（`epcd_project init` 的 `work_dir`）。
- **实例名** = `<器件名>-inst`（`epcd_device add` 的 `name`）。
- **session / db**：`--session <器件名>`；`--db` 固定为项目工作区 `backend/epcd-agent-session.sqlite3`（单一事实源，审计+恢复）。
- 以上自动生成的命名在 **M1 确认卡里一并展示**，用户可在「修改」选项里改器件名/实例名，改后派生路径随之更新。

## epcd_agent.cli 调用范式（本机 pwsh）

工作目录 `backend/`，所有参数经 **stdin 一个 UTF-8 JSON 对象**，stdout 恰好一行
JSON，退出码 0 成功 / 1 业务失败（结构化错误仍在 stdout）/ 2 用法错误：

```powershell
$in = '{"action":"init","work_dir":"<自动生成的work_dir>","technology":"<全局配置technology>"}'
$in | .\.venv\Scripts\python.exe -m epcd_agent.cli `
  --server <全局配置ssh> `
  --db backend/epcd-agent-session.sqlite3 --session <器件名> epcd_project
```

> `--server <ssh>` 从 `backend/servers.json` 读 `{ssh, pkg}`；等价显式写法
> `--ssh <alias> --pkg <pkg>`（`--ssh` 接受 `~/.ssh/config` 别名）。`--server`
> 未命中 / `servers.json` 缺该别名 / 文件缺失 → 退出码 2（USAGE）。

12 个工具：`epcd_health` / `epcd_template` / `epcd_project` / `epcd_device` /
`epcd_config` / `epcd_formula` / `epcd_run` / `epcd_job` / `optimization_start` /
`optimization_status` / `optimization_cancel` / `artifact_view`。

## 阶段流程

1. **健康检查（自主）**：`epcd_health`。`data.status=="degraded"` 时解释原因并停。
2. **建工程（自主）**：`epcd_project` init（`work_dir` = 自动生成路径 + `technology`
   = 全局配置工艺）；随后 describe + validate。
3. **选型（自主 + M1 确认）**：优先用本地对比表 `references/inductor-templates-comparison.md`
   （9 个电感/tcoil 模板的 opt 边界、synth 默认目标、指标族），仅未覆盖信息才回退
   `epcd_template` list/describe。向用户展示候选 + **自动生成的器件名/实例名/工作路径**，
   **用 `ask_user_question` 做 M1**（批准 / 修改（可改器件名·实例名·模板）/ 终止）。
   批准后 `epcd_device` add。
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