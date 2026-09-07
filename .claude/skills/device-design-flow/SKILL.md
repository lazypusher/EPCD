---
name: device-design-flow
description: EPCD 标准器件设计全流程编排。用户用自然语言发起元器件设计（如"设计一个电感"）时使用。批量 TPE 调优见本目录 references/batch-tpe-tuning.md。
---

# Device Design Flow

用户一句话发起设计后，按下列阶段推进。所有后端调用走单一 CLI 入口
（工作目录 `backend/`）：

    ./.venv/Scripts/python -m epcd_agent.cli --ssh zhubo@192.168.20.243 \
      --pkg /package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default \
      --db <本地会话db路径> --session <会话名> <tool>
    （工具参数 JSON 经 stdin 传入；stdout 单行 JSON；退出码 0 成功 / 1 业务失败 / 2 用法错误）

**Windows Git Bash 注意**：`--pkg /package/...` 这类 POSIX 路径作为 argv 会被 MSYS
转换成 Windows 路径，导致远端命令静默失败。每次调用必须加前缀 `MSYS_NO_PATHCONV=1`
（或改用 `EPCD_PKG_ROOT`/`EPCD_SSH_HOST` 环境变量，env 值不被转换）。stdin JSON 里的
路径不受影响。

## 阶段

1. **健康检查（自主）**：`epcd_health`。`data.status=="degraded"` 时向用户解释并停止。
2. **建工程（自主）**：`epcd_project` init，`{"action":"init","work_dir":"/home/zhubo/epcd-runs/<器件名>","technology":"/home/zhubo/demo_revised.ptxt"}`（工艺基线=demo_revised.ptxt，远程需先存在该文件）；随后 describe + validate。
3. **选型（自主 + M1 确认）**：**优先用本地对比表 `references/inductor-templates-comparison.md`**（已含 9 个电感/tcoil 模板的 opt 参数边界、synth 默认目标、指标族，不必再走 `epcd_template` list/describe）；仅当模板涉及本地表未覆盖的信息（如动态参数细节）才回退 `epcd_template` describe。向用户展示候选模板与关键指标，用 **AskUserQuestion 做 M1 确认**（选定模板 + 实例名；选项：批准/换一个/终止）。确认后 `epcd_device` add。
4. **目标与仿真配置（M2 确认）**：`epcd_config` schema/get 拿配置骨架与 digest；用 `parse_synth_targets` 语义（模板 synth 组 suffix+default）构造 synthesisTargets。**评分目标现已可由 objectives 直接生效**（2026-09-04 服务器端修复实证）：objective 的 `metric` 用模板族名（`Inductance Value(nH)`→L、`Min Q Factor`→Q、`Max Size(um)`→size），`targetValue` 写数值即作用于 EM 评价（旧 build 会忽略、恒取模板内置 L=2.1/Q=8，见 release §4.12 历史）。**不再需要 customMetrics 注入**；仅供真要自定义公式时放 `/synthesisTargets/customMetrics`（勿与内置同名，否则 `CUSTOM_METRIC_CONFLICT`）。**扫频按目标推导**（与批量采集同语义，objective/simulation 段可直接复用 `scripts/collect_mf.toml` 等配置模板）：
   - **point 目标 → 不配扫频**（实证：服务器在目标频点直接评价出 targetValues，无需 sweep）。
   - **修复后的目标达成判断（2026-09-04 实证，取代旧结论）**：评分目标已可由配置改写——EM 评价的 `targetValue` 现等于用户配置的 objectives（验证口径：`targetValues[].targetValue == objectives[].targetValue`，用一个 `/synthesisTargets/customMetrics:[]` 的干净配置即可确认；若又出现恒=模板内置 2.1/8，说明服务端回退，报告并停）。达成判断直接看 `satisfied` 与 `actualValue`，不再需要 actualValue 自查+手动补仿那套老路。
   - **range 目标 → 顶层 sweep 覆盖该 range**（start/stop/step 带单位字符串，如 `{"sweeps":[{"enabled":true,"type":"adaptive","start":"1GHz","stop":"3GHz","step":"10MHz","points":""}]}`）。
   - **模板 EM 必须 sweep 时（stack 家族）→ 最小覆盖带宽**：单频点 `±0.1GHz @0.1`；多频点 `(max-min)/(n-1)` 粗步进恰落各目标频点。**勿用默认 1~3GHz@10MHz**（数据多、仿真慢）。CLI 流程里 sweep patch 放 JSON **顶层** `{"sweeps":[...]}`（`simulation.sweeps` 不持久化）；批量脚本里对应 config 的 `[simulation].force_sweep`。
   把指标/频点/比较方式/权重/扫频/优化预算（默认 max_rounds=3、startup_trials=3）合并成一张 **AskUserQuestion M2 确认卡**。批准后 `epcd_config` patch 写回（`--if-match` 由工具自动注入，勿手写），objectives 与 sweeps 两个 patch 分开提交、每次用最新 digest。
5. **迭代优化（自主）**：`optimization_start`，stdin 传 `parameter_schema`（**不用 describe 原样**——describe 的 `opt.properties` 为空，会落入 22 维 addinParams 兜底空间（L/Q 恒定、无优化信号）。用 live `config schema` 的 `device.parameters.opt` 构造：`{"type":"object","properties":{"opt":{"properties":{名:{minimum,maximum,step,enabled}}}}},"template_id":<模板>`——**取全部 enabled、忽略 locked**（A/B 实证 locked 是实例/UI 状态、非仿真门；实现参考 `scripts/collect_sim_data.py` 的 `build_param_schema`））、`initial_candidates`（基于目标推理的 1~2 组起点）、预算。期间用户问进度 → `optimization_status`；喊停 → `optimization_cancel`。`OPTIMIZATION_PAUSED` 时读 `data.errors`/`category` 诊断并询问用户；**`succeeded`+`warnings`+空 targetValues = 仿真失败轮（无效参数组合），控制器现已按 FAIL 处理让 TPE 规避，不暂停**。

   **候选信封（2026-09-04 血泪实证）**：所有手动 `epcd_run` 候选（含优化器之外的手工补仿、对照验证），`input_obj` 必须带 `{"schemaVersion":"epcd-candidate/v1","parameters":{...}}` 信封；只传 `{"parameters":{...}}` 会被服务端**静默忽略**（`parametersUsed:{}`、跑默认几何 tw10/ts2/nt2.5/ir60）。优化控制器内部已带正确信封；脚本/手工补仿必须照此构造。
6. **写回（M3 确认）**：报告 best cost / 各指标达成情况（**AskUserQuestion M3**），批准后 `epcd_config` apply-result（jobId=best_job_id）。
7. **最终仿真（M4 确认）**：**AskUserQuestion M4** 批准后 `epcd_run` final：不带候选输入、`request_id="final-<best-job-id>"`（if-match 用写回后 digest，工具注入）。**修复后验收口径**：读最终 job 的 `targetValues`，核对每条 `targetValue` == 我们配置的 objectives 值（本轮实证：L=3.0/Q=10.0/size=250），`satisfied` 判断达标，`parametersUsed` 应写回几何（tw/ts/nt/ir）。
8. **交付**：`artifact_view`（带 fetch_dir）取最终 job 产物卡片；向用户汇报 GDS/版图/SNP/目标值与图表路径。

## 硬规则

- 里程碑 M1~M4 必须 AskUserQuestion 确认，三选项语义：批准 / 修改后批准（对话中改，重构 JSON 重新确认）/ 终止。每次确认的选项与理由在最终验收报告中留痕（Store milestone 表由计划 3 的 SDK 接入层写入）。
- id/digest/jobId 永远取自工具响应；绝不从路径或名字推测。
- `job result` 的 `status=="succeeded"` 不等于仿真成功：必须检查 `warnings`（如 `SIMULATION_FAILED`）与 `targetValues` 是否非空（release §4.12 校正）。
- 同一调用自纠上限 2 次；退出码语义见 release §2/§10。
- 候选提交必带 `epcd-candidate/v1` 信封，见阶段 5 详细说明（2026-09-04 实证，血泪教训）。
- 分支只看 `ok`/`error.type`/退出码；`error.message` 只给用户看。
- 预算：MVP 冒烟 max_rounds=3、startup_trials=3；**startup_trials 可由脚本按模板自动配置**（`references/tpe-settings.toml`，9 模板实测）；生产 max_rounds 由用户设定，推荐值见 `references/tpe-tuning-9template-20260903.md`（简单电感 ~10 轮、几何受限模板 stack 家族 ≥20 轮）；用户可覆盖。
