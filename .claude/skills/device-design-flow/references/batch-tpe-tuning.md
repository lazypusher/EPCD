# 批量 TPE 调优（collect_sim_data.py）

> 独立于【device-design-flow】设计流程。用途：批量采集优化器每轮真实仿真数据（参数→cost→L/Q@目标频点），基于大量数据调优 `startup_trials`/`max_rounds` 等 TPE 设置。
> 位置：本 skill 目录内自包含 —— 脚本 `../scripts/collect_sim_data.py` + 配置模板同目录 + 结论参考 `tpe-tuning-9template-20260903.md`。

## 调用

```bash
# 工作目录 backend/；Git Bash 必须 MSYS_NO_PATHCONV=1
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python \
  skills/device-design-flow/scripts/collect_sim_data.py \
  --config skills/device-design-flow/scripts/collect_mf.toml \
  --template 1                # config [[templates]] 的编号或名
```

- `[optimizer].startup_trials` 通常留空：**脚本按模板自动配置**最优值（读 `references/tpe-settings.toml`，9 模板实测）。需批量校验时显式设数组 `[3,5,10]`。
- **TPE 设置解析优先级**：`--startup-trials 3,5,10` > config `[optimizer].startup_trials` > `references/tpe-settings.toml`（按 templateId 自动）> 默认 `[3]`；`max_rounds` 由用户设定（`[optimizer].max_rounds` 或 `--max-rounds`，tpe-settings 的 max_rounds 仅作推荐打印）。
- Flags：`--startup-trials a,b`  `--tpe-settings <file>`(换设置源；`--no-tpe-settings` 关闭自动)  `--only N`  `--max-rounds N`  `--max-wall-seconds`  `--no-cleanup`  `--render-only <分组目录>`。
- 输出：`[output].out_dir` 下按 objectives hash 分组；`results.md` 每配置一个子表 + 每配置独立 `<tag>.csv`（单表头：参数→L/Q(带单位/真实目标)→cost）。

## 配置模板（本目录 scripts/）

| 模板 | 适用指标族 / 模板 | 频点 | sweep |
|---|---|---|---|
| `collect.toml` | Inductance/MinQ：simple/adv/bow/stack 通用底板 | 内置 @2.5 | point 无 |
| `collect_mf.toml` | Inductance/MinQ：simple/adv | 1.5/2.0/2.5/3.0GHz | force_sweep 1.5-3@0.5 |
| `collect_mf_ld.toml` | Ld/Qd：differential/bow/stack 族 | 同上 | force_sweep |
| `collect_mf_tcoil.toml` | tcoil 类（`category="tcoil"`）| 同上 | force_sweep |
| `collect_stack.toml` | stack 强制最小 sweep 示例 | 单频 | force_sweep |

## 语义（与设计流程共享的实证结论）

- **point 目标 → 默认不配 sweep**；服务器在目标频点直接评价出 targetValues。
- **range 目标 → 顶层 sweep 覆盖该 range**。
- **模板 EM 必须 sweep 时（stack 家族）→ `[simulation].force_sweep = true`**：自动推导最小覆盖带宽（单频 ±0.1GHz；多频 `(max-min)/(n-1)` 粗步进恰落各目标频点），勿用默认 1~3GHz@10MHz（数据多、仿真慢）。
- **`category` 必须写在 config 顶层**（`[server]` 内是 `server.category`，顶层读到 None 会默认 inductor）。
- 参数单位：trackWidth/trackSpace/innerRadius = um；numOfTurns 无量纲。
- `parameters` 取 live `config schema` 的 `device.parameters.opt`（全部 enabled、**忽略 locked**——A/B 实证 locked 非仿真门），实现见 `build_param_schema`。

## TPE 设置结论（9 模板 540 轮实测）

见 `tpe-tuning-9template-20260903.md`。要点：**无全局最优，按模板设置**；st10（optuna 默认）多数模板次优；几何受限模板（stack 家族）需 st10+≥20 轮。

## 工程侧修复记录

- 控制器：`succeeded` + warnings + 空 targetValues = sim-failed 轮（FAIL trial 让 TPE 规避），不再误判 scoring-unavailable 暂停。
- point 无 sweep 对 simple/adv/bow/tcoil 有效；stack 族必须 sweep；differential 族含首轮即负。