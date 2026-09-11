---
name: epcd-agent-flow
description: EPCD 元器件设计 Agent 端到端全流程编排。用户自然语言发起器件设计（"帮我设计一个 2.4GHz 下 L≈10nH、Q>20 的电感"）时使用。只确认两件主观决策：synth 目标（仅当用户没给具体指标时，逐项）与模板（推荐）；命名/路径/仿真配置/TPE 参数全自动，并一路执行到全部仿真结果，再按结果确认写回/优化方案与最终仿真。服务器连接/工艺/工作目录统一读项目内 `epcd-configs.json`（平铺 multi-config，active 一键切换）。核心流程走 epcd_agent 确定性后端（epcd_cli 直调 --config-file），运维/传输走 dsh-ssh 工具。
---

# EPCD Agent Flow

在 `epcd-cli` 之上编排一套完整的器件设计流程：
健康检查 → 目标/模板确认 → 自动执行（建工程 → 实例化 → 配目标 → TPE 优化 → 仿真）→ 结果确认 → 最终仿真 → 交付。
用户只确认「目标」与「模板」两项主观决策，其余全部自动生成并自动跑完。
本 skill 是**流程编排配方**，不含器件领域知识（模板边界见 `references/`）。

## ⚡ 快速启动（先把第一步做对，再谈其它）

用户一开口就直奔第一步，**在健康检查之前禁止任何仓库探索与提前提问**。这直接决定
「输入 → 首步」的延迟，也是本 skill 的第一条纪律：

1. **读项目配置**（一次工具 `epcd_config`，`action=get`）：从返回的 `activeConfig` 取
   `host`/`port`/`user`/`identityFile`/`pkg`/`technology`/`workDirRoot`（= 项目内
   `<cwd>/epcd-configs.json` 的 active config，平铺字段）。
   关键字段缺失时，用**一次** `ask_user_question` 把缺失字段问齐并 `epcd_config`
   （`action=save`）写回（这是健康检查前唯一允许的提问）。
2. **立刻跑健康检查**（一次 `epcd_cli` 的 `epcd_health`，见下），`data.status=="degraded"` 时解释原因并停。
3. 健康检查通过后，才按需读 `references/inductor-templates-comparison.md` 或
   `epcd_template list/describe`（它们服务于模板/目标确认，不是第一步）。

**禁止在健康检查前做这些事**：

- `glob` 仓库 / 读 `backend/README.md`、`cli.py`、`store.py` —— 这些不影响第一步；
- 提前问设计规格/目标 —— 目标确认在健康检查之后、且只在用户没给具体指标时才问；
- 先读模板对比表 / 先看 schema —— 那是模板/目标确认阶段的事。

## 项目配置（`epcd-configs.json`：平铺 multi-config）

单一事实源 = 项目内 `<cwd>/epcd-configs.json`，结构：

```json
{ "active": "zhubo-prod",
  "configs": { "zhubo-prod": { "host": "...", "port": 22, "user": "...",
    "identityFile": "~/.ssh/id_rsa_epcdB", "pkg": "/package/...",
    "technology": "...", "workDirRoot": "..." } } }
```

| 字段 | 含义 |
| --- | --- |
| `host` | 服务器地址 |
| `port` | SSH 端口 |
| `user` | SSH 用户名 |
| `identityFile` | 私钥路径（`~` 由后端跨平台展开） |
| `pkg` | EPCD 包根（远端绝对路径） |
| `technology` | 工艺文件（远端绝对路径，如 `demo_revised.ptxt`） |
| `workDirRoot` | 器件工作目录根（远端，`/…/epcd-runs`） |

- **一套 config = 一组平铺属性**（连接 + pkg + 工艺 + 工作目录），可增删改；`active` 指向当前生效的 config。
- **读取**：`epcd_config`（`action=get`）拿 `activeConfig`；`action=list` 拿全部 config 名。
- **一键切换**：`epcd_config action=activate name=<config>`（或面板「EPCD 配置」tab 点选）。
- **面板 `[EPCD 配置]` tab**：配置下拉 + 新建/修改/删除/切换，操作同一份文件。
- backend 通过 `--config-file <项目内 epcd-configs.json 绝对路径>` 读 active config（`epcd_cli` 工具自动带上）。

## 自动命名（器件名/路径/实例名，全自动）

- **器件名**：从规格自动生成，如「2.4GHz 下 L≈5nH 电感」→ `ind-2p4g-5nh`（如 `workDirRoot` 下已存在该目录，主动加后缀）；提取不到时按`ind-001`、`ind-002`…全局递增。
- **work_dir** = `<workDirRoot>/<器件名>`（`epcd_project init` 的 `work_dir`）。
- **实例名** = `<器件名>-inst`（`epcd_device add` 的 `name`）。
- **session / db**：`--session <器件名>`；`--db` **不手工指定**——backend 自动落到统一产物根
  `<repo>/runs/epcd-agent-session.sqlite3`（全局审计库，单一事实源，审计+恢复；与 cwd 解耦，绝不落在 `backend/`）。
  本地产物统一落 `<repo>/runs/<器件名>/`：优化输入中间文件归 `runs/<器件名>/opt-input/`，交付产物归 `runs/<器件名>/artifacts/`。
- 以上命名/路径**全自动生成、不进任何确认卡**；用户无需（也不应被要求）手动填或改。

## epcd_cli 调用范式（进程直调，Win11 / Linux 通用）

**一律用 `epcd_cli` 宿主工具直调后端，绝不手写 pwsh/bash 命令行**——这样同一份
流程在 Windows 本机与 Linux 部署服务器上都能跑（工具内部按平台自动选
`.venv/Scripts/python.exe` 或 `.venv/bin/python`，`spawn` 直调、无 shell）。

工具入参：`tool`（12 个后端工具名之一）、`input`（stdin 传给该工具的一个 JSON 对象）、
`session`（可选，省略用 default）。**连接参数不再走 `server`**：`epcd_cli` 工具自动读项目内
`epcd-configs.json`（active config）并加 `--config-file` 传给后端。

健康检查（`tool="epcd_health"`，`input` 空对象，`session="probe"`）：

```text
epcd_cli { tool: "epcd_health", input: {}, session: "probe" }
```

普通工具（`input` 传字典给工具函数；`technology` 由后端从 active config 自动带出，**无需传**）：

```text
epcd_cli {
  tool: "epcd_project",
  input: { action: "init", work_dir: "<自动生成的work_dir>" },
  session: "<器件名>"
}
```

> `work_dir` = `<workDirRoot>/<器件名>`（skill 用 active config 的 `workDirRoot` + 器件名拼好）；
> `technology` 由后端从 active config 自动带出（`ToolContext.technology`）。
> 后端只认 `--config-file <项目内 epcd-configs.json 绝对路径>`；未传 / 文件缺失 → 退出码 2。

12 个后端工具（`tool` 取值）：`epcd_health` / `epcd_template` / `epcd_project` /
`epcd_device` / `epcd_config` / `epcd_formula` / `epcd_run` / `epcd_job` /
`optimization_start` / `optimization_status` / `optimization_cancel` / `artifact_view`。

## config 配方（复制即用）

`epcd_config patch` = **JSON merge patch**（stdin 只提交顶层改项；`--if-match` 的 digest 自动带/自动更新，永不手填）。
完整可复制模板见 `references/config-patch-templates.md`（读它即可，勿再翻 backend/demo、backend/tests）。

三条最关键的坑（其余细节进上面那份文档）：

- **metrics 两套名字**：写入 objectives 用显示名 `Inductance Value(nH)` / `Min Q Factor` / `Max Size(um)`；
  读 job result 验收用短 key `L` / `Q` / `maxSize`。
- **apply-result 顺序**：校验当前 digest == job 的 `configDigestUsed`，否则报 `JOB_CONFIG_CHANGED`；
  「放宽目标」必须**先 apply-result 写回几何 → 再 patch 放宽 objectives → 再 epcd_run final**，顺序不能反。
- **最终结果**：`epcd_run`（`task="simulation-evaluation"`）只回 `jobId`+`status`，必须再 `epcd_job action="result"` 取 `targetValues`/`artifacts`。

## 确认卡写作规范（最小卡 / 单用途）

**一张卡只解决一个决策点**，绝不把不同决策点堆进同一张卡（这是硬纪律）：

- 一个 `ask_user_question` 只对应一个决策点：目标卡只列目标、模板卡只列模板、结果卡只列结果。
- **逐项呈现**：每个目标一行 `指标: 值`（如 `L: 5 nH · Q: ≥8 · size: ≤300 µm · freq: 2.4 GHz`），
  缺项标「默认代入」，可读、可逐项改。
- 数字/指标用紧凑列表或小表，**不要**贴 JSON 原文。
- 选项固定三选「批准 / 修改后批准 / 终止」，每个 option 的 description 写一句
  「点了会发生什么」；「修改后批准」的 description 写清本卡能改哪些项。

## 阶段流程

### 0. 确认原则（第一性）

用户在整个流程里只确认两件**主观决策**，其余全部自动生成并自动执行：

| 决策点 | 何时确认 |
| --- | --- |
| synth 目标 | **只有用户没给具体指标时**，逐项确认 |
| 模板 | **总是**确认（按目标推荐） |

**全自动、不进任何卡**：器件名 / 实例名 / `work_dir` / `session`；仿真配置（objectives、
sweep 按目标自动推导、`frequencyMode`）；TPE 参数（`parameter_schema` 用模板
`describe().parameterSchema`、`initial_candidates` 1~2 组、`max_rounds` 按模板推荐）。

### 1. 快速启动（自主）
读项目配置 + `epcd_health`，`degraded` 停。

### 2. 目标与模板确认（执行前仅有的确认）

- **用户给了具体/完整 synth 目标**（如「2.4GHz、L≈10nH、Q>20、≤300µm」）→ **跳过目标确认**，直接确认模板。
- **用户没给（全部）目标** → 先「逐项确认缺失的目标」，批准后再确认模板。

**逐项确认缺失目标**（最小卡，只放缺失目标）：每项一行 `L / Q / size / freq`；提取不到的项给 MVP
默认（2.4GHz、L=5nH、Q≥8、≤300µm）并标「默认代入」，可逐项改。

**确认模板**（最小卡，只放模板）：按目标读 `references/inductor-templates-comparison.md`
（未覆盖再 `epcd_template list/describe`）推荐模板；卡里只放 模板名 + `template_id` + 优化边界（紧凑一行）。

> 「目标」是设计要什么、「模板」是在哪个空间里找——这是执行前仅有的（目标缺失时两次，否则一次）确认。

### 3. 自动执行（不打断，一路跑到全部仿真结果）

批准模板后**连续自动**执行、中途不发起任何确认：

1. `epcd_project init`（`work_dir` + `technology`）→ describe → validate
2. `epcd_device add`（`template_id` + 自动实例名）
3. `epcd_config schema`（action=`schema`，**不是 `schema/get`**）→ 按已确认目标构造
   `synthesisTargets`/objectives；sweep 按目标自动推导：point 目标不配扫频，range 目标顶层
   `sweeps` 覆盖 range，stack 家族模板用最小覆盖带宽。
   ⚠️ 此 `epcd_config` 是 epcd-cli 的 config 工具（读/写器件 config），**区别于**「项目配置」
   一节的 `epcd_config`（DSH 宿主工具，action=get/set 读/写 ssh/pkg/technology/workDirRoot）。
4. `epcd_config patch`（objectives 与 sweeps 分开提交、每次最新 digest）
5. `optimization_start` 后台启动（唯一例外，见下）：
   `parameter_schema` 必须用模板 `describe()` 返回的 `parameterSchema`（优化边界只在这里；
   `config schema` 的 `device.parameters` 是默认值骨架、`addinParams` 是面板参数堆——都不是优化空间）；
   `initial_candidates` 1~2 组；`max_rounds` 按模板推荐。
   —— `optimization_start` 内部阻塞整轮 TPE（每轮 ~25s × 多轮），不能用同步 `epcd_cli`；
   改用**当前平台的 shell 工具 `run_in_background`**（Win11 用 pwsh、Linux 部署服务器用 bash，
   DSH 已按平台二选一，二者行为对称，不依赖 pwsh）。命令用 backend venv 的 python：
   - Win11：`backend\.venv\Scripts\python.exe -m epcd_agent.cli --config-file <项目内epcd-configs.json绝对路径> --session <器件名> optimization_start`
   - Linux：`backend/.venv/bin/python -m epcd_agent.cli --config-file <项目内epcd-configs.json绝对路径> --session <器件名> optimization_start`
   + stdin 传 `{"parameter_schema":…,"initial_candidates":…,"max_rounds":…}`（工作目录 = `backend/`）。
   ⚠️ **不传 `--db`**：backend 自动落统一根 `<repo>/runs/epcd-agent-session.sqlite3`，与 cwd 解耦。
   其余 11 个工具仍一律走 `epcd_cli`（`epcd_cli` 内部已按平台自动选 python、自动带 `--config-file`，无需区分）。
   ⚠️ 后台 bash 直跑 `python -m epcd_agent.cli` 走的是**本机 ssh 二进制**（非 dsh-ssh 工具）。
   ssh 连接已实现**平台无关 + 与本机 ssh config 路径解耦**：连接参数来自 active config 的平铺字段
   `host/port/user/identityFile`（backend 用 `-F <temp空config> -o HostName=… -o User=… -i …` 连接，
   不读本机/系统 ssh config）。若仍报 `ENVELOPE_PARSE_ERROR: empty stdout`，
   见 `references/ssh-troubleshooting.md`。
6. **紧轮询** `optimization_status`（读 SQLite）：`optimization_start` 是后台任务、内部**逐轮**写库
   （每轮 `_record_round` 落 `rounds`/`consumed.rounds`）；因此**每读到 `done_rounds` 增加一轮，就立刻调一次
   `epcd_status` 刷新进度条**，让进度逐轮推进（0→1→…→20），**绝不让多轮攒成一次 epcd_status**。
   不要用 `job_output(wait=true)` 长时间阻塞等待整体结束——那会让进度条从 0 直接跳到收尾；
   `request_prefix` 默认已唯一，**不要复用同一前缀**。
   ⚠️ **`optimization_status` 不传 `task_id`**（`input` 空对象 `{}`）：它自动查该 session 最近一个
   running/pending 任务（否则最新一个）。`task_id` 是 `opt-{job行数+1}`、随每轮候选仿真漂移、且只
   在 `optimization_start` 返回时才暴露——**绝不能靠猜或手填 task_id**，否则轮询会 `OPTIMIZATION_TASK_NOT_FOUND`。
7. 读 best job `targetValues`，对照每条 objective 做差距表

仅 `OPTIMIZATION_PAUSED`（读 `data.errors`/`category` 诊断）/ degraded 等**硬故障**才停下问用户。

### 4. 结果确认（全部结果出来后，才向用户确认）

- **未达标** → 一张卡主动给三条方案：① 追轮续优 ② 放宽目标为区间 ③ 换模板；每条 option
  description 写预期收益/代价。
- **达标** → 一张卡问是否**写回**。

批准后 `epcd_config apply-result`（stdin 关键字 `job_id`=best_job_id，`{"action":"apply-result","job_id":"<best_job_id>"}`）。

**追轮续优（勿从头）**：`optimization_start(parameter_schema=…, initial_candidates=[上次best],
resume_from=<上一 task_id>, max_rounds=<新增轮数>)`。`resume_from` 把上一 task 的成功轮（参数+cost）
喂回 TPE 后验继续；`max_rounds` 是**本轮新增轮数**（不是累计总数），`data.warm_started_rounds` 供汇报。

### 5. 最终仿真确认 → 交付
写回后 `ask_user_question` 确认最终仿真 → `epcd_run`（`task="simulation-evaluation"`、
`request_id="final-<best-job-id>"`、`wait=true` 不传 timeout）。注意 `epcd_run` 的 `task` 白名单
只有 `simulation-evaluation` / `gds-generation`，**没有 `final`**；「final」只是流程语义，落在
`request_id` 前缀。验收：逐条 `targetValue == objectives`、`satisfied` 判达标、`parametersUsed` 含写回几何。
交付：`artifact_view`（不传 `fetch_dir`，产物自动落 `<repo>/runs/<器件名>/artifacts/`）拉产物、
`epcd_artifacts` 渲染图库——版图三视图（`preview_top`/`preview_iso`/`preview_side`，
kind=`image`，label=俯视/轴测/侧视）+ S2P/GDS/目标值。**所有本地产物只在 `<repo>/runs/<器件名>/` 下，
不得落到 `backend/` 或其它散落目录。**

## 硬规则

- 仅有的用户确认点：synth 目标（仅当用户没给具体指标）/ 模板（推荐）/ 结果确认（写回或优化方案）/
  最终仿真，全部用 `ask_user_question`，三选项语义：批准 / 修改后批准 / 终止，留痕。
- 除项目配置缺失字段外，目标/模板确认之前不发任何提问；命名/路径/仿真配置/TPE 参数一律自动、不确认。
- id/digest/jobId 永远取自工具响应，绝不从路径或名字推测。
- 分支只看 `ok`/`error.type`/退出码；`error.message` 只给用户看，绝不程序分支。
- `job result` 的 `status=="succeeded"` 不等于仿真成功：必须检查 `warnings`（如
  `SIMULATION_FAILED`）与 `targetValues` 非空才算真成功。
- 候选信封（血泪教训）：手动 `epcd_run` 候选的 input_obj 必带
  `{"schemaVersion":"epcd-candidate/v1","parameters":{...}}`；只传 `{"parameters":{...}}`
  会被服务端静默忽略、跑默认几何。优化控制器内部已带正确信封。
- objectives patch 格式 / 写回顺序的完整模板见 `references/config-patch-templates.md`
  （撰写前必读）；字段写错依次报 `INVALID_OBJECTIVE_TARGET` / `INVALID_OBJECTIVE_WEIGHT` /
  `INVALID_FREQUENCY`；`frequencyMode` 档位与 objective 的 `frequency.mode` 不一致报
  `FREQUENCY_MODE_MISMATCH`，写回前改 objectives 触发 `JOB_CONFIG_CHANGED`。
- `epcd_run` 最终仿真（`task="simulation-evaluation"`）：`wait=true` 时**不要**传 `timeout_seconds`（服务端 `TIMEOUT_WITH_WAIT`；
  timeout 仅异步提交 wait=false 可用）。
- 追加轮次用 `resume_from` 续优，**不从头重跑**；`request_prefix` 默认已唯一，别复用。
- 后台 bash 直跑 backend 若报 `ENVELOPE_PARSE_ERROR: empty stdout`，先按
  `references/ssh-troubleshooting.md` 查本机 ssh 环境（temp 目录可写性 / identityFile 存在性），
  不要改 backend 逻辑或反复重试——那不是流程 bug 就是环境 bug，二者定位路径不同。
- 同一调用自纠上限 2 次；退出码语义见 release §2/§10。