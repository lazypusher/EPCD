# EPCD Agent 平台 —— 计划 2：Claude Code 驱动全部后端功能 + 真实环境全流程实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把计划 1 交付的确定性后端（工具层 + Store + 优化控制器）封装成单一 CLI 入口，补齐平台工具（optimization_* / artifact_view）与真实 schema 适配，写 1 个编排 skill，让 Claude Code 经 Bash 驱动，在真实服务器上跑通 M1–M4 全流程（最小预算冒烟：2~3 轮迭代 + 写回 + 最终仿真）。

**Architecture:** 不引入 MCP。所有后端能力收敛为一个 CLI 入口 `python -m epcd_agent.cli <tool>`（stdin JSON 入、stdout 单行 JSON 出、严格退出码），完全镜像 epcd-cli 自身的调用纪律。部署模式仅由配置区分：本机 + ssh 前缀（计划 2）与服务器本地（计划 3），代码零改动。跨进程优化取消经 SQLite Store（kv_state）传递。Claude Code 侧的编排配方放在项目 skill `standard-optimize-flow` 中。

**Tech Stack:** Python 3.11（本机 epcd-agent 包；服务器 epcd-cli 运行时为 3.8，互不干涉）、pytest、Optuna、SQLite、ssh（BatchMode 免密已就绪）。

**Spec:** `c:/Users/cube/Desktop/EPCD/docs/superpowers/specs/2026-08-17-epcd-agent-platform-design.md`（§4 工具层、§5 skill、§7 优化控制器、§8 里程碑、§10 错误处理）。CLI 契约与**实测校正**见 `c:/Users/cube/Desktop/EPCD/agent-demo-command-flow_release.md`（2026-08-20 校正版）。计划 1 交付与边界见 `docs/superpowers/plans/2026-08-17-epcd-agent-plan1-backend-core.md`。

## Global Constraints

- **分支判断只用结构化字段**：`ok`、`errors[].code`、`errors[].path`、退出码；`message` 仅展示，绝不程序分支（spec §4.1 硬规则 1）。
- **身份与摘要自动注入**：`--project` / `--instance-id` / `--if-match` 一律由工具层从 Store 注入，LLM/Claude Code 永不提供（硬规则 2）。
- **关键写操作自动记账**：init/add/patch/apply-result/run 成功后写回 Store（硬规则 3）。
- **CLI 入口纪律**：工具参数经 stdin UTF-8 JSON；stdout 只输出一行 JSON 结果；退出码 0=成功 / 1=工具执行失败或业务错（结构化结果仍在 stdout）/ 2=用法错误（参数缺失、JSON 非法）。
- **ssh argv 规则**：ssh 会把 argv token 以空格拼成一行交给远端 shell；含空格/元字符的完整远端命令必须作为**一个** argv token 传入。现有前缀模式：`("ssh","-o","BatchMode=yes",HOST,"source",PKG+"/user.bashrc.ePCD",">/dev/null","2>&1;","epcd-cli")`。
- **测试命令**：`./.venv/Scripts/python -m pytest tests -q`（Windows）。每个 commit 前全量绿。
- **提交前缀**：feat: / test: / fix: / chore: / docs:。
- **真实服务器事实**：HOST=`zhubo@192.168.20.243`；PKG=`/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default`；demo ptxt=`$PKG/tutorial/command_use/transmission_line/demo.ptxt`；smoke 工程 `/home/zhubo/epcd-agent-smoke`（已有实例 `20260820030940000`）。ssh 输出需过滤 post-quantum 提示：`grep -v "post-quantum\|store now\|may need to be upgraded\|openssh.com"`。
- **验收预算（用户已确认）**：最小预算冒烟——优化 `max_rounds=3`，2~3 轮真实迭代 + apply-result + 最终仿真。目标用模板内置 synth 默认（inductance Equal 2.1、minQFactor Greater 8、maxSize Less 300）。
- **真实 vs release 偏差处置惯例**：修正代码兼容 + release 文档就地校正（原错误内容 HTML 注释保留）。
- **密码纪律**：任何文件/脚本不得出现服务器密码明文；只用免密公钥。

---

## File Structure

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `src/epcd_agent/optimizer/space.py` | 优化空间解析；新增真实嵌套 parameterSchema 解析与 synth 默认目标提取 | 修改 |
| `src/epcd_agent/optimizer/controller.py` | 优化循环；新增跨进程 `cancel_probe` 钩子 | 修改 |
| `src/epcd_agent/platform/__init__.py` | 平台工具包 | 新建 |
| `src/epcd_agent/platform/optimize_tools.py` | `optimization_start/status/cancel`（Store 记账 + kv_state 取消信号） | 新建 |
| `src/epcd_agent/platform/artifact_view.py` | artifact 清单 → 预览卡片；远端拉取到本地缓存 | 新建 |
| `src/epcd_agent/cli.py` | 单一 CLI 入口：dispatcher + 部署配置（ssh/local）+ stdin/stdout 纪律 | 新建 |
| `src/epcd_agent/__main__.py` | `python -m epcd_agent.cli` 支持 | 新建 |
| `.claude/skills/standard-optimize-flow/SKILL.md` | 唯一编排 skill：4.1~4.15 阶段 + M1–M4 确认点 + 异常分支（EPCD 根目录，Claude Code 项目 skill） | 新建 |
| `demo/probe_run_contract.py` | 真实 run/job 契约探针脚本（任务 7 用） | 新建 |
| `docs/plan2-real-run-report.md` | 真实全流程验收报告 | 新建（任务 8） |
| `README.md` | 更新计划 1 边界节（平台工具已落地）+ CLI 入口用法 | 修改（任务 9） |

接口约定（跨任务契约，逐字遵守）：

- `parse_real_parameter_schema(schema: dict) -> ParsedSpace`（space.py）
- `parse_synth_targets(schema: dict) -> tuple[dict, ...]`，每项 `{"metric": str, "comparison": "equal"|"greater-than"|"less-than", "targetValue": float, "unit": ""}`（space.py）
- `OptimizationController(..., cancel_probe: Callable[[], bool] | None = None)`（controller.py）
- `optimization_start(ctx, *, parameter_schema, initial_candidates=(), max_rounds=20, max_wall_seconds=600.0, target_cost=None, request_prefix="iteration") -> ToolResult`
- `optimization_status(ctx, task_id) -> ToolResult`、`optimization_cancel(ctx, task_id) -> ToolResult`
- `artifact_view(ctx, job_id, fetch_dir=None) -> ToolResult`
- CLI 输出信封：`{"ok": bool, "data": <obj|null>, "error": <{"type": str, "message": str}|null>}`
- `build_argv_prefix(ssh_host: str | None, pkg_root: str | None, cli_bin: str = "epcd-cli") -> tuple[str, ...]`

---

### Task 1: 真实嵌套 parameterSchema 解析（opt 变量空间 + synth 默认目标）

**Files:**
- Modify: `src/epcd_agent/optimizer/space.py`
- Test: `tests/test_space.py`

**Interfaces:**
- Consumes: 真实 `device-template describe` 的 `data.parameterSchema`（实测形状见 release §4.3 校正：basic/opt/synth 三组嵌套，default/minimum/maximum/step/enabled 均为字符串，`"None"`=无界，`"@0.25"`=离散步进，逗号分隔串=枚举候选）。
- Produces: `parse_real_parameter_schema(schema: dict) -> ParsedSpace`（仅 opt 组进优化空间）；`parse_synth_targets(schema: dict) -> tuple[dict, ...]`（synth 组 → 默认设计目标，suffix 映射：`Equal→equal`、`Greater→greater-than`、`Less→less-than`）。

真实样例（取证自服务器，测试夹具按此构造）：

```json
{"type":"object","properties":{
  "basic":{"type":"object","properties":{
    "shape":{"default":"Rectangular,Hexagonal,Octagonal,Circular,","minimum":"None","maximum":"None","step":"None","enabled":"1"}}},
  "opt":{"type":"object","properties":{
    "trackWidth":{"minimum":"6.0","maximum":"20.0","step":"None","enabled":"1"},
    "numOfTurns":{"minimum":"0.25","maximum":"8.0","step":"@0.25","enabled":"1"}}},
  "synth":{"type":"object","properties":{
    "inductance":{"default":"2.1","minimum":"None","maximum":"None","step":"None","suffix":"Equal","enabled":"1"},
    "minQFactor":{"default":"8","minimum":"None","maximum":"None","step":"None","suffix":"Greater","enabled":"1"}}}
}}
```

- [ ] **Step 1: 写失败测试（追加到 `tests/test_space.py`）**

```python
from epcd_agent.optimizer.space import (
    parse_real_parameter_schema,
    parse_synth_targets,
)

REAL_SCHEMA = {
    "type": "object",
    "properties": {
        "basic": {"type": "object", "properties": {
            "shape": {"default": "Rectangular,Hexagonal,Octagonal,Circular,",
                      "minimum": "None", "maximum": "None", "step": "None", "enabled": "1"},
        }},
        "opt": {"type": "object", "properties": {
            "trackWidth": {"minimum": "6.0", "maximum": "20.0", "step": "None", "enabled": "1"},
            "numOfTurns": {"minimum": "0.25", "maximum": "8.0", "step": "@0.25", "enabled": "1"},
            "innerRadius": {"minimum": "None", "maximum": "None", "step": "None", "enabled": "1"},
            "shape": {"default": "Rectangular,Circular,",
                      "minimum": "None", "maximum": "None", "step": "None", "enabled": "1"},
        }},
        "synth": {"type": "object", "properties": {
            "inductance": {"default": "2.1", "minimum": "None", "maximum": "None",
                           "step": "None", "suffix": "Equal", "enabled": "1"},
            "minQFactor": {"default": "8", "minimum": "None", "maximum": "None",
                           "step": "None", "suffix": "Greater", "enabled": "1"},
            "maxSize": {"default": "300", "minimum": "None", "maximum": "None",
                        "step": "None", "suffix": "Less", "enabled": "1"},
        }},
    },
}


def test_parse_real_schema_opt_space():
    space = parse_real_parameter_schema(REAL_SCHEMA)
    by = {s.name: s for s in space.specs}
    assert set(by) == {"trackWidth", "numOfTurns", "shape"}
    assert by["trackWidth"].kind == "float"
    assert by["trackWidth"].low == 6.0 and by["trackWidth"].high == 20.0
    assert by["trackWidth"].step is None
    assert by["numOfTurns"].step == 0.25
    assert by["shape"].kind == "categorical"
    assert by["shape"].choices == ("Rectangular", "Circular")
    assert space.unbounded == ("innerRadius",)


def test_parse_real_schema_disabled_param_skipped():
    schema = {"type": "object", "properties": {"opt": {"type": "object", "properties": {
        "w": {"minimum": "1", "maximum": "2", "step": "None", "enabled": "0"}}}}}
    assert parse_real_parameter_schema(schema).specs == ()


def test_parse_synth_targets_from_real_schema():
    targets = parse_synth_targets(REAL_SCHEMA)
    assert targets == (
        {"metric": "inductance", "comparison": "equal", "targetValue": 2.1, "unit": ""},
        {"metric": "minQFactor", "comparison": "greater-than", "targetValue": 8.0, "unit": ""},
        {"metric": "maxSize", "comparison": "less-than", "targetValue": 300.0, "unit": ""},
    )


def test_parse_real_schema_rejects_non_object_root():
    import pytest
    with pytest.raises(ValueError):
        parse_real_parameter_schema({"properties": {}})
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python -m pytest tests/test_space.py -q -k real`
Expected: FAIL（`ImportError: cannot import name 'parse_real_parameter_schema'`）

- [ ] **Step 3: 最小实现（追加到 `space.py` 末尾）**

```python
_SUFFIX_TO_COMPARISON = {"Equal": "equal", "Greater": "greater-than", "Less": "less-than"}


def _to_bound(value) -> float | None:
    """Real builds give bounds as strings; "None" means unbounded."""
    if value is None or str(value).strip() in ("", "None"):
        return None
    return float(value)


def _real_group(schema: dict, group: str) -> dict:
    properties = schema.get("properties") or {}
    node = properties.get(group) or {}
    return node.get("properties") or {}


def parse_real_parameter_schema(schema: dict) -> ParsedSpace:
    """Parse the nested basic/opt/synth parameterSchema observed on real
    server builds (release doc section 4.3 corrected). Only the opt group
    feeds the optimization space; basic/synth are handled elsewhere."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter schema root must be an object schema")
    specs: list[ParamSpec] = []
    unbounded: list[str] = []
    for name, prop in _real_group(schema, "opt").items():
        if not isinstance(prop, dict) or str(prop.get("enabled", "1")) != "1":
            continue
        low, high = _to_bound(prop.get("minimum")), _to_bound(prop.get("maximum"))
        if low is None and high is None:
            default = str(prop.get("default") or "")
            choices = tuple(part for part in (p.strip() for p in default.split(",")) if part)
            if len(choices) >= 2:
                specs.append(ParamSpec(name, "categorical", choices=choices))
            else:
                unbounded.append(name)
            continue
        if low is None or high is None:
            unbounded.append(name)
            continue
        step_raw = str(prop.get("step") or "None").strip()
        step = float(step_raw.lstrip("@")) if step_raw not in ("", "None") else None
        specs.append(ParamSpec(name, "float", low=low, high=high, step=step))
    return ParsedSpace(specs=tuple(specs), unbounded=tuple(unbounded))


def parse_synth_targets(schema: dict) -> tuple[dict, ...]:
    """Default design objectives from the synth group (suffix + default)."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter schema root must be an object schema")
    targets: list[dict] = []
    for name, prop in _real_group(schema, "synth").items():
        if not isinstance(prop, dict) or str(prop.get("enabled", "1")) != "1":
            continue
        comparison = _SUFFIX_TO_COMPARISON.get(str(prop.get("suffix", "")))
        target_value = _to_bound(prop.get("default"))
        if comparison is None or target_value is None:
            continue
        targets.append({"metric": name, "comparison": comparison,
                        "targetValue": target_value, "unit": ""})
    return tuple(targets)
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python -m pytest tests/test_space.py -q`
Expected: PASS（含计划 1 原有用例）

- [ ] **Step 5: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add src/epcd_agent/optimizer/space.py tests/test_space.py
git commit -m "feat: parse real nested parameterSchema (opt space + synth targets)"
```

---

### Task 2: 优化控制器跨进程取消钩子 `cancel_probe`

**Files:**
- Modify: `src/epcd_agent/optimizer/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: 计划 1 的 `OptimizationController`（本轮事实：`__init__(ctx, specs, initial_candidates=(), budget=..., request_prefix="iteration", poll_interval=0.05, on_progress=None, task_id=None)`；取消检查在 `run()` 轮界与 `_poll()` 内用 `self._cancel_requested`）。
- Produces: 新参数 `cancel_probe: Callable[[], bool] | None = None`；探测为真时等价于 `request_cancel()`（stop_reason="canceled"）。供任务 3 传入 Store 探针实现跨进程取消。

- [ ] **Step 1: 写失败测试（追加到 `tests/test_controller.py`；复用文件顶部既有的 `make_ctx` / `submit` / `job_get` / `job_result` / `controller` 工厂与 `SPECS`）**

```python
def test_cancel_probe_stops_loop(tmp_path):
    ctx, calls, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1"), submit("j-2"), submit("j-3")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")] * 3},
        {"argvPrefix": ["job", "result"], "responses": [
            job_result(0.5, "j-1"), job_result(0.4, "j-2"), job_result(0.3, "j-3")]},
    ])
    probe_calls = {"n": 0}

    def probe():
        probe_calls["n"] += 1
        return probe_calls["n"] >= 3  # 第三次探测起请求取消

    c = controller(ctx, budget=OptimizationBudget(max_rounds=5), cancel_probe=probe)
    report = c.run()
    assert report.stop_reason == "canceled"
    assert len(report.rounds) < 5
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python -m pytest tests/test_controller.py -q -k cancel_probe`
Expected: FAIL（`TypeError: unexpected keyword argument 'cancel_probe'`）

- [ ] **Step 3: 最小实现**

`controller.py` 三处修改：

```python
# __init__ 增加参数（放在 task_id 之后）：
    def __init__(self, ctx: ToolContext, specs: Iterable[ParamSpec],
                 initial_candidates: Iterable[dict] = (),
                 budget: OptimizationBudget = OptimizationBudget(),
                 request_prefix: str = "iteration", poll_interval: float = 0.05,
                 on_progress: Callable[[dict], None] | None = None,
                 task_id: str | None = None,
                 cancel_probe: Callable[[], bool] | None = None):
        ...
        self._cancel_probe = cancel_probe
```

```python
# 新增私有方法（request_cancel 之后）：
    def _probe_cancel(self) -> None:
        if not self._cancel_requested and self._cancel_probe is not None:
            if self._cancel_probe():
                self._cancel_requested = True
```

在 `run()` 每轮循环体开头（现有 `if self._cancel_requested:` 检查之前）与 `_poll()` 轮询循环体内（同样在现有检查之前）各插入一行：

```python
            self._probe_cancel()
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python -m pytest tests/test_controller.py -q`
Expected: PASS（含既有取消/预算/恢复用例）

- [ ] **Step 5: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add src/epcd_agent/optimizer/controller.py tests/test_controller.py
git commit -m "feat: OptimizationController cross-process cancel_probe hook"
```

---

### Task 3: 平台工具 `optimization_start/status/cancel`

**Files:**
- Create: `src/epcd_agent/platform/__init__.py`（空文件）
- Create: `src/epcd_agent/platform/optimize_tools.py`
- Test: `tests/test_platform_optimize.py`

**Interfaces:**
- Consumes: `Task 1` 的 `parse_real_parameter_schema`；`Task 2` 的 `cancel_probe`；Store 的 `create_optimization(session_id, task_id, budget)` / `update_optimization(session_id, task_id, *, status=..., ...)` / `get_optimization(session_id, task_id)` / `set_state/get_state`（kv_state）；`OptimizationController` / `OptimizationBudget` / `OptimizationPausedError`。
- Produces: `optimization_start(ctx, *, parameter_schema, initial_candidates=(), max_rounds=20, max_wall_seconds=600.0, target_cost=None, request_prefix="iteration") -> ToolResult`；`optimization_status(ctx, task_id) -> ToolResult`；`optimization_cancel(ctx, task_id) -> ToolResult`。
- 取消协议：`optimization_cancel` 写 `store.set_state(session, f"opt-cancel:{task_id}", True)`；`optimization_start` 传 `cancel_probe=lambda: bool(store.get_state(session, key))`。
- 报告协议：成功 → `ToolResult(ok=True, data={"task_id":..., "report": {...}})`，report 字段 `best_job_id/best_cost/best_parameters/stop_reason/rounds`（rounds 每项 `round_no/request_id/parameters/job_id/status/cost`）；`OptimizationPausedError` → `ToolResult(ok=False, error_code="OPTIMIZATION_PAUSED", message=str(exc), data={"task_id":..., "category": exc.category, "report": ..., "errors": list(exc.errors)})`。

- [ ] **Step 1: 写失败测试 `tests/test_platform_optimize.py`**

```python
import mock_cli
import pytest

from epcd_agent.optimizer.controller import OptimizationBudget
from epcd_agent.platform.optimize_tools import (
    optimization_cancel,
    optimization_start,
    optimization_status,
)
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext

SCHEMA = {
    "type": "object",
    "properties": {
        "opt": {"type": "object", "properties": {
            "trackWidth": {"minimum": "6.0", "maximum": "20.0", "step": "None", "enabled": "1"},
        }},
        "synth": {"type": "object", "properties": {
            "inductance": {"default": "2.1", "minimum": "None", "maximum": "None",
                           "step": "None", "suffix": "Equal", "enabled": "1"},
        }},
    },
}


def ok_envelope(data):
    return {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
            "data": data, "errors": []}


def submit(job_id):
    return {"exitCode": 0, "envelope": ok_envelope({
        "jobId": job_id, "requestId": None,
        "taskType": "simulation-evaluation", "status": "queued"})}


def job_get(status):
    return {"exitCode": 0, "envelope": ok_envelope({"jobId": "ignored", "status": status})}


def job_result(cost, job_id):
    return {"exitCode": 0, "envelope": ok_envelope({
        "jobId": job_id, "taskType": "simulation-evaluation", "status": "succeeded",
        "objectiveCost": cost, "targetValues": [], "warnings": [], "artifacts": []})}


def job_routes(n_jobs):
    """n 轮成功仿真：cost 递减（1/1, 1/2, ...），最后一轮最优。"""
    costs = [1.0 / i for i in range(1, n_jobs + 1)]
    return [
        {"argvPrefix": ["run"], "responses": [submit(f"j-{i}") for i in range(1, n_jobs + 1)]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")] * n_jobs},
        {"argvPrefix": ["job", "result"], "responses": [
            job_result(costs[i - 1], f"j-{i}") for i in range(1, n_jobs + 1)]},
    ]


def make_ctx(tmp_path, routes):
    cli, calls = mock_cli.make_cli(tmp_path, routes)
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    store.set_config_digest("s1", "sha256:d0")
    return ToolContext(cli=cli, store=store, session_id="s1"), store


def test_optimization_start_runs_and_reports(tmp_path):
    ctx, store = make_ctx(tmp_path, job_routes(3))
    r = optimization_start(ctx, parameter_schema=SCHEMA,
                           initial_candidates=[{"trackWidth": 10.0}],
                           max_rounds=3)
    assert r.ok is True
    assert r.data["report"]["stop_reason"] == "budget_rounds"
    assert r.data["report"]["best_job_id"] == "j-3"  # cost 递减，最后一轮最优
    task = store.get_optimization("s1", r.data["task_id"])
    assert task["status"] == "finished"


def test_optimization_start_pause_reports_structured(tmp_path):
    ctx, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [{"exitCode": 5, "envelope": {
            "schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
            "data": None, "errors": [{"code": "BUSINESS_RULE_VIOLATION", "path": None,
                                      "message": "nope"}]}}]},
    ])
    r = optimization_start(ctx, parameter_schema=SCHEMA)
    assert r.ok is False
    assert r.errors[0]["code"] == "OPTIMIZATION_PAUSED"
    assert r.data["category"] == "needs_decision"
    task = store.get_optimization("s1", r.data["task_id"])
    assert task["status"] == "paused"


def test_optimization_cancel_sets_flag_and_status_reads_task(tmp_path):
    ctx, store = make_ctx(tmp_path, job_routes(1))
    store.create_optimization("s1", "opt-1", {"max_rounds": 3})
    assert optimization_cancel(ctx, "opt-1").ok is True
    assert store.get_state("s1", "opt-cancel:opt-1") is True
    st = optimization_status(ctx, "opt-1")
    assert st.ok is True and st.data["task_id"] == "opt-1"
    assert st.data["cancel_requested"] is True
    assert optimization_status(ctx, "nope").ok is False
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python -m pytest tests/test_platform_optimize.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `platform/optimize_tools.py`**

```python
"""Platform tools: optimization_start/status/cancel (design doc section 7).

optimization_start BLOCKS for the whole loop (CLI usage: one call, one
report). Cross-process cancel goes through the Store kv_state.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from epcd_agent.optimizer.controller import (
    OptimizationBudget,
    OptimizationController,
    OptimizationPausedError,
)
from epcd_agent.optimizer.space import parse_real_parameter_schema
from epcd_agent.tools.base import ToolContext, ToolInputError, ToolResult


def _cancel_key(task_id: str) -> str:
    return f"opt-cancel:{task_id}"


def _report_dict(report) -> dict:
    return {
        "best_job_id": report.best_job_id,
        "best_cost": report.best_cost,
        "best_parameters": report.best_parameters,
        "stop_reason": report.stop_reason,
        "rounds": [asdict(r) for r in report.rounds],
    }


def optimization_start(ctx: ToolContext, *, parameter_schema: dict,
                       initial_candidates: Iterable[dict] = (),
                       max_rounds: int = 20, max_wall_seconds: float = 600.0,
                       target_cost: float | None = None,
                       request_prefix: str = "iteration") -> ToolResult:
    space = parse_real_parameter_schema(parameter_schema)
    if not space.specs:
        raise ToolInputError("parameter schema yields no optimizable opt parameters")
    task_id = f"opt-{len(ctx.store.list_jobs(ctx.session_id)) + 1}"
    budget_dict = {"max_rounds": max_rounds, "max_wall_seconds": max_wall_seconds,
                   "target_cost": target_cost}
    ctx.store.create_optimization(ctx.session_id, task_id, budget_dict)
    controller = OptimizationController(
        ctx, space.specs,
        initial_candidates=initial_candidates,
        budget=OptimizationBudget(max_rounds=max_rounds,
                                  max_wall_seconds=max_wall_seconds,
                                  target_cost=target_cost),
        request_prefix=request_prefix,
        task_id=task_id,
        cancel_probe=lambda: bool(ctx.store.get_state(ctx.session_id, _cancel_key(task_id))))
    try:
        report = controller.run()
    except OptimizationPausedError as exc:
        ctx.store.update_optimization(ctx.session_id, task_id, status="paused")
        return ToolResult(ok=False,
                          errors=({"code": "OPTIMIZATION_PAUSED", "path": None,
                                   "message": str(exc)},),
                          category=exc.category,
                          data={"task_id": task_id, "category": exc.category,
                                "report": _report_dict(exc.report),
                                "errors": list(exc.errors)})
    ctx.store.update_optimization(ctx.session_id, task_id, status="finished")
    return ToolResult(ok=True, data={"task_id": task_id, "report": _report_dict(report)})


def optimization_status(ctx: ToolContext, task_id: str) -> ToolResult:
    task = ctx.store.get_optimization(ctx.session_id, task_id)
    if task is None:
        return ToolResult(ok=False,
                          errors=({"code": "OPTIMIZATION_TASK_NOT_FOUND", "path": "/task_id",
                                   "message": f"unknown optimization task: {task_id}"},))
    cancel_flag = bool(ctx.store.get_state(ctx.session_id, _cancel_key(task_id)))
    return ToolResult(ok=True, data={**task, "cancel_requested": cancel_flag})


def optimization_cancel(ctx: ToolContext, task_id: str) -> ToolResult:
    task = ctx.store.get_optimization(ctx.session_id, task_id)
    if task is None:
        return ToolResult(ok=False,
                          errors=({"code": "OPTIMIZATION_TASK_NOT_FOUND", "path": "/task_id",
                                   "message": f"unknown optimization task: {task_id}"},))
    ctx.store.set_state(ctx.session_id, _cancel_key(task_id), True)
    return ToolResult(ok=True, data={"task_id": task_id, "cancel_requested": True})
```

（`ToolResult` 字段为 `ok/data/errors/exit_code/category`——`errors` 是 `{code,path,message}` dict 的元组；与 `tools/base.py` 保持一致。）

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python -m pytest tests/test_platform_optimize.py -q`
Expected: PASS

- [ ] **Step 5: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add src/epcd_agent/platform/ tests/test_platform_optimize.py
git commit -m "feat: platform tools optimization_start/status/cancel with Store-backed cancel"
```

---

### Task 4: 平台工具 `artifact_view`（预览卡片 + 远端拉取）

**Files:**
- Create: `src/epcd_agent/platform/artifact_view.py`
- Test: `tests/test_platform_artifact.py`

**Interfaces:**
- Consumes: `tools/read.py` 的 `epcd_job(ctx, action="result", job_id)`（返回 `data.artifacts` 列表，每项含 `type`/`path`，见 release §5 与 e2e 夹具 FINAL_ARTIFACTS）；`ctx.cli.argv_prefix`（判断是否 ssh 远端模式）。
- Produces: `artifact_view(ctx, job_id, fetch_dir: str | None = None) -> ToolResult`，`data={"job_id":..., "cards":[{type,title,remotePath,localPath|null}]}`。远端模式且给 `fetch_dir` 时，用 `ssh <host> base64 -w0 <remotePath>` 逐个拉取写入 `fetch_dir/<basename>` 并填 `localPath`；本地模式直接 `shutil.copy`。

- [ ] **Step 1: 写失败测试 `tests/test_platform_artifact.py`**

```python
import base64
import pathlib

import mock_cli

from epcd_agent.platform.artifact_view import artifact_view, build_artifact_cards
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext

RESULT_ENVELOPE = {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
                   "data": {"jobId": "j-1", "artifacts": [
                       {"type": "gds", "path": "/abs/proj/out/L1.gds"},
                       {"type": "layout-preview-image", "path": "/abs/proj/out/L1.png"},
                   ]}, "errors": []}


def test_build_cards_titles_and_paths():
    cards = build_artifact_cards(RESULT_ENVELOPE["data"])
    assert cards == [
        {"type": "gds", "title": "GDS", "remotePath": "/abs/proj/out/L1.gds", "localPath": None},
        {"type": "layout-preview-image", "title": "Layout preview",
         "remotePath": "/abs/proj/out/L1.png", "localPath": None},
    ]


def test_artifact_view_local_copy(tmp_path):
    src = tmp_path / "L1.gds"
    src.write_bytes(b"GDSDATA")
    cli, _ = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["job", "result"], "responses": [
            {"exitCode": 0, "envelope": {"schemaVersion": "epcd-response/v1", "ok": True,
             "requestId": None, "data": {"jobId": "j-1", "artifacts": [
                 {"type": "gds", "path": str(src)}]}, "errors": []}}]}])
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    ctx = ToolContext(cli=cli, store=store, session_id="s1")
    fetch = tmp_path / "cache"
    r = artifact_view(ctx, "j-1", fetch_dir=str(fetch))
    assert r.ok is True
    card = r.data["cards"][0]
    assert pathlib.Path(card["localPath"]).read_bytes() == b"GDSDATA"
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python -m pytest tests/test_platform_artifact.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `platform/artifact_view.py`**

```python
"""artifact_view: job result artifacts -> UI-renderable preview cards.

Remote (ssh) deployments fetch artifact bytes into a local cache so the
agent/user side can open them; local deployments just copy.
"""
from __future__ import annotations

import base64
import pathlib
import shutil
import subprocess

from epcd_agent.tools.base import ToolContext, ToolResult
from epcd_agent.tools.read import epcd_job

_TITLES = {
    "gds": "GDS",
    "gtxt": "Gtxt",
    "layout-preview-image": "Layout preview",
    "snp": "S-parameters",
    "objective-values": "Objective values",
    "objective-chart": "Objective chart",
    "manifest": "Manifest",
    "range-em": "RangeEM publication",
}


def build_artifact_cards(job_result_data: dict) -> list[dict]:
    cards = []
    for item in job_result_data.get("artifacts") or []:
        artifact_type = str(item.get("type"))
        cards.append({
            "type": artifact_type,
            "title": _TITLES.get(artifact_type, artifact_type),
            "remotePath": item.get("path"),
            "localPath": None,
        })
    return cards


def _fetch_remote(cli_argv_prefix: tuple, remote_path: str, local_path: pathlib.Path) -> bool:
    """ssh joins argv tokens with spaces; the base64 command must be ONE token.
    Returns False when the fetch fails (card keeps localPath=None)."""
    host = cli_argv_prefix[3]
    proc = subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                           f"base64 -w0 {remote_path}"],
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        return False
    local_path.write_bytes(base64.b64decode(proc.stdout.strip()))
    return True


def artifact_view(ctx: ToolContext, job_id: str, fetch_dir: str | None = None) -> ToolResult:
    result = epcd_job(ctx, action="result", job_id=job_id)
    if not result.ok:
        return result
    cards = build_artifact_cards(result.data or {})
    if fetch_dir:
        target_dir = pathlib.Path(fetch_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        remote_mode = bool(ctx.cli.argv_prefix) and ctx.cli.argv_prefix[0] == "ssh"
        for card in cards:
            remote = card["remotePath"]
            if not remote:
                continue
            # 实测校正：PurePosixPath 在 Windows 上不切分反斜杠路径（.name 返回整串，
            # join 后退化为源文件自身 → SameFileError）；PurePath 平台相关且
            # Windows 版同样认 "/" 分隔，两种路径都正确。
            local = target_dir / pathlib.PurePath(remote).name
            if remote_mode:
                if not _fetch_remote(ctx.cli.argv_prefix, remote, local):
                    continue  # 单件失败不阻塞清单
            else:
                shutil.copy(remote, local)
            card["localPath"] = str(local)
    return ToolResult(ok=True, data={"job_id": job_id, "cards": cards})
```

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python -m pytest tests/test_platform_artifact.py -q`
Expected: PASS

- [ ] **Step 5: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add src/epcd_agent/platform/artifact_view.py tests/test_platform_artifact.py
git commit -m "feat: platform tool artifact_view with local/remote fetch"
```

---

### Task 5: 单一 CLI 入口 `python -m epcd_agent.cli`

**Files:**
- Create: `src/epcd_agent/cli.py`
- Create: `src/epcd_agent/__main__.py`
- Test: `tests/test_cli_entry.py`

**Interfaces:**
- Consumes: 全部工具函数（`tools/read.py`、`tools/write.py`、`tools/config.py`、`platform/optimize_tools.py`、`platform/artifact_view.py`）；`EpcdCli(argv_prefix=...)`；`SessionStore`；`ToolContext(cli=cli, store=store, session_id=...)`。
- Produces:
  - `build_argv_prefix(ssh_host: str | None = None, pkg_root: str | None = None, cli_bin: str = "epcd-cli") -> tuple[str, ...]`
  - `main(argv: list[str], stdin_text: str, build_ctx=...) -> tuple[int, str]`（返回退出码与 stdout 行；测试可注入 ctx 工厂）
  - `python -m epcd_agent.cli [全局选项] <tool> [工具选项]`，工具参数 JSON 走 stdin。
- 全局选项：`--db PATH`（默认 env `EPCD_AGENT_DB` 或 `./epcd-agent-session.sqlite3`）、`--session ID`（默认 env `EPCD_AGENT_SESSION` 或 `default`）、`--ssh HOST`（默认 env `EPCD_SSH_HOST`）、`--pkg PATH`（默认 env `EPCD_PKG_ROOT`）。`--ssh` 与 `--pkg` 必须同时给出（或同时缺省=本地模式）；只给一个 → 退出码 2。
- 输出信封：`{"ok": bool, "data": ..., "error": {"type": ..., "message": ...} | null}` 一行。
- 退出码：0 成功；1 工具返回 `ok=False` 或抛出 `ToolInputError`/Envelope 类业务异常（stdout 仍有结构化信封）；2 用法错误（未知工具、stdin JSON 非法、缺全局参数）。

工具注册表（10 个条目 ↔ 12 个子命令）：

| 子命令 | 目标函数 | stdin JSON 关键字段 |
| --- | --- | --- |
| `epcd_health` | `epcd_health(ctx)` | 无 |
| `epcd_template` | `epcd_template(ctx, action, category?, template_id?)` | `{"action":"list|describe","category"?,"template_id"?}` |
| `epcd_project` | `epcd_project(ctx, action, work_dir?, technology?)` | `{"action":"init|describe|validate","work_dir"?,"technology"?}` |
| `epcd_device` | `epcd_device(ctx, action, template_id?, name?, instance_id?)` | 对应字段 |
| `epcd_config` | `epcd_config(ctx, action, path?, patch_obj?, apply_job_id?)` | 以 `tools/config.py` 现有签名为准 |
| `epcd_formula` | `epcd_formula(ctx, formula)` | `{"formula": {...}}` |
| `epcd_run` | `epcd_run(ctx, task, request_id, input_obj?, use_if_match?, wait?, timeout_seconds?)` | 对应字段 |
| `epcd_job` | `epcd_job(ctx, action, job_id)` | `{"action":"get|result|cancel","job_id":...}` |
| `optimization_start` | 任务 3 | `{"parameter_schema":{...},"initial_candidates":[...],"max_rounds":3,...}` |
| `optimization_status` | 任务 3 | `{"task_id":...}` |
| `optimization_cancel` | 任务 3 | `{"task_id":...}` |
| `artifact_view` | 任务 4 | `{"job_id":...,"fetch_dir":...}` |

- [ ] **Step 1: 写失败测试 `tests/test_cli_entry.py`**

```python
import json

import pytest

from epcd_agent.cli import build_argv_prefix, main


def test_build_argv_prefix_local():
    assert build_argv_prefix() == ("epcd-cli",)


def test_build_argv_prefix_ssh():
    prefix = build_argv_prefix(ssh_host="zhubo@192.168.20.243", pkg_root="/package/PKG")
    assert prefix == (
        "ssh", "-o", "BatchMode=yes", "zhubo@192.168.20.243",
        "source", "/package/PKG/user.bashrc.ePCD", ">/dev/null", "2>&1;", "epcd-cli")


def test_unknown_tool_is_usage_error(tmp_path):
    code, out = main(["--db", str(tmp_path / "s.db"), "nope"], stdin_text="{}")
    assert code == 2
    assert json.loads(out)["error"]["type"] == "USAGE"


def test_invalid_stdin_json_is_usage_error(tmp_path):
    code, out = main(["--db", str(tmp_path / "s.db"), "epcd_health"], stdin_text="not json")
    assert code == 2


def test_ssh_without_pkg_is_usage_error(tmp_path):
    code, out = main(["--db", str(tmp_path / "s.db"), "--ssh", "h", "epcd_health"],
                     stdin_text="{}")
    assert code == 2


def test_tool_result_envelope_and_exit_code(tmp_path):
    # 注入假 ctx 工厂：返回 ok 的 ToolResult
    from epcd_agent.tools.base import ToolResult

    def fake_build_ctx(args):
        class _Ctx:  # 仅本测试使用
            session_id = "default"
        return _Ctx()

    def fake_health(ctx, **kwargs):
        return ToolResult(ok=True, data={"status": "ok"})

    code, out = main(["--db", str(tmp_path / "s.db"), "epcd_health"], stdin_text="{}",
                     build_ctx=fake_build_ctx,
                     registry_override={"epcd_health": fake_health})
    assert code == 0
    doc = json.loads(out)
    assert doc == {"ok": True, "data": {"status": "ok"}, "error": None}
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python -m pytest tests/test_cli_entry.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.cli`）

- [ ] **Step 3: 实现 `cli.py`**

```python
"""Single CLI entry point for every epcd-agent tool.

Usage: python -m epcd_agent.cli [global options] <tool>
Tool arguments: one UTF-8 JSON object on stdin.
stdout: exactly one JSON line: {"ok": bool, "data": ..., "error": ...}.
Exit codes: 0 success; 1 tool/business failure (structured output still on
stdout); 2 usage error. Mirrors epcd-cli's own calling discipline so the
Plan-3 SDK can reuse this entry unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from epcd_agent.cli_client import EpcdCli
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext, ToolInputError, ToolResult
from epcd_agent.tools.read import epcd_health, epcd_template, epcd_formula, epcd_job
from epcd_agent.tools.write import epcd_project, epcd_device, epcd_run
from epcd_agent.tools.config import epcd_config
from epcd_agent.platform.optimize_tools import (
    optimization_cancel, optimization_start, optimization_status)
from epcd_agent.platform.artifact_view import artifact_view


def build_argv_prefix(ssh_host: str | None = None, pkg_root: str | None = None,
                      cli_bin: str = "epcd-cli") -> tuple[str, ...]:
    if ssh_host is None and pkg_root is None:
        return (cli_bin,)
    return ("ssh", "-o", "BatchMode=yes", ssh_host,
            "source", f"{pkg_root}/user.bashrc.ePCD", ">/dev/null", "2>&1;", cli_bin)


def default_registry() -> dict:
    return {
        "epcd_health": lambda ctx, **kw: epcd_health(ctx),
        "epcd_template": epcd_template,
        "epcd_project": epcd_project,
        "epcd_device": epcd_device,
        "epcd_config": epcd_config,
        "epcd_formula": epcd_formula,
        "epcd_run": epcd_run,
        "epcd_job": epcd_job,
        "optimization_start": optimization_start,
        "optimization_status": optimization_status,
        "optimization_cancel": optimization_cancel,
        "artifact_view": artifact_view,
    }


def _build_ctx(args) -> ToolContext:
    prefix = build_argv_prefix(args.ssh, args.pkg)
    cli = EpcdCli(argv_prefix=prefix)
    store = SessionStore(args.db)
    if store.get_session(args.session) is None:  # create_session 非幂等，需先查
        store.create_session(args.session)
    return ToolContext(cli=cli, store=store, session_id=args.session)


def _emit(ok: bool, data=None, error: dict | None = None) -> str:
    return json.dumps({"ok": ok, "data": data, "error": error}, ensure_ascii=False)


def main(argv: list[str], stdin_text: str, build_ctx=None,
         registry_override: dict | None = None) -> tuple[int, str]:
    parser = argparse.ArgumentParser(prog="epcd-agent-cli", add_help=True)
    parser.add_argument("--db", default=os.environ.get(
        "EPCD_AGENT_DB", "epcd-agent-session.sqlite3"))
    parser.add_argument("--session", default=os.environ.get("EPCD_AGENT_SESSION", "default"))
    parser.add_argument("--ssh", default=os.environ.get("EPCD_SSH_HOST"))
    parser.add_argument("--pkg", default=os.environ.get("EPCD_PKG_ROOT"))
    parser.add_argument("tool", nargs="?", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2, _emit(False, error={"type": "USAGE", "message": "bad arguments"})
    if args.tool is None or bool(args.ssh) != bool(args.pkg):
        return 2, _emit(False, error={
            "type": "USAGE",
            "message": "tool name required; --ssh and --pkg must be given together"})
    registry = registry_override or default_registry()
    fn = registry.get(args.tool)
    if fn is None:
        return 2, _emit(False, error={"type": "USAGE",
                                      "message": f"unknown tool: {args.tool}"})
    try:
        kwargs = json.loads(stdin_text) if stdin_text.strip() else {}
        if not isinstance(kwargs, dict):
            raise ValueError("stdin JSON must be an object")
    except (json.JSONDecodeError, ValueError) as exc:
        return 2, _emit(False, error={"type": "USAGE",
                                      "message": f"invalid stdin JSON: {exc}"})
    ctx = (build_ctx or _build_ctx)(args)
    try:
        result = fn(ctx, **kwargs)
    except ToolInputError as exc:
        return 1, _emit(False, error={"type": "ToolInputError", "message": str(exc)})
    except TypeError as exc:
        return 2, _emit(False, error={"type": "USAGE", "message": f"bad tool args: {exc}"})
    if isinstance(result, ToolResult):
        if result.ok:
            return 0, _emit(True, data=result.data)
        first = result.errors[0] if result.errors else {
            "code": "TOOL_FAILED", "path": None, "message": ""}
        return 1, _emit(False, data=result.data, error={
            "type": first.get("code") or "TOOL_FAILED",
            "message": first.get("message") or ""})
    return 1, _emit(False, error={"type": "INTERNAL", "message": "tool returned no result"})


def cli_main() -> None:
    code, out = main(sys.argv[1:], sys.stdin.read())
    sys.stdout.write(out + "\n")
    sys.exit(code)


if __name__ == "__main__":  # 支持 python -m epcd_agent.cli
    cli_main()
```

`src/epcd_agent/__main__.py`：

```python
from epcd_agent.cli import cli_main

if __name__ == "__main__":
    cli_main()
```

实现注意（均为既有代码事实，已体现在上方代码中）：
- `SessionStore.create_session` 是裸 INSERT，对已存在 session 会抛唯一约束错——必须先 `get_session` 判空。
- `ToolResult` 字段为 `ok/data/errors/exit_code/category`（无 `error_code`/`message` 标量字段）；序列化取 `errors[0]`。
- `epcd_run` 的签名为 `(ctx, task, request_id, input_obj=None, use_if_match=False, wait=False, timeout_seconds=None)`，注册表直接透传 `**kwargs` 即可；其余工具同样按各自关键字签名透传。
- 实测校正（执行中发现）：`EpcdCli.exec` 原先只捕获 `TimeoutExpired`；本机无 epcd-cli 时 `subprocess.run` 抛 `FileNotFoundError`，入口纪律被击穿（stderr 出 traceback）。已在 `cli_client.py` 追加 `except OSError` 分支返回 `exit_code=-1` 的结构化失败（与超时同形），并加回归测试 `test_exec_missing_binary_returns_structured_failure`。

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python -m pytest tests/test_cli_entry.py -q`
Expected: PASS

- [ ] **Step 5: 手工冒烟（本地 mock）**

用计划 1 的 mock 当 epcd-cli 替身验证进程级链路（在 epcd-agent 目录）：

```bash
./.venv/Scripts/python -c "import json,subprocess,sys; p=subprocess.run([sys.executable,'-m','epcd_agent.cli','--db','smoke.db','epcd_health'],input='{}',capture_output=True,text=True); print(p.returncode); print(p.stdout); print(p.stderr[-500:])"
```

Expected: 退出码 1（本地无 epcd-cli，工具失败），但 stdout 是单行 JSON 信封、stderr 无 traceback——证明入口纪律成立。（真实 health 冒烟放任务 8。）

- [ ] **Step 6: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add src/epcd_agent/cli.py src/epcd_agent/__main__.py tests/test_cli_entry.py
git commit -m "feat: single CLI entry point for all tools (stdin JSON/stdout JSON/exit codes)"
```

---

### Task 6: 编排 skill `standard-optimize-flow`

**Files:**
- Create: `c:/Users/cube/Desktop/EPCD/.claude/skills/standard-optimize-flow/SKILL.md`

**Interfaces:**
- Consumes: 任务 5 的 CLI 入口与子命令名；release 文档 4.1~4.15 流程与实测校正；spec §8 里程碑。
- Produces: Claude Code 项目 skill——主 Agent（Claude Code 自己）在用户发起设计请求时加载，按阶段调用 CLI 工具，在 M1–M4 用 AskUserQuestion 确认。无单测（文档型交付），验收靠任务 8 实际使用。

- [ ] **Step 1: 写 SKILL.md（frontmatter + 全文）**

```markdown
---
name: standard-optimize-flow
description: EPCD 标准器件设计全流程编排（4.1~4.15 + M1~M4 里程碑确认）。用户用自然语言发起元器件设计（如"设计一个电感"）时使用。
---

# Standard Optimize Flow

用户一句话发起设计后，按下列阶段推进。所有后端调用走单一 CLI 入口
（工作目录 `epcd-agent/`）：

    ./.venv/Scripts/python -m epcd_agent.cli --ssh zhubo@192.168.20.243 \
      --pkg /package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default \
      --db <本地会话db路径> --session <会话名> <tool>
    （工具参数 JSON 经 stdin 传入；stdout 单行 JSON；退出码 0 成功 / 1 业务失败 / 2 用法错误）

## 阶段

1. **健康检查（自主）**：`epcd_health`。`data.status=="degraded"` 时向用户解释并停止。
2. **建工程（自主）**：`epcd_project` init，`{"action":"init","work_dir":"/home/zhubo/epcd-runs/<器件名>","technology":"<pkg>/tutorial/command_use/transmission_line/demo.ptxt"}`；随后 describe + validate。
3. **选型（自主 + M1 确认）**：`epcd_template` list/describe；向用户展示候选模板与关键指标，用 **AskUserQuestion 做 M1 确认**（选定模板 + 实例名；选项：批准/换一个/终止）。确认后 `epcd_device` add。
4. **目标与仿真配置（M2 确认）**：`epcd_config` schema/get 拿配置骨架与 digest；用 `parse_synth_targets` 语义（模板 synth 组 suffix+default）构造 synthesisTargets；配 simulation（em + adaptive sweep 1~3GHz）。把指标/频点/比较方式/权重/扫频/优化预算（默认 max_rounds=3）合并成一张 **AskUserQuestion M2 确认卡**。批准后 `epcd_config` patch 写回（`--if-match` 由工具自动注入，勿手写）。
5. **迭代优化（自主）**：`optimization_start`，stdin 传 `parameter_schema`（describe 原样）、`initial_candidates`（你基于目标推理的 1~2 组起点）、预算。期间用户问进度 → `optimization_status`；喊停 → `optimization_cancel`。`OPTIMIZATION_PAUSED` 时读 `data.errors`/`category` 诊断并询问用户。
6. **写回（M3 确认）**：报告 best cost / 各指标达成情况（**AskUserQuestion M3**），批准后 `epcd_config` apply-result（jobId=best_job_id）。
7. **最终仿真（M4 确认）**：**AskUserQuestion M4** 批准后 `epcd_run` final：不带候选输入、`request_id="final-<best-job-id>"`（if-match 用写回后 digest，工具注入）。
8. **交付**：`artifact_view`（带 fetch_dir）取最终 job 产物卡片；向用户汇报 GDS/版图/SNP/目标值与图表路径。

## 硬规则

- 里程碑 M1~M4 必须 AskUserQuestion 确认，三选项语义：批准 / 修改后批准（对话中改，重构 JSON 重新确认）/ 终止。每次确认的选项与理由在最终验收报告中留痕（Store milestone 表由计划 3 的 SDK 接入层写入）。
- id/digest/jobId 永远取自工具响应；绝不从路径或名字推测。
- 分支只看 `ok`/`error.type`/退出码；`error.message` 只给用户看。
- 同一调用自纠上限 2 次；退出码语义见 release §2/§10。
- 预算：MVP 冒烟 max_rounds=3；用户可覆盖。
```

- [ ] **Step 2: 校验 skill 可发现**

在 Claude Code 会话里确认 `.claude/skills/standard-optimize-flow/SKILL.md` 出现在可用 skill 列表（新会话或 `/skills` 刷新）；frontmatter `name`/`description` 无语法错误。

- [ ] **Step 3: 提交（EPCD 根目录非 git 仓库：skill 文件随平台目录存在即可；在 epcd-agent 仓库内放一份只读副本用于版本化）**

```bash
mkdir -p skills/standard-optimize-flow
cp ../.claude/skills/standard-optimize-flow/SKILL.md skills/standard-optimize-flow/SKILL.md
git add skills/
git commit -m "docs: standard-optimize-flow orchestration skill (versioned copy)"
```

---

### Task 7: 真实 run/job 契约探针与适配

**Files:**
- Create: `demo/probe_run_contract.py`
- Modify（视探针结果）: `src/epcd_agent/tools/write.py`（候选 JSON 形状）、`src/epcd_agent/optimizer/controller.py`（result 字段读取）
- Test（视适配）: `tests/test_tools_write.py` / `tests/test_controller.py` 追加回归
- Modify: `c:/Users/cube/Desktop/EPCD/agent-demo-command-flow_release.md` §4.11/§4.12/§4.14/§4.15（按惯例注释原文 + 实测校正）

**Interfaces:**
- Consumes: 真实服务器 smoke 工程与实例（`/home/zhubo/epcd-agent-smoke`，instance `20260820030940000`，digest 取最新 config get）。
- Produces: 确认或修正三件事——(a) `run --task simulation-evaluation` 的候选 JSON 形状（epcd-candidate/v1 的 `parameters` 是扁平还是按 opt 嵌套）；(b) `job get` / `job result` 的真实字段（status 词表、objectiveCost、targetValues、artifacts）；(c) `config apply-result` 的真实请求/响应形状。

- [ ] **Step 1: 写探针脚本 `demo/probe_run_contract.py`**

脚本结构（与 `demo/smoke_real_flow.py` 同款：ssh argv_prefix + 临时 SessionStore）：

```python
"""Probe the REAL run/job/apply-result contract on the server (Plan 2 Task 7).

Steps: config get (fresh digest) -> run one candidate (request-id probe-1)
-> job get until terminal -> job result -> print raw envelopes; then
config apply-result for that job. Prints every raw envelope for evidence.
"""
from epcd_agent.cli_client import EpcdCli
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext

HOST = "zhubo@192.168.20.243"
PKG = ("/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-"
       "NINECUBE-2026-08-07-linux-x86-64-default")
PROJECT = "/home/zhubo/epcd-agent-smoke"
INSTANCE = "20260820030940000"

cli = EpcdCli(argv_prefix=("ssh", "-o", "BatchMode=yes", HOST,
                           "source", f"{PKG}/user.bashrc.ePCD",
                           ">/dev/null", "2>&1;", "epcd-cli"))
```

步骤：
1. `config get`（--project/--instance-id）→ 打印 digest 与 value 形状。
2. 先试嵌套候选：`run --task simulation-evaluation --input - --if-match <digest> --request-id probe-run-1`，stdin `{"schemaVersion":"epcd-candidate/v1","parameters":{"opt":{"trackWidth":10.0,"trackSpace":2.0,"numOfTurns":3.0,"innerRadius":40.0}}}`。若退出码 2/3/4 或 errors 指向 parameters 形状，再试扁平：`{"schemaVersion":"epcd-candidate/v1","parameters":{"trackWidth":10.0,...}}`。两种都打印原始信封与退出码。
3. 成功的一方：`job get --job-id`（轮询至终态，最长 10 分钟）→ `job result` → 打印全量 data。
4. `config apply-result`：stdin 与参数按 release §4.14 原样试一次，打印信封（失败也记录——形状即证据）。

- [ ] **Step 2: 运行探针并记录证据**

Run: `./.venv/Scripts/python demo/probe_run_contract.py`
Expected: 打印 4 步原始信封；把关键结论（候选形状、status 词表、objectiveCost/targetValues/artifacts 字段名、apply-result 形状）记到任务 8 报告草稿。

- [ ] **Step 3: 按证据适配代码**

若候选形状与计划 1 假设（扁平 `parameters`）不符：修改 `epcd_run`/控制器构造候选处（候选由 `normalize_candidate` 产出扁平 dict → 如需嵌套，在提交点包一层 `{"opt": ...}`），并追加 mock 回归测试断言新 argv/stdin 形状。若 `job result` 字段名与控制器读取不符：修 `_poll`/result 读取处 + 回归。

- [ ] **Step 4: 校正 release 文档**

按既定惯例修正 `agent-demo-command-flow_release.md` §4.11（候选 JSON 形状）、§4.12（job result 字段）、§4.14（apply-result 形状）、§4.15（final run 约定，如实测有偏差）：原错误内容 HTML 注释保留，新增“实测校正（2026-08-XX）”块。EPCD 根目录非 git 仓库，无需提交；epcd-agent 内代码改动随 Step 5 提交。

- [ ] **Step 5: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add demo/probe_run_contract.py src/ tests/
git commit -m "fix: adapt run/job/apply-result handling to real server contract"
```

（若探针证实契约与文档一致、零代码改动，则提交信息改 `chore: verify real run/job contract (no deviation)`，只含探针脚本。）

---

### Task 8: 真实环境端到端冒烟验收（Claude Code 驱动，M1–M4）

**Files:**
- Create: `c:/Users/cube/Desktop/EPCD/epcd-agent/docs/plan2-real-run-report.md`

**Interfaces:**
- Consumes: 任务 1~7 全部产物 + skill `standard-optimize-flow`。
- Produces: 一次真实全流程记录：M1–M4 四次确认、2~3 轮真实迭代、apply-result、final run、artifact_view 交付清单。报告含：每步 CLI 调用与关键响应、里程碑选择、优化轮次表（round/params/cost）、最终 artifacts 清单与本地缓存路径、遇到的偏差与处置。

- [ ] **Step 1: 全新会话准备**

新工程目录 `/home/zhubo/epcd-runs/plan2-acceptance`；本地会话 db `epcd-agent/acceptance.sqlite3`，`--session acceptance`。

- [ ] **Step 2: 按 skill 逐阶段执行（阶段 1~4）**

健康检查 → 建工程（init/describe/validate）→ 模板 list/describe（inductor 类别）→ **M1 AskUserQuestion**（simple_inductor + 实例名）→ device add → config schema/get。每步核对 stdout 信封与 Store 记账（`epcd_config get` 返回 digest 非空）。

- [ ] **Step 3: M2 确认 + 优化（阶段 4~5）**

构造 synthesisTargets（模板 synth 默认：inductance Equal 2.1 / minQFactor Greater 8 / maxSize Less 300）+ simulation（em、adaptive 1~3GHz）→ **M2 AskUserQuestion**（含预算 max_rounds=3）→ patch 写回 → `optimization_start`（initial_candidates 用模板默认语义推理 1~2 组 opt 参数，如 trackWidth 10 / numOfTurns 3 / innerRadius 40）。

- [ ] **Step 4: M3 + 写回（阶段 6）**

读优化报告（best_cost/rounds）→ **M3 AskUserQuestion** → `epcd_config` apply-result（best_job_id）。

- [ ] **Step 5: M4 + 最终仿真 + 交付（阶段 7~8）**

**M4 AskUserQuestion** → final run（`request_id="final-<best-job-id>"`，不带 input）→ `artifact_view`（fetch_dir=`epcd-agent/artifacts-cache/acceptance`）→ 核对 artifacts 类型覆盖（GDS/Gtxt/PNG/SNP/目标值/Manifest，以实际返回为准）。

- [ ] **Step 6: 写验收报告并提交**

`docs/plan2-real-run-report.md`：按上文 Produces 要求记录。失败分支也如实记录（哪个退出码、error code、如何处置）。

```bash
git add docs/plan2-real-run-report.md
git commit -m "docs: Plan 2 real-environment end-to-end acceptance report"
```

---

### Task 9: 文档收口（README / 计划 1 边界 / release 索引）

**Files:**
- Modify: `epcd-agent/README.md`
- Modify: `c:/Users/cube/Desktop/EPCD/agent-demo-command-flow_release.md`（仅当任务 7 未覆盖的收尾）

**Interfaces:**
- Consumes: 任务 1~8 的最终状态。
- Produces: README 反映计划 2 交付（CLI 入口用法、平台工具、skill 位置、远程/本地两种部署模式）；“计划 1 边界”一节改为“计划 2 边界”（SDK 接入、web 前端、多用户属计划 3）。

- [ ] **Step 1: 更新 README**

- 目录树补 `cli.py`、`platform/`、`skills/`。
- 新增“CLI 入口”节：子命令表（任务 5 注册表）、stdin/stdout/退出码纪律、ssh/local 配置（环境变量名）。
- “计划 1 边界”节改写为计划 2 边界：计划 3 = SDK 接入（替换 Claude Code）+ web 前端 + WebSocket/SSE。
- 测试数更新为当前实际值。

- [ ] **Step 2: 全量测试 + 提交**

Run: `./.venv/Scripts/python -m pytest tests -q` → 全绿后：

```bash
git add README.md
git commit -m "docs: Plan 2 deliverables in README (CLI entry, platform tools, boundaries)"
```

- [ ] **Step 3: 计划 2 收官核对**

对照本计划 Global Constraints 与 spec §4/§5/§7/§8 逐条核对：10 个工具条目全部经 CLI 可达；M1–M4 在真实流程中发生；skill 存在且被使用；偏差全部按惯例处置。核对结论写入报告附录。

spec §11 的 golden 对话分支（中途改目标 / 优化中喊停 / 异常诊断）不重复真实环境演练（预算约束）：喊停由控制器取消测试（计划 1 + 任务 2）覆盖，异常暂停由 pause 用例覆盖，中途改目标属对话层行为、由 skill 指引覆盖；计划 3 接入 SDK 后再补对话级 golden 用例。
