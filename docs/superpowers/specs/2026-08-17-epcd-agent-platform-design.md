# EPCD 元器件设计 Agent 平台 —— 设计文档

日期：2026-08-17
状态：已与需求方逐节确认（总体架构 / Tools·Skills / 优化控制器·里程碑 / 错误处理·测试·MVP）

## 1. 背景与目标

EPCD 是一个电路元器件设计平台（后台服务），已通过 `epcd-cli` 暴露 P0 固定命令接口（见 `agent-demo-command-flow_release.md`，覆盖 4.1~4.15：健康检查 → 建工程 → 选模板 → 实例化 → 配置 Schema → 读写参数 → 预览 → 公式校验 → 设计目标 → 仿真配置 → 迭代仿真 → 写回最优参数 → 最终正式仿真）。

本平台在 epcd-cli 之上构建一个 **Agent 层**，目标：

- 覆盖完整的 P0 设计周期闭环，用户以自然语言驱动全流程（"帮我设计一个 2.4GHz 下 L≈10nH、Q>20 的电感"）。
- 主动执行后台命令（epcd-cli），在里程碑处与用户确认，在预算内自主迭代优化器件参数。
- 支持 skill / tools / subagent 等平台形式（按需启用，不预置无用组件）。

**MVP 验收场景**：工程师一句话发起设计，Agent 自动完成选型 → 建工程 → 定目标 → 仿真迭代 → 写回 → 最终仿真，里程碑处确认，最后交付版图预览、目标图表、SNP 与指标报告。

## 2. 已确认的需求决策

以下决策均与需求方逐项确认：

| 决策点 | 结论 |
| --- | --- |
| 产品形态 | 独立对话式产品（Web 聊天界面，面向设计工程师） |
| 周期范围 | 以 P0 流程（release 文档 4.1~4.15）闭环为准，不做后段流程预留 |
| 自主权边界 | 里程碑确认制：选型、设计目标、写回、最终仿真必须人工确认；预算内迭代优化自主执行，用户可随时介入 |
| 迭代策略 | LLM + 数值优化器混合：LLM 负责目标理解、初始候选、异常诊断、结果解读；数值优化器负责参数空间搜索 |
| 技术底座 | Claude Agent SDK |
| 部署模式 | 单用户起步；会话/存储/权限模型按可隔离设计，预留多用户 |
| 模型接入 | MVP 只支持 Anthropic 协议端点（官方 API 或兼容网关），`base_url` / `api_key` / `model` 配置化；多模型适配层留作演进 |
| Skill 定位 | 仅流程编排配方，不承载器件领域知识 |
| 验收场景 | 端到端一句话设计（电感示例） |

## 3. 总体架构

采用 **方案 1：主 Agent 编排 + 独立优化控制器**（Agentic 主干 + 确定性孤岛）。

```
┌───────────────────────────────────────────────────────┐
│ Chat UI (Web)                                         │
│  对话流 · 里程碑确认卡片 · Artifact 渲染              │
│  （版图预览 PNG / 目标图表 / 产物清单下载）           │
└────────────────────────▲──────────────────────────────┘
                         │ WebSocket/SSE（按 session 推送）
┌────────────────────────┴──────────────────────────────┐
│ Agent Service（单进程；内部按 session 隔离，          │
│                预留多用户扩展边界）                   │
│                                                       │
│  ┌──────────────┐        ┌───────────────────────┐    │
│  │ 主 Agent     │◄──────►│ Design Session Store  │    │
│  │ (Agent SDK)  │        │ SQLite 持久化         │    │
│  │ 对话理解 /   │        │ （单一事实源，        │    │
│  │ 流程编排 /   │        │   LLM 之外）          │    │
│  │ 结果解读     │        └───────────────────────┘    │
│  └──────┬───────┘                                     │
│         │ 工具调用                                    │
│  ┌──────┴──────────────────────────────────────┐      │
│  │ Tools 层：epcd-* 工具 · optimization_* ·    │      │
│  │           artifact_view                     │      │
│  └──────┬──────────────────────┬───────────────┘      │
│         │                      │                      │
│  （无内置 Subagent）   ┌───────┴──────────────────┐   │
│                        │ OptimizationController   │   │
│                        │ 确定性优化循环：         │   │
│                        │ 优化器 + job 轮询 + 预算 │   │
│                        └───────┬──────────────────┘   │
└────────────────────────────────┼──────────────────────┘
                                 │ subprocess（stdout 紧凑 JSON / stdin JSON）
                        ┌────────┴────────┐
                        │ epcd-cli（既有）│
                        └─────────────────┘
```

### 3.1 组件职责

| 组件 | 职责 | 关键特性 |
| --- | --- | --- |
| Chat UI | 自然语言对话；渲染里程碑确认卡片与 artifacts（PNG / SNP / Manifest） | 瘦前端，全部状态来自后端会话 |
| 主 Agent | 理解用户意图、推进 P0 流程、适时发起里程碑确认、解读 `objectiveCost` / `targetValues` 并向用户解释 | Agent SDK 主循环；不参与长轮询 |
| Design Session Store | 持久化设计记录：project-dir、instanceId、最新 `configDigest`、templateId、job 索引、里程碑状态、优化任务快照 | 单一事实源；Agent 上下文可重置而此层不丢；恢复 / 审计 / 多用户隔离的基础 |
| Tools 层 | epcd-cli 薄封装：统一解析 `ok` / `errors[].code` / 退出码，返回结构化结果 | 见 §4 |
| OptimizationController | 运行 4.11~4.13 迭代循环：数值优化器产出候选 → 提交 `run` → 轮询 `job get` → 读 `job result` → 更新优化器；管理预算与提前终止 | 确定性程序，可恢复，进度推送 UI；LLM 只在三点介入（初始候选 / 异常诊断 / 终报解读） |

### 3.2 两条数据流

1. **对话流**：用户消息 → 主 Agent → 工具调用 → Store 更新 → 回复 / 确认卡片。
2. **优化流**：主 Agent 经 `optimization start` 工具启动控制器 → 控制器独立运行（不消耗 LLM 上下文）→ 进度 / 结果写回 Store 并推送 UI → 完成时通知主 Agent → 主 Agent 汇报并发起 M3 确认。

### 3.3 多用户预留

session 为隔离单元；Store 按 session 组织表/目录。MVP 单用户单进程，但所有接口按 session 粒度设计。未来增加用户鉴权与并发会话时，只需扩展接入层（鉴权中间件 + 会话路由），不动核心组件。

## 4. Tools 层

10 个工具条目（里程碑确认不单独建工具，走 SDK 内置 AskUserQuestion；`optimization_*` 一组含 start / status / cancel 三个操作）：

| 工具 | 封装命令 | 说明 |
| --- | --- | --- |
| `epcd_health` | `version` + `health` | 启动前环境探测，解读 `degraded` 原因 |
| `epcd_template` | `device-template list/describe` | 模板查询与选型 |
| `epcd_project` | `project init/describe/validate` | 工程创建与验证 |
| `epcd_device` | `project device add/list/describe/remove` | 器件实例管理 |
| `epcd_config` | `config schema/get/patch/apply-result` | 配置读写（核心） |
| `epcd_formula` | `formula validate` | 自定义指标公式校验 |
| `epcd_run` | `run --task ...` | 预览 / 仿真任务提交（`--wait` 同步或异步） |
| `epcd_job` | `job get/result/cancel` | 任务轮询、取结果、取消 |
| `optimization_*` | —（平台工具） | start / status / cancel 优化控制器 |
| `artifact_view` | —（平台工具） | artifact 清单 → UI 可渲染预览卡片 |

### 4.1 三条硬规则

继承 release 文档的接口纪律：

1. **分支判断只用结构化字段**：`ok`、`errors[].code`、`errors[].path`、进程退出码。`message` 仅用于向用户展示，绝不用于程序分支。
2. **身份与摘要自动注入**：`--project`、`--instance-id`、`--if-match <config-digest>` 一律由工具层从 Session Store 取最新值注入，LLM 不手写这些值（杜绝从目录名或显示名推测 id）。例外：`project init` 尚无工程，其 `--work-dir` 由主 Agent 显式给出。遇 `CONFIG_DIGEST_MISMATCH` 时，工具自动 `config get` 刷新摘要并重试一次；仍失败才上报 Agent。
3. **关键写操作自动记账**：`init` / `add` / `patch` / `apply-result` / `run` 成功后，工具将返回的 `instanceId`、新 `configDigest`、`jobId` 等写回 Session Store，保证 Store 永远是单一事实源。

## 5. Skills 层

只保留 1 个 skill（Markdown 形式，由主 Agent 加载）：

| Skill | 内容 |
| --- | --- |
| `standard-optimize-flow` | 端到端标准设计流程：4.1~4.15 阶段划分、每个里程碑确认点（何时用 AskUserQuestion）、预算约定、异常分支指引；含快速预览与中途调优的分支说明 |

明确移除 / 不建的设计：

- 会话恢复不单设 skill：直接使用 SDK 原生的 session 中断/恢复能力（按 session ID 续接，Store 提供状态对齐）。
- 快速预览、中途调优不单设 skill：主 Agent 用现有工具即可完成，作为 `standard-optimize-flow` 内的分支说明。
- Skill 只写"何时做什么、在哪确认、如何调工具"，不含器件领域知识。

## 6. Subagents

内置 0 个，保留机制：

- 启动健康检查用启动钩子调 `epcd_health`，无需 subagent。
- 失败诊断与结果报告由主 Agent 自己用工具读 `logFile`、`job result` 完成。
- SDK 的 subagent 机制作为平台能力保留；未来确有并行隔离需求（如多候选并行探索）再启用。能力支持，但不预置。

## 7. OptimizationController

### 7.1 启动输入

主 Agent 调用 `optimization start` 时移交三样东西：

1. **参数空间**：从 `config schema` 的字段 / 类型 / 枚举 / 范围解析出优化边界。若 Schema 中某参数无范围约束，在 M2 里程碑确认时向用户询问经验范围（作为目标确认的一部分）。
2. **初始候选**：LLM 基于设计目标推理给出的 1~2 组起点参数。
3. **预算**：最大轮数 / 最大时长 / 达标阈值（`objectiveCost` 下限），三者先到即停；预算在 M2 与目标一并确认。

### 7.2 循环体

```
每轮：
  数值优化器（贝叶斯优化 / 无梯度法，Optuna 实现）产出候选 parameters
  → 构造 epcd-candidate/v1 JSON
  → epcd-cli run --task simulation-evaluation --input -
       --if-match <store 中最新 digest> --request-id iteration-N（异步提交）
  → 轮询 job get 至终态
  → job result 读取 objectiveCost / targetValues
  → 回写 Store（本轮参数、cost、状态）→ 推送进度事件给 UI
  → 喂给优化器，产出下一候选
终止：预算耗尽 或 达到阈值 或 用户取消
产出：{ bestJobId, bestCost, 全轮历史 } → 通知主 Agent 解读汇报
```

### 7.3 关键设计点

- **可恢复性借用 CLI 原生机制**：`requestId` 语义是"同一作用域（规范化工程路径 + instanceId + requestId）、相同请求返回原 Job"。控制器崩溃重启后，用相同 `iteration-N` 重新提交即可接回原任务，无需自建断点协议。
- **失败分类处理**：瞬时类错误（退出码 7/8/9）以同 requestId 重试一次；校验/业务类错误（4/5）立即暂停循环并上报主 Agent，由主 Agent 诊断并询问用户。
- **进度实时可见**：每轮把轮次、候选参数、cost 趋势推送 UI，用户可观察收敛或震荡。
- **评价字段纪律**：只用 `objectiveCost`（越小越好）做选择；同时保留各频点 `actualValue` / `relativeDeviation` / `satisfied` 供 LLM 解读。

### 7.4 优化期间的用户干预

优化进行中用户可随时对话：

- 问进度：主 Agent 查 `optimization status` 回答。
- 喊停：主 Agent 调 `optimization cancel`（对应 `job cancel`）。
- 改目标：暂停优化 → `config patch` 新目标 → 以新 requestId 前缀重启优化（旧结果保留在 Store 供对比）。

## 8. 里程碑确认机制

4 个强制确认点，全部经 SDK 内置 AskUserQuestion 发起（Web 端渲染为确认卡片）：

| 里程碑 | 时机 | 确认内容 |
| --- | --- | --- |
| M1 选型确认 | 模板 describe 之后、`device add` 之前 | 选定模板 + 实例名 |
| M2 目标确认 | 解析出 `synthesisTargets` + 仿真配置之后、patch 之前 | 指标 / 频点 / 比较方式 / 权重 / 扫频 / 优化预算（合并确认，减少打断） |
| M3 写回确认 | 优化完成、`apply-result` 之前 | 最优 cost、各指标达成表、与目标偏差对比 |
| M4 最终仿真确认 | 写回成功之后、final run 之前 | 确认以写回参数做正式仿真 |

规则：

- 每个确认点用户有三个选项：批准 / 修改后批准（对话中修改，Agent 重构 JSON 后重新确认）/ 终止。
- M2 之前的所有步骤（健康检查、建工程、读 schema）自主执行，不打断用户。
- 所有确认留痕写入 Store（`milestone` 表），支持审计。

## 9. Design Session Store

单文件 SQLite，表按 session 组织（多用户预留）：

| 表 | 内容 |
| --- | --- |
| `session` | sessionId、createdAt、模型端点配置快照 |
| `instance` | projectDir、libName、technologyDigest、instanceId、templateId、name |
| `job` | jobId、requestId、taskType、status、parameters 快照、objectiveCost、startedAt/finishedAt |
| `optimization_task` | taskId、status、预算、已消耗、bestJobId、全轮历史引用 |
| `milestone` | 确认点编号、时间、用户选择、确认时的数据快照 |

核心运行时字段：projectDir、最新 `configDigest`、objectives 快照、jobs 索引。审计价值：任何时刻可回答"这个设计是怎么一步步走到当前状态的"。

## 10. 错误处理

按退出码分层路由：

| 退出码 | 分类 | 处理 |
| --- | --- | --- |
| 2/3/4（参数/输入/Schema 错） | Agent 自纠 | 主 Agent 依据 `errors[].code` + `errors[].path` 修正输入重试（同一调用上限 2 次），仍失败向用户说明 |
| 5（业务规则错） | 需决策 | 展示结构化错误，AskUserQuestion 询问用户调整方式 |
| 6（工艺错） | 阻断 | 提示工艺文件问题，流程停在工程创建阶段 |
| 7（License 不可用） | 阻断 | 明确告知用户，不重试 |
| 8（GDS/仿真失败） | 诊断 | 主 Agent 读 `logFile` + `job result` 诊断原因，建议修复或调整参数 |
| 9（写入失败） | 环境类 | 重试一次，仍失败上报（磁盘/权限） |
| 10（已取消） | 正常分支 | 按用户意图继续 |
| 11（request-id 冲突） | 恢复语义 | 控制器利用"相同请求返回原 Job"接回任务；对话层冲突则更换 requestId |

全局规则：

- `CONFIG_DIGEST_MISMATCH` 由工具层自动刷新摘要重试一次（§4.1）。
- 优化循环内瞬时错误（7/8/9）同 requestId 重试一次；校验类错误（4/5）暂停上报（§7.3）。
- `apply-result` 因状态漂移被拒绝时（工程/器件/工艺/摘要在 Job 创建后变化），向用户解释并询问是否基于当前状态重新优化。

## 11. 测试策略

三层：

1. **工具层单测**：mock epcd-cli 子进程（夹具：各退出码 + `epcd-response/v1` 信封），覆盖全部退出码路由与 `CONFIG_DIGEST_MISMATCH` 重试路径。
2. **OptimizationController 测试**：mock CLI 层跑完整循环——预算停止、失败暂停、崩溃后用同 requestId 恢复接回原 Job。
3. **端到端验收**：真实 epcd-cli（利用其 mock 模式）执行验收场景——"设计 2.4GHz 下 L≈10nH、Q>20 的电感"。断言：恰好 4 次里程碑确认、最终 artifacts 齐全（GDS / Gtxt / PNG / SNP / 目标值 JSON / 目标图表 / Manifest）、RangeEM 发布产物落盘。另备 golden 对话用例：中途改目标、优化中喊停、异常诊断。

## 12. MVP 范围与技术选型

| 项 | 选择 | 理由 |
| --- | --- | --- |
| Agent Service | Python：Claude Agent SDK (Python) + Optuna（数值优化）+ SQLite | 与 epcd-cli 的 Python 3.8 运行时生态一致，优化库成熟 |
| 前端 | 轻量 Web（对话流 + 确认卡片 + PNG/图表渲染 + artifact 下载） | 验收场景需要富媒体展示 |
| 通信 | WebSocket/SSE，按 session 推送 | 优化进度实时可见 |
| 模型接入 | `base_url` / `api_key` / `model` 配置化（Anthropic 协议） | MVP 只支持 Anthropic 协议端点（官方或兼容网关） |

**MVP 明确不做**：多用户鉴权与并发、非 Anthropic 协议模型适配、器件领域知识库、多候选并行比选、DRC/LVS 等后段流程。

## 13. 演进路线

1. **V1.1**：模型适配层——当国产模型端点与 Anthropic 协议不完全兼容（工具调用、流式、长上下文）时，建设内置模型网关层，支持多模型配置与按任务切换。
2. **V1.2**：多用户——鉴权、并发会话、任务队列。
3. **V2**：多候选并行比选、器件领域知识 skill（设计经验沉淀）、设计反向诊断（"为什么 Q 不达标"）。

## 14. 开放问题

1. **无界参数的默认边界**：`config schema` 未给范围的参数，M2 时询问用户经验范围是否足够，是否需要内置一份器件类别的默认范围表——MVP 先采用询问策略。
2. **前端技术栈细节**（框架、构建工具）在实现计划阶段确定，不影响本设计的架构约束。
