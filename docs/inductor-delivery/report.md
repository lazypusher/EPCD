# 电感设计交付报告

> **结论速览**：许可证已修复（emsolver 端到端可跑）。**服务器评分链路已打通**——2026-08-27
> 通过向顶层 `customMetrics` 注入 L/Q 导出公式，job 首次产出非空 `targetValues` 与
> `target-chart`（objectiveCost=2766.15，详见 §5 缺陷1「修复实证」）；但 EM 端口开路缺陷
> （§5 缺陷 2）使 L/Q 实际值为负，**指标达标仍被阻断**。交付形式为：
> **【真实配置 + 真实合成/仿真产物】 + 【真实打分输出】 + 【工程估算指标】**。

## 1. 器件信息

| 项 | 值 |
|---|---|
| 模板 | `system.inductor.simple_inductor`（Simple Inductor） |
| 实例 | `inductor_l1`（instanceId `20260820090223000`） |
| 工程 | `/home/zhubo/epcd-runs/inductor` |
| 工艺 | `<pkg>/tutorial/command_use/transmission_line/demo.ptxt` |

## 2. 设计目标（M2 批准 · 真实写入远端配置）

| 指标 | 目标 | 比较 | 频点 | 权重 |
|---|---|---|---|---|
| inductance | 2.1 nH | equal | 2.4 GHz | 1 |
| minQFactor | 8 | greater-than | 2.4 GHz | 1 |
| maxSize | 300 µm | less-than | 2.4 GHz | 1 |

扫频：adaptive **1–3 GHz，step 10 MHz**（顶层 `sweeps`）· 优化预算 max_rounds=3
configDigest（校验中）：`sha256:c26cbe0a1663deaf5a0997f16394234ee558a12a74884ad526ec1c089158578d`

## 3. 里程碑留痕（全部落库 session `inductor`）

- **M1** approved：simple_inductor / inductor_l1
- **M2** approved：上述目标 + 扫频 + max_rounds=3
- **M3** approved：按估算结果写回（先以假设结果执行，随后 license 修复后真跑核实 → 见 §5 平台缺陷）
- **M4** approved：最终真实仿真延后至评分缺陷修复（见 §6）

## 4. 真实交付产物

| 产物 | 说明 | 本地 |
|---|---|---|
| GDS 版图 | iteration-1 候选合成（真实，1204 B） | [SimpleInd.gds](SimpleInd.gds) |
| S 参数 | 探针 job `a6b32523…`（真实 201 频点 Touchstone，1–3GHz） | [graphs_s2p_probe.s2p](graphs_s2p_probe.s2p) |
| BestResult.txt | 该候选合成参数回执（真实） | [BestResult.txt](BestResult.txt) |
| 服务器打分结果 | **`{"targetValues": [], "objectiveCost": 0.0}`**（见 §5 缺陷 1） | [target-values_server.json](target-values_server.json) |
| manifest（迭代/探针） | 产物清单 | [manifest.json](manifest.json) / [manifest-probe.json](manifest-probe.json) |
| 版图预览（俯视/3D/侧视） | server-update-test-1 产物（真实，2026-08-21 接口更新后新增类型） | [previews/preview_top.png](previews/preview_top.png) / [preview_iso.png](previews/preview_iso.png) / [preview_side.png](previews/preview_side.png) |
| publication GDS（参数命名） | `SimpleInd__p__10_3_3_50.gds`（真实，1218 B，接口更新后新增出版目录） | [previews/SimpleInd__p__10_3_3_50.gds](previews/SimpleInd__p__10_3_3_50.gds) |
| 样点 Touchstone | `graphs_sample.s2p`（真实，publication 产物） | [previews/graphs_sample.s2p](previews/graphs_sample.s2p) |
| **打分结果（2026-08-27 打通）** | cm-3：402 条 targetValues、objectiveCost 2766.15、actualValue L≈−14nH/Q≈−0.5（负值 = 缺陷 2 端口开路） | [previews/cm-20260827/target-values.json](previews/cm-20260827/target-values.json) |
| **打分图表（2026-08-27）** | target-chart.svg/.png（服务端首次产出 target-chart 类型） | [previews/cm-20260827/target-chart.png](previews/cm-20260827/target-chart.png) |
| **公式定义（2026-08-27 恢复）** | formula.json：`["L=Im(1/Y(1,1))/(2*pi*f)","Q=…","maxSize"]`（此前 `[]`） | [previews/cm-20260827/formula.json](previews/cm-20260827/formula.json) |

候选参数（已真实写回 apply-result）：**trackWidth 10 µm / trackSpace 3 µm / numOfTurns 3 / innerRadius 50 µm**

## 5. 平台侧发现（证据充分，已复现）

**缺陷 1 — 服务器不做目标评分**：配置已含 3 个 synthesisTargets（多次验证 get/schema 可见），
但所有 succeeded job 的 `result.targetValues` 恒为 `[]`、`objectiveCost` 恒为 `0.0`，
且从不产出设计文档承诺的 `objective-values`/`objective-chart` 产物类型。
探针 job（`a6b32523…`）与迭代 job（`reopt-1`）的 target-values 字节级相同（sha256 `714907cb…`）。
→ 违反 release §4.12 契约（应含每目标 actualValue/relativeDeviation/satisfied/objectiveCost）。
另：objective 的 frequency 被服务器规范化成其自有字段 `freq`（demo 契约用 `value`/`unit`），
打分代码无法解析，与空 targetValues 自洽。
**已排除「缺仿真设置」假设（实证 2026-08-21）**：配置已处于仿真设置齐全状态 —— solver/execution 为 P0 默认
`em`/`Local`，扫频顶层 `sweeps`（1–3GHz/10MHz adaptive）已持久化生效（digest 变化 + 回读一致 +
EM 命令行带 `--multiSweep`）；release §4.10 实测校正亦确认 `simulation.sweeps` 对象形状不持久化、
顶层 `sweeps` 是唯一有效路径且与 `simulation` 无关。此前 reopt-1 / probe-tv 均在该齐全状态下运行仍恒空；
2026-08-21 新增**干净 probe `simcfg-1`**（jobId `19260c9f…`：新 request-id、无缓存、`status=succeeded`、
无 warnings）**仍 `targetValues:[]`、`objectiveCost:null`**。故该缺陷根因在服务端打分
（frequency `freq` 规范化不匹配），与客户端配置写法无关。**2026-08-21 服务器端已更新
run / job get / job result 三个接口**（补回 `configDigestUsed`/`technologyDigestUsed`/`durationSeconds`
元数据契约字段、新增 gtxt/layout-preview-image/gtxt-scene 产物与 `publication` 出版目录），
实测新 job `server-update-test-1`（`bd8eccb3…`，24.0s、无 warnings）**目标评分仍恒空、stub sha 未变**
（`714907cb…`），缺陷 1 未修复、独立于 job 接口层。

**2026-08-26 服务器端再次更新 → 根因定位到「指标导出公式缺失」**（job `reverify-1`=`394da71a…`）：
scoring 环节本次给出确定性警告 `TARGET_VALUES_EMPTY`（"formula.json parsed but no metric
matched calcItems; formulaKeys=[] calcItemKeys=[]"）。校验 `inductor_l1/synthesis/formula.json`：
S 参数（graphs.s2p）与 201 频点数据齐全，但 **`"formula":[]`**（无 S↔L/Q 导出公式）、config
`customMetrics:[]`、模板 describe 亦不再下发 builtInMetrics → **服务端无可计算的指标项**，
是空 targetValues 的直接成因（此前推测的 frequency `freq` 规范化问题为次因，主因是无指标公式）。
产物目录同时迁移为 `<device>/.epcd-cli/runs/<job>/`。
**2026-08-21 服务器端二次通知（job result 已可返回 targetValues）复核**：全新 job
score-verify-1（`b85335e5…`）/ score-verify-2（`9c9f065e…`，重写 synthesisTargets 后）同样
`succeeded`、无 warnings、`targetValues` 仍空。run.log 已新增打分表头
`[RESULT] 0 Width(um)…Freq(GHz) Score`，但 **0 行结果**（EM `Range EM With Initial success!`
但无 Score 数据行）→ 打分缺 actualValue 输入，与缺陷 2 自洽：**打分接口修复 ≠ 有分可打**，
根因在求解器未产出频点结果行（EM 端口模型）。

**2026-08-27 修复实证 — customMetrics 注入后打分真正产出（缺陷 1 打通）**：向**顶层**
`/customMetrics` 注入 L/Q 导出公式（`inductance=Im(Z(1,1))/(2*3.14159*2.4e9)`、
`minQFactor=Im(Z(1,1))/Re(Z(1,1))`，target/unit 填数值以绕过 epcdopt 固定位 float 解析，
§2.6 可复现）。全新 job `cm-3`（`fe00a15b…`，succeeded、无 warnings、23.0s）：
- `targetValues` **首次非空**（402 条 = 201 频点 1–3 GHz × L/Q）
- `formula.json` 恢复 `["L=Im(1/Y(1,1))/(2*pi*f)","Q=…","maxSize"]`
- `objectiveCost=2766.15`（此前恒 0.0/None）
- `target-values.json` sha256 `3930d2c0…`（152,190 B 实际数据 vs 旧 stub `714907cb…` 48 B）
- artifacts 新增 `target-values` + `target-chart`(svg/png)
- 产物本地归档 [previews/cm-20260827/](previews/cm-20260827/)

但 `actualValue` 为负（L@2.4G≈−14.09nH，Q≈−0.50）→ `satisfied=false`。负值源于
`Im(1/Y(1,1))/(2*pi*f)` 中 EM 端口开路（Im(Z11)<0，容性）→ **打分链路本身可用，指标达标仍由
缺陷 2 阻断**。缺陷 1 根因收敛为「模板 describe 不再下发内置公式 + 客户端此前未注入」——
非打分代码缺陷，注入自定义公式即可激活服务端 scoring。

**缺陷 2 — EM 端口模型近乎开路**：对真实 s2p 做全频段（1–3GHz）差分阻抗提取，
得到的等效阻抗**在所有频点均为容性**（2.4GHz：Z≈345−198j Ω，等效 L≈−13 nH），
`|S21|≈0.017–0.033`（约 −30 dB，随频率缓慢上升 = 跨 gap 寄生电容）。
即两端口之间没有经线圈的感性传输路径 —— pin 未连通线圈端或缺少参考回路，
且 run.log 有 `layer initialized with invalid valueIndex…` 层级告警。

**根因裁定（2026-08-31 终审：A/B 工艺文件对照实验实锤 = demo.ptxt 工艺损耗/衬底参数，非缺 ref、非断链）**：
为上证以**工艺文件为唯一变量**（其余配置/目标/公式/优化器入参字节一致）各跑 3 轮 optimization
（session `inductor`=原始 demo.ptxt vs session `ctl-rev`=demo_revised.ptxt，
见 [ptxt-ab-verify-20260831.md](ptxt-ab-verify-20260831.md)）：
- **A 臂（原始）**：tw10/ts3/nt3/ir50 → L@2.4G **−14.09nH**、Q **−0.50**，cost 2766；3 轮 L/Q 恒负、无任何满足。
- **B 臂（修订）**：同候选项 → L@2.4G **+1.749nH**、Q **+10.67（≥8 达标）**，cost 11.85；3 轮 Q 全部 satisfied，L 最近 1.75nH（目标 2.1）。
- 修订差异（**未加任何 ref/ground**）：`substrate σ 10S/m→0.0001S/m`、`metal1 sheet-R 22.5→0.02Ω/□`、`metal2 14.5→0.01Ω/□`、`via 2.0→0.01Ω`。

**结论（终审更正此前的"缺回流导体（一审）/结构连通性断链（二审）"判定）**：demo.ptxt 的
`substrate σ=10 S/m`（≈半导电衬底，等效紧贴线圈的有损回流/镜像层）叠加金属/via 极高损耗，
使端口全频段深容性（Im(Z)<0）→ L/Q 恒负；非引脚断链（若断链，仅换工艺参数不可能使 L 转正）。
修复 = 采用低衬底电导 + 低损耗金属叠层的电感工艺文件（修订版已实证有效）；
`demo_revised.ptxt` 已归档 `docs/template-library/inductor/`。对照实验全部真实命令/输出见
[ptxt-ab-verify-20260831.md](ptxt-ab-verify-20260831.md)。
**此前判定（已被终审更正，留档备查）**：一审"demo.ptxt 缺 ground/ref 回流导体故开路"——
修订版未加任何 ref 也修复，故该判定不成立、只是表象。二审"T1/T2 引脚与绕组结构连通性
断链"（基于对照组 C 环路端口 `P001=T1:T2` 零 ref 仍深容性，2026-08-28，见
[diagnosis-em-port-open-20260828.md](diagnosis-em-port-open-20260828.md)）——若引脚真断链，
仅换工艺参数不可能使 L 转正，故亦被本次 A/B 实证推翻（该工艺下环路端口呈深容性属工艺
引起的测量呈现，非连接断链）。

**已解决 — 许可证**：`NINECUBE_LICENSE_FILE=2048@192.168.20.109` 下 emsolver 正常
（此前 `Flexnet/Bitanswer license file does not exist`、exit 255 全链路失败）。
环境变量已持久化到远端 `~/.epcd-env`，agent CLI 前缀自动 source（[cli.py](../backend/src/epcd_agent/cli.py) `build_argv_prefix`）。

## 6. 指标（工程估算，非平台评分）

| 指标 | 目标 | 估算值 | 方法 |
|---|---|---|---|
| inductance | 2.1 nH | ≈2.2 nH（几何估算） | 3 圈 50 µm 矩形线圈解析估算 |
| minQFactor | 8 | 不可评估 | EM 端口开路（缺陷 2） |
| maxSize | ≤300 µm | ≈188 µm | 2·ir + 2·n·(tw+ts) + tw = 2·50+2·3·13+10 |

真实 L/Q 需平台修复缺陷 1/2 后用其 scoring 补全；此前「L≈2.15nH/Q≈11」为占位假设，勿当实测。

## 7. 后续动作

1. **上游修复缺陷 1**（评分读 `frequency.value`/`valueHz` 或修复规范化与打分不一致）。
2. **上游确认缺陷 2**（端口/pin 模型与 simple_inductor + demo.ptxt 的兼容性）。
3. 修复后：重跑 `optimization_start`（3 轮真实评分）→ M3 apply-result（真实 best）→
   M4 `epcd_run final` → 补全 SNP/目标值/图表交付。

验证命令速查（`backend/` 下）：`./.venv/Scripts/python -m epcd_agent.cli --db epcd-agent-session.sqlite3 --session inductor <tool>`，
stdin JSON 传参；远端 env 走 `~/.epcd-env`（自动 source）。