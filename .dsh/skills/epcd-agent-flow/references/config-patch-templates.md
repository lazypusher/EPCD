# EPCD config 配方（复制即用）

> 固化自 0.1.0 服务端实测 + backend/demo、backend/tests 的调用契约，避免每次重读 demo/test。
> 配套 SKILL.md「阶段流程 · 3 自动执行 / 4 结果确认 / 5 最终仿真」使用。

## 0. 总原则

- `epcd_config patch` 是 **JSON merge patch（RFC 7386）**：stdin 只提交要改的顶层 key，其余字段保留。
- **工具入参关键字是 `patch_obj`**（不是 `patch` 也不是 `path`）：stdin 对象形如
  `{"action":"patch","patch_obj":{...要改的顶层 key...}}`。传 `patch`/`path` 会依次报
  `USAGE`（unexpected keyword 'patch'）/ `ToolInputError`（config patch requires patch_obj）。
  后端 SDK 直接调用时同理：`epcd_config(ctx, action="patch", patch_obj=objectives_patch)`。
- `--if-match` 的 digest 由 Session Store 自动带上、成功后自动更新；**永远不手填 digest**。
- `id`/`digest`/`jobId`/`instanceId` 全部取自工具响应，绝不从路径或名字推测。

### 0.1 epcd_config 的四个 action（与源码 `tools/config.py` 逐字对齐）

| action | stdin 关键字 | 用途 |
| --- | --- | --- |
| `schema` | `{action:"schema", path?}` | 读**可写配置契约 schema**（`schemaVersion:"epcd-device-schema/v1"`），用于核对字段约束。**注意：不是 `schema/get`，也没有 `/` 分隔**。 |
| `get` | `{action:"get", path?}` | 读当前 config 值（`value` + `configDigest`），**并登记 digest** 到 Store。 |
| `patch` | `{action:"patch", patch_obj:{…}}` | JSON merge patch；`--if-match` 的 digest 自动带/自动更新。 |
| `apply-result` | `{action:"apply-result", job_id:"<jobId>"}` | 把 job 的最优几何写回当前 config；**stdin 关键字是 `job_id`**（snake_case，不是 `jobId`）。 |

> `epcd_config` 有两个来源、两套语义，极易混淆：
> - **本 skill 里 `action=get/set` 的 `epcd_config`** 是 DSH 宿主 MCP 工具，读/写「项目配置」（ssh/pkg/technology/workDirRoot），与后端工具无关。
> - **上表 + 后端的 `epcd_config`** 是 epcd-cli 的 config 工具（读/写器件 config 的 synthesisTargets/simulation）。

## 1. metrics 两套名字（别混用）

| 物理量 | objectives 写入（metric 显示名，最稳） | job result 读取/验收（短 key） |
| --- | --- | --- |
| 电感 | `Inductance Value(nH)`（也认 `inductance`） | `L` |
| 品质因数 | `Min Q Factor`（也认 `minQFactor`） | `Q` |
| 最大尺寸 | `Max Size(um)`（也认 `maxSize`） | `maxSize` |

写入用显示名，读取/判断达标用短 key。

## 2. objectives（synthesisTargets）

### point 目标（最常见）

```json
{"synthesisTargets": {
  "frequencyMode": "points",
  "customMetrics": [],
  "objectives": [
    {"metric":"Inductance Value(nH)","frequency":{"mode":"point","value":3,"unit":"GHz"},"comparison":"equal","targetValue":3,"unit":"-","weight":1},
    {"metric":"Min Q Factor","frequency":{"mode":"point","value":3,"unit":"GHz"},"comparison":"greater-than","targetValue":15,"unit":"-","weight":1},
    {"metric":"Max Size(um)","frequency":{"mode":"point","value":3,"unit":"GHz"},"comparison":"less-than","targetValue":300,"unit":"-","weight":1}
  ]
}}
```

字段约束（写错依次报 `INVALID_OBJECTIVE_TARGET` / `INVALID_OBJECTIVE_WEIGHT` / `INVALID_FREQUENCY`）：

- `frequency.value`、`targetValue` 是**数字**；`weight` **整数 1~10**；`unit` 常量 `"-"`。
- `comparison`：电感 `equal`（设计点）、Q `greater-than`、尺寸 `less-than`。

### range 目标

```json
{"synthesisTargets": {
  "frequencyMode": "range",
  "customMetrics": [],
  "objectives": [
    {"metric":"Inductance Value(nH)","frequency":{"mode":"range","minimum":2.7,"step":0.1,"maximum":3.3,"unit":"GHz"},"comparison":"equal","targetValue":3,"unit":"-","weight":1}
  ]
}}
```

range 目标须同时配 `simulation.sweeps` 覆盖同一带宽（见 §3）。

### `frequencyMode` 与 objective `frequency` 必须一致（撞过 `FREQUENCY_MODE_MISMATCH`）

`frequencyMode` 是 `synthesisTargets` 的**全局档位**，`points` / `range` 二选一，且
**所有 objective 的 `frequency.mode` 都必须匹配它**——只要有一条不一致，整包被拒：

```
error.type = FREQUENCY_MODE_MISMATCH
error.message = "Objective frequency conflicts with frequencyMode"
```

具体约束：

- `frequencyMode:"points"` → 每条 objective 的 `frequency` 必须是 `{"mode":"point","value":…,"unit":"GHz"}`。
- `frequencyMode:"range"` → 每条 objective 的 `frequency` 必须是
  `{"mode":"range","minimum":…,"step":…,"maximum":…,"unit":"GHz"}`（minimum < maximum、step > 0）。
  此时**不能**混入任何 `mode:"point"` 的 objective。

**实体案例（2nH@2.4GHz + Q>10@1-3GHz 电感）**：目标语义是「L 是 2.4GHz 设计点、Q 是 1-3GHz 全频段下限」，
一个点、一个段，无法在单一 `frequencyMode` 下原样表达。第一次提交写
`frequencyMode:"range"` + L 用 `{"mode":"point","value":2.4}`，服务端直接报
`FREQUENCY_MODE_MISMATCH`。

> 冲突判别经验：目标是「点指标（L@频点）」还是「段指标（Q@频段）」？哪个更强（更硬）就用它定
> `frequencyMode`，另一个指标要么收敛到单点、要么（若语义上是频段）用它自己的 range。
> 尺寸 `Max Size(um)` 与频率无关，range 模式下给不出单一频点时套 `frequencyMode` 同款 range 即可
> （它逐频点重复返回同一个 size 值，对 `less-than` 判定无影响）。

## 3. simulation.sweeps

- **point 目标**：默认 adaptive sweep 已覆盖目标频点，**不动**。
- **range 目标** / 需自定义扫频：

```json
{"simulation": {"sweeps": [
  {"enabled": true, "type": "adaptive", "start":{"value":1,"unit":"GHz"}, "stop":{"value":3,"unit":"GHz"}, "maximumStep":{"value":10,"unit":"MHz"}}
]}}
```

`solver.type:"em"` / `execution.mode:"local"` 保持默认；只改 `sweeps`。
可选 sweep 类型：`single`（`frequency:{value,unit}`）、`linear`（`start/stop/points`）、`adaptive`（`start/stop/maximumStep`）。

## 4. 写回 + 放宽目标的顺序（撞过 `JOB_CONFIG_CHANGED`）

`apply-result` 校验**当前 config digest == job 的 `configDigestUsed`**，不匹配报
`JOB_CONFIG_CHANGED: Device config changed after the job was created`。

stdin 写法（**apply-result 用 `job_id`，snake_case**）：

```text
{"action":"apply-result","job_id":"<best_job_id>"}
```

「放宽目标」与「写回几何」的**唯一正确顺序**：

1. `epcd_config apply-result(job_id=best_job_id)` —— **先写回几何**（此刻 digest 仍是优化时的 objectives）
2. `epcd_config patch` 放宽 objectives（如 L=2.8、Q≥13）
3. `epcd_run` 最终仿真（见 §5，**`task` 取值是 `simulation-evaluation`，不是 `final`**）

反了（先 patch objectives 再 apply-result）必失败；补救 = 把 objectives patch 回优化时值 →
apply-result → 再放宽。

## 5. 最终结果读取 / 验收

**`epcd_run` 的 `task` 白名单（源码 `tools/write.py` `_RUN_TASKS`）只有两个值：**
- `simulation-evaluation` —— 跑 EM 仿真并评估 objectives（最终仿真用它）
- `gds-generation` —— 只产 GDS

没有叫 `final` 的 task；skill 里的「final」是**流程语义**（写回后的最终仿真），
落到 `epcd_run` 时 **`task` 必须填 `simulation-evaluation`**（否则报 `unsupported run task: 'final'`）。

**`epcd_run` 的入参关键字**（stdin）：`task` / `request_id` / `input_obj`（候选信封，可选）/
`wait` / `timeout_seconds` / `use_if_match`。最终仿真调用：

```text
{"task":"simulation-evaluation","request_id":"final-<best-job-id>","wait":true}
```

`epcd_run` 返回**只含 `jobId`+`status`，不含结果**；必须再
`epcd_job action="result" job_id=<jobId>` 取正式结果：

- `targetValues[].satisfied` 每条都 `true` 才算达标；`actualValue`/`relativeDeviation` 做差距表。
- `warnings` 非空 = 仿真失败（如 `SIMULATION_FAILED`）；`status=="succeeded"` 不算真成功。
- `parametersUsed` 应等于已写回几何。
- 交付产物在 `artifacts[]`：`gds` / `snp`(S2P) / `layout-preview-image`(三视图) / `target-values`。

## 6. optimization_start 的 parameter_schema

**三种等价传法（按优先级，源码 `tools/read.py` + `platform/optimize_tools.py::_space_from_schema`）：**

1. **只传 `{"template_id":"<id>"}`（最简、推荐）** —— 内部自动 `describe()` 拿 `parameterSchema`。
2. 直接传 describe 返回的完整 `parameterSchema`（嵌套 `basic`/`opt`/`synth`）。
3. legacy 服务端无 parameterSchema 时，回退 `describe().addinParams`（面板参数堆，**非首选**）。

`initial_candidates` 启 1~2 组、只填 opt 参数名。

> 优化空间参数名 = 模板 `describe().parameterSchema.properties.opt.properties` 的 key
> （trackWidth / numOfTurns / innerRadius…），与 config 的 `device.parameters.opt` 的 key 一致。

### 6.1 `x-epcd-locked`：为什么有的 opt 参数不进 TPE 优化空间

优化空间 = `describe().parameterSchema` 里 **`properties.opt` 组中满足全部三条**的参数：

1. `x-epcd-enabled` 为 true（或未标，默认 enabled）；
2. `x-epcd-locked` **不为 true**（locked = 模板作者声明该参数为「设计固定值」，TPE 不搜）；
3. 有可用边界（`minimum`/`maximum`，或 `enum` 分类、或 step/`multipleOf`）。

`x-epcd-locked` / `x-epcd-enabled` 是 **epcd-cli 接口真实返回的模板元数据**，不是 agent 侧
擅自过滤，也不是 TPE 全局写死某参数名。当前实例：`system.inductor.simple_inductor` 的
`trackSpace` 返回 `x-epcd-locked:true`（实测 verify 2026-09），所以 TPE 只优化
trackWidth / numOfTurns / innerRadius 三项；`trackSpace` 保持默认值 2.0。

> 语义边界：opt 组**默认**应全部进优化空间；`x-epcd-locked:true` 是模板层面对「这个 opt
> 参数本轮不做自由变量」的声明，agent 尊重它即可。若某模板的 opt 参数异常地被标 locked
> 而业务上应该可优化，那是**模板元数据问题**，应修模板 describe 返回，而不是在 agent 侧
> 反向解锁（源码 `space.py::_is_locked` 不提供解锁旁路，也不该提供）。