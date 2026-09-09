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

「放宽目标」与「写回几何」的**唯一正确顺序**：

1. `epcd_config apply-result(job_id=best_job_id)` —— **先写回几何**（此刻 digest 仍是优化时的 objectives）
2. `epcd_config patch` 放宽 objectives（如 L=2.8、Q≥13）
3. `epcd_run final`

反了（先 patch objectives 再 apply-result）必失败；补救 = 把 objectives patch 回优化时值 →
apply-result → 再放宽。

## 5. 最终结果读取 / 验收

`epcd_run final` 返回**只含 `jobId`+`status`，不含结果**；必须再
`epcd_job action="result" job_id=<jobId>` 取正式结果：

- `targetValues[].satisfied` 每条都 `true` 才算达标；`actualValue`/`relativeDeviation` 做差距表。
- `warnings` 非空 = 仿真失败（如 `SIMULATION_FAILED`）；`status=="succeeded"` 不算真成功。
- `parametersUsed` 应等于已写回几何。
- 交付产物在 `artifacts[]`：`gds` / `snp`(S2P) / `layout-preview-image`(三视图) / `target-values`。

## 6. optimization_start 的 parameter_schema

直接传 `epcd_template describe` 返回的 `parameterSchema`（`properties.opt`=优化空间，
`x-epcd-locked:true` 的参数被排除，如 adv_simple_inductor 锁定 trackSpace）；或只传
`{"template_id":"<id>"}`（内部自动 describe、等价）。`initial_candidates` 启 1~2 组、只填 opt 参数名。

> 优化空间参数名 = config `device.parameters.opt` 的 key（trackWidth / numOfTurns / innerRadius…），
> 与 describe `parameterSchema.properties.opt.properties` 的 key 一致。