# 参数优化器（OptimizationController + optuna TPE）实测评估

> 评估时间：2026-08-27（评分通路打通之后）
> 环境：epcd-cli 0.1.0，真实 EM + 真实评分（customMetrics 注入后）

## 1. 结论速览

| 维度 | 结论 |
|---|---|
| cost 提取（cost_from_result） | ✅ 正确，实测提取顶层 `objectiveCost`，与手工 job 一致 |
| TPE 采样/初始候选 | ✅ 正确（enqueue 初始候选 + 建议后续点），确定性 seed |
| 闭环机制（提交→轮询→读结果→比较→选 best） | ✅ 完整跑通 2 轮，best 正确选中更低 cost 轮 |
| 输入源（parse_real_parameter_schema） | ~~❌ 断链~~ ✅ **P0 修复 + 真机实测通过**——空 opt schema 兜底 describe.addinParams，1 轮真实 EM+评分闭环成功 |
| 失败/暂停/取消 | ✅ 逻辑完备（连续失败 2 次暂停、无目标值暂停、跨进程 cancel） |

## 2. 实测证据

### 2.1 正向闭环（真实 EM + 真实评分，5 分钟完成两轮）

```
$ optimization_start（request_prefix=optv1, max_rounds=2, 2 组初始候选）
round 1  optv1-1  trackWidth10/trackSpace3/numOfTurns3/innerRadius50  cost=2766.16  succeeded
round 2  optv1-2  trackWidth12/trackSpace2.5/numOfTurns2.5/innerRadius40  cost=2376.18  succeeded
→ best_job_id=a7f2af74…, best_cost=2376.18, best_parameters={tw12,ts2.5,nt2.5,ir40}
```

验证点：
- **cost 正确提取**：round-1 的 `2766.157844` 与先前手工 cm-3 job（同参数）的 `2766.15296`
  几乎完全一致 → cost_from_result 的 `objectiveCost` 分支现已生效（评分打通前该分支恒 None 会暂停）。
- **TPE 正确比较**：best 选了 cost 更小的 round-2，best_job_id/best_parameters 都对。
- **幂等 request-id**：`optv1-1`/`optv1-2` 每次提交同一 requestId 会重连原 job（重跑安全）。

### 2.2 输入断链（真实 describe 空 opt 空间）

用真实服务器 describe 的 `parameterSchema`（`opt.properties={}`）调用 optimization_start：

```
error: {"type":"ToolInputError","message":"parameter schema yields no optimizable opt parameters"}
```

- 服务器现状：模板 describe 返回 `parameterSchema.properties.{basic,opt,synth}` 中
  **opt/synth 均为空对象 `{}`**；参数真实载体是 **`addinParams`**（一组面板描述，
  每个参数含 `jsonKeyStr`/`tagStr`/`defValue`/`value`/`min`/`max`/`stepValue`/
  `suffixStr`/`fieldType`/`valueType`/`enableWhole` 等，实测 `width`/`spacing` 等
  数值参数 min/max/step 齐全）。
- `parse_real_parameter_schema(schema)` 只读 `schema.properties.opt.properties` → 空
  → 无 spec → ToolInputError。
- 本地 describe 透传 cache（docs/template-library/inductor/cache.json）同样如此，
  确认非瞬时故障。

### 2.3 P0/P2 修复后验证（2026-08-27 下午）

```
$ 单测：pytest tests/test_space.py tests/test_platform_optimize.py → 19 passed
$ 全量：pytest tests/ → 126 passed（含 1 处过期断言修正：build_argv_prefix 现已带
  ~/.epcd-env source 段；无关功能）
$ 真机解析校验：空 opt schema + active-instance template_id → _space_from_schema
  解析出 22 个 spec（width/spacing/shape/pinDir/rotation/offset/pinWidth/pinExt …
  面板完整参数），unbounded=()
$ 真机闭环（纯 fallback 路径）：
  optimization_start{parameter_schema.opt.properties={}, initial_candidates=[], max_rounds=1}
  → round p0live-1 job=046a36ba… status=succeeded cost=2758.47 stop_reason=budget_rounds
```

- **修复内容**：`space.py` 新增 `parse_addin_params`（按 fieldType 0/3→数值、1→枚举、
  2/6→跳过、`visibleControlKey` 条件可见→跳过、`enableWhole`≠1→跳过、跨组去重、
  首个同名参数胜出）；`optimize_tools.py` 新增 `_space_or_raise` 在经典
  `opt.properties` 为空时经 active-instance `template_id` 调 `describe()` 走 addinParams
  兜底，仍空才报错；`normalize_candidate` 新增 step 网格对齐（P2）。
- **已知取舍**：addinParams 是整面板，不是旧 `opt.properties` 那种精选可优化集——
  兜底空间达 22 维（含 guard-ring/fill 噪音参数）。对 ≤3 轮的冒烟够用；真实量产优化
  仍应显式传精选 `opt.properties`（optv1 已验证服务器仍接受）。建议后续加
  「主面板 group 0」或 allowlist 收窄。

### 2.4 P4 · TPE 启动期修复（2026-08-31）

optuna TPE 默认 `n_startup_trials=10`：前 10 轮为固定种子纯随机游走、**不消费观测 cost**。
A/B 工艺对照实验暴露其影响——两臂第 3 轮 TPE 建议出完全相同的参数（RNG 消费序列一致），
B 臂 cost 出现"递增"假象。`controller.py` 设 `_TPE_STARTUP_TRIALS=3`（第 4 轮起 EI 引导），
新增回归测试，全量单测 **127 passed**。10 轮现场验证见
[ptxt-ab-verify-20260831.md §9](ptxt-ab-verify-20260831.md)。

## 3. 改进方案（按优先级）

### P0 · 适配 addinParams 为优化空间唯一输入源
`parse_real_parameter_schema` 增加对 `addinParams` 的解析路径：
- 遍历每个面板 group 的参数条目，用 `jsonKeyStr` 作参数名；
- `fieldType` 决定类型：`0`（数值，用 min/max/stepValue 构造 float/int spec）、
  `1`（枚举，defValue 逗号分隔 → categorical）、`6`/`8`（图层多选/开关等 → 排除或定值）；
- `enableWhole=="1"` 才纳入优化空间（用户层面 enableWhole 为引入开关）；
- `suffixStr` 含单位提示（非必要）；`tagStr` 作显示别名。
- 向后兼容：若 `parameterSchema.opt.properties` 仍非空，优先用旧路径（防回归）。

### P1 · schema 优先取 describe 的 parameterSchema；addinParams 兜底
optimize_tools.optimization_start 在 space.specs 为空时，fallback 用 describe 响应的
`addinParams` 再解析一次；仍空才报错（报错文案带上「模板未提供可优化参数」而非通用
「yields no optimizable opt parameters」，便于对上游定位）。

### P2 · 候选非数值归一（低）
normalize_candidate 对 float 只做 clip，未按 step 取整。若 optuna/初始候选写了
step 网格外的值（如 numOfTurns=3.17），服务端仍会接受但偏离离散语义。
建议按 step 对齐（round to nearest step，再 clip）。

### P3 · 目标值可达性提示（当 EM 端口模型修复后可激活）
已知缺陷 2（EM 端口开路）致 L/Q 为负、cost 恒高。可在 report 增加
`cost_scale_hint`（如「所有目标 actualValue 为负，疑似端口/参考问题」），
避免把「优化不进展」误判为采样器问题。

## 4. 结论

优化器**机制实现正确、健康**，与真实评分已端到端打通（评分未通时它会正确暂停并
报 scoring-unavailable，而非产生垃圾结果）。唯一硬缺陷（输入源断链）已通过 P0
修复**并用真机 1 轮闭环验证**：empty opt schema 现在会走 describe.addinParams 兜底
并成功驱动真实 EM + 评分（p0live-1，cost 2758.47），带单测的修复全量 126 用例通过。
P0 兜底空间为整面板（22 维）属已知取舍，量产建议显式传精选 opt.properties；P3
目标可达性提示待 EM 端口模型（缺陷 2）修复后可激活。

## 5. 复现

```bash
# 正向闭环
cat epcd-agent/opt_v1_fixture.json | python -m epcd_agent.cli ... optimization_start
# 输入断链（真实 describe 形状）
cat epcd-agent/opt_real_empty_test.json | python -m epcd_agent.cli ... optimization_start
```

## 6. 关联产物

- 本评估依赖 customMetrics 打分通路（2026-08-27 打通），见 docs/inductor-delivery/report.md §5。
- 真实 describe 快照：docs/template-library/inductor/cache.json（addinParams 含完整参数元数据）。