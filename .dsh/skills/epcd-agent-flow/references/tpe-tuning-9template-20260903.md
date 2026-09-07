# TPE 优化器参数完备性实验分析（9 电感/变压器模板 × 多频点）

> 实验时间：2026-09-03
> 环境：epcd-cli 0.1.0，demo_revised.ptxt，4 参数 TPE 空间（trackWidth/trackSpace/numOfTurns/innerRadius）
> objectives：Inductance(L) =2.1nH + Min Q(Q) >8 @ 1.5/2.0/2.5/3.0 GHz（4 频点），Max Size 1 条；force_sweep 最小带宽 1.5~3GHz @0.5（恰好 4 目标点）
> 每模板 × startup_trials[3,5,10] × 20 轮，9 模板共 540 轮真实 EM（两批：2026-09-03 前 4 模板 + 补 5 模板）

## 1. 结果总表（9 模板）

| 模板 | 指标族 | st=3 | st=5 | st=10 | 首负轮(3/5/10) | ok(3/5/10) | 最优 |
|---|---|---|---|---|---|---|---|
| simple_inductor | Inductance/Q | **−1.417** | −1.383 | −0.976 | 6/13/10 | 20/20 全 | **3** |
| adv_simple_inductor | Inductance/Q | −1.347 | **−2.348** | −1.235 | 6/9/10 | 全 | **5** |
| bowtie_inductor | Ld/Qd | **−0.809** | −0.552 | −0.392 | 4/6/11 | 全 | **3** |
| stack_inductor | Ld/Qd | 4.206 | 1.148 | **0.809** | — | 5/6/10 | **10** |
| differential_inductor | Ld/Qd | −2.239 | −2.174 | **−2.299** | 1/1/1 | 全 | **10**（margin 0.06）|
| differential_inductor_step | Ld/Qd | −2.239 | −2.174 | **−2.286** | 1/1/1 | 全 | **10**（margin 0.05）|
| stack_inductor_overlapped | Ld/Qd | −3.878 | −3.770 | **−4.083** | 1/1/1 | 全 | **10** |
| tcoil_inductor_oct | Inductance/Q | −0.975 | −1.058 | **−1.082** | 6/13/10 | 全 | **10**（margin 0.1）|
| tcoil_inductor_rec | Inductance/Q | **3.494** | 3.622 | 3.772 | — | 全 | **3**（全正 cost）|

## 2. 结论（9 模板全量）：按模板单独设置，不存在单一全局最优

1. **无全局最优 startup_trials**：st3 赢 3 个（simple/bowtie/tcoil_rec）、st5 赢 1 个（adv，且 −2.35 vs −1.35 差距大）、st10 赢 5 个（stack 家族/differential 家族/tcoil_oct，其中 differential 家族 margin 很小≈0.05-0.06）。
2. **st10（optuna 默认）仍是多数模板的次优/最差**：simple/bow/adv/tcoil_rec 上明显劣于各自的 st3/st5。
3. **收敛速度恒随 startup 单调变慢**（simple/bow/tcoil：首负轮 st3<st5<st10）。
4. **"困难"模板**（stack/tcoil_rec 全正 cost；stack 有效几何域小仅 5-10/20 轮成功）需更大的探索预算 st10 且可能需重新审定目标可达性。

## 3. 每模板推荐配置

| 模板 | startup | max_rounds | 备注 |
|---|---|---|---|
| simple_inductor | 3 | ~10 | r8 达最优 |
| adv_simple_inductor | 5 | ~12 | st5 显著更优 |
| bowtie_inductor | 3 | ~8 | r4 即最优，EM 慢 ~45s/轮 |
| stack_inductor | 10 | 20+ | 必须 force_sweep；有效域小、全正 cost |
| differential_inductor | 10**（或 3） | ~15 | st10 仅微优 0.06，等价可取 3 |
| differential_inductor_step | 10**（或 3） | ~15 | 同左 |
| stack_inductor_overlapped | 10 | ~15 | st10 优 0.2，EM 慢（~110s/轮，37 分钟/档）|
| tcoil_inductor_oct | 10**（或 5） | ~15 | st10 微优 0.1，等价可取 5 |
| tcoil_inductor_rec | 3 | ~10 | 全正 cost（目标可达性疑虑）|

**统一建议**：默认 `startup_trials=3` + 按困难度上调（stack 家族/几何受限模板 → 10）；`max_rounds` 按模板收敛轮次收紧（简单类 ~10，困难类 ≥20）。**st10 不应作全局默认**。

## 4. 工程侧发现（脚本/控制器）

- **stack 类模板必须 sweep**：point 目标无 sweep 时 EM succeeded 但 targetValues 为空 → 控制器曾误判 scoring-unavailable 暂停。现已修复：`succeeded`+warnings+空 targetValues = 仿真失败轮（FAIL trial），TPE 学习规避（详见 controller._read_cost）。配合 `[simulation].force_sweep=true` 按目标频点推导最小带宽。
- **单位**：trackWidth/trackSpace/innerRadius 为 um。
- 多频点后 objectiveCost 为 4 频点上 L/Q 偏离之和——更能反映宽带行为，难度也更高（正负区间扩大）。

## 5. 关联产物

- 数据：`epcd-agent/collect-out-mf-{sim,adv,bow,stk,diff,dst,sov,tco-oct,tco-rec}/objectives_{0056e444,9d37bf9d}/{results.md, <tag>.csv}`
- 配置模板：`scripts/collect_mf.toml`（Inductance/MinQ 族）、`scripts/collect_mf_ld.toml`（Ld/Qd 族）、`scripts/collect_mf_tcoil.toml`（tcoil，category=tcoil；tcoil 模板是 Inductance/MinQ 指标但类别不同）、`scripts/collect_stack.toml`（stack 单频示例）
- 工程修复：**category 须在 config 顶层**（`[server]` 内不算顶层，`cfg.get("category")` 得 None → 默认 inductor → tcoil 校验失败）。main 已兼容两处。
- 相关记忆：[[epcd-collect-sim-data]]、[[epcd-license-blocker]]、[[epcd-process-baseline]]