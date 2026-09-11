# EPCD CLI 全流程操作手册（远端 SSH 复核）

> 覆盖 `epcd-cli 0.1.0` 全部公开接口；按「SSH 远端手敲」视角编写，附本地 agent wrapper 映射。
> 所有输出均为 epcd-response envelope：`{"schemaVersion":"epcd-response/v1","ok":Bool,"requestId":…,"data":…,"errors":[…]}`；
> 退出码 **0**=成功 / **1**=业务失败 / **2**=用法错误。加 `--format text` 可输出 YAML。

## 0. 环境准备（每次 ssh 会话开头）

```bash
# 登录远端仿真机
ssh zhubo@192.168.20.243

# 包根（含 user.bashrc.ePCD、ehouse/64bit/emsolver 等）
PKG=/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default
# 工程/实例/模板（本会话真实值，通用时替换）
PROJ=/home/zhubo/epcd-runs/inductor
INST=20260820090223000
TID=system.inductor.simple_inductor

# 环境链：pkg 环境 + 用户级 dotfile（NINECUBE_LICENSE_FILE 等）
source $PKG/user.bashrc.ePCD >/dev/null 2>&1
[ -f ~/.epcd-env ] && source ~/.epcd-env
# 验证：epcd-cli 在 PATH 上，emsolver 有 license
epcd-cli version
emsolver --version
```

## 1. 命令面总览（远端子命令树，来自 `epcd-cli --help`）

```
epcd-cli [--format {json,text}]
├── version           版本与协议
├── health            运行时环境体检
├── device-template
│   ├── list          [--category CATEGORY]
│   └── describe      <template_id> [--project]
├── project
│   ├── init          --work-dir D --technology T [--password P]
│   ├── describe      [--project]
│   ├── validate      [--project]
│   └── device
│       ├── list      [--project]
│       ├── add       --template-id ID [--name NAME] [--project]
│       ├── describe  --instance-id ID [--project]
│       └── remove    --instance-id ID [--project]
├── config
│   ├── schema        --instance-id ID [--path P] [--project]
│   ├── get           --instance-id ID [--path P] [--project]
│   ├── patch         --instance-id ID --input - [--if-match DIGEST] [--project]
│   └── apply-result  --instance-id ID --job-id JID [--project]
├── formula
│   └── validate      --input -
├── run               --instance-id ID --task {gds-generation,simulation-evaluation}
│                     [--input -] [--if-match DIGEST] [--request-id RID] [--wait|--timeout S]
└── job
    ├── get           --id JID
    ├── result        --id JID
    └── cancel        --id JID
```

- `--project` 默认 = 当前目录；除 project/device-template 外**必须**给 `--instance-id`。
- `--input -` = 从 stdin 读一个 JSON 对象（管道传入）；patch/run/formula 都这样用。

## 2. 逐接口手册

### 2.1 version / health（健康检查）
```bash
epcd-cli version                                   # {version:0.1.0, responseSchemaVersion, python}
epcd-cli health
```
`health` 关键字段：`status:ok`、`runtime.mode:private-api`、`modules[]`（project/param/tech `available:true`）、
`missingModules:[]`、`stateHome{writable:true}`。`status != ok` 时先修环境再继续。
> agent 映射：`epcd_health`（直接封装 version+health）。

### 2.2 建工程 project init / describe / validate
```bash
epcd-cli project init \
  --work-dir /home/zhubo/epcd-runs/inductor \
  --technology $PKG/tutorial/command_use/transmission_line/demo.ptxt
epcd-cli project describe --project $PROJ
epcd-cli project validate --project $PROJ
```
- init 返回 `path`（或 `project`）、`libName`、`technologyDigest`（hard rule：id/digest 取自响应，勿猜测）。
- init 幂等不友好：已存在则报错；describe/validate 可重复跑。
> agent 映射：`epcd_project`（action init/describe/validate；store 自动记账）。

### 2.3 选型 device-template list / describe
```bash
epcd-cli device-template list --category inductor
epcd-cli device-template describe system.inductor.simple_inductor --project $PROJ
```
describe 载荷三组：`basic`（层/形状/过孔）、`opt`（可优化参数 min/max/step/enabled）、`synth`（合成目标 suffix: Equal/Greater/Less），外加 `builtInMetrics`（key/default/weight/formula）。
> 本地缓存：`docs/template-library/inductor/cache.json`（9 模板原始载荷）+ comparison.md，刷新脚本 `backend/scripts/template_cache.py`。
> agent 映射：`epcd_template`（action list/describe）。

### 2.4 器件 project device add / list / describe / remove
```bash
epcd-cli project device add --template-id $TID --name inductor_l1 --project $PROJ
# → data.instanceId（如 20260820090223000），后续 INST 用它
epcd-cli project device list --project $PROJ
epcd-cli project device describe --instance-id $INST --project $PROJ
epcd-cli project device remove --instance-id $INST --project $PROJ   # 慎用，删除不可逆
```
> agent 映射：`epcd_device`（add 自动 set active instance）。

### 2.5 配置 config schema / get / patch / apply-result
```bash
# schema：可写配置骨架（注意 --path 是 JSON Pointer，不是 JSON Schema 路径）
epcd-cli config schema --instance-id $INST --project $PROJ [--path /sweeps]

# get：读规范化配置，响应含 configDigest（乐观锁基准）
epcd-cli config get --instance-id $INST --project $PROJ [--path /]
epcd-cli config get --instance-id $INST --project $PROJ --path /synthesisTargets

# patch：原子替换，必须带最新 digest；patch 前先 get 刷新
epcd-cli config get --instance-id $INST --project $PROJ >/dev/null   # 刷新 digest
echo '{"synthesisTargets":{"frequencyMode":"points","customMetrics":[],"objectives":[
  {"metric":"inductance","frequency":{"mode":"point","value":2.4,"unit":"GHz"},"comparison":"equal","targetValue":2.1,"unit":"nH","weight":1},
  {"metric":"minQFactor","frequency":{"mode":"point","value":2.4,"unit":"GHz"},"comparison":"greater-than","targetValue":8,"unit":"","weight":1},
  {"metric":"maxSize","frequency":{"mode":"point","value":2.4,"unit":"GHz"},"comparison":"less-than","targetValue":300,"unit":"um","weight":1}]}}' \
  | epcd-cli config patch --instance-id $INST --project $PROJ --input - --if-match sha256:……

# 扫频写顶层 sweeps（放 simulation.sweeps 下不持久化；start/stop 必须是带单位字符串）
echo '{"sweeps":[{"enabled":true,"type":"adaptive","start":"1GHz","stop":"3GHz","step":"10MHz","points":""}]}' \
  | epcd-cli config patch --instance-id $INST --project $PROJ --input - --if-match sha256:……

# apply-result：把 succeeded job 的器件参数写回；同样自动更新 digest
epcd-cli config apply-result --instance-id $INST --project $PROJ --job-id <job-id>
```
注意：
- digest 冲突 → `CONFIG_DIGEST_MISMATCH`；agent 工具自动 get 刷新重试一次。
- **实测**：服务器会把 objectives.frequency 规范化为自有字段 `freq`（见 §5 缺陷1）。
> agent 映射：`epcd_config`（action schema/get/patch/apply-result；`--if-match` 自动注入不提）。

### 2.5.1 仿真设置（release §4.10 校正，2026-08-20 实测）

P0 只开放 **EM / Local|LSF / subCommand / 扫频** 四类，`simulation` 段是配置里唯一的仿真设置入口，但**该 build 的有效持久化路径只有顶层 `sweeps`**：

```json
{ "simulation": {
    "solver":    { "type": "em" },
    "execution": { "mode": "local" },
    "sweeps":    []            /* 字典形状写这里不会持久化（见下） */ } }
```

- **solver / execution**：默认值 `em` / `Local` 已符合 P0，**一般无需 patch**；LSF 才需要写 `execution.mode: "lsf"` + `subCommand`。
- **扫频（关键）**：对象形状 `{"start":{"value":1,"unit":"GHz"},"stop":{...},"maximumStep":{...}}` 写进 `simulation.sweeps` 实测 **不持久化** —— patch 返回 `changed:true` 但 digest 不变、回读 sweeps 仍为空；且字典 start/stop 会被服务端强转成 Python repr 字符串而损坏。**唯一持久化路径 = 配置顶层 `sweeps` 键、与 `simulation` 平级、标量带单位字符串**（见上方 §2.5 命令）。持久化成功的判据：digest 变化 + 回读一致 + EM 命令行出现 `--multiSweep=1.0:0.01:3.0`。
- `config schema --path /sweeps` 在本 build 返回 `INTERNAL_ERROR`（exit 8），只能靠全量 `config schema`/`config get` 回读核对。
- **结论（用于缺陷 1 归因，已实证）**：本会话配置早已处于「仿真设置齐全」状态（顶层 sweeps 1–3GHz/10MHz 已持久化 + solver/execution 为 P0 默认 `em`/`Local`），reopt-1 / probe-tv 均在该状态下运行；**2026-08-21 新增干净 probe `simcfg-1`**（新 request-id `19260c9f…`，`status=succeeded`、无 warnings）仍 `targetValues:[]` → **空目标值与仿真设置配置无关**，根因在服务端打分（§5 缺陷1）。

### 2.6 自定义指标公式 formula validate / customMetrics 注入（2026-08-27 实证）
```bash
# 语法校验（只验 AST，不验常量：字面量之外一律 UNSAFE_NAME，见下）
echo '{"key":"Q","expression":"Im(Z(1,1))/Re(Z(1,1))","unit":""}' \
  | epcd-cli formula validate --input -
# 实测接受：Im(Z(1,1))/(2*3.14159*2.4e9) valid（nH）；Im(Z(1,1))/Re(Z(1,1)) valid（Q）
# 实测拒绝：Im(Z(1,1))/(2*PI*F) → UNSAFE_NAME 'PI'/'F' —— 表达式只能用 Z(1,1)/Re/Im 与数字常量，频点须内联
```
内置指标来自 device-template describe；**注意：本构建模板 describe 的 builtInMetrics 为空**，空打分的
根因恰是「无指标导出公式」（release §4.8 + 2026-08-26 §5 缺陷1）。**实证可行的修复 = 顶层 `customMetrics`
注入**（而非 `synthesisTargets.customMetrics`，那个字段 patch 后被静默丢弃）：
```bash
# ① 顶层 customMetrics 注入 L/Q 导出公式（target/unit 必须填数值字符串，见注意③④）
echo '{"customMetrics":[
  {"name":"inductance","expression":"Im(Z(1,1))/(2*3.14159*2.4e9)","target":"2.1","weight":"1","comparison":"greater-than","unit":"1"},
  {"name":"minQFactor","expression":"Im(Z(1,1))/Re(Z(1,1))","target":"8","weight":"1","comparison":"greater-than","unit":"1"}]}' \
  | epcd-cli config patch --instance-id $INST --project $PROJ --input - --if-match sha256:……
# ② 回读验证：config get --path /customMetrics 应见持久化项（含服务端补的 method/weight）
# ③ customMetrics 项会被服务端转写进 inductor_l1/config.xml 的 <ParamGroup groupName="formula">：
#    <paramItem jsonKeyStr=… formulaStr=… value=… weight=… unit=… method=… />
#    该 XML 由 epcdopt.parseConfigFile 按固定位置 float() 解析 → unit 必须是数字（填 "1" 占位），
#    填 "nH" 会 `could not convert string to float: 'nH'`、target 留空会 `''` 崩溃
# ④ comparison 词表用 greater-than/less-than/equal（服务端会再规范化为 greater/less/equal）
# ⑤ 注入后单轮 run（新 request-id，如 cm-*）→ scoring 产出非空 targetValues + target-chart 产物（§2.8 cm-3 实测）
```

### 2.7 运行 run
```bash
# 单候选仿真（异步提交：立即拿 jobId）
echo '{"schemaVersion":"epcd-candidate/v1","parameters":{"trackWidth":10,"trackSpace":3,"numOfTurns":3,"innerRadius":50}}' \
  | epcd-cli run --instance-id $INST --project $PROJ --task simulation-evaluation \
      --input - --if-match sha256:…… --request-id iteration-1

# 同步等待至终态（--wait 单独用，勿与 --timeout 同用）
... | epcd-cli run ... --request-id probe-1 --wait

# 异步 + 有界阻塞（到期不取消后台 job，返回 waitTimedOut）
... | epcd-cli run ... --request-id probe-2 --timeout 120
```
- `--request-id` 幂等：同 (项目, instance, requestId) 重复提交 → 返回**原 job**；不同请求撞同名 → `REQUEST_ID_CONFLICT`。**重跑优化务必换前缀**（如 reopt-*）。
- `--if-match` 用 config get 返回的最新 digest。
> agent 映射：`epcd_run`（task 白名单 gds-generation/simulation-evaluation）。

### 2.8 任务 job get / result / cancel
```bash
epcd-cli job get --id <job-id>        # 含 status/state、parameters、artifacts[]
epcd-cli job result --id <job-id>     # 终态结果：targetValues[]/objectiveCost/warnings/artifacts
epcd-cli job cancel --id <job-id>     # 取消运行中 job
```
状态机：`queued → validating → running → succeeded | failed | canceled`（运行中有 canceling）。
result 契约（release §4.12）：`targetValues[].{metric, frequency{value,unit,valueHz}, comparison,
targetValue, actualValue, unit, weight, satisfied, relativeDeviation, objectiveCost}` + 顶层 `objectiveCost`。
**判定铁律**：`status=="succeeded"` ≠ 仿真成功 ≠ 有评分。必须看 `warnings`（如 `SIMULATION_FAILED`）且 `targetValues` 非空。

**2026-08-21 服务器端更新实测**（job `bd8eccb3-33c4-4e73-b072-64172435ffa9` = request-id `server-update-test-1`，
覆盖率：run / job get / job result 三个接口均已更新）：
- `job get`/`job result` **补回元数据契约字段**：`configDigestUsed`（本次 `sha256:c26cbe0a…`）、
  `technologyDigestUsed`（`sha256:e04cb25e…`，与 `project validate` 返回的 technologyDigest 一致）、
  `startedAt`/`finishedAt`/`durationSeconds`（本次 24.0 s）、`pid`。
- `artifacts[]` **新增产物类型**：`gtxt`（如 `test_pmrg.gtxt`）、`layout-preview-image`
  （`preview_top.png`/`preview_iso.png`/`preview_side.png`）、`gtxt-scene`（scene.json）。
- **新增 `publication` 出版目录**：`{directory, artifacts[]}`，含参数命名 GDS
  （`SimpleInd__p__10_3_3_50.gds`）、`graphs.s2p`、`graphs_sample.s2p`（新样点矩阵文件）。
- **缺陷 1 未修复**：`targetValues` 仍恒 `[]`，`target-values.json` 仍为 size 48 / sha256 `714907cb…`
  的恒定 stub（跨旧 job 字节相同，见 §5）。
> agent 映射：`epcd_job`（action get/result/cancel）+ `artifact_view`（result 产物落本地缓存）。

**2026-08-27 实测：customMetrics 注入后打分真正产出**（job `fe00a15b-97df-411e-86cc-2f011a594cf3`
= request-id `cm-3`，23.0s，succeeded，无 warnings）：
- 前置：顶层 `/customMetrics` 注入 L/Q 公式（§2.6 步骤①），digest `sha256:0e778856…`。
- **`targetValues` 首次非空**：402 条 = 201 频点（1–3 GHz，每 5 MHz 点）× L/Q 两个 metric。
- **`formula.json` 恢复**：`"formula":["L=Im(1/Y(1,1))/(2*pi*f)","Q=Im(1/Y(1,1))/Re(1/Y(1,1))","maxSize"]`
  （此前 `[]`，见 §5 缺陷1）——当前 scoring 现在有可计算的指标项。
- **`objectiveCost` 首次非零 = 2766.15**；`artifacts` 新增 `target-values` +
  `target-chart`(svg/png)（此前这两种类型从不产出）。
- **`target-values.json` sha256 `3930d2c0…`（152,190 B 实际数据）**，不再是与旧 stub
  `714907cb…`（48 B）相同的常量 → 打分链路真通。
- 但 `actualValue` 为**负**：L@2.4G ≈ −14.09 nH、Q ≈ −0.50 → `satisfied=false`、`relativeDeviation`
  L≈7.71 / Q≈1.06。负值来源 = EM 端口开路（缺陷 2，`Im(Z11)<0` 容性）→ **打分通 ≠ 指标达标**，
  与实际器件最终可用性仍由缺陷 2 阻断（§5）。

## 3. 状态机 / 幂等 / 乐观锁语义速记

| 机制 | 语义 |
|---|---|
| request-id | 幂等键=（规范工程路径, instanceId, requestId）；重复=原 job，撞名=REQUEST_ID_CONFLICT |
| configDigest | 每次 patch/apply-result/get 返回；patch/run 需 `--if-match` 一致 |
| run --wait | 本进程阻塞到终态（同步模式） |
| run --timeout | 异步提交后阻塞≤N 秒；**与 --wait 互斥**（TIMEOUT_WITH_WAIT） |

## 4. 本会话现场快照（可直接照抄复核）

| 项 | 值 |
|---|---|
| PKG | `/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default` |
| PROJ | `/home/zhubo/epcd-runs/inductor`（libName `inductor`） |
| 工艺 | `$PKG/tutorial/command_use/transmission_line/demo.ptxt` |
| INST / 实例名 | `20260820090223000` / `inductor_l1` |
| TID | `system.inductor.simple_inductor` |
| configDigest | `sha256:0e7788566de9ae577c1f8e7d108e90aa2fb813d7894c10b54a53734943047802`（2026-08-27，customMetrics 注入后；此前 `c26cbe0a`/`dcd7d900`/`9b29878b` 演进） |
| 目标 | L=2.1nH@2.4GHz equal / Q≥8 greater-than / size≤300µm less-than，w1/1/1 |
| customMetrics | 顶层： inductance=`Im(Z(1,1))/(2*3.14159*2.4e9)` tgt2.1 w1 gte unit1； minQFactor=`Im(Z(1,1))/Re(Z(1,1))` tgt8 w1 gte unit1 |
| 扫频 | 顶层 sweeps：adaptive 1–3GHz step 10MHz |
| job | `0da11824…`=iteration-1（license 前失败）；`b0f54c39…`=reopt-1；`a6b32523…`=probe-tv；`19260c9f…`=simcfg-1；`bd8eccb3…`=server-update-test-1；`394da71a…`=reverify-1（TARGET_VALUES_EMPTY 根因定位）；**`fe00a15b…`=cm-3（2026-08-27 打分首次非空，sha `3930d2c0`）** |

```bash
# 复核命令（照抄）
epcd-cli health
epcd-cli project describe --project $PROJ
epcd-cli project device list --project $PROJ
epcd-cli config get --instance-id $INST --project $PROJ --path /synthesisTargets
epcd-cli config get --instance-id $INST --project $PROJ --path /sweeps
epcd-cli job result --id a6b32523-e684-4ec2-9ac5-6d9b673826ae
```

## 5. 已知问题与规避（含复现命令）

1. **目标值恒空（缺陷1）**：所有 succeeded job `targetValues:[]`、`objectiveCost:0.0`，且
   target-values.json 在完成时刻即定稿（mtime 不再变、跨 job 字节相同）。复现：
   ```bash
   epcd-cli job result --id a6b32523-e684-4ec2-9ac5-6d9b673826ae | jq .data.targetValues
   ssh zhubo@192.168.20.243 'cat /home/zhubo/epcd-runs/inductor/devices/20260820090223000/runs/\
     a6b32523-e684-4ec2-9ac5-6d9b673826ae/artifacts/target-values.json'
   ```
   > **归因排除（已实证 2026-08-21）**：非仿真设置缺失所致 —— 配置处于「仿真设置齐全」状态
   > （顶层 sweeps 已持久化生效、solver/execution 为 P0 默认 em/Local，§2.5.1），全新干净 probe
   > `simcfg-1`（`19260c9f…`，succeeded 且无 warnings）仍 `targetValues:[]`。根因是服务端打分
   > （frequency 被规范化成自身字段 `freq`，打分代码按 `value`/`valueHz` 解析 → 恒空）。
   > **2026-08-21 服务器端更新后复测**：三个接口（run / job get / job result）更新生效
   > （补回 `configDigestUsed`/`technologyDigestUsed`/`durationSeconds` 等元数据契约字段、
   > 新增 layout-preview/gtxt/publication 产物，见 §2.8），但 `server-update-test-1`
   > （`bd8eccb3…`，succeeded、无 warnings、24.0s）**`targetValues` 仍空、stub sha 未变** →
   > 缺陷独立于 job 接口层，位于服务端打分环节本身。
   > **服务器端二次通知复核（2026-08-21，通知称 job result 已可返回 targetValues）**：
   > 用全新 job-id 实测 score-verify-1（`b85335e5…`）与 score-verify-2（`9c9f065e…`，
   > 重写 synthesisTargets 标准契约形状后）——均 `succeeded`、无 warnings，`targetValues` 仍空、
   > stub sha 未变（`714907cb…`）。**run.log 新出现打分表头**：
   > `[RESULT] 0 Width(um) Spacing(um) Num of Turns Inner Radius(um) Temperature(degC) Freq(GHz) Score`
   > —— 仅表头、**0 行结果**：EM 求解成功（`Range EM With Initial success!`，命令行已带
   > `--multiSweep`/`--discreteFreq`）但无 Score 数据行 → 打分缺 actualValue 输入，与缺陷 2
   > （EM 端口开路）自洽：**打分接口修复 ≠ 有分可打**；需求解器先产出频点结果行。
   > **2026-08-26 服务器端再次更新后的确定性根因（job `reverify-1`=`394da71a…`，24.0s）**：
   > scoring 环节已完全植入并获得结构化警告：
   > `"warnings":[{"code":"TARGET_VALUES_EMPTY","message":"formula.json parsed but no metric matched calcItems; formulaKeys=[] calcItemKeys=[]"}]`
   > 定位到 [`synthesis/formula.json`]（打分解析的指标定义）：
   > `{"snp":[…graphs.s2p], "formula":[], "value":{"25.0":{"freq":[1.0e9…3.0e9]}}, "unitstr":[]}`
   > —— S 参数与 201 频点数据齐全，但 **`"formula":[]`（无指标导出公式）→ `formulaKeys=[]`**；
   > 配置侧 `synthesisTargets.customMetrics:[]` 同空；模板 describe 亦不再下发
   > `builtInMetrics`（现为 `[]`）→ **calcItemKeys 无从派生** → 空 targetValues 的直接原因收敛为
   > 「metric 导出公式缺失，服务端无可计算的指标项」，非仿真/EM 设置问题。另：job 产物目录
   > 改为 `<device>/.epcd-cli/runs/<job>/`（不再是 `devices/<inst>/runs/`）。
   > **2026-08-27 修复实证（customMetrics 注入）**：空打分的直接成因（无公式）可通过**顶层
   > `/customMetrics`** 提供导出公式消除（§2.6 可复现步骤：target/unit 填数值、comparison 用
   > greater-than 词表）。注入后 job `cm-3`=`fe00a15b…` **targetValues 非空**（402 条）、
   > `formula.json` 恢复 `["L=…","Q=…","maxSize"]`、`objectiveCost=2766.15`、
   > `target-values.json` sha `3930d2c0…`（152 KB 实际数据，非 stub）、artifacts 新增
   > `target-values` + `target-chart`(svg/png) → **服务端打分链路本身可用**，缺陷 1 的根因
   > 收敛为「模板 describe 不再下发内置公式 + 客户端此前未注入」。
   > **剩余阻断（缺陷 2）**：L/Q 的 actualValue 为负（L@2.4G ≈ −14.09 nH、Q ≈ −0.50，
   > 源：`Im(1/Y(1,1))/(2*pi*f)` 中 EM 端口开路→ `Im(Z11)<0` 容性）→ `satisfied=false`，
   > 目标仍不可达。即：**打分通 ≠ 器件可用**；指标达标的根因是 EM 端口模型（缺陷 2）。
2. **EM 端口开路（缺陷2）**：simple_inductor+demo.ptxt 的 s2p 全频段差分阻抗为容性（|S21|≈0.03）。
3. **MSYS 路径转换（Windows Git Bash）**：直接跑 epcd-cli 时对 `--pkg /…` 类 POSIX 路径要
   `MSYS_NO_PATHCONV=1` 前缀（stdin JSON 路径不受影响）。
4. **license**：`NINECUBE_LICENSE_FILE=2048@192.168.20.109` 已写入远端 `~/.epcd-env`，agent 前缀自动 source。
5. **污染提醒**：探针用过的 requestId（probe-tv / reopt-1）别再复用；apply-result 在本构建未改 device.parameters。

## 6. agent 工具 → epcd-cli 命令映射

| agent 工具 | 远端命令 |
|---|---|
| epcd_health | version + health |
| epcd_project init/describe/validate | project init/describe/validate |
| epcd_template list/describe | device-template list/describe |
| epcd_device add/list/describe/remove | project device add/list/describe/remove |
| epcd_formula validate | formula validate |
| epcd_config schema/get/patch/apply-result | config schema/get/patch/apply-result（if-match 自动注入） |
| epcd_run | run（task/input/if-match/request-id） |
| epcd_job get/result/cancel | job get/result/cancel |
| optimization_start/status/cancel | **agent 层循环**（epcd_run+epcd_job+本地 optuna），无远端单命令 |
| artifact_view | job result + ssh base64 拉产物 |

> 本地 wrapper 固定入口（Windows Git Bash）：
> `MSYS_NO_PATHCONV=1 EPCD_SSH_HOST=zhubo@192.168.20.243 EPCD_PKG_ROOT=$PKG \
>   ./.venv/Scripts/python -m epcd_agent.cli --session inductor <tool>`
> 参数 JSON 经 stdin 传入；stdout 单行 JSON；退出码 0/1/2。
> （`--db` 可省略：默认落统一产物根 `<repo>/runs/epcd-agent-session.sqlite3`。）