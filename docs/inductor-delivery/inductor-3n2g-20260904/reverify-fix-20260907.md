# 2026-09-07 复核：EM 评分目标已可由配置改写（服务端修复确认）

## 背景

交付时（2026-09-04）job targetValues 的 targetValue 恒为模板内置 **L=2.1/Q=8**，
synthesisTargets.objectives 与顶层 customMetrics 的 patch 均不生效（release §4.12 旧结论）。
用户怀疑服务端已修复，要求复核。

## 实证链（同几何 tw12/ts2/nt3.5/ir66，config-driven 运行，result 全部 succeeded 且无 warnings）

| # | 配置目标（synthesisTargets.objectives） | customMetrics | 评价出的 targetValue | 结论 |
|---|---|---|---|---|
| 1 | L=3.0/Q=10/maxSize=250 | synthesisTargets.customMetrics 留旧 | **3.0 / 10.0 / 250.0** | 目标已生效 |
| 2 | L=3.5/Q=12/maxSize=220（改值） | **清空**（干净配置） | **3.5 / 12.0 / 220.0** | 目标跟随配置，customMetrics 非必需 |
| 3 | L=3.0/Q=10/maxSize=250（恢复） | 清空 | **3.0 / 10.0 / 250.0**，全部 satisfied | 恢复原样 |

- Job：运行 1=`8bd10904…`、运行 2=`e4afcbe3…`、运行 3=`9f649a98…`（正式复跑）。
- 运行 3 产物已拉取至 `reverify-fixed/`，主目录 target-values.json / target-chart 亦已更新为修复后版本。
- `CUSTOM_METRIC_CONFLICT`：再往 customMetrics 填与内置同名（L/Q）的指标会报错 → 说明
  现在目标是模板族名直达，不再需要 customMetrics 注入 hack。

## 结论

**服务器端已修复**：EM 评分用的 `targetValue` 取配置 objectives；objective 的 `metric`
须用模板族名（`Inductance Value(nH)`→L、`Min Q Factor`→Q、`Max Size(um)`→size），
`targetValue` 写数值。验收口径：`targetValues[].targetValue == objectives[].targetValue`，
达成判断直接看 `satisfied`。若再出现恒=2.1/8，视为服务端回退。

## skill / 脚本同步（复盘任务伴随更新）

- `backend/skills/device-design-flow/SKILL.md`：M2 补"评分目标可由 objectives 直接生效、
  metric 用模板族名、customMetrics 仅放 /synthesisTargets 且勿与内置同名"；M5 补候选信封
  `epcd-candidate/v1`（手写 run 必带，否则静默跑默认几何）；M4 补验收口径。
- `scripts/collect_sim_data.py`：custom_metrics_patch 顶层注入改为 `/synthesisTargets/customMetrics`
  （服务端现只接受该位置），并入 objectives patch。
- `.claude/skills/device-design-flow/` 已与 epcd-agent 副本重新同步（此前严重发散）。
- 记忆 `epcd-run-candidate-envelope-scoring.md` 与 release §4.12 追加修复实证。