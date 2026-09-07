# EPCD Agent Demo 固定命令流程

更新时间：2026-09-01

实测环境：服务器 build `epcd-cli 0.1.0`，包 `/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default`，工艺 `demo_revised.ptxt`，许可证 `NINECUBE_LICENSE_FILE=2048@192.168.20.109`（经 `~/.epcd-env` 注入，见 §2）。本文每个接口保留一条最新实测结果；EM 仿真端到端打通（succeeded、warnings 空、`objectiveCost`/`targetValues` 非空，见 §4.12/§4.15）。

## 1. 文档定位

本文是 `ePCD_Agent_Demo_Flow_Scratch.xlsx` 对应的 P0 命令交付说明，规定 Agent 和测试程序应当用的公开接口、调用顺序和最低响应字段。

## 2. 通用调用约定

服务器 build 的 `epcd-cli` 不在非交互 shell 的默认 `PATH` 中，调用前必须先 source 包内环境脚本。EM 求解还需许可证环境变量，持久化在 `~/.epcd-env`，必须在 `user.bashrc.ePCD` **之前** source（否则 emsolver 取不到许可证、仿真 succeeded 但携带 `SIMULATION_FAILED`、无 targetValues/SNP）：

```bash
source ~/.epcd-env            # export NINECUBE_LICENSE_FILE=2048@192.168.20.109
source <package-root>/user.bashrc.ePCD
epcd-cli <command> [arguments]
```

Agent 调用时省略 `--format`，使用默认的单行紧凑 JSON 输出；人工调试可加 `--format text` 输出多行 YAML，字段不变。需要结构化输入时，Agent 统一使用 `--input -`，向子进程 stdin 写入一个 UTF-8 JSON object；不生成临时文件，也不把 JSON 拼接到 shell 命令字符串中。

真实 build（如 `device-template describe`）会在信封**之前**向 stdout 泄漏求解器/工艺告警行：

```text
Warning:layer initialized with invalid valueIndex or index out of defValue bound, will reset to first element of defValue.
Warning:groundLayer initialized with invalid valueIndex or index out of defValue bound, will reset to first element of defValue.
{"schemaVersion":"epcd-response/v1","ok":true,...}
```

Agent 解析时必须**自 stdout 中第一个 `{` 起**解析 JSON 信封，不能假设整段 stdout 都是 JSON，也不能把告警行当作错误分支依据。成功：

```json
{
  "schemaVersion": "epcd-response/v1",
  "ok": true,
  "requestId": null,
  "data": {},
  "errors": []
}
```

失败：

```json
{
  "schemaVersion": "epcd-response/v1",
  "ok": false,
  "requestId": null,
  "data": null,
  "errors": [
    {"code": "ERROR_CODE", "path": "/field/path", "message": "Human-readable message"}
  ]
}
```

Agent 必须使用 `ok`、`errors[].code`、`errors[].path` 和进程退出码判断结果，不能解析 `message` 文本做程序分支。

| 退出码 | 含义 |
| ---: | --- |
| 0 | 成功 |
| 2 | 命令参数错误 |
| 3 | JSON/YAML 输入格式错误 |
| 4 | Schema 校验错误 |
| 5 | 业务规则错误 |
| 6 | 工艺错误 |
| 7 | License 不可用 |
| 8 | GDS/仿真执行失败 |
| 9 | 结果写入失败 |
| 10 | 任务已取消 |
| 11 | request-id 冲突 |

本文中的 `<project-dir>`、`<instance-id>`、`<template-id>`、`<digest>` 和 `<job-id>` 必须使用前序命令响应中的实际值，不允许从目录名或显示名推测。

## 3. 固定命令树

```text
epcd-cli
├── version
├── health
├── device-template
│   ├── list
│   └── describe
├── project
│   ├── init
│   ├── describe
│   ├── validate
│   └── device
│       ├── list
│       ├── add
│       ├── describe
│       └── remove
├── config
│   ├── schema
│   ├── get
│   ├── patch
│   └── apply-result
├── formula
│   └── validate
├── run
│   └── --task gds-generation|simulation-evaluation
└── job
    ├── get
    ├── result
    └── cancel
```

`_run-job` 为内部受抑制子命令（`--run-dir`），Agent 不调用。`run --timeout` 语义：异步提交后阻塞最多 N 秒，到期**终止子进程并使 Job 失败**（`RUN_TIMEOUT`），不再保留后台 Job。

## 4. Demo 完整调用流程

### 4.1 启动前健康检查

```bash
epcd-cli version
epcd-cli health
```

`version` 实测：

```json
{"schemaVersion":"epcd-response/v1","ok":true,"requestId":null,"data":{"version":"0.1.0","responseSchemaVersion":"epcd-response/v1","python":{"releaseBaseline":"3.8","current":"3.8.7","cacheTag":"cpython-38"}},"errors":[]}
```

`health` 实测（节选）：

```json
{
  "status": "ok",
  "version": "0.1.0",
  "runtime": {
    "mode": "private-api",
    "mock": false,
    "available": true,
    "python": {"version": "3.8.7", "implementation": "CPython", "cacheTag": "cpython-38", "releaseBaseline": "3.8", "compatible": true},
    "modules": [
      {"name": "project", "available": true},
      {"name": "param", "available": true},
      {"name": "tech", "available": true}
    ],
    "missingModules": [],
    "stateHome": {"path": "/home/zhubo/.epcd", "exists": true, "writable": true}
  }
}
```

探测命令本身成功时 `ok` 为 `true`；环境不完整则 `data.status` 为 `degraded`，并通过 `available`、`compatible`、`missingModules` 和 `stateHome.writable` 表明原因。

### 4.2 创建工程

```bash
epcd-cli project init \
  --work-dir <project-dir> \
  --technology <process.ptxt> \
  [--password <plaintext-password>]
```

`--password` 接收明文，仅用于本次调用。重复提交等价工程同样返回成功信封（无 `created` 字段）。实测（工艺 `demo_revised.ptxt`）：

```json
{
  "path": "/home/zhubo/epcd-reltest-0901",
  "libName": "epcd-reltest-0901",
  "techFile": "/home/zhubo/epcd-reltest-0901/demo_revised.ptxt",
  "technologyPath": "/home/zhubo/epcd-reltest-0901/demo_revised.ptxt",
  "modules": []
}
```

Agent 记账时按 `project` 优先、`path` 兜底读取工程路径。创建后立即验证：

```bash
epcd-cli project describe --project <project-dir>
epcd-cli project validate --project <project-dir>
```

`describe` 响应与 `init` 的 `data` 形状一致。`validate` 实测（返回 `technologyDigest`，描述命令无此字段）：

```json
{
  "valid": true,
  "project": "/home/zhubo/epcd-reltest-0901",
  "technologyDigest": "sha256:d087a081b7047108ed2a83d6fa3bf065662df5ec16e5012ed0f6805da85b78f4",
  "devices": []
}
```

### 4.3 查询并选择器件模板

`device-template` 只查询可实例化的器件模板，不创建或修改工程器件。模板使用稳定的 `templateId` 标识。

```bash
epcd-cli device-template list                       # 全部类别
epcd-cli device-template list --category inductor   # 按类别过滤
epcd-cli device-template describe <template-id> --project <project-dir>
```

`describe` 的 `--project` 必需，因为动态参数、工艺层、默认 Gtxt 和模板可用性依赖工程工艺。`list` 实测返回 `data.categories`，按类别分组，每项 `{templateId, name}`：

```json
{
  "category": null,
  "categories": {
    "inductor": [
      {"templateId": "system.inductor.simple_inductor", "name": "simple_inductor"},
      {"templateId": "system.inductor.adv_simple_inductor", "name": "adv_simple_inductor"}
    ],
    "cap": [{"templateId": "system.cap.finger_capacitor", "name": "finger_capacitor"}],
    "balun": [{"templateId": "system.balun.simple_balun", "name": "simple_balun"}],
    "coupler": [{"templateId": "system.coupler.coupler", "name": "coupler"}],
    "tcoil": [{"templateId": "system.tcoil.tcoil_flatwiring", "name": "tcoil_flatwiring"}],
    "tline": [{"templateId": "system.tline.single_tline", "name": "single_tline"}],
    "trfm": [{"templateId": "system.trfm.flexratio_transformer", "name": "flexratio_transformer"}]
  }
}
```

`describe` 实测要点（以 `system.inductor.simple_inductor` 为例）：

- `parameterSchema` 为**空骨架**（`basic/opt/synth` 三组 `properties` 均为 `{}`），不含参数定义与取值范围。
- `builtInMetrics` 为空数组 `[]`。
- 参数定义全部在 `addinParams`（面向 UI 的数组的数组，含 `jsonKeyStr/min/max/stepValue/defValue/fieldType` 等，Agent 一般忽略）。
- `previewArtifacts`、`warnings` 实测为空数组。
- stdout 信封之前有 `Warning:` 行，见 §2。

```json
{
  "templateId": "system.inductor.simple_inductor",
  "namespace": "system",
  "category": "inductor",
  "name": "simple_inductor",
  "moduleName": "Simple Inductor",
  "schemaVersion": "1.0",
  "available": true,
  "parameterSchema": {"type": "object", "properties": {"basic": {"type": "object", "properties": {}}, "opt": {"type": "object", "properties": {}}, "synth": {"type": "object", "properties": {}}}},
  "builtInMetrics": [],
  "addinParams": ["...面向 UI 的参数定义，Agent 可忽略..."],
  "previewArtifacts": [],
  "warnings": []
}
```

参数取值范围与可优化变量名不在 `describe` 中，需从 `project device add`/`config schema` 的 `device.parameters` 取得（见 §4.4/§4.5）。

### 4.4 实例化器件

`project device` 管理某个工程内已经实例化的器件。一个模板可实例化多次，每个实例都有独立 `instanceId`；后续配置和任务只使用 `instanceId`。

```bash
epcd-cli project device add \
  --project <project-dir> \
  --template-id <template-id> \
  [--name <instance-name>]
```

`--name` 可选；缺省按模板基本名加递增数字生成。实例的 `showName` 和 `folderName` 始终相同。`add` 实测返回 `instanceId`（时间戳形式字符串）+ 实例初始配置骨架 `config`，其中 `device.parameters` 已含**带取值范围的可优化变量**（`value`/`min`/`max`/`step`，`value:null` 表示待设置）：

```json
{
  "project": "/home/zhubo/epcd-reltest-0901",
  "instanceId": "20260901024041000",
  "path": "/home/zhubo/epcd-reltest-0901/Lprobe1",
  "config": {
    "schemaVersion": "epcd-device/v1",
    "device": {
      "id": "system.inductor.simple_inductor",
      "parameters": {
        "trackWidth":  {"value": null, "min": "6.0",  "max": "20.0", "step": "None"},
        "trackSpace":  {"value": null, "min": "1.5",  "max": "5.0",  "step": "None"},
        "numOfTurns":  {"value": null, "min": "0.25", "max": "8.0",  "step": "@0.25"},
        "innerRadius": {"value": null, "min": "20.0", "max": "80.0", "step": "None"}
      }
    },
    "instance": {"name": "Lprobe1"}
  }
}
```

`project device list` 实测返回 `data.devices[]`，每项为：

```json
{
  "instance": "20260901024041000",
  "instanceId": "20260901024041000",
  "type": "inductor",
  "folderName": "Lprobe1",
  "module": "system.inductor.simple_inductor",
  "showName": "Lprobe1",
  "solverType": "EM",
  "rangeType": "EM",
  "model": "",
  "path": "/home/zhubo/epcd-reltest-0901/Lprobe1"
}
```

后续实例接口只接受 `instanceId`：

```bash
epcd-cli project device describe \
  --project <project-dir> \
  --instance-id <instance-id>
```

`describe` 响应形状与 `add` 的 `data` 一致（`project`/`instanceId`/`path`/`config`）。

### 4.5 获取实例配置 Schema

模板详情中的 `parameterSchema` 用于选型；实例创建后，Agent 使用 `config schema` 获取当前工程、工艺和器件实例共同决定的完整可写规则：

```bash
epcd-cli config schema \
  --project <project-dir> \
  --instance-id <instance-id> \
  [--path /device/parameters]   # 只读某段
```

`--path` 使用与 `config get --path` 相同的配置 JSON Pointer，不使用 JSON Schema 内部的 `/properties/...` 路径。`schema` 实测返回**带类型/取值范围/锁定标志的规则**（不是纯默认值骨架）：

```json
{
  "project": "/home/zhubo/epcd-reltest-0901",
  "instanceId": "20260901024041000",
  "templateId": "system.inductor.simple_inductor",
  "schemaVersion": "epcd-device-schema/v1",
  "path": "/",
  "schema": {
    "schemaVersion": "epcd-device/v1",
    "device": {
      "id": "system.inductor.simple_inductor",
      "parameters": {
        "basic": {
          "layer": "metal2", "layerCross": "metal1", "shape": "Rectangular",
          "aspectRatio": "1", "stackOption": "End Connect", "startPoint": "Center",
          "angleCoplanar": "90", "angleUnder": "90", "coplanarPass": "10", "underPass": "10", "copPassType": "1"
        },
        "opt": {
          "trackWidth":  {"value": "10.0", "min": "6.0",  "max": "20.0", "step": "None", "locked": false, "enabled": true},
          "trackSpace":  {"value": "2.0",  "min": "1.5",  "max": "5.0",  "step": "None", "locked": true,  "enabled": true},
          "numOfTurns":  {"value": "2.5",  "min": "0.25", "max": "8.0",  "step": "@0.25", "locked": false, "enabled": true},
          "innerRadius": {"value": "60.0", "min": "20.0", "max": "80.0", "step": "None", "locked": false, "enabled": true}
        }
      }
    },
    "simulation": {"solver": {"type": "em", "emSolver": ""}, "execution": {"mode": "Local", "subCommand": "", "parallel": "1"}, "sweeps": []},
    "sweeps": [],
    "synthesisTargets": {
      "frequencyMode": "points",
      "objectives": [
        {"metric": "Inductance Value(nH)", "frequency": {"mode": "point", "freq": "2.5"}, "comparison": "equal",        "targetValue": "2.1", "unit": "-", "weight": "1"},
        {"metric": "Min Q Factor",         "frequency": {"mode": "point", "freq": "2.5"}, "comparison": "greater-than", "targetValue": "8",   "unit": "-", "weight": "1"},
        {"metric": "Max Size(um)",         "frequency": {"mode": "point", "freq": "2.5"}, "comparison": "less-than",    "targetValue": "300", "unit": "-", "weight": "1"}
      ],
      "customMetrics": []
    },
    "customMetrics": []
  },
  "schemaDigest": "sha256:94dff3dc299d9ebe7997bdf7d672ccfb900fa1113e2b73ae22c72ac824de59a5"
}
```

关键约定：

- `opt` 组为可优化变量：`enabled:true && locked:false` 才可调（本例 `trackWidth`/`numOfTurns`/`innerRadius` 可调，`trackSpace` 锁定）。`basic` 为基础参数（扁平字符串值）。
- `synthesisTargets` 已预置内置目标（Inductance/Min Q/Max Size，频点 2.5）；Agent 可整体替换。
- `schemaDigest` 用于判断缓存是否变化，与同一实例的 `configDigest` 实测相同。
- `config schema --path /sweeps` 实测返回 `INTERNAL_ERROR`（exit 8），只能以全量 `config schema`/`config get` 的回读形状为准。

### 4.6 读取和修改基础参数

```bash
epcd-cli config get  --project <project-dir> --instance-id <instance-id> [--path /device/parameters]
epcd-cli config patch --project <project-dir> --instance-id <instance-id> --input - --if-match <config-digest>
```

`config get` 实测（`--path /device/parameters/opt`，返回该段 `value` + 完整配置对应的 `configDigest`）：

```json
{
  "project": "/home/zhubo/epcd-reltest-0901",
  "instanceId": "20260901024041000",
  "path": "/device/parameters/opt",
  "value": {
    "trackWidth":  {"value": "10.0", "min": "6.0",  "max": "20.0", "step": "None", "locked": false, "enabled": true},
    "trackSpace":  {"value": "2.0",  "min": "1.5",  "max": "5.0",  "step": "None", "locked": true,  "enabled": true},
    "numOfTurns":  {"value": "2.5",  "min": "0.25", "max": "8.0",  "step": "@0.25", "locked": false, "enabled": true},
    "innerRadius": {"value": "60.0", "min": "20.0", "max": "80.0", "step": "None", "locked": false, "enabled": true}
  },
  "configDigest": "sha256:94dff3dc299d9ebe7997bdf7d672ccfb900fa1113e2b73ae22c72ac824de59a5"
}
```

每次 Patch 必须用最近一次 `config get/patch` 返回的摘要。摘要不匹配且目标值尚未存在时返回 `CONFIG_DIGEST_MISMATCH`。

**未决异常（仍存在）**：对 `device.parameters` 的 patch **不持久化**。提交 `{"device":{"parameters":{"opt":{"trackWidth":"12","numOfTurns":"3","innerRadius":"40"}}}}`（数值须为字符串，数值类型触发 `INTERNAL_ERROR` exit 8）返回 `ok:true, changed:true`，但 `configDigest` 不变，`config get` 回读仍为默认值（10.0/2.5/60.0）。候选参数的实际生效路径以 `run --input`（epcd-candidate/v1）为准；写回正式参数用 `config apply-result`（§4.14，该路径已实测可持久化）。

### 4.7 预览当前器件

```bash
epcd-cli run \
  --project <project-dir> \
  --instance-id <instance-id> \
  --task gds-generation \
  --wait \
  --request-id preview-001
```

`--wait` 同步执行至终态。实测 `run` 响应 data（含 `configDigestUsed`）：

```json
{
  "jobId": "857b15de-b22a-47ff-a45c-0143a1252655",
  "requestId": "preview-001",
  "taskType": "gds-generation",
  "status": "succeeded",
  "configDigestUsed": "sha256:8c8044954545aa06dca3596d0549ae0cca9ebe346d1023b7b4a8eea9b7aa4667"
}
```

预览 Job 产物见 §4.12 的 `job result` 形状；GDS/Gtxt 成功但 PNG 渲染失败时 Job 仍成功并返回 `PREVIEW_RENDER_FAILED` warning。

### 4.8 校验自定义指标公式

内置指标由 `config schema` 的 `synthesisTargets.objectives` 给出，不提供独立 metric list 命令。需要自定义指标时：

```bash
epcd-cli formula validate --input -
```

stdin JSON：

```json
{"name": "Q", "expression": "Im(Z(1,1))/Re(Z(1,1))", "unit": "", "description": null}
```

实测响应：

```json
{"valid": true, "name": "Q", "expression": "Im(Z(1,1))/Re(Z(1,1))", "errors": [], "unit": "", "description": null}
```

公式校验只做 AST 白名单语法和依赖检查，不启动仿真。

### 4.9 设置设计目标

先取得最新摘要：

```bash
epcd-cli config get --project <project-dir> --instance-id <instance-id> --path /synthesisTargets
```

Agent 构造 stdin JSON（`objectives`/`customMetrics` 整体替换）：

```json
{
  "synthesisTargets": {
    "frequencyMode": "points",
    "customMetrics": [],
    "objectives": [
      {
        "metric": "Inductance Value(nH)",
        "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
        "comparison": "equal",
        "targetValue": 10,
        "unit": "nH",
        "weight": 5
      }
    ]
  }
}
```

提交：

```bash
epcd-cli config patch --project <project-dir> --instance-id <instance-id> --input - --if-match <config-digest>
```

规则：

- `frequencyMode` 只能是 `points` 或 `range`，同一配置不得混合。
- 比较方式只能是 `equal`、`greater-than`、`less-than`。
- 权重只能是整数 1～10。
- `customMetrics` 和 `objectives` 数组整体替换。
- 尚未配置仿真扫频时允许保存，但返回 `SIMULATION_SWEEP_NOT_CONFIGURED` warning。

实测：`synthesisTargets` patch **持久化成功**（`changed:true`、digest 变化）。回读时服务端把数值统一存为字符串，频点字段名由 `value` 变为 `freq`、丢弃 unit：

```json
{
  "frequencyMode": "points",
  "objectives": [
    {"metric": "Inductance Value(nH)", "frequency": {"mode": "point", "freq": "2.4"}, "comparison": "equal", "targetValue": "10", "unit": "nH", "weight": "5"}
  ],
  "customMetrics": []
}
```

Agent 读回配置时不得假设数值类型；以结构化字段（comparison/metric 等）分支，数值一律 `float()` 转换。

频段目标示例（`frequencyMode: "range"`，frequency 用 `{mode:"range", minimum, step, maximum, unit}`）：

```json
{
  "synthesisTargets": {
    "frequencyMode": "range",
    "customMetrics": [],
    "objectives": [
      {"metric": "Min Q Factor", "frequency": {"mode": "range", "minimum": 1, "step": 0.1, "maximum": 3, "unit": "GHz"}, "comparison": "greater-than", "targetValue": 20, "unit": "", "weight": 8}
    ]
  }
}
```

### 4.10 设置仿真配置

P0 只开放 EM、Local/LSF、`subCommand` 和扫频。solver/execution 默认值（`em`/`Local`）已符合 P0，一般无需 patch；扫频必须写入配置**顶层 `sweeps`** 键（与 `simulation` 平级），条目字段为 `{enabled, type, start, stop, step, points}`，频率/步进用**带单位字符串**标量（字典对象会被服务端强转为字符串而损坏）。`simulation.sweeps` 不持久化。实测持久化成功（digest 变化、回读一致、EM 命令行正确带上 `--multiSweep=1.0:0.01:3.0`）：

```json
{
  "sweeps": [
    {"enabled": true, "type": "adaptive", "start": "1GHz", "stop": "3GHz", "step": "10MHz", "points": ""}
  ]
}
```

`config schema --path /sweeps` 实测返回 `INTERNAL_ERROR`（exit 8），只能以全量 `config schema`/`config get` 的回读形状为准。提交前重新 `config get` 取摘要，再 `config patch ... --if-match <config-digest>`。

### 4.11 启动第 N 轮单候选仿真

Agent 为第 N 轮构造 stdin JSON（`parameters` 为扁平 dict，键名取自 §4.5 的 `opt` 可调变量）：

```json
{
  "schemaVersion": "epcd-candidate/v1",
  "parameters": {"trackWidth": 12, "trackSpace": 2, "numOfTurns": 3.5, "innerRadius": 50}
}
```

异步提交：

```bash
epcd-cli run \
  --project <project-dir> \
  --instance-id <instance-id> \
  --task simulation-evaluation \
  --input - \
  --if-match <config-digest> \
  --request-id iteration-N
```

实测 run 响应 data（含 `configDigestUsed`）：

```json
{
  "jobId": "1ff2bc7a-1d80-430d-b5f2-774361d5d5f6",
  "requestId": "iteration-best",
  "taskType": "simulation-evaluation",
  "status": "queued",
  "configDigestUsed": "sha256:ae9e91b8ccdc3049658bacd41eb69c540324ad1db20a32a514971d518f9568f8"
}
```

候选 `parameters` 扁平与嵌套 `{"opt":{...}}` 均被接受；服务端统一按扁平形状记录。digest 记账以 `config get`/`apply-result` 响应为准，亦可直接用 run 响应的 `configDigestUsed`。轮询：

```bash
epcd-cli job get --id <job-id>
```

状态集合：

```text
queued → validating → running → succeeded
                         ├─────→ failed
                         └─────→ canceling → canceled
```

也可同步等待至终态（`--wait` 与 `--timeout` 互斥，同用返回 `TIMEOUT_WITH_WAIT` exit 2）：

```bash
epcd-cli run --project <project-dir> --instance-id <instance-id> \
  --task simulation-evaluation --input - --if-match <config-digest> \
  --request-id iteration-N --wait
```

或异步提交后阻塞最多 N 秒（`--timeout`，**不**与 `--wait` 同用；到期终止子进程并使 Job 失败为 `RUN_TIMEOUT`）：

```bash
epcd-cli run --project <project-dir> --instance-id <instance-id> \
  --task simulation-evaluation --input - --if-match <config-digest> \
  --request-id iteration-N --timeout 300
```

显式取消：

```bash
epcd-cli job cancel --id <job-id>
```

`job cancel` 实测返回完整 `epcd-job/v1` 快照（`state: "canceling"`），随后 `job get` 转为 `"canceled"`。

### 4.12 获取本轮结果

终态后调用（只接受 `--id`，无 `--project`/`--instance-id`）：

```bash
epcd-cli job result --id <job-id>
```

非终态返回 `JOB_NOT_FINISHED`，不返回空成功结果。`job result` 返回 `epcd-job/v1` 完整快照，顶层**含** `objectiveCost`/`configDigestUsed`/`technologyDigestUsed`/`createdAt`/`startedAt`/`finishedAt`/`updatedAt`/`durationSeconds`/`pid`；job 标识字段是 `id`。以 §4.11 的 iteration-best（候选 tw12/ts2/nt3.5/ir50，许可证环境已 source）为例（节选；`targetValues` 实测 201 条频点，此处只示首尾各一条）：

```json
{
  "schemaVersion": "epcd-job/v1",
  "id": "1ff2bc7a-1d80-430d-b5f2-774361d5d5f6",
  "requestId": "iteration-best",
  "project": "/home/zhubo/epcd-reltest-0901",
  "device": "20260901024041000",
  "taskType": "simulation-evaluation",
  "state": "succeeded",
  "status": "succeeded",
  "runDirectory": "/home/zhubo/epcd-reltest-0901/Lprobe1/.epcd-cli/runs/1ff2bc7a-1d80-430d-b5f2-774361d5d5f6",
  "logFile": "<runDirectory>/run.log",
  "technology": {"format": "ptxt", "digest": "unknown"},
  "parameters": {"trackWidth": 12, "trackSpace": 2, "numOfTurns": 3.5, "innerRadius": 50},
  "parametersUsed": {"trackWidth": 12, "trackSpace": 2, "numOfTurns": 3.5, "innerRadius": 50},
  "createdAt": "2026-09-01T03:12:00Z",
  "startedAt": "2026-09-01T03:12:00Z",
  "finishedAt": "2026-09-01T03:12:23Z",
  "durationSeconds": 23.39,
  "configDigestUsed": "sha256:ae9e91b8ccdc3049658bacd41eb69c540324ad1db20a32a514971d518f9568f8",
  "technologyDigestUsed": "sha256:d087a081b7047108ed2a83d6fa3bf065662df5ec16e5012ed0f6805da85b78f4",
  "objectiveCost": 21.758331,
  "artifacts": [
    {"type": "gds", "path": ".../synthesis/SimpleInd/SimpleInd.gds", "size": 1262, "sha256": "...", "mediaType": "application/octet-stream"},
    {"type": "gtxt", "path": ".../test_pmrg.gtxt", "size": 864, "sha256": "...", "mediaType": "application/json"},
    {"type": "layout-preview-image", "path": ".../preview_top.png", "size": 9487, "sha256": "...", "mediaType": "image/png"},
    {"type": "gtxt-scene", "path": ".../scene.json", "size": 4320, "sha256": "...", "mediaType": "application/json"},
    {"type": "snp", "path": ".../synthesis/RangeEM/graphs.s2p", "size": 29144, "sha256": "...", "mediaType": "application/octet-stream"},
    {"type": "target-values", "path": ".../artifacts/target-values.json", "size": 75516, "sha256": "...", "mediaType": "application/json"},
    {"type": "target-chart", "path": ".../artifacts/target-chart.svg", "size": 3203, "sha256": "...", "mediaType": "image/svg+xml"},
    {"type": "target-chart", "path": ".../artifacts/target-chart.png", "size": 18811, "sha256": "...", "mediaType": "image/png"},
    {"type": "best-result", "path": ".../synthesis/BestResult.txt", "size": 579, "sha256": "...", "mediaType": "text/plain"},
    {"type": "manifest", "path": ".../artifacts/manifest.json", "size": 3425, "sha256": "...", "mediaType": "application/json"}
  ],
  "publication": {
    "directory": "/home/zhubo/epcd-reltest-0901/Lprobe1/synthesis/RangeEM",
    "artifacts": [
      {"type": "gds", "path": ".../synthesis/RangeEM/SimpleInd__p__12_2_3p5_50.gds", "size": 1262, "sha256": "...", "mediaType": "application/octet-stream"},
      {"type": "snp", "path": ".../synthesis/RangeEM/graphs.s2p", "size": 29144, "sha256": "...", "mediaType": "application/octet-stream"},
      {"type": "snp", "path": ".../synthesis/RangeEM/graphs_sample.s2p", "size": 987, "sha256": "...", "mediaType": "application/octet-stream"}
    ]
  },
  "targetValues": [
    {"metric": "L", "actualValue": 2.3133635679415816, "comparison": "equal", "frequency": {"unit": "GHz", "value": 1.0, "valueHz": 1000000000.0}, "targetValue": 2.1, "unit": "(nH)", "weight": 1.0, "objectiveCost": 0.101602, "relativeDeviation": 0.101602, "satisfied": false},
    "...1.01 ～ 2.99 GHz 各频点各一条（共 201 条），actualValue≈2.31～2.38nH、targetValue 2.1、satisfied:false...",
    {"metric": "L", "actualValue": 2.3783713122106924, "comparison": "equal", "frequency": {"unit": "GHz", "value": 3.0, "valueHz": 3000000000.0}, "targetValue": 2.1, "unit": "(nH)", "weight": 1.0, "objectiveCost": 0.132558, "relativeDeviation": 0.132558, "satisfied": false}
  ],
  "warnings": []
}
```

实测要点：

- **顶层 `objectiveCost` 现已存在**（21.758331），数值越小越好；此处 = 各频点 `targetValues[].objectiveCost` 之和。仍保留回退取值顺序以防缺字段：顶层 `objectiveCost` → 逐条 `targetValues[].objectiveCost` 求和 → 逐条 `relativeDeviation` 求和 → 按 `satisfied` 记 0/1；全缺时视为无评价数据（暂停上报）。
- **`status == "succeeded"` 且 `warnings` 为空**才表示仿真成功。若未 source 许可证环境（§2），job 仍 succeeded 但 `warnings` 携带 `SIMULATION_FAILED`、`targetValues` 空、无 SNP——分支判断必须同时检查 warnings/targetValues。
- `targetValues` 每条含 `metric`（逻辑名，如 `L`）/`actualValue`/`comparison`/`frequency{unit,value,valueHz}`/`targetValue`/`unit`/`weight`/`objectiveCost`/`relativeDeviation`/`satisfied`；按配置扫频逐点给出（本例 1.0～3.0 GHz 共 201 条）。`job get --id` 返回同一快照（运行中无 `result` 段）；`parameters` 保留提交形状（扁平），`parametersUsed` 恒为扁平。
- EM 评价的 `targetValue`（本例 L=2.1nH，模板内置电感目标）与频点范围取自模板/工艺内置指标与配置扫频，跨整段扫频逐点评价；`synthesisTargets.objectives` 的 patch（§4.9）虽持久化（回读一致），但本轮未反映到 EM 的 `targetValues`，二者的对接关系待进一步确认。
- **修正（2026-09-04 实证，服务端已修复）**：EM 评价的 `targetValue` 现已取**配置的 `synthesisTargets.objectives`** 而非模板内置。验证：清空 `/synthesisTargets/customMetrics` 的干净配置下，patch objectives 为 3.5/12/220 → run 的 `targetValues` 逐条 = 3.5/12.0/220.0；恢复 3/10/250 → 逐条 = 3.0/10.0/250.0（全 `satisfied:true`）。objective 的 `metric` 须用模板族名（`Inductance Value(nH)`→L、`Min Q Factor`→Q、`Max Size(um)`→size）；自定义公式放 `/synthesisTargets/customMetrics`（与内置同名会报 `CUSTOM_METRIC_CONFLICT`）。验收口径：`targetValues[].targetValue == objectives[].targetValue`。

评价字段固定为 `objectiveCost`（数值越小越好），不是 `score` 或 `objectCost`。Agent 同时使用各频点的 actualValue、relativeDeviation 和 satisfied 判断下一组参数。

### 4.13 Agent 迭代规则

requestId 作用域是规范化工程路径、instanceId 和 requestId。同一作用域、相同请求返回原 Job；同一作用域、不同请求返回 `REQUEST_ID_CONFLICT`；不同器件可以复用 `iteration-1` 等名称。实测：同一 instance 用新 requestId 提交成功、响应回带该 requestId；`job get` 快照中 requestId 与提交一致。

Agent 重复执行 4.11～4.12：

```text
读取上一轮 targetValues
→ 分析偏离最大的指标和频点
→ 生成一组新 parameters
→ 使用新的 requestId 创建 Job
→ 等待结果
→ 比较 objectiveCost
```

必须选择 `objectiveCost` 最小的 succeeded Job。

### 4.14 写回最优参数

```bash
epcd-cli config apply-result \
  --project <project-dir> \
  --instance-id <instance-id> \
  --job-id <best-job-id>
```

`--project` 可省略（默认 cwd），`--instance-id`/`--job-id` 必填。只允许写回 succeeded Job 中由候选显式提供的器件参数：优化参数定向更新 opt 参数的 `value`；不修改参数范围、步长、启用状态、仿真、目标、工艺、端口或任务产物。工程/器件/工艺/正式配置摘要在 Job 创建后变化时拒绝写回。实测：写回**已持久化**——返回 `applied:true` + 变化后的 `configDigest`，`config get` 回读 opt 参数为候选值：

```json
{
  "project": "/home/zhubo/epcd-reltest-0901",
  "instanceId": "20260901024041000",
  "jobId": "1ff2bc7a-1d80-430d-b5f2-774361d5d5f6",
  "applied": true,
  "configDigest": "sha256:077e055746b33fb5b1d8de12905999ec081ec1bf1ac639ecadde764fd43e362a"
}
```

回读 `/device/parameters/opt`（候选值已写入 `value`）：

```json
{
  "trackWidth":  {"value": "12", "min": "6.0",  "max": "20.0", "step": "None", "locked": false, "enabled": true},
  "trackSpace":  {"value": "2",  "min": "1.5",  "max": "5.0",  "step": "None", "locked": true,  "enabled": true},
  "numOfTurns":  {"value": "3.5", "min": "0.25", "max": "8.0",  "step": "@0.25", "locked": false, "enabled": true},
  "innerRadius": {"value": "50", "min": "20.0", "max": "80.0", "step": "None", "locked": false, "enabled": true}
}
```

注意：`config patch` 写 `device.parameters` 仍不持久化（§4.6），但 `config apply-result` 可持久化——二者路径不同，写回正式参数必须用 `apply-result`。

### 4.15 最终正式仿真和 RangeEM 结果

写回后不带 candidate 重新仿真（用写回后 digest）：

```bash
epcd-cli run \
  --project <project-dir> \
  --instance-id <instance-id> \
  --task simulation-evaluation \
  --if-match <post-apply-config-digest> \
  --request-id final-<best-job-id> \
  --wait
```

无 `--input` 表示使用刚写回的正式参数。实测（`--wait` 同步，许可证环境已 source）：响应 `{jobId:"3719f9fc-ede6-4190-a521-46e2cbf9617a", requestId:"final-best", taskType:"simulation-evaluation", status:"succeeded", configDigestUsed:"sha256:077e055746b33fb5b1d8de12905999ec081ec1bf1ac639ecadde764fd43e362a"}`，`requestId` 原样回带。终态 `job result` 为与 §4.12 相同的 `epcd-job/v1` 快照：

- `status:"succeeded"`、`warnings:[]`（EM 仿真成功，无 `SIMULATION_FAILED`）。
- `objectiveCost: 21.75177`、`targetValues` 201 条（L≈2.31nH vs 目标 2.1nH，`satisfied:false`，跨 1.0～3.0 GHz 扫频）。
- artifacts 完整：`gds`+`gtxt`+3×`layout-preview-image`+`gtxt-scene`+`snp`+`target-values`+`target-chart`(svg/png)+`best-result`+`manifest`；`publication` 段含 `synthesis/RangeEM` 目录下的 `gds`+`snp`(`graphs.s2p`)+`snp`(`graphs_sample.s2p`)。
- final run 无候选输入，`parametersUsed` 为 `{}`（预期行为，非异常）；按写回的正式参数（tw12/ts2/nt3.5/ir50）执行，与 §4.11 候选轮结果一致。

**结论：最终正式仿真产出完整 RangeEM 结果（SNP + 目标值 + 图表 + publication），§4.15 成功判据满足。**

## 5. Artifact 规则

每个 Artifact 至少返回：

```json
{
  "type": "gds",
  "path": "/absolute/path/to/file.gds",
  "size": 1214,
  "sha256": "<sha256>",
  "mediaType": "application/octet-stream"
}
```

P0 类型：

| 类型 | 来源 |
| --- | --- |
| `gds` | GDS 文件 |
| `gtxt` | 原始 Gtxt |
| `layout-preview-image` | Gtxt 渲染 PNG |
| `gtxt-scene` | Gtxt 渲染场景 JSON |
| `snp` | Touchstone 文件 |
| `target-values` | 指标明细 JSON |
| `target-chart` | 目标图表 PNG/SVG |
| `best-result` | 最优结果摘要文本 |
| `manifest` | Artifact 清单 JSON |

PNG 渲染失败只产生 warning；GDS、EM、SNP、指标或 objectiveCost 失败使 Job 失败。Manifest 记录产物状态和失败原因。
