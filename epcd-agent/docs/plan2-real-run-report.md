# 计划 2 真实环境端到端验收报告（Claude Code 驱动，M1–M4）

- **日期**：2026-08-20
- **服务器**：`zhubo@192.168.20.243`，包 `/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default`（epcd-cli 0.1.0，Python 3.8.7）
- **通道**：单一 CLI 入口 `python -m epcd_agent.cli --ssh <host> --pkg <pkg> --db acceptance.sqlite3 --session acceptance <tool>`（stdin JSON / stdout 单行 JSON / 退出码 0/1/2）
- **会话**：本地 Store `epcd-agent/acceptance.sqlite3`，会话名 `acceptance`
- **工程**：远端 `/home/zhubo/epcd-runs/plan2-acceptance`，实例 `L1`（instanceId `20260820070615000`，模板 `system.inductor.simple_inductor`）
- **编排依据**：`.claude/skills/device-design-flow/SKILL.md`（epcd-agent/skills 同步副本）

## 环境级阻断声明

**EM 求解器许可授权不可用（非技术配置问题，待供应方开通）**。排查链与最终定性见
`agent-demo-command-flow_release.md` §4.12 实测阻断备注。影响：仿真 job 状态为
`succeeded` 但 `warnings` 携带 `SIMULATION_FAILED`、`targetValues` 为空、无
`objectiveCost` → 优化循环按设计进入 `OPTIMIZATION_PAUSED` 上报路径。本次验收
覆盖全编排链路与该暂停分支的真实表现；"产生真实目标值/成本"的成功判据留待许可
开通后复核（仅需重跑阶段 5~8）。

## 阶段记录

### 阶段 1：健康检查（自主）— ✅

`epcd_health` → `{"ok": true}`：`status=ok`，version 0.1.0，runtime
`private-api`（mock=false，available=true），modules project/param/tech 全可用，
stateHome `/home/zhubo/.epcd` 存在且可写。

### 阶段 2：建工程（自主）— ✅

| 调用 | 结果 |
| --- | --- |
| `epcd_project` init（work_dir=/home/zhubo/epcd-runs/plan2-acceptance，technology=demo.ptxt） | `{"ok":true,"data":{"path":...,"libName":"plan2-acceptance","techFile":...}}`，Store 记账 project_dir |
| `epcd_project` describe | 同上骨架回读 |
| `epcd_project` validate | `{"valid":true,"technologyDigest":"sha256:e04cb25e...","devices":[]}` |

### 阶段 3：选型 + M1（AskUserQuestion）— ✅

`epcd_template` list：44 个模板，inductor 类 7 个（simple_inductor /
adv_simple_inductor / bowtie / differential / differential_step / stack /
stack_overlapped）。`describe system.inductor.simple_inductor` 取回嵌套
parameterSchema（basic/opt/synth 分组，字符串数值边界）与 builtInMetrics
（inductance 2.1 / minQFactor 8 / maxSize 300，权重均 1）。

**M1 确认**（AskUserQuestion，选项：批准/换模板/终止）：用户**批准**
simple_inductor，实例名 `L1`。

`epcd_device` add → `instanceId=20260820070615000`，`path=.../L1`，返回
epcd-device/v1 配置骨架；Store 记账并设为活跃实例。

### 阶段 4：配置骨架（自主）— ✅

`epcd_config` get → digest `sha256:20a0f6a0...`（Store 记账）；骨架含空
`synthesisTargets.objectives`、空 `simulation.sweeps`、空顶层 `sweeps`。
`epcd_config` schema → epcd-device-schema/v1（配置默认值骨架，与 release §4.5
校正一致）。

### 阶段 4b：目标与扫频写回（M2 后）— ✅

M2 确认卡内容：① inductance Equal 2.1 nH @2GHz（权重 5）② minQFactor
Greater 8 @2GHz（权重 3）③ maxSize Less 300 um @2GHz（权重 2）；EM + adaptive
1~3GHz（step 10MHz，顶层 sweeps 形状带单位字符串）；预算 max_rounds=3；初始
候选 2 组。**用户批准**（AskUserQuestion：批准/修改后批准/终止）。

- patch 1 `{"synthesisTargets": {...3 objectives...}}` → `changed:true`，
  digest `sha256:20a0f6a0...` → `sha256:e661fc36...`（Store 自动记账）
- patch 2 顶层 `{"sweeps":[{"enabled":true,"type":"adaptive","start":"1GHz","stop":"3GHz","step":"10MHz","points":""}]}` → `changed:true`，
  digest → `sha256:c84a5ad2...`

**回读验证**（config get）：synthesisTargets 持久化（字符串化形状：frequency
变为 `{"mode":"point","freq":"2.0"}`，targetValue/weight 为字符串——与 release
§4.9 校正一致）；顶层 sweeps 原样持久化；`simulation.sweeps` 保持为空（确认
release §4.10 校正：该路径不持久化，顶层 sweeps 才是正路）。

### 阶段 5：迭代优化（自主）— ✅（按设计暂停）

`optimization_start` stdin：`parameter_schema`=describe 原样（嵌套
basic/opt/synth），`initial_candidates` 2 组（trackWidth 10/trackSpace 2/
numOfTurns 3/innerRadius 40；trackWidth 12/trackSpace 3/numOfTurns 5/
innerRadius 60），`max_rounds=3`，`request_prefix="acceptance-iter"`。

真实执行：round 1 提交成功（Optuna TPE 先取首个入队候选），job
`735ece64-dd16-4453-89eb-1200b07c7895` 轮询至 `succeeded`；`job result`
无 `objectiveCost`、`targetValues` 为空、warnings 携带
`SIMULATION_FAILED: rangeInitParam failed` → 控制器按设计触发
`OptimizationPausedError`，工具返回退出码 1：

```json
{"ok": false, "data": {"task_id": "opt-1", "category": "success",
  "report": {"best_job_id": null, "best_cost": null, "stop_reason": "paused", "rounds": []},
  "errors": []},
 "error": {"type": "OPTIMIZATION_PAUSED",
  "message": "job 735ece64-dd16-4453-89eb-1200b07c7895 result has no objectiveCost/targetValues"}}
```

`optimization_status` 交叉验证 Store 状态：`{"task_id":"opt-1","status":"paused",
"budget":{"max_rounds":3,...},"best_job_id":null,"cancel_requested":false}`。

job result 证据：`parametersUsed` 扁平 `{trackWidth:10.0, trackSpace:2.0,
numOfTurns:3.0, innerRadius:40.0}`；artifacts 仅 gds+manifest。

### 阶段 6：M3 + 写回 — ✅

**M3 确认**（AskUserQuestion，暂停上报语义）：如实报告"无最优 cost、唯一可用
job 为 round-1、产物 GDS+manifest、暂停原因为许可阻断"。用户**批准：继续机械
链路**（备选：到此为止/终止）。

`epcd_config` apply-result（job_id=735ece64...）→
`{"applied":true,"configDigest":"sha256:c84a5ad2..."}`——digest 与写回前相同，
与 release §4.14 记录的"applied 但未持久化"未决异常一致（config get 回读
device.parameters.opt 仍空）。

### 阶段 7：M4 + 最终仿真 — ✅

**M4 确认**（AskUserQuestion）：用户**批准**以写回参数做最终正式仿真。

`epcd_run`（task=simulation-evaluation，不带候选 input，
request_id=`final-735ece64-dd16-4453-89eb-1200b07c7895`，use_if_match=true）→
`{"jobId":"505cb06c-efb4-48e0-8ca3-f8cf624a1566","requestId":"final-...",
"status":"queued"}`——**§4.15 命令约定实测验证**（原 release 标注"待实测"，
本次已就地校正）。job 约 1 分钟内终态 `succeeded`；result 快照同 §4.12 形状：
warnings SIMULATION_FAILED、无目标值（许可阻断，预期内）。

新证据：final run 的 `parametersUsed` 为 `{}`——无候选输入时按写回配置执行，
而写回未持久化（§4.14 异常），故参数集为空。已校正进 release §4.15。

### 阶段 8：交付（artifact_view）— ✅

`artifact_view`（job_id=505cb06c...，fetch_dir=`artifacts-cache/acceptance`）→
2 张卡片并拉取成功（ssh base64 通道）：

| 卡片 | 远端路径 | 本地缓存 |
| --- | --- | --- |
| GDS | `<project>/L1/synthesis/SimpleInd/SimpleInd.gds` | `artifacts-cache/acceptance/SimpleInd.gds`（1180 B） |
| Manifest | `<project>/devices/<instance>/runs/<job>/artifacts/manifest.json` | `artifacts-cache/acceptance/manifest.json`（341 B，epcd-artifacts/v1） |

许可开通后此处预期还会出现 SNP/目标值/图表等卡片（release §5 类型表），
届时复核。

## 遇到的问题与处置

1. **Git Bash MSYS 路径转换**：`--pkg /package/...` 作为 argv 被转换为
   `C:/Program Files/Git/package/...`，导致远端 `source` 静默失败、stdout 为空
   （首次 epcd_health 报 ENVELOPE_PARSE_ERROR）。处置：所有调用前缀
   `MSYS_NO_PATHCONV=1`（或经 `EPCD_PKG_ROOT` 环境变量传路径）。已记入 skill。
2. **许可证排查全过程**（占位 DAEMON → PHY_ETHER 虚机检查 → ETHER 后
   Invalid license key → 定性为授权不可用）：见 release §4.12；实验用
   lmgrd 已停止、现场保留 `/home/zhubo/ninecube-fixed.lic` 供开通后使用。

## 附录：计划 2 收官核对（spec §4/§5/§7/§8）

**§4 工具层：10 个工具条目（12 个 CLI 子命令）全部经单一入口真实可达**

| 工具 | 本次真实执行位置 | 结果 |
| --- | --- | --- |
| `epcd_health` | 阶段 1 | ✅ ok |
| `epcd_template` | 阶段 3（list 44 模板 / describe） | ✅ |
| `epcd_project` | 阶段 2（init/describe/validate） | ✅ |
| `epcd_device` | 阶段 3（add L1） | ✅ |
| `epcd_config` | 阶段 4（schema/get）、4b（patch×2）、6（apply-result） | ✅ |
| `epcd_formula` | 覆盖补齐（Q=Im(Z11)/Re(Z11) 校验） | ✅ valid:true |
| `epcd_run` | 阶段 5（控制器提交）、7（final run） | ✅ |
| `epcd_job` | 阶段 5/7/8（get/result） | ✅ |
| `optimization_start` / `optimization_status` | 阶段 5（真实暂停路径 / Store 状态交叉验证） | ✅ |
| `optimization_cancel` | 单元/集成测试覆盖（任务 2 + controller 测试；计划明确不真实演练） | ✅ 测试 |
| `artifact_view` | 阶段 8（卡片 + ssh base64 拉取） | ✅ |

**§4.1 三条硬规则**：① 分支判断全程只用 `ok`/`error.type`/退出码（暂停处置、
M3 上报均由结构化字段驱动）；② `--project`/`--instance-id`/`--if-match` 全程
由工具层注入，未手写一次（digest 失配自动刷新重试有单测覆盖）；③ init/add/
patch/apply-result/run/优化任务均自动记账（`optimization_status` 交叉验证了
Store 为单一事实源）。

**§5 Skills 层**：唯一 skill `device-design-flow` 存在且本次全程按其阶段
执行；M1–M4 确认点、预算约定、异常分支指引均落地；本次新增 Git Bash MSYS
路径转换注意事项，已同步 `.claude/skills` 与 `epcd-agent/skills` 两份副本。

**§7 OptimizationController**：启动输入三要素（describe 原样 schema / 2 组初始
候选 / max_rounds=3 预算）经 M2 确认后移交 ✅；循环体 run→poll→result→cost
回退→Store 回写在真实环境执行一轮 ✅；requestId 语义实测（iteration 前缀、
`final-<best-job-id>` 回带）✅；失败分类与暂停上报 `OPTIMIZATION_PAUSED`
（结构化 error + 退出码 1）在真实环境触发并被编排层正确消费 ✅；取消/中断/
改目标分支按测试策略由控制器单测覆盖，不重复真实演练。

**§8 里程碑机制**：M1（选型）/M2（目标+预算）/M3（写回，暂停上报形态）/M4
（最终仿真）四次确认全部以 AskUserQuestion 在真实流程发生，三选项语义齐备
（批准/修改后批准/终止）；M2 之前全程自主无打断；选项与理由留痕于本报告
（Store milestone 表写入按计划 3 由 SDK 接入层实现）。

**许可开通后复核清单**（本次受授权阻断未竟项）：

1. 真实 `targetValues`/`objectiveCost` 产生后 `cost_from_result` 回退链的
   形状复核（可能需要细化）。
2. 优化循环多轮收敛（本次仅真实执行 1 轮即暂停）。
3. `apply-result`/`config patch` 对 `device.parameters`、`simulation.sweeps`
   的持久化异常（applied/changed:true 但 digest 不变、读回空）是否修复。
4. §4.15 完整 RangeEM 产物（SNP/目标值 JSON/图表）与 `parametersUsed` 回填。
5. final run 写回生效链路（依赖第 3 项）。
