# EPCD Agent 平台 —— 计划 1：后端核心 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 epcd-cli 之上构建不依赖 LLM 的后端核心：CLI 调用层、Design Session Store、10 个工具的封装层、确定性 OptimizationController，以及跑通 P0 全流程（4.1~4.15）的 headless 演示与端到端测试。

**Architecture:** Python 包 `epcd_agent`。自底向上四层：`envelope/exitcodes/cli_client`（子进程调用与 `epcd-response/v1` 解析）→ `store`（SQLite 单一事实源）→ `tools/*`（10 个工具条目，身份/摘要自动注入 + 写操作记账）→ `optimizer/*`（Optuna 驱动的确定性优化循环）。全部测试基于 mock epcd-cli 子进程（场景 JSON 驱动），不需要真实 EPCD 环境与 LLM。

**Tech Stack:** Python ≥3.10，SQLite（stdlib `sqlite3`），Optuna ≥3.0（数值优化），pytest ≥8（测试）。无网络、无 LLM 依赖。

**Spec:** `c:/Users/cube/Desktop/EPCD/docs/superpowers/specs/2026-08-17-epcd-agent-platform-design.md`
**接口文档:** `c:/Users/cube/Desktop/EPCD/agent-demo-command-flow_release.md`（下称 release 文档，§2 为调用约定，§4.1~4.15 为流程）

**Claude Agent SDK 对接备注（供计划 2，不影响本计划验收）：** SDK 会话用 `ClaudeAgentOptions(resume=session_id)` 续接（session_id 取自 `ResultMessage.session_id`）；skills 是文件系统产物 `.claude/skills/<name>/SKILL.md`，经 `setting_sources=["user","project"]` + `skills="all"` 加载；自定义工具经 `@tool` + `create_sdk_mcp_server` 进程内注册（`allowed_tools=["mcp__epcd__*"]`）；里程碑确认走内置 AskUserQuestion，经 `can_use_tool` 回调拦截。本计划的 `SessionStore` 与工具函数签名按此对接设计：工具层是纯函数（`ToolContext` 注入），计划 2 只需薄包装成 SDK tool。

## Global Constraints

- Python ≥ 3.10；运行时依赖仅 `optuna`，开发依赖仅 `pytest`。计划 1 不得引入 `claude-agent-sdk`、`anthropic`、任何网络/LLM 依赖。
- 分支判断只用结构化字段：信封 `ok`、`errors[].code`、`errors[].path`、进程退出码。**绝不解析 `message` 文本做程序分支**（release 文档 §2）。
- 结构化输入一律 `--input -` + 向 stdin 写 UTF-8 JSON；禁止临时文件、禁止把 JSON 拼进 shell 字符串（release 文档 §2）。
- `project-dir`/`instanceId`/`templateId`/`digest`/`jobId` 只来自前序命令响应或 Session Store，禁止从名称推测（release 文档 §2）。
- 调用省略 `--format`，使用默认单行紧凑 JSON（release 文档 §2）。
- 提交信息格式：`feat:` / `test:` / `fix:` / `chore:` 前缀 + 英文简述。
- 每个任务结束前必须 `python -m pytest tests -q` 全绿后才能提交。
- 代码风格：stdlib `from __future__ import annotations`；dataclass 优先；不写注释掉的死代码。

## 文件结构

仓库根目录：`c:/Users/cube/Desktop/EPCD/backend/`（任务 1 中 `git init`）。

```
backend/
├── pyproject.toml                 # 包定义 + pytest 配置
├── .gitignore
├── README.md
├── src/epcd_agent/
│   ├── __init__.py                # __version__
│   ├── envelope.py                # epcd-response/v1 信封解析（任务 2）
│   ├── exitcodes.py               # 退出码分类路由（任务 2）
│   ├── cli_client.py              # epcd-cli 子进程封装（任务 3）
│   ├── store.py                   # SessionStore：SQLite 单一事实源（任务 4）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                # ToolResult/ToolContext/注入/分类（任务 5）
│   │   ├── read.py                # epcd_health/epcd_template/epcd_formula/epcd_job（任务 6）
│   │   ├── write.py               # epcd_project/epcd_device/epcd_run + 记账（任务 7）
│   │   └── config.py              # epcd_config：schema/get/patch/apply-result（任务 8）
│   └── optimizer/
│       ├── __init__.py
│       ├── space.py               # 参数空间解析（任务 9）
│       └── controller.py          # OptimizationController 优化循环（任务 10）
├── tests/
│   ├── mock_cli.py                # mock epcd-cli 可执行脚本 + make_cli/read_calls 夹具（任务 3）
│   ├── test_envelope.py           # （任务 2）
│   ├── test_exitcodes.py          # （任务 2）
│   ├── test_cli_client.py         # （任务 3）
│   ├── test_store.py              # （任务 4）
│   ├── test_tools_base.py         # （任务 5）
│   ├── test_tools_read.py         # （任务 6）
│   ├── test_tools_write.py        # （任务 7）
│   ├── test_tools_config.py       # （任务 8）
│   ├── test_space.py              # （任务 9）
│   ├── test_controller.py         # （任务 10）
│   └── test_e2e_flow.py           # 全流程端到端（任务 11）
└── demo/
    └── headless_flow.py           # 无 LLM 全流程演示脚本（任务 11）
```

---

### Task 1: 仓库脚手架

**Files:**
- Create: `backend/pyproject.toml`、`backend/.gitignore`、`backend/README.md`
- Create: `backend/src/epcd_agent/__init__.py`、`backend/src/epcd_agent/tools/__init__.py`、`backend/src/epcd_agent/optimizer/__init__.py`
- Create: `backend/tests/test_scaffold.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: 可安装、可测试的包骨架；后续所有任务的源码/测试目录与 pytest 运行方式（`python -m pytest tests -q`）

- [ ] **Step 1: 初始化仓库**

```bash
mkdir -p c:/Users/cube/Desktop/EPCD/epcd-agent
cd c:/Users/cube/Desktop/EPCD/epcd-agent
git init
git config user.name >/dev/null 2>&1 || git config user.name "EPCD Agent Dev"
git config user.email >/dev/null 2>&1 || git config user.email "dev@epcd.local"
mkdir -p src/epcd_agent/tools src/epcd_agent/optimizer tests demo
```

- [ ] **Step 2: 写 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "epcd-agent"
version = "0.1.0"
description = "EPCD component-design agent backend core (Plan 1, no LLM dependency)"
requires-python = ">=3.10"
dependencies = ["optuna>=3.0"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 写 .gitignore、README.md 与包入口**

`.gitignore`：

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
.venv/
```

`README.md`：

```markdown
# epcd-agent

EPCD 元器件设计 Agent 平台后端核心（计划 1）。
在 epcd-cli 之上提供：CLI 调用层、Design Session Store、工具封装层、确定性优化控制器。
开发：`pip install -e .[dev]`，测试：`python -m pytest tests -q`。
```

`src/epcd_agent/__init__.py`：

```python
"""EPCD agent backend core."""

__version__ = "0.1.0"
```

`src/epcd_agent/tools/__init__.py` 与 `src/epcd_agent/optimizer/__init__.py`：空文件（各写一行 docstring 即可）。

- [ ] **Step 4: 写冒烟测试**

`tests/test_scaffold.py`：

```python
def test_package_importable():
    import epcd_agent

    assert epcd_agent.__version__ == "0.1.0"
```

- [ ] **Step 5: 安装并运行测试**

```bash
cd c:/Users/cube/Desktop/EPCD/epcd-agent
python -m pip install -e ".[dev]"
python -m pytest tests -q
```

Expected: `1 passed`

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml .gitignore README.md src tests/test_scaffold.py
git commit -m "chore: scaffold epcd-agent package"
```

---

### Task 2: 信封解析与退出码分类（envelope.py / exitcodes.py）

**Files:**
- Create: `src/epcd_agent/envelope.py`、`src/epcd_agent/exitcodes.py`
- Test: `tests/test_envelope.py`、`tests/test_exitcodes.py`

**Interfaces:**
- Consumes: 任务 1 的包骨架
- Produces:
  - `envelope.py`：`EnvelopeParseError`（异常）；`EpcdErrorItem(code: str, path: str | None, message: str | None)`；`EpcdResponse(schema_version: str, ok: bool, request_id: str | None, data: dict | None, errors: tuple[EpcdErrorItem, ...])`，方法 `error_codes() -> list[str]`、`has_error_code(code: str) -> bool`；`parse_envelope(stdout: str) -> EpcdResponse`（非法输入抛 `EnvelopeParseError`）。
  - `exitcodes.py`：`classify_exit(exit_code: int) -> str`，返回 `"success" | "agent_retryable" | "needs_decision" | "blocking" | "transient" | "canceled" | "request_id_conflict" | "unknown"`；`LOOP_TRANSIENT_EXIT_CODES: frozenset[int] == frozenset({7, 8, 9})`（优化循环内瞬时错误集合，设计文档 §7.3）。

- [ ] **Step 1: 写信封解析的失败测试**

`tests/test_envelope.py`：

```python
import json

import pytest

from epcd_agent.envelope import (
    EnvelopeParseError,
    EpcdResponse,
    parse_envelope,
)

OK_ENVELOPE = {
    "schemaVersion": "epcd-response/v1",
    "ok": True,
    "requestId": None,
    "data": {"created": True},
    "errors": [],
}


def test_parse_success_envelope():
    resp = parse_envelope(json.dumps(OK_ENVELOPE))
    assert isinstance(resp, EpcdResponse)
    assert resp.schema_version == "epcd-response/v1"
    assert resp.ok is True
    assert resp.request_id is None
    assert resp.data == {"created": True}
    assert resp.errors == ()


def test_parse_failure_envelope_with_errors():
    doc = dict(
        OK_ENVELOPE,
        ok=False,
        data=None,
        errors=[
            {"code": "CONFIG_DIGEST_MISMATCH", "path": "/device", "message": "digest mismatch"},
            {"code": "OTHER", "path": None, "message": None},
        ],
    )
    resp = parse_envelope(json.dumps(doc))
    assert resp.ok is False
    assert resp.data is None
    assert resp.error_codes() == ["CONFIG_DIGEST_MISMATCH", "OTHER"]
    assert resp.has_error_code("CONFIG_DIGEST_MISMATCH") is True
    assert resp.has_error_code("NOPE") is False
    assert resp.errors[0].path == "/device"
    assert resp.errors[0].message == "digest mismatch"


def test_parse_tolerates_surrounding_whitespace():
    resp = parse_envelope("  " + json.dumps(OK_ENVELOPE) + "\n")
    assert resp.ok is True


@pytest.mark.parametrize(
    "bad_stdout",
    [
        "",                                   # 空输出
        "not json at all",                    # 非 JSON
        "[1, 2, 3]",                          # 根不是对象
        json.dumps({"ok": True}),             # 缺 schemaVersion
        json.dumps(dict(OK_ENVELOPE, schemaVersion="epcd-response/v2")),  # 版本不符
        json.dumps(dict(OK_ENVELOPE, ok="yes")),                          # ok 非布尔
        json.dumps(dict(OK_ENVELOPE, errors={"code": "X"})),              # errors 非列表
        json.dumps(dict(OK_ENVELOPE, data="plain")),                      # data 非对象
    ],
)
def test_parse_rejects_invalid_envelope(bad_stdout):
    with pytest.raises(EnvelopeParseError):
        parse_envelope(bad_stdout)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_envelope.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.envelope`）

- [ ] **Step 3: 实现 envelope.py**

```python
"""epcd-response/v1 envelope parsing (release doc section 2)."""
from __future__ import annotations

import json
from dataclasses import dataclass

ENVELOPE_SCHEMA = "epcd-response/v1"


class EnvelopeParseError(Exception):
    """stdout is not a valid epcd-response/v1 envelope."""


@dataclass(frozen=True)
class EpcdErrorItem:
    code: str
    path: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class EpcdResponse:
    schema_version: str
    ok: bool
    request_id: str | None = None
    data: dict | None = None
    errors: tuple[EpcdErrorItem, ...] = ()

    def error_codes(self) -> list[str]:
        return [e.code for e in self.errors]

    def has_error_code(self, code: str) -> bool:
        return any(e.code == code for e in self.errors)


def parse_envelope(stdout: str) -> EpcdResponse:
    text = stdout.strip()
    if not text:
        raise EnvelopeParseError("empty stdout: no envelope")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EnvelopeParseError(f"stdout is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise EnvelopeParseError("envelope root must be a JSON object")
    schema = doc.get("schemaVersion")
    if schema != ENVELOPE_SCHEMA:
        raise EnvelopeParseError(f"unexpected schemaVersion: {schema!r}")
    if not isinstance(doc.get("ok"), bool):
        raise EnvelopeParseError("envelope.ok missing or not a boolean")
    errors_raw = doc.get("errors") or []
    if not isinstance(errors_raw, list):
        raise EnvelopeParseError("envelope.errors must be a list")
    errors = tuple(
        EpcdErrorItem(code=str(item.get("code")), path=item.get("path"), message=item.get("message"))
        for item in errors_raw
    )
    data = doc.get("data")
    if data is not None and not isinstance(data, dict):
        raise EnvelopeParseError("envelope.data must be an object or null")
    return EpcdResponse(
        schema_version=schema,
        ok=doc["ok"],
        request_id=doc.get("requestId"),
        data=data,
        errors=errors,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_envelope.py -q`
Expected: PASS（11 个用例）

- [ ] **Step 5: 写退出码分类的失败测试**

`tests/test_exitcodes.py`：

```python
import pytest

from epcd_agent.exitcodes import LOOP_TRANSIENT_EXIT_CODES, classify_exit


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "success"),
        (2, "agent_retryable"),
        (3, "agent_retryable"),
        (4, "agent_retryable"),
        (5, "needs_decision"),
        (6, "blocking"),
        (7, "blocking"),
        (8, "transient"),
        (9, "transient"),
        (10, "canceled"),
        (11, "request_id_conflict"),
        (1, "unknown"),
        (99, "unknown"),
        (-1, "unknown"),
    ],
)
def test_classify_exit(code, expected):
    assert classify_exit(code) == expected


def test_loop_transient_set():
    # design doc section 7.3: within the optimization loop,
    # exit codes 7/8/9 are retried once with the same requestId.
    assert LOOP_TRANSIENT_EXIT_CODES == frozenset({7, 8, 9})
```

- [ ] **Step 6: 运行确认失败**

Run: `python -m pytest tests/test_exitcodes.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.exitcodes`）

- [ ] **Step 7: 实现 exitcodes.py**

```python
"""Exit-code routing (design doc section 10, release doc section 2)."""
from __future__ import annotations

SUCCESS = 0

_CATEGORIES: dict[int, str] = {
    0: "success",
    2: "agent_retryable",    # command argument error: agent fixes input and retries
    3: "agent_retryable",    # JSON/YAML input format error
    4: "agent_retryable",    # schema validation error
    5: "needs_decision",     # business rule error: escalate to user decision
    6: "blocking",           # technology error
    7: "blocking",           # license unavailable: blocking at conversation layer
    8: "transient",          # GDS/simulation execution failure
    9: "transient",          # result write failure
    10: "canceled",
    11: "request_id_conflict",
}

# Within the optimization loop (design doc section 7.3) exit codes 7/8/9 are
# all treated as transient: retry once with the identical requestId.
LOOP_TRANSIENT_EXIT_CODES = frozenset({7, 8, 9})


def classify_exit(exit_code: int) -> str:
    return _CATEGORIES.get(exit_code, "unknown")
```

- [ ] **Step 8: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 9: 提交**

```bash
git add src/epcd_agent/envelope.py src/epcd_agent/exitcodes.py tests/test_envelope.py tests/test_exitcodes.py
git commit -m "feat: parse epcd-response/v1 envelope and classify exit codes"
```

---

### Task 3: mock epcd-cli 夹具与子进程客户端（mock_cli.py / cli_client.py）

**Files:**
- Create: `tests/mock_cli.py`、`src/epcd_agent/cli_client.py`
- Test: `tests/test_cli_client.py`

**Interfaces:**
- Consumes: 任务 2 的 `parse_envelope` / `EpcdResponse`
- Produces:
  - `cli_client.py`：`ExecResult(exit_code: int, response: EpcdResponse | None, stdout: str, stderr: str, timed_out: bool = False, parse_error: str | None = None)`；`EpcdCli(argv_prefix: Sequence[str] = ("epcd-cli",), default_timeout: float = 120.0)`，方法 `exec(args: Sequence[str], stdin_obj: Any = None, timeout: float | None = None) -> ExecResult`（stdin_obj 非 None 时序列化为 UTF-8 JSON 写入 stdin；超时返回 `timed_out=True, exit_code=-1`；stdout 无法解析为信封时 `response=None, parse_error=<原因>`）。
  - `tests/mock_cli.py`：可独立执行的 mock epcd-cli（由 `$MOCLI_SCENARIO` 场景文件驱动，每次调用追加一行 JSON 到 `$MOCLI_CALLS`），以及测试夹具函数 `make_cli(tmp_path, routes) -> tuple[EpcdCli, Path]`（返回指向 mock 的客户端与调用日志路径）和 `read_calls(calls_path) -> list[dict]`。

**mock 场景格式**（后续所有任务测试复用）：

```json
{
  "routes": [
    {
      "argvPrefix": ["config", "patch"],
      "responses": [
        {"exitCode": 0, "envelope": {"schemaVersion": "epcd-response/v1", "ok": true, "requestId": null, "data": {}, "errors": []}, "sleepSeconds": 0}
      ]
    }
  ]
}
```

匹配规则：取 `argvPrefix` 是实际 argv 最长前缀的 route；每次调用弹出该 route 队列首个 response；队列空则退出码 97（让测试大声失败）。`sleepSeconds` 可选，用于超时测试。

- [ ] **Step 1: 写 mock_cli.py（测试基础设施，先于被测代码）**

`tests/mock_cli.py`：

```python
"""Mock epcd-cli: scenario-driven stand-in for the real binary.

Run directly: python tests/mock_cli.py <args...>
Env:
  MOCLI_SCENARIO  path to scenario JSON (routes with response queues)
  MOCLI_CALLS     path to JSONL call log (argv + stdin per call)

Also importable by tests for the make_cli/read_calls fixtures.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    stdin_text = sys.stdin.read()
    calls_path = os.environ.get("MOCLI_CALLS")
    if calls_path:
        try:
            stdin_obj = json.loads(stdin_text) if stdin_text.strip() else None
        except json.JSONDecodeError:
            stdin_obj = stdin_text
        with open(calls_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": args, "stdin": stdin_obj}, ensure_ascii=False) + "\n")

    def emit(code: str, message: str, exit_code: int) -> int:
        print(json.dumps({
            "schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
            "data": None, "errors": [{"code": code, "path": None, "message": message}],
        }, ensure_ascii=False))
        return exit_code

    scenario_path = os.environ.get("MOCLI_SCENARIO")
    if not scenario_path:
        return emit("MOCLI_NO_SCENARIO", "no scenario file configured", 96)
    with open(scenario_path, encoding="utf-8") as f:
        scenario = json.load(f)

    best = None
    for route in scenario["routes"]:
        prefix = route["argvPrefix"]
        if args[: len(prefix)] == prefix and (best is None or len(prefix) > len(best["argvPrefix"])):
            best = route
    if best is None:
        return emit("MOCLI_NO_ROUTE", f"no route matches argv {args}", 96)

    responses = best["responses"]
    if not responses:
        return emit("MOCLI_QUEUE_EMPTY", f"route {best['argvPrefix']} exhausted", 97)

    entry = responses.pop(0)
    with open(scenario_path, "w", encoding="utf-8") as f:
        json.dump(scenario, f, ensure_ascii=False)

    sleep_s = entry.get("sleepSeconds")
    if sleep_s:
        time.sleep(sleep_s)
    if entry.get("envelope") is not None:
        print(json.dumps(entry["envelope"], ensure_ascii=False))
    return int(entry.get("exitCode", 0))


# ---- test fixtures (imported by test modules) -------------------------------

from epcd_agent.cli_client import EpcdCli  # noqa: E402

MOCK_PATH = pathlib.Path(__file__).resolve().parent / "mock_cli.py"


def make_cli(tmp_path, routes):
    """Create an EpcdCli pointed at the mock, driven by a scenario file.

    Returns (cli, calls_path). Sets MOCLI_SCENARIO / MOCLI_CALLS in os.environ;
    each test that calls make_cli reconfigures both variables.
    """
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(json.dumps({"routes": routes}, ensure_ascii=False), encoding="utf-8")
    calls_path = tmp_path / "calls.jsonl"
    os.environ["MOCLI_SCENARIO"] = str(scenario_path)
    os.environ["MOCLI_CALLS"] = str(calls_path)
    return EpcdCli(argv_prefix=(sys.executable, str(MOCK_PATH))), calls_path


def read_calls(calls_path):
    path = pathlib.Path(calls_path)
    if not path.exists():  # the mock was never invoked
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
```

- [ ] **Step 2: 写 cli_client 的失败测试**

`tests/test_cli_client.py`：

```python
import mock_cli

OK = {
    "schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
    "data": {"status": "ok"}, "errors": [],
}


def test_exec_success_parses_envelope(tmp_path):
    cli, calls = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["health"], "responses": [{"exitCode": 0, "envelope": OK}]},
    ])
    result = cli.exec(["health"])
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.parse_error is None
    assert result.response is not None and result.response.ok is True
    assert result.response.data == {"status": "ok"}
    assert mock_cli.read_calls(calls) == [{"argv": ["health"], "stdin": None}]


def test_exec_writes_stdin_json(tmp_path):
    cli, calls = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["config", "patch"], "responses": [{"exitCode": 0, "envelope": OK}]},
    ])
    payload = {"device": {"parameters": {"width": 12}}}
    result = cli.exec(["config", "patch", "--input", "-"], stdin_obj=payload)
    assert result.exit_code == 0
    recorded = mock_cli.read_calls(calls)[0]
    assert recorded["stdin"] == payload


def test_exec_propagates_nonzero_exit_and_failure_envelope(tmp_path):
    fail_envelope = {
        "schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
        "data": None, "errors": [{"code": "CONFIG_DIGEST_MISMATCH", "path": None, "message": "m"}],
    }
    cli, _ = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["config", "patch"], "responses": [{"exitCode": 4, "envelope": fail_envelope}]},
    ])
    result = cli.exec(["config", "patch"], stdin_obj={})
    assert result.exit_code == 4
    assert result.response is not None
    assert result.response.ok is False
    assert result.response.has_error_code("CONFIG_DIGEST_MISMATCH")


def test_exec_unparseable_stdout_sets_parse_error(tmp_path):
    cli, _ = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["version"], "responses": [{"exitCode": 0, "envelope": None}]},
    ])
    result = cli.exec(["version"])
    assert result.exit_code == 0
    assert result.response is None
    assert result.parse_error is not None


def test_exec_timeout(tmp_path):
    cli, _ = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["job", "get"],
         "responses": [{"exitCode": 0, "envelope": OK, "sleepSeconds": 5}]},
    ])
    result = cli.exec(["job", "get", "--id", "j-1"], timeout=0.3)
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.response is None
```

- [ ] **Step 3: 运行确认失败**

Run: `python -m pytest tests/test_cli_client.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.cli_client`）

- [ ] **Step 4: 实现 cli_client.py**

```python
"""epcd-cli subprocess wrapper (release doc section 2 calling conventions)."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence

from .envelope import EnvelopeParseError, EpcdResponse, parse_envelope


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    response: EpcdResponse | None
    stdout: str
    stderr: str
    timed_out: bool = False
    parse_error: str | None = None


def _as_text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


class EpcdCli:
    """Runs epcd-cli as a subprocess.

    argv_prefix lets tests point the client at the mock
    (e.g. (sys.executable, "tests/mock_cli.py")).
    """

    def __init__(self, argv_prefix: Sequence[str] = ("epcd-cli",), default_timeout: float = 120.0):
        self.argv_prefix = tuple(argv_prefix)
        self.default_timeout = default_timeout

    def exec(
        self,
        args: Sequence[str],
        stdin_obj: Any = None,
        timeout: float | None = None,
    ) -> ExecResult:
        argv = list(self.argv_prefix) + list(args)
        stdin_bytes = (
            json.dumps(stdin_obj, ensure_ascii=False).encode("utf-8")
            if stdin_obj is not None
            else None
        )
        effective_timeout = timeout if timeout is not None else self.default_timeout
        try:
            proc = subprocess.run(argv, input=stdin_bytes, capture_output=True, timeout=effective_timeout)
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                exit_code=-1,
                response=None,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                timed_out=True,
            )
        stdout = _as_text(proc.stdout)
        stderr = _as_text(proc.stderr)
        try:
            response: EpcdResponse | None = parse_envelope(stdout)
            parse_error = None
        except EnvelopeParseError as exc:
            response, parse_error = None, str(exc)
        return ExecResult(
            exit_code=proc.returncode,
            response=response,
            stdout=stdout,
            stderr=stderr,
            parse_error=parse_error,
        )
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add tests/mock_cli.py tests/test_cli_client.py src/epcd_agent/cli_client.py
git commit -m "feat: subprocess cli client with scenario-driven mock harness"
```

---

### Task 4: Design Session Store（store.py）

**Files:**
- Create: `src/epcd_agent/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: 任务 1 包骨架
- Produces: `SessionStore(db_path: str | Path)`，SQLite 单一事实源（设计文档 §9）。全部方法：
  - `create_session(session_id: str, model_config: dict | None = None) -> None`
  - `get_session(session_id: str) -> dict | None`（键：`session_id, created_at, model_config`）
  - `set_project(session_id, project_dir: str, lib_name: str | None = None, technology_digest: str | None = None)`；`get_project(session_id) -> dict | None`（键：`project_dir, lib_name, technology_digest`）
  - `upsert_instance(session_id, instance_id, *, template_id, name, project_dir)`；`set_active_instance(session_id, instance_id)`；`get_active_instance(session_id) -> dict | None`（键：`instance_id, template_id, name, project_dir, config_digest`）
  - `set_config_digest(session_id, digest: str)`；`get_config_digest(session_id) -> str | None`
  - `add_job(session_id, job_id, *, request_id, task_type, status, parameters: dict | None = None)`；`update_job(session_id, job_id, *, status: str | None = None, objective_cost: float | None = None, started_at: str | None = None, finished_at: str | None = None)`；`get_job(session_id, job_id) -> dict | None`；`list_jobs(session_id) -> list[dict]`；`find_job_by_request(session_id, request_id: str) -> dict | None`（job dict 键：`session_id, job_id, request_id, task_type, status, parameters, objective_cost, started_at, finished_at`，其中 `parameters` 已反序列化为 dict/None）
  - `create_optimization(session_id, task_id, budget: dict)`；`update_optimization(session_id, task_id, *, status: str | None = None, best_job_id: str | None = None, rounds: list | None = None, consumed: dict | None = None)`；`get_optimization(session_id, task_id) -> dict | None`（键：`task_id, status, budget, consumed, best_job_id, rounds`）
  - `record_milestone(session_id, name: str, choice: str, snapshot: dict | None = None)`；`list_milestones(session_id) -> list[dict]`（键：`name, choice, snapshot, recorded_at`，按记录顺序）
  - `set_state(session_id, key: str, value: Any)`；`get_state(session_id, key: str, default: Any = None)`（任意 JSON 值）
  - 时间戳：全部 UTC ISO8601 字符串（`_utc_now()` 内部函数）。

- [ ] **Step 1: 写失败测试**

`tests/test_store.py`：

```python
import pytest

from epcd_agent.store import SessionStore


@pytest.fixture()
def store(tmp_path):
    return SessionStore(tmp_path / "store.sqlite3")


def test_session_roundtrip(store):
    store.create_session("s1", model_config={"model": "claude-x"})
    s = store.get_session("s1")
    assert s["session_id"] == "s1"
    assert s["model_config"] == {"model": "claude-x"}
    assert s["created_at"]
    assert store.get_session("missing") is None


def test_project_roundtrip(store):
    store.create_session("s1")
    assert store.get_project("s1") is None
    store.set_project("s1", "/abs/proj", lib_name="demo", technology_digest="sha256:t")
    p = store.get_project("s1")
    assert p == {"project_dir": "/abs/proj", "lib_name": "demo", "technology_digest": "sha256:t"}


def test_instance_and_active_selection(store):
    store.create_session("s1")
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="system.inductor.simple_inductor",
                          name="simple_inductor1", project_dir="/abs/proj")
    store.upsert_instance("s1", "m-2", template_id="system.inductor.simple_inductor",
                          name="simple_inductor2", project_dir="/abs/proj")
    assert store.get_active_instance("s1") is None
    store.set_active_instance("s1", "m-2")
    inst = store.get_active_instance("s1")
    assert inst["instance_id"] == "m-2"
    assert inst["template_id"] == "system.inductor.simple_inductor"
    assert inst["config_digest"] is None
    # upsert keeps active pointer and updates fields in place
    store.upsert_instance("s1", "m-2", template_id="system.inductor.simple_inductor",
                          name="renamed", project_dir="/abs/proj")
    assert store.get_active_instance("s1")["name"] == "renamed"


def test_config_digest_roundtrip(store):
    store.create_session("s1")
    assert store.get_config_digest("s1") is None
    store.set_config_digest("s1", "sha256:d1")
    assert store.get_config_digest("s1") == "sha256:d1"
    store.set_config_digest("s1", "sha256:d2")
    assert store.get_config_digest("s1") == "sha256:d2"


def test_job_lifecycle(store):
    store.create_session("s1")
    store.add_job("s1", "j-1", request_id="iteration-1", task_type="simulation-evaluation",
                  status="queued", parameters={"width": 11})
    assert store.get_job("s1", "j-1")["status"] == "queued"
    store.update_job("s1", "j-1", status="succeeded", objective_cost=0.15,
                     started_at="t0", finished_at="t1")
    job = store.get_job("s1", "j-1")
    assert job["status"] == "succeeded"
    assert job["objective_cost"] == pytest.approx(0.15)
    assert job["parameters"] == {"width": 11}
    assert job["started_at"] == "t0" and job["finished_at"] == "t1"
    assert store.find_job_by_request("s1", "iteration-1")["job_id"] == "j-1"
    assert store.find_job_by_request("s1", "iteration-9") is None
    store.add_job("s1", "j-2", request_id="iteration-2", task_type="simulation-evaluation",
                  status="queued")
    assert [j["job_id"] for j in store.list_jobs("s1")] == ["j-1", "j-2"]


def test_optimization_task_roundtrip(store):
    store.create_session("s1")
    store.create_optimization("s1", "opt-1", budget={"max_rounds": 10})
    task = store.get_optimization("s1", "opt-1")
    assert task["status"] == "pending"
    assert task["budget"] == {"max_rounds": 10}
    store.update_optimization("s1", "opt-1", status="running", rounds=[{"round": 1}])
    store.update_optimization("s1", "opt-1", best_job_id="j-3", consumed={"rounds": 1})
    task = store.get_optimization("s1", "opt-1")
    assert task["status"] == "running"
    assert task["best_job_id"] == "j-3"
    assert task["rounds"] == [{"round": 1}]
    assert task["consumed"] == {"rounds": 1}
    assert store.get_optimization("s1", "missing") is None


def test_milestones_ordered(store):
    store.create_session("s1")
    store.record_milestone("s1", "M1", "approved", snapshot={"templateId": "t"})
    store.record_milestone("s1", "M2", "approved_with_changes")
    rows = store.list_milestones("s1")
    assert [r["name"] for r in rows] == ["M1", "M2"]
    assert rows[0]["choice"] == "approved"
    assert rows[0]["snapshot"] == {"templateId": "t"}
    assert rows[1]["snapshot"] is None
    assert rows[0]["recorded_at"]


def test_kv_state_roundtrip(store):
    store.create_session("s1")
    assert store.get_state("s1", "k") is None
    assert store.get_state("s1", "k", default=7) == 7
    store.set_state("s1", "k", {"nested": [1, 2]})
    assert store.get_state("s1", "k") == {"nested": [1, 2]}
    store.set_state("s1", "k", "replaced")
    assert store.get_state("s1", "k") == "replaced"


def test_sessions_isolated(store):
    store.create_session("s1")
    store.create_session("s2")
    store.set_project("s1", "/p1")
    store.set_project("s2", "/p2")
    assert store.get_project("s1")["project_dir"] == "/p1"
    assert store.get_project("s2")["project_dir"] == "/p2"


def test_store_persists_across_instances(tmp_path):
    db = tmp_path / "store.sqlite3"
    first = SessionStore(db)
    first.create_session("s1")
    first.set_project("s1", "/abs/proj")
    second = SessionStore(db)
    assert second.get_project("s1")["project_dir"] == "/abs/proj"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_store.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.store`）

- [ ] **Step 3: 实现 store.py**

```python
"""Design Session Store: single source of truth outside the LLM (design doc section 9)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
    session_id     TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    model_config   TEXT
);
CREATE TABLE IF NOT EXISTS instance (
    session_id    TEXT NOT NULL,
    instance_id   TEXT NOT NULL,
    project_dir   TEXT NOT NULL,
    template_id   TEXT,
    name          TEXT,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, instance_id)
);
CREATE TABLE IF NOT EXISTS job (
    session_id      TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    request_id      TEXT,
    task_type       TEXT,
    status          TEXT,
    parameters      TEXT,
    objective_cost  REAL,
    started_at      TEXT,
    finished_at     TEXT,
    PRIMARY KEY (session_id, job_id)
);
CREATE TABLE IF NOT EXISTS optimization_task (
    session_id   TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    status       TEXT NOT NULL,
    budget       TEXT,
    consumed     TEXT,
    best_job_id  TEXT,
    rounds       TEXT,
    PRIMARY KEY (session_id, task_id)
);
CREATE TABLE IF NOT EXISTS milestone (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    choice       TEXT NOT NULL,
    snapshot     TEXT,
    recorded_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_info (
    session_id          TEXT PRIMARY KEY,
    project_dir         TEXT NOT NULL,
    lib_name            TEXT,
    technology_digest   TEXT
);
CREATE TABLE IF NOT EXISTS kv_state (
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT,
    PRIMARY KEY (session_id, key)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def _loads(text: str | None) -> Any:
    return None if text is None else json.loads(text)


class SessionStore:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- session ---------------------------------------------------------
    def create_session(self, session_id: str, model_config: dict | None = None) -> None:
        self._conn.execute(
            "INSERT INTO session (session_id, created_at, model_config) VALUES (?, ?, ?)",
            (session_id, _utc_now(), _dumps(model_config)),
        )
        self._conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM session WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "model_config": _loads(row["model_config"]),
        }

    # -- project ---------------------------------------------------------
    def set_project(self, session_id: str, project_dir: str,
                    lib_name: str | None = None, technology_digest: str | None = None) -> None:
        self._conn.execute(
            """INSERT INTO project_info (session_id, project_dir, lib_name, technology_digest)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 project_dir = excluded.project_dir,
                 lib_name = excluded.lib_name,
                 technology_digest = excluded.technology_digest""",
            (session_id, project_dir, lib_name, technology_digest),
        )
        self._conn.commit()

    def get_project(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM project_info WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "project_dir": row["project_dir"],
            "lib_name": row["lib_name"],
            "technology_digest": row["technology_digest"],
        }

    # -- instance --------------------------------------------------------
    def upsert_instance(self, session_id: str, instance_id: str, *,
                        template_id: str | None, name: str | None, project_dir: str) -> None:
        self._conn.execute(
            """INSERT INTO instance (session_id, instance_id, project_dir, template_id, name, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, instance_id) DO UPDATE SET
                 project_dir = excluded.project_dir,
                 template_id = excluded.template_id,
                 name = excluded.name""",
            (session_id, instance_id, project_dir, template_id, name, _utc_now()),
        )
        self._conn.commit()

    def set_active_instance(self, session_id: str, instance_id: str) -> None:
        self.set_state(session_id, "active_instance_id", instance_id)

    def get_active_instance(self, session_id: str) -> dict | None:
        instance_id = self.get_state(session_id, "active_instance_id")
        if not instance_id:
            return None
        row = self._conn.execute(
            "SELECT * FROM instance WHERE session_id = ? AND instance_id = ?",
            (session_id, instance_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "instance_id": row["instance_id"],
            "template_id": row["template_id"],
            "name": row["name"],
            "project_dir": row["project_dir"],
            "config_digest": self.get_config_digest(session_id),
        }

    # -- config digest ----------------------------------------------------
    def set_config_digest(self, session_id: str, digest: str) -> None:
        self.set_state(session_id, "config_digest", digest)

    def get_config_digest(self, session_id: str) -> str | None:
        return self.get_state(session_id, "config_digest")

    # -- jobs -------------------------------------------------------------
    def add_job(self, session_id: str, job_id: str, *, request_id: str | None,
                task_type: str, status: str, parameters: dict | None = None) -> None:
        self._conn.execute(
            """INSERT INTO job (session_id, job_id, request_id, task_type, status, parameters)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, job_id, request_id, task_type, status, _dumps(parameters)),
        )
        self._conn.commit()

    def update_job(self, session_id: str, job_id: str, *, status: str | None = None,
                   objective_cost: float | None = None,
                   started_at: str | None = None, finished_at: str | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if objective_cost is not None:
            fields.append("objective_cost = ?")
            values.append(objective_cost)
        if started_at is not None:
            fields.append("started_at = ?")
            values.append(started_at)
        if finished_at is not None:
            fields.append("finished_at = ?")
            values.append(finished_at)
        if not fields:
            return
        values.extend([session_id, job_id])
        self._conn.execute(
            f"UPDATE job SET {', '.join(fields)} WHERE session_id = ? AND job_id = ?", values
        )
        self._conn.commit()

    def _job_row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "job_id": row["job_id"],
            "request_id": row["request_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "parameters": _loads(row["parameters"]),
            "objective_cost": row["objective_cost"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def get_job(self, session_id: str, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM job WHERE session_id = ? AND job_id = ?", (session_id, job_id)
        ).fetchone()
        return self._job_row(row)

    def list_jobs(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM job WHERE session_id = ? ORDER BY rowid", (session_id,)
        ).fetchall()
        return [self._job_row(r) for r in rows]

    def find_job_by_request(self, session_id: str, request_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM job WHERE session_id = ? AND request_id = ? ORDER BY rowid LIMIT 1",
            (session_id, request_id),
        ).fetchone()
        return self._job_row(row)

    # -- optimization tasks -----------------------------------------------
    def create_optimization(self, session_id: str, task_id: str, budget: dict) -> None:
        self._conn.execute(
            """INSERT INTO optimization_task (session_id, task_id, status, budget)
               VALUES (?, ?, 'pending', ?)""",
            (session_id, task_id, _dumps(budget)),
        )
        self._conn.commit()

    def update_optimization(self, session_id: str, task_id: str, *, status: str | None = None,
                            best_job_id: str | None = None, rounds: list | None = None,
                            consumed: dict | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if best_job_id is not None:
            fields.append("best_job_id = ?")
            values.append(best_job_id)
        if rounds is not None:
            fields.append("rounds = ?")
            values.append(_dumps(rounds))
        if consumed is not None:
            fields.append("consumed = ?")
            values.append(_dumps(consumed))
        if not fields:
            return
        values.extend([session_id, task_id])
        self._conn.execute(
            f"UPDATE optimization_task SET {', '.join(fields)} WHERE session_id = ? AND task_id = ?",
            values,
        )
        self._conn.commit()

    def get_optimization(self, session_id: str, task_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM optimization_task WHERE session_id = ? AND task_id = ?",
            (session_id, task_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "budget": _loads(row["budget"]),
            "consumed": _loads(row["consumed"]),
            "best_job_id": row["best_job_id"],
            "rounds": _loads(row["rounds"]),
        }

    # -- milestones ---------------------------------------------------------
    def record_milestone(self, session_id: str, name: str, choice: str,
                         snapshot: dict | None = None) -> None:
        self._conn.execute(
            "INSERT INTO milestone (session_id, name, choice, snapshot, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, name, choice, _dumps(snapshot), _utc_now()),
        )
        self._conn.commit()

    def list_milestones(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM milestone WHERE session_id = ? ORDER BY id", (session_id,)
        ).fetchall()
        return [
            {
                "name": r["name"],
                "choice": r["choice"],
                "snapshot": _loads(r["snapshot"]),
                "recorded_at": r["recorded_at"],
            }
            for r in rows
        ]

    # -- generic kv state ----------------------------------------------------
    def set_state(self, session_id: str, key: str, value: Any) -> None:
        self._conn.execute(
            """INSERT INTO kv_state (session_id, key, value) VALUES (?, ?, ?)
               ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value""",
            (session_id, key, _dumps(value)),
        )
        self._conn.commit()

    def get_state(self, session_id: str, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM kv_state WHERE session_id = ? AND key = ?", (session_id, key)
        ).fetchone()
        if row is None:
            return default
        return _loads(row["value"])
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/store.py tests/test_store.py
git commit -m "feat: SQLite design session store as single source of truth"
```

---

### Task 5: 工具层公共件（tools/base.py）

**Files:**
- Create: `src/epcd_agent/tools/base.py`
- Test: `tests/test_tools_base.py`

**Interfaces:**
- Consumes: 任务 2 `classify_exit`；任务 3 `EpcdCli` / `ExecResult`；任务 4 `SessionStore`
- Produces（后续所有工具任务依赖，签名不得漂移）：
  - `ToolInputError`（异常：工具入参或 Store 前置条件不满足）
  - `ToolResult(ok: bool, data: Any = None, errors: tuple[dict, ...] = (), exit_code: int | None = None, category: str = "success")`；`errors` 每项为 `{"code": str, "path": str | None, "message": str | None}`
  - `ToolContext(cli: EpcdCli, store: SessionStore, session_id: str)`（dataclass）
  - `result_from_exec(result: ExecResult) -> ToolResult`：超时 → `errors=[{"code":"CLI_TIMEOUT",...}], category="transient"`；信封解析失败 → `errors=[{"code":"ENVELOPE_PARSE_ERROR",...}], category="unknown"`；否则按信封构造，`ok=False` 时 `category = classify_exit(exit_code)`
  - `inject_ids(ctx: ToolContext, args: list[str], *, project: bool = True, instance: bool = True) -> list[str]`：从 Store 取最新 `project_dir` / 活动 `instance_id` 追加 `--project` / `--instance-id`（设计文档 §4.1 规则 2）；Store 缺失时抛 `ToolInputError`，错误信息指明缺什么、应先调哪个工具
  - `require_digest(ctx: ToolContext) -> str`：返回 Store 中最新 `configDigest`；缺失抛 `ToolInputError`（提示先 `epcd_config(action="get")`）

- [ ] **Step 1: 写失败测试**

`tests/test_tools_base.py`：

```python
import json

import mock_cli
import pytest

from epcd_agent.cli_client import ExecResult
from epcd_agent.envelope import parse_envelope
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import (
    ToolContext,
    ToolInputError,
    ToolResult,
    inject_ids,
    require_digest,
    result_from_exec,
)

OK = {
    "schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
    "data": {"v": 1}, "errors": [],
}
FAIL = {
    "schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
    "data": None,
    "errors": [{"code": "CONFIG_DIGEST_MISMATCH", "path": "/device", "message": "mismatch"}],
}


@pytest.fixture()
def ctx(tmp_path):
    cli, _ = mock_cli.make_cli(tmp_path, [])
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    return ToolContext(cli=cli, store=store, session_id="s1")


def test_result_from_exec_success():
    er = ExecResult(exit_code=0, response=parse_envelope(json.dumps(OK)), stdout="", stderr="")
    r = result_from_exec(er)
    assert isinstance(r, ToolResult)
    assert r.ok is True
    assert r.category == "success"
    assert r.data == {"v": 1}
    assert r.errors == ()


def test_result_from_exec_failure_maps_category_and_errors():
    er = ExecResult(exit_code=4, response=parse_envelope(json.dumps(FAIL)), stdout="", stderr="")
    r = result_from_exec(er)
    assert r.ok is False
    assert r.exit_code == 4
    assert r.category == "agent_retryable"
    assert r.errors == ({"code": "CONFIG_DIGEST_MISMATCH", "path": "/device", "message": "mismatch"},)


def test_result_from_exec_timeout():
    er = ExecResult(exit_code=-1, response=None, stdout="", stderr="", timed_out=True)
    r = result_from_exec(er)
    assert r.ok is False
    assert r.category == "transient"
    assert r.errors[0]["code"] == "CLI_TIMEOUT"


def test_result_from_exec_unparseable():
    er = ExecResult(exit_code=0, response=None, stdout="garbage", stderr="", parse_error="bad")
    r = result_from_exec(er)
    assert r.ok is False
    assert r.category == "unknown"
    assert r.errors[0]["code"] == "ENVELOPE_PARSE_ERROR"


def test_inject_ids_raises_without_project(ctx):
    with pytest.raises(ToolInputError, match="no project"):
        inject_ids(ctx, ["config", "get"])


def test_inject_ids_raises_without_instance(ctx):
    ctx.store.set_project("s1", "/abs/proj")
    with pytest.raises(ToolInputError, match="no active device instance"):
        inject_ids(ctx, ["config", "get"])


def test_inject_ids_appends_from_store(ctx):
    ctx.store.set_project("s1", "/abs/proj")
    ctx.store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    ctx.store.set_active_instance("s1", "m-1")
    args = inject_ids(ctx, ["config", "get"])
    assert args == ["config", "get", "--project", "/abs/proj", "--instance-id", "m-1"]


def test_inject_ids_project_only(ctx):
    ctx.store.set_project("s1", "/abs/proj")
    args = inject_ids(ctx, ["device-template", "describe", "t-1"], instance=False)
    assert args == ["device-template", "describe", "t-1", "--project", "/abs/proj"]


def test_require_digest(ctx):
    with pytest.raises(ToolInputError, match="config digest"):
        require_digest(ctx)
    ctx.store.set_config_digest("s1", "sha256:d")
    assert require_digest(ctx) == "sha256:d"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tools_base.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.tools.base`）

- [ ] **Step 3: 实现 tools/base.py**

```python
"""Shared plumbing for the epcd tool layer (design doc section 4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..cli_client import EpcdCli, ExecResult
from ..exitcodes import classify_exit
from ..store import SessionStore


class ToolInputError(Exception):
    """Tool arguments invalid, or Session Store prerequisites not met."""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    errors: tuple[dict, ...] = ()
    exit_code: int | None = None
    category: str = "success"


@dataclass
class ToolContext:
    cli: EpcdCli
    store: SessionStore
    session_id: str


def result_from_exec(result: ExecResult) -> ToolResult:
    if result.timed_out:
        return ToolResult(
            ok=False,
            errors=({"code": "CLI_TIMEOUT", "path": None,
                     "message": "epcd-cli execution timed out"},),
            exit_code=result.exit_code,
            category="transient",
        )
    if result.response is None:
        return ToolResult(
            ok=False,
            errors=({"code": "ENVELOPE_PARSE_ERROR", "path": None,
                     "message": result.parse_error},),
            exit_code=result.exit_code,
            category="unknown",
        )
    errors = tuple(
        {"code": e.code, "path": e.path, "message": e.message}
        for e in result.response.errors
    )
    category = "success" if result.response.ok else classify_exit(result.exit_code)
    return ToolResult(
        ok=result.response.ok,
        data=result.response.data,
        errors=errors,
        exit_code=result.exit_code,
        category=category,
    )


def inject_ids(ctx: ToolContext, args: list[str], *,
               project: bool = True, instance: bool = True) -> list[str]:
    """Append --project / --instance-id from the Session Store (hard rule 2).

    The LLM never supplies these values; they always come from prior
    command responses recorded in the Store.
    """
    out = list(args)
    if project:
        proj = ctx.store.get_project(ctx.session_id)
        if not proj:
            raise ToolInputError(
                "no project in session store yet; call epcd_project(action='init') first"
            )
        out += ["--project", proj["project_dir"]]
    if instance:
        inst = ctx.store.get_active_instance(ctx.session_id)
        if not inst:
            raise ToolInputError(
                "no active device instance in session store; call epcd_device(action='add') first"
            )
        out += ["--instance-id", inst["instance_id"]]
    return out


def require_digest(ctx: ToolContext) -> str:
    digest = ctx.store.get_config_digest(ctx.session_id)
    if not digest:
        raise ToolInputError(
            "no config digest in session store; call epcd_config(action='get') first"
        )
    return digest
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/tools/base.py tests/test_tools_base.py
git commit -m "feat: tool layer plumbing with id injection from session store"
```

---

### Task 6: 只读工具（tools/read.py）—— epcd_health / epcd_template / epcd_formula / epcd_job

**Files:**
- Create: `src/epcd_agent/tools/read.py`
- Test: `tests/test_tools_read.py`

**Interfaces:**
- Consumes: 任务 5 `ToolContext` / `ToolResult` / `result_from_exec` / `inject_ids`
- Produces（函数签名）：
  - `epcd_health(ctx: ToolContext) -> ToolResult`：依次执行 `version` 与 `health`；`data = {"version": <version 响应 data>, "health": <health 响应 data>}`；任一失败即返回失败 ToolResult（`version` 失败时 `data={"version": None, "health": None}` 不适用，直接返回该失败结果）。不做 Store 写入。
  - `epcd_template(ctx: ToolContext, action: str, category: str | None = None, template_id: str | None = None) -> ToolResult`：`action="list"` → `device-template list [--category ...]`；`action="describe"` → `device-template describe <template-id>` + 注入 `--project`（仅 project，release §4.3）；非法 action 抛 `ToolInputError`；describe 缺 `template_id` 抛 `ToolInputError`。
  - `epcd_formula(ctx: ToolContext, formula: dict) -> ToolResult`：`formula validate --input -`，stdin 为 `formula` 原样（release §4.8）。
  - `epcd_job(ctx: ToolContext, action: str, job_id: str) -> ToolResult`：`action ∈ {"get","result","cancel"}` → `job <action> --id <job-id>`（release §4.11~4.12）。注意：本工具不写 Store，记账由调用方（epcd_run / 控制器）负责。

- [ ] **Step 1: 写失败测试**

`tests/test_tools_read.py`：

```python
import json

import mock_cli
import pytest

from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext, ToolInputError
from epcd_agent.tools.read import epcd_formula, epcd_health, epcd_job, epcd_template


def make_ctx(tmp_path, routes):
    cli, calls = mock_cli.make_cli(tmp_path, routes)
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    return ToolContext(cli=cli, store=store, session_id="s1"), calls


def ok_envelope(data):
    return {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
            "data": data, "errors": []}


def test_health_runs_version_then_health(tmp_path):
    ctx, calls = make_ctx(tmp_path, [
        {"argvPrefix": ["version"], "responses": [{"exitCode": 0, "envelope": ok_envelope({"version": "1.2.3"})}]},
        {"argvPrefix": ["health"], "responses": [{"exitCode": 0, "envelope": ok_envelope({"status": "ok"})}]},
    ])
    r = epcd_health(ctx)
    assert r.ok is True
    assert r.data == {"version": {"version": "1.2.3"}, "health": {"status": "ok"}}
    assert [c["argv"] for c in mock_cli.read_calls(calls)] == [["version"], ["health"]]


def test_health_stops_on_version_failure(tmp_path):
    fail = {"schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
            "data": None, "errors": [{"code": "E", "path": None, "message": "x"}]}
    ctx, calls = make_ctx(tmp_path, [
        {"argvPrefix": ["version"], "responses": [{"exitCode": 7, "envelope": fail}]},
    ])
    r = epcd_health(ctx)
    assert r.ok is False
    assert r.category == "blocking"
    assert mock_cli.read_calls(calls) == [{"argv": ["version"], "stdin": None}]


def test_health_degraded_envelope_is_still_ok(tmp_path):
    ctx, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["version"], "responses": [{"exitCode": 0, "envelope": ok_envelope({"version": "1"})}]},
        {"argvPrefix": ["health"], "responses": [{"exitCode": 0, "envelope": ok_envelope({"status": "degraded", "missingModules": ["tech"]})}]},
    ])
    r = epcd_health(ctx)
    assert r.ok is True
    assert r.data["health"]["status"] == "degraded"


def test_template_list_with_category(tmp_path):
    ctx, calls = make_ctx(tmp_path, [
        {"argvPrefix": ["device-template", "list"],
         "responses": [{"exitCode": 0, "envelope": ok_envelope({"templates": []})}]},
    ])
    r = epcd_template(ctx, action="list", category="inductor")
    assert r.ok is True
    assert mock_cli.read_calls(calls)[0]["argv"] == ["device-template", "list", "--category", "inductor"]


def test_template_describe_injects_project_only(tmp_path):
    ctx, calls = make_ctx(tmp_path, [
        {"argvPrefix": ["device-template", "describe"],
         "responses": [{"exitCode": 0, "envelope": ok_envelope({"templateId": "t-1"})}]},
    ])
    ctx.store.set_project("s1", "/abs/proj")
    r = epcd_template(ctx, action="describe", template_id="t-1")
    assert r.ok is True
    assert mock_cli.read_calls(calls)[0]["argv"] == [
        "device-template", "describe", "t-1", "--project", "/abs/proj"]


def test_template_describe_requires_template_id(tmp_path):
    ctx, _ = make_ctx(tmp_path, [])
    ctx.store.set_project("s1", "/abs/proj")
    with pytest.raises(ToolInputError):
        epcd_template(ctx, action="describe")


def test_template_invalid_action(tmp_path):
    ctx, _ = make_ctx(tmp_path, [])
    with pytest.raises(ToolInputError):
        epcd_template(ctx, action="destroy")


def test_formula_validate_sends_stdin(tmp_path):
    ctx, calls = make_ctx(tmp_path, [
        {"argvPrefix": ["formula", "validate"],
         "responses": [{"exitCode": 0, "envelope": ok_envelope({"valid": True})}]},
    ])
    formula = {"name": "Q", "expression": "Im(Z(1,1))/Re(Z(1,1))", "unit": "", "description": None}
    r = epcd_formula(ctx, formula=formula)
    assert r.ok is True
    call = mock_cli.read_calls(calls)[0]
    assert call["argv"] == ["formula", "validate", "--input", "-"]
    assert call["stdin"] == formula


def test_job_actions(tmp_path):
    ctx, calls = make_ctx(tmp_path, [
        {"argvPrefix": ["job"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"status": "running"})},
            {"exitCode": 0, "envelope": ok_envelope({"objectiveCost": 0.15})},
            {"exitCode": 0, "envelope": ok_envelope({"status": "canceling"})},
        ]},
    ])
    assert epcd_job(ctx, action="get", job_id="j-1").ok
    assert epcd_job(ctx, action="result", job_id="j-1").ok
    assert epcd_job(ctx, action="cancel", job_id="j-1").ok
    argvs = [c["argv"] for c in mock_cli.read_calls(calls)]
    assert argvs == [
        ["job", "get", "--id", "j-1"],
        ["job", "result", "--id", "j-1"],
        ["job", "cancel", "--id", "j-1"],
    ]


def test_job_invalid_action(tmp_path):
    ctx, _ = make_ctx(tmp_path, [])
    with pytest.raises(ToolInputError):
        epcd_job(ctx, action="restart", job_id="j-1")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tools_read.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.tools.read`）

- [ ] **Step 3: 实现 tools/read.py**

```python
"""Read-only tools: health, templates, formula validation, job queries."""
from __future__ import annotations

from .base import ToolContext, ToolInputError, ToolResult, inject_ids, result_from_exec

_JOB_ACTIONS = ("get", "result", "cancel")


def epcd_health(ctx: ToolContext) -> ToolResult:
    """Probe environment: epcd-cli version + health (release doc section 4.1)."""
    version_result = result_from_exec(ctx.cli.exec(["version"]))
    if not version_result.ok:
        return version_result
    health_result = result_from_exec(ctx.cli.exec(["health"]))
    if not health_result.ok:
        return health_result
    return ToolResult(ok=True, exit_code=0,
                      data={"version": version_result.data, "health": health_result.data})


def epcd_template(ctx: ToolContext, action: str,
                  category: str | None = None,
                  template_id: str | None = None) -> ToolResult:
    """device-template list/describe (release doc section 4.3)."""
    if action == "list":
        args = ["device-template", "list"]
        if category:
            args += ["--category", category]
        return result_from_exec(ctx.cli.exec(args))
    if action == "describe":
        if not template_id:
            raise ToolInputError("template_id is required for action='describe'")
        args = inject_ids(ctx, ["device-template", "describe", template_id], instance=False)
        return result_from_exec(ctx.cli.exec(args))
    raise ToolInputError(f"unsupported epcd_template action: {action!r}")


def epcd_formula(ctx: ToolContext, formula: dict) -> ToolResult:
    """formula validate with stdin JSON (release doc section 4.8)."""
    return result_from_exec(ctx.cli.exec(["formula", "validate", "--input", "-"], stdin_obj=formula))


def epcd_job(ctx: ToolContext, action: str, job_id: str) -> ToolResult:
    """job get/result/cancel (release doc sections 4.11-4.12)."""
    if action not in _JOB_ACTIONS:
        raise ToolInputError(f"unsupported epcd_job action: {action!r}")
    return result_from_exec(ctx.cli.exec(["job", action, "--id", job_id]))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/tools/read.py tests/test_tools_read.py
git commit -m "feat: read-only tools (health, template, formula, job)"
```

---

### Task 7: 写操作工具与记账（tools/write.py）—— epcd_project / epcd_device / epcd_run

**Files:**
- Create: `src/epcd_agent/tools/write.py`
- Test: `tests/test_tools_write.py`

**Interfaces:**
- Consumes: 任务 5 全部公共件；任务 4 Store 的 project/instance/job/digest 方法
- Produces（函数签名）：
  - `epcd_project(ctx: ToolContext, action: str, work_dir: str | None = None, technology: str | None = None, password: str | None = None) -> ToolResult`：`action="init"` → `project init --work-dir <work_dir> --technology <technology> [--password ...]`（release §4.2；**例外：init 不注入 --project**，work_dir 由调用方显式给出）；成功后记账 `set_project(project_dir=data["project"], lib_name=data["libName"], technology_digest=data["technologyDigest"])`。`action="describe"|"validate"` → 注入 `--project`（仅 project）。init 缺 work_dir/technology 抛 `ToolInputError`。
  - `epcd_device(ctx: ToolContext, action: str, template_id: str | None = None, name: str | None = None, instance_id: str | None = None) -> ToolResult`：`add`（注入 project；`--template-id` 必填，`--name` 可选；成功后记账 `upsert_instance(...)` + `set_active_instance(data["instanceId"])`，release §4.4）；`list`（注入 project）；`describe`/`remove`（注入 project + 显式 `--instance-id <instance_id>` 参数，不走活动实例）。非法 action 抛 `ToolInputError`。
  - `epcd_run(ctx: ToolContext, task: str, request_id: str, input_obj: dict | None = None, wait: bool = False, timeout_seconds: float | None = None, use_if_match: bool = False) -> ToolResult`（release §4.7/4.11/4.15）：
    - `task ∈ {"gds-generation","simulation-evaluation"}`，否则 `ToolInputError`
    - 组装：`inject_ids(["run","--task",task])`；有 `input_obj` 加 `--input -`（stdin 传 JSON）；`use_if_match=True` 加 `--if-match <store digest>`（经 `require_digest`）；再加 `--request-id <request_id>`；`wait=True` 加 `--wait`，`timeout_seconds` 加 `--timeout <int>`
    - **记账（硬规则 3）**：成功且 `data["jobId"]` 存在时——Store 无此 jobId → `add_job(job_id, request_id=request_id, task_type=task, status=data.get("status","queued"), parameters=input_obj.get("parameters") if input_obj else None)`；已有（requestId 恢复返回原 Job，release §4.13）→ `update_job(status=data.get("status"))`。`data["configDigestUsed"]` 存在时 `set_config_digest`。
    - 失败（含退出码 11）按 `result_from_exec` 原样返回，不做特殊处理（恢复语义由控制器/对话层决定）。

- [ ] **Step 1: 写失败测试**

`tests/test_tools_write.py`：

```python
import mock_cli
import pytest

from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext, ToolInputError
from epcd_agent.tools.write import epcd_device, epcd_project, epcd_run


def make_ctx(tmp_path, routes):
    cli, calls = mock_cli.make_cli(tmp_path, routes)
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    return ToolContext(cli=cli, store=store, session_id="s1"), calls, store


def ok_envelope(data):
    return {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
            "data": data, "errors": []}


def test_project_init_ledgers_project(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["project", "init"], "responses": [{"exitCode": 0, "envelope": ok_envelope({
            "created": True, "project": "/abs/proj", "libName": "demo_project",
            "technologyDigest": "sha256:tech", "warnings": []})}]},
    ])
    r = epcd_project(ctx, action="init", work_dir="/abs/proj", technology="/abs/process.ptxt")
    assert r.ok is True
    assert r.data["created"] is True
    assert mock_cli.read_calls(calls)[0]["argv"] == [
        "project", "init", "--work-dir", "/abs/proj", "--technology", "/abs/process.ptxt"]
    p = store.get_project("s1")
    assert p["project_dir"] == "/abs/proj"
    assert p["lib_name"] == "demo_project"
    assert p["technology_digest"] == "sha256:tech"


def test_project_init_requires_work_dir_and_technology(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [])
    with pytest.raises(ToolInputError):
        epcd_project(ctx, action="init", work_dir="/abs/proj")
    with pytest.raises(ToolInputError):
        epcd_project(ctx, action="init", technology="/abs/process.ptxt")


def test_project_describe_injects_project(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["project", "describe"], "responses": [{"exitCode": 0, "envelope": ok_envelope({})}]},
        {"argvPrefix": ["project", "validate"], "responses": [{"exitCode": 0, "envelope": ok_envelope({})}]},
    ])
    store.set_project("s1", "/abs/proj")
    assert epcd_project(ctx, action="describe").ok
    assert epcd_project(ctx, action="validate").ok
    argvs = [c["argv"] for c in mock_cli.read_calls(calls)]
    assert argvs == [
        ["project", "describe", "--project", "/abs/proj"],
        ["project", "validate", "--project", "/abs/proj"],
    ]


def test_device_add_ledgers_and_activates(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["project", "device", "add"], "responses": [{"exitCode": 0, "envelope": ok_envelope({
            "created": True, "project": "/abs/proj", "instanceId": "m-1",
            "name": "simple_inductor1", "folderName": "simple_inductor1",
            "templateId": "system.inductor.simple_inductor", "warnings": []})}]},
    ])
    store.set_project("s1", "/abs/proj")
    r = epcd_device(ctx, action="add", template_id="system.inductor.simple_inductor", name="L1")
    assert r.ok is True
    assert mock_cli.read_calls(calls)[0]["argv"] == [
        "project", "device", "add", "--template-id", "system.inductor.simple_inductor",
        "--name", "L1", "--project", "/abs/proj"]
    active = store.get_active_instance("s1")
    assert active["instance_id"] == "m-1"
    assert active["template_id"] == "system.inductor.simple_inductor"


def test_device_describe_uses_explicit_instance_id(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["project", "device", "describe"], "responses": [{"exitCode": 0, "envelope": ok_envelope({})}]},
    ])
    store.set_project("s1", "/abs/proj")
    epcd_device(ctx, action="describe", instance_id="m-9")
    assert mock_cli.read_calls(calls)[0]["argv"] == [
        "project", "device", "describe", "--instance-id", "m-9", "--project", "/abs/proj"]


def test_run_submits_candidate_and_ledgers_job(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [{"exitCode": 0, "envelope": ok_envelope({
            "jobId": "j-1", "requestId": "iteration-1",
            "taskType": "simulation-evaluation", "status": "queued",
            "configDigestUsed": "sha256:d1"})}]},
    ])
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    store.set_config_digest("s1", "sha256:d0")
    candidate = {"schemaVersion": "epcd-candidate/v1", "parameters": {"width": 11, "numOfTurns": 3}}
    r = epcd_run(ctx, task="simulation-evaluation", request_id="iteration-1",
                 input_obj=candidate, use_if_match=True)
    assert r.ok is True
    call = mock_cli.read_calls(calls)[0]
    assert call["argv"] == [
        "run", "--task", "simulation-evaluation",
        "--project", "/abs/proj", "--instance-id", "m-1",
        "--input", "-", "--if-match", "sha256:d0", "--request-id", "iteration-1"]
    assert call["stdin"] == candidate
    job = store.get_job("s1", "j-1")
    assert job["request_id"] == "iteration-1"
    assert job["status"] == "queued"
    assert job["parameters"] == {"width": 11, "numOfTurns": 3}
    assert store.get_config_digest("s1") == "sha256:d1"


def test_run_resume_returns_existing_job_without_error(tmp_path):
    ctx, _, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({
                "jobId": "j-1", "requestId": "iteration-1",
                "taskType": "simulation-evaluation", "status": "queued"})},
            {"exitCode": 0, "envelope": ok_envelope({
                "jobId": "j-1", "requestId": "iteration-1",
                "taskType": "simulation-evaluation", "status": "running"})},
        ]},
    ])
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    epcd_run(ctx, task="simulation-evaluation", request_id="iteration-1")
    r2 = epcd_run(ctx, task="simulation-evaluation", request_id="iteration-1")
    assert r2.ok is True
    assert store.get_job("s1", "j-1")["status"] == "running"
    assert len(store.list_jobs("s1")) == 1


def test_run_wait_and_timeout_flags(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [{"exitCode": 0, "envelope": ok_envelope({"jobId": "j-2"})}]},
    ])
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    epcd_run(ctx, task="gds-generation", request_id="preview-001", wait=True, timeout_seconds=300)
    argv = mock_cli.read_calls(calls)[0]["argv"]
    assert argv == [
        "run", "--task", "gds-generation",
        "--project", "/abs/proj", "--instance-id", "m-1",
        "--request-id", "preview-001", "--wait", "--timeout", "300"]


def test_run_invalid_task_and_missing_digest(tmp_path):
    ctx, _, store = make_ctx(tmp_path, [])
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    with pytest.raises(ToolInputError):
        epcd_run(ctx, task="bogus-task", request_id="r")
    with pytest.raises(ToolInputError, match="config digest"):
        epcd_run(ctx, task="simulation-evaluation", request_id="r", use_if_match=True)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tools_write.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.tools.write`）

- [ ] **Step 3: 实现 tools/write.py**

```python
"""Write tools with automatic ledgering into the Session Store (hard rule 3)."""
from __future__ import annotations

from .base import (
    ToolContext,
    ToolInputError,
    ToolResult,
    inject_ids,
    require_digest,
    result_from_exec,
)

_RUN_TASKS = ("gds-generation", "simulation-evaluation")


def epcd_project(ctx: ToolContext, action: str, work_dir: str | None = None,
                 technology: str | None = None, password: str | None = None) -> ToolResult:
    """project init/describe/validate (release doc section 4.2)."""
    if action == "init":
        if not work_dir or not technology:
            raise ToolInputError("project init requires work_dir and technology")
        args = ["project", "init", "--work-dir", work_dir, "--technology", technology]
        if password:
            args += ["--password", password]
        result = result_from_exec(ctx.cli.exec(args))
        if result.ok and result.data:
            ctx.store.set_project(
                ctx.session_id,
                project_dir=result.data["project"],
                lib_name=result.data.get("libName"),
                technology_digest=result.data.get("technologyDigest"),
            )
        return result
    if action in ("describe", "validate"):
        args = inject_ids(ctx, ["project", action], instance=False)
        return result_from_exec(ctx.cli.exec(args))
    raise ToolInputError(f"unsupported epcd_project action: {action!r}")


def epcd_device(ctx: ToolContext, action: str, template_id: str | None = None,
                name: str | None = None, instance_id: str | None = None) -> ToolResult:
    """project device add/list/describe/remove (release doc section 4.4)."""
    if action == "add":
        if not template_id:
            raise ToolInputError("device add requires template_id")
        args = ["project", "device", "add", "--template-id", template_id]
        if name:
            args += ["--name", name]
        args = inject_ids(ctx, args, instance=False)
        result = result_from_exec(ctx.cli.exec(args))
        if result.ok and result.data:
            new_id = result.data["instanceId"]
            ctx.store.upsert_instance(
                ctx.session_id, new_id,
                template_id=result.data.get("templateId") or template_id,
                name=result.data.get("name"),
                project_dir=result.data.get("project")
                or (ctx.store.get_project(ctx.session_id) or {}).get("project_dir", ""),
            )
            ctx.store.set_active_instance(ctx.session_id, new_id)
        return result
    if action == "list":
        return result_from_exec(ctx.cli.exec(inject_ids(ctx, ["project", "device", "list"], instance=False)))
    if action in ("describe", "remove"):
        if not instance_id:
            raise ToolInputError(f"device {action} requires instance_id")
        args = inject_ids(ctx, ["project", "device", action, "--instance-id", instance_id], instance=False)
        return result_from_exec(ctx.cli.exec(args))
    raise ToolInputError(f"unsupported epcd_device action: {action!r}")


def epcd_run(ctx: ToolContext, task: str, request_id: str,
             input_obj: dict | None = None, wait: bool = False,
             timeout_seconds: float | None = None, use_if_match: bool = False) -> ToolResult:
    """run --task ... (release doc sections 4.7 / 4.11 / 4.15)."""
    if task not in _RUN_TASKS:
        raise ToolInputError(f"unsupported run task: {task!r}")
    args = inject_ids(ctx, ["run", "--task", task])
    stdin_obj = None
    if input_obj is not None:
        args += ["--input", "-"]
        stdin_obj = input_obj
    if use_if_match:
        args += ["--if-match", require_digest(ctx)]
    args += ["--request-id", request_id]
    if wait:
        args += ["--wait"]
        if timeout_seconds is not None:
            args += ["--timeout", str(int(timeout_seconds))]
    result = result_from_exec(ctx.cli.exec(args, stdin_obj=stdin_obj))
    if result.ok and result.data and result.data.get("jobId"):
        _ledger_job(ctx, result.data, request_id, task, input_obj)
    return result


def _ledger_job(ctx: ToolContext, data: dict, request_id: str,
                task: str, input_obj: dict | None) -> None:
    job_id = data["jobId"]
    status = data.get("status", "queued")
    if ctx.store.get_job(ctx.session_id, job_id) is None:
        ctx.store.add_job(
            ctx.session_id, job_id,
            request_id=request_id,
            task_type=task,
            status=status,
            parameters=(input_obj or {}).get("parameters"),
        )
    else:
        # requestId resume returned the original Job (release doc section 4.13)
        ctx.store.update_job(ctx.session_id, job_id, status=status)
    if data.get("configDigestUsed"):
        ctx.store.set_config_digest(ctx.session_id, data["configDigestUsed"])
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/tools/write.py tests/test_tools_write.py
git commit -m "feat: write tools with session-store ledgering"
```

---

### Task 8: 配置工具（tools/config.py）—— epcd_config：schema / get / patch / apply-result

**Files:**
- Create: `src/epcd_agent/tools/config.py`
- Test: `tests/test_tools_config.py`

**Interfaces:**
- Consumes: 任务 5 公共件；任务 4 Store digest 方法
- Produces：`epcd_config(ctx: ToolContext, action: str, path: str | None = None, patch_obj: dict | None = None, job_id: str | None = None) -> ToolResult`，`action ∈ {"schema","get","patch","apply-result"}`（release §4.5~4.6/4.9~4.10/4.14）：
  - `schema`：`config schema` + 注入 ids，可选 `--path`。**不记账**（`schemaDigest` 不是配置并发控制用的 `configDigest`，release §4.5）。
  - `get`：`config get` + 注入 ids，可选 `--path`。成功后 `data["configDigest"]` 存在 → `set_config_digest`。
  - `patch`：`patch_obj` 必填（否则 `ToolInputError`）；经 `require_digest` 取 digest，`config patch --input - --if-match <digest>`。**遇 `CONFIG_DIGEST_MISMATCH` 自动恢复一次**（设计文档 §4.1 规则 2）：自动执行 `config get` 刷新 Store 中 digest，再以新 digest 重试一次 patch；仍失败返回第二次结果。成功后 `data["configDigest"]` 存在 → `set_config_digest`。
  - `apply-result`：`job_id` 必填（否则 `ToolInputError`）；`config apply-result --job-id <job-id>` + 注入 ids；成功后 `data["configDigest"]` → `set_config_digest`（写回后的新摘要供最终仿真使用，release §4.14~4.15）。
  - 非法 action 抛 `ToolInputError`。

- [ ] **Step 1: 写失败测试**

`tests/test_tools_config.py`：

```python
import mock_cli
import pytest

from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext, ToolInputError
from epcd_agent.tools.config import epcd_config


def make_ctx(tmp_path, routes):
    cli, calls = mock_cli.make_cli(tmp_path, routes)
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    return ToolContext(cli=cli, store=store, session_id="s1"), calls, store


def ok_envelope(data):
    return {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
            "data": data, "errors": []}


def fail_envelope(code, exit_code=4):
    return {"exitCode": exit_code, "envelope": {
        "schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
        "data": None, "errors": [{"code": code, "path": None, "message": code}]}}


BASE = ["--project", "/abs/proj", "--instance-id", "m-1"]


def test_schema_with_path(tmp_path):
    ctx, calls, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["config", "schema"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"schema": {}, "schemaDigest": "s1"})}]},
    ])
    r = epcd_config(ctx, action="schema", path="/device/parameters")
    assert r.ok is True
    assert mock_cli.read_calls(calls)[0]["argv"] == ["config", "schema"] + BASE + ["--path", "/device/parameters"]
    # schemaDigest must NOT be ledgered as configDigest
    assert ctx.store.get_config_digest("s1") is None


def test_get_ledgers_digest(tmp_path):
    ctx, _, store = make_ctx(tmp_path, [
        {"argvPrefix": ["config", "get"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"value": {}, "configDigest": "sha256:d9"})}]},
    ])
    r = epcd_config(ctx, action="get")
    assert r.ok is True
    assert store.get_config_digest("s1") == "sha256:d9"


def test_patch_uses_store_digest_and_ledgers_new_one(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["config", "patch"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"changed": True, "configDigest": "sha256:new"})}]},
    ])
    store.set_config_digest("s1", "sha256:old")
    patch_obj = {"device": {"parameters": {"width": 12}}}
    r = epcd_config(ctx, action="patch", patch_obj=patch_obj)
    assert r.ok is True
    call = mock_cli.read_calls(calls)[0]
    assert call["argv"] == ["config", "patch"] + BASE + ["--input", "-", "--if-match", "sha256:old"]
    assert call["stdin"] == patch_obj
    assert store.get_config_digest("s1") == "sha256:new"


def test_patch_digest_mismatch_auto_refreshes_and_retries(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["config", "patch"], "responses": [
            fail_envelope("CONFIG_DIGEST_MISMATCH"),
            {"exitCode": 0, "envelope": ok_envelope({"changed": True, "configDigest": "sha256:v3"})},
        ]},
        {"argvPrefix": ["config", "get"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"value": {}, "configDigest": "sha256:v2"})}]},
    ])
    store.set_config_digest("s1", "sha256:stale")
    r = epcd_config(ctx, action="patch", patch_obj={"device": {"parameters": {"width": 12}}})
    assert r.ok is True
    argvs = [c["argv"] for c in mock_cli.read_calls(calls)]
    assert argvs == [
        ["config", "patch"] + BASE + ["--input", "-", "--if-match", "sha256:stale"],
        ["config", "get"] + BASE,
        ["config", "patch"] + BASE + ["--input", "-", "--if-match", "sha256:v2"],
    ]
    assert store.get_config_digest("s1") == "sha256:v3"


def test_patch_digest_mismatch_twice_returns_failure(tmp_path):
    ctx, _, store = make_ctx(tmp_path, [
        {"argvPrefix": ["config", "patch"], "responses": [
            fail_envelope("CONFIG_DIGEST_MISMATCH"),
            fail_envelope("CONFIG_DIGEST_MISMATCH"),
        ]},
        {"argvPrefix": ["config", "get"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"value": {}, "configDigest": "sha256:v2"})}]},
    ])
    store.set_config_digest("s1", "sha256:stale")
    r = epcd_config(ctx, action="patch", patch_obj={"x": 1})
    assert r.ok is False
    assert r.category == "agent_retryable"
    assert r.errors[0]["code"] == "CONFIG_DIGEST_MISMATCH"


def test_patch_requires_patch_obj_and_digest(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [])
    with pytest.raises(ToolInputError):
        epcd_config(ctx, action="patch")
    with pytest.raises(ToolInputError, match="config digest"):
        epcd_config(ctx, action="patch", patch_obj={"x": 1})


def test_apply_result_ledgers_post_apply_digest(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["config", "apply-result"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"configDigest": "sha256:post"})}]},
    ])
    r = epcd_config(ctx, action="apply-result", job_id="j-best")
    assert r.ok is True
    assert mock_cli.read_calls(calls)[0]["argv"] == [
        "config", "apply-result", "--job-id", "j-best"] + BASE
    assert store.get_config_digest("s1") == "sha256:post"


def test_apply_result_requires_job_id(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [])
    with pytest.raises(ToolInputError):
        epcd_config(ctx, action="apply-result")


def test_invalid_action(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [])
    with pytest.raises(ToolInputError):
        epcd_config(ctx, action="wipe")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tools_config.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.tools.config`）

- [ ] **Step 3: 实现 tools/config.py**

```python
"""Config tools: schema/get/patch/apply-result (release doc sections 4.5-4.6, 4.14)."""
from __future__ import annotations

from .base import (
    ToolContext,
    ToolInputError,
    ToolResult,
    inject_ids,
    require_digest,
    result_from_exec,
)


def _ledger_digest(ctx: ToolContext, result: ToolResult) -> None:
    if result.ok and result.data and result.data.get("configDigest"):
        ctx.store.set_config_digest(ctx.session_id, result.data["configDigest"])


def epcd_config(ctx: ToolContext, action: str, path: str | None = None,
                patch_obj: dict | None = None, job_id: str | None = None) -> ToolResult:
    if action == "schema":
        args = inject_ids(ctx, ["config", "schema"])
        if path:
            args += ["--path", path]
        return result_from_exec(ctx.cli.exec(args))

    if action == "get":
        args = inject_ids(ctx, ["config", "get"])
        if path:
            args += ["--path", path]
        result = result_from_exec(ctx.cli.exec(args))
        _ledger_digest(ctx, result)
        return result

    if action == "patch":
        if patch_obj is None:
            raise ToolInputError("config patch requires patch_obj")
        result = _patch_once(ctx, patch_obj, require_digest(ctx))
        if not result.ok and any(e["code"] == "CONFIG_DIGEST_MISMATCH" for e in result.errors):
            # hard rule 2: auto-refresh digest via config get, retry once
            refresh = epcd_config(ctx, action="get")
            if not refresh.ok:
                return refresh
            result = _patch_once(ctx, patch_obj, require_digest(ctx))
        _ledger_digest(ctx, result)
        return result

    if action == "apply-result":
        if not job_id:
            raise ToolInputError("config apply-result requires job_id")
        args = inject_ids(ctx, ["config", "apply-result", "--job-id", job_id])
        result = result_from_exec(ctx.cli.exec(args))
        _ledger_digest(ctx, result)
        return result

    raise ToolInputError(f"unsupported epcd_config action: {action!r}")


def _patch_once(ctx: ToolContext, patch_obj: dict, digest: str) -> ToolResult:
    args = inject_ids(ctx, ["config", "patch"])
    args += ["--input", "-", "--if-match", digest]
    return result_from_exec(ctx.cli.exec(args, stdin_obj=patch_obj))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/tools/config.py tests/test_tools_config.py
git commit -m "feat: config tools with digest auto-refresh retry"
```

---

### Task 9: 参数空间解析（optimizer/space.py）

**Files:**
- Create: `src/epcd_agent/optimizer/space.py`
- Test: `tests/test_space.py`

**Interfaces:**
- Consumes: 无（纯解析模块，输入来自 `epcd_config(action="schema")` 响应中的 `schema` 字段，release §4.5）
- Produces:
  - `ParamSpec(name: str, kind: str, low: float | None = None, high: float | None = None, step: float | None = None, choices: tuple = ())`，`kind ∈ {"float","int","categorical"}`
  - `ParsedSpace(specs: tuple[ParamSpec, ...], unbounded: tuple[str, ...])`
  - `parse_parameter_schema(schema: dict) -> ParsedSpace`：解析 `{"type":"object","properties":{...}}`。规则：有 `enum` → categorical；`type=="integer"` 且同时有 `minimum` 和 `maximum` → int；`type=="number"` 且同时有 `minimum` 和 `maximum` → float；`step` 键存在则取之。其余（无 enum 且缺任一边界）→ 计入 `unbounded`（设计文档 §7.1/§14：无界参数在 M2 询问用户经验范围）。根不是 object 抛 `ValueError`。
  - `normalize_candidate(params: dict, specs: Iterable[ParamSpec]) -> dict`：只保留 specs 中存在的键；数值裁剪到 `[low, high]`（int 裁剪后取整）；categorical 值不在 choices 中抛 `ValueError`。
  - `to_optuna_distributions(specs: Iterable[ParamSpec]) -> dict[str, optuna.distributions.BaseDistribution]`：float → `FloatDistribution(low, high, step=step)`（step 为 None 时不传）；int → `IntDistribution(...)`；categorical → `CategoricalDistribution(tuple(choices))`。

- [ ] **Step 1: 写失败测试**

`tests/test_space.py`：

```python
import optuna
import pytest

from epcd_agent.optimizer.space import (
    ParamSpec,
    parse_parameter_schema,
    normalize_candidate,
    to_optuna_distributions,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "width": {"type": "number", "minimum": 2.0, "maximum": 50.0},
        "numOfTurns": {"type": "integer", "minimum": 1, "maximum": 12, "step": 1},
        "shape": {"type": "string", "enum": ["square", "octagon"]},
        "innerRadius": {"type": "number"},
        "numOfSlots": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}


def test_parse_parameter_schema():
    space = parse_parameter_schema(SCHEMA)
    by_name = {s.name: s for s in space.specs}
    assert by_name["width"] == ParamSpec("width", "float", low=2.0, high=50.0)
    assert by_name["numOfTurns"] == ParamSpec("numOfTurns", "int", low=1, high=12, step=1)
    assert by_name["shape"] == ParamSpec("shape", "categorical", choices=("square", "octagon"))
    # unbounded: no bounds at all, or only one bound present
    assert set(space.unbounded) == {"innerRadius", "numOfSlots"}


def test_parse_rejects_non_object_root():
    with pytest.raises(ValueError):
        parse_parameter_schema({"type": "array"})


def test_normalize_candidate_clips_and_filters():
    space = parse_parameter_schema(SCHEMA)
    out = normalize_candidate({"width": 999, "numOfTurns": -3, "shape": "square", "bogus": 1},
                              space.specs)
    assert out == {"width": 50.0, "numOfTurns": 1, "shape": "square"}


def test_normalize_candidate_rejects_unknown_choice():
    space = parse_parameter_schema(SCHEMA)
    with pytest.raises(ValueError):
        normalize_candidate({"shape": "triangle"}, space.specs)


def test_to_optuna_distributions():
    space = parse_parameter_schema(SCHEMA)
    dists = to_optuna_distributions(space.specs)
    assert isinstance(dists["width"], optuna.distributions.FloatDistribution)
    assert dists["width"].low == 2.0 and dists["width"].high == 50.0
    assert isinstance(dists["numOfTurns"], optuna.distributions.IntDistribution)
    assert dists["numOfTurns"].step == 1
    assert isinstance(dists["shape"], optuna.distributions.CategoricalDistribution)
    assert dists["shape"].choices == ("square", "octagon")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_space.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.optimizer.space`）

- [ ] **Step 3: 实现 space.py**

```python
"""Parse config-schema parameter definitions into an optimization space.

Inputs come from epcd_config(action="schema") responses (release doc section
4.5). Parameters without usable bounds are reported in `unbounded`; per design
doc section 7.1 the agent asks the user for an empirical range at milestone M2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import optuna


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str  # "float" | "int" | "categorical"
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple = ()


@dataclass(frozen=True)
class ParsedSpace:
    specs: tuple[ParamSpec, ...]
    unbounded: tuple[str, ...]


def parse_parameter_schema(schema: dict) -> ParsedSpace:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter schema root must be an object schema")
    properties = schema.get("properties") or {}
    specs: list[ParamSpec] = []
    unbounded: list[str] = []
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            unbounded.append(name)
            continue
        if "enum" in prop:
            specs.append(ParamSpec(name, "categorical", choices=tuple(prop["enum"])))
            continue
        low, high = prop.get("minimum"), prop.get("maximum")
        if low is None or high is None:
            unbounded.append(name)
            continue
        step = prop.get("step")
        if prop.get("type") == "integer":
            specs.append(ParamSpec(name, "int", low=float(low), high=float(high),
                                   step=float(step) if step is not None else None))
        else:
            specs.append(ParamSpec(name, "float", low=float(low), high=float(high),
                                   step=float(step) if step is not None else None))
    return ParsedSpace(specs=tuple(specs), unbounded=tuple(unbounded))


def normalize_candidate(params: dict, specs: Iterable[ParamSpec]) -> dict:
    """Keep only known keys, clip numerics into bounds, validate choices."""
    by_name = {s.name: s for s in specs}
    out: dict = {}
    for key, value in params.items():
        spec = by_name.get(key)
        if spec is None:
            continue
        if spec.kind == "categorical":
            if value not in spec.choices:
                raise ValueError(f"{key}: {value!r} not in choices {spec.choices}")
            out[key] = value
        elif spec.kind == "int":
            clipped = min(max(float(value), spec.low), spec.high)
            out[key] = int(round(clipped))
        else:
            out[key] = float(min(max(float(value), spec.low), spec.high))
    return out


def to_optuna_distributions(specs: Iterable[ParamSpec]) -> dict:
    dists: dict = {}
    for spec in specs:
        if spec.kind == "float":
            if spec.step is not None:
                dists[spec.name] = optuna.distributions.FloatDistribution(
                    spec.low, spec.high, step=spec.step)
            else:
                dists[spec.name] = optuna.distributions.FloatDistribution(spec.low, spec.high)
        elif spec.kind == "int":
            step = int(spec.step) if spec.step is not None else 1
            dists[spec.name] = optuna.distributions.IntDistribution(
                int(spec.low), int(spec.high), step=step)
        else:
            dists[spec.name] = optuna.distributions.CategoricalDistribution(spec.choices)
    return dists
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/optimizer/space.py tests/test_space.py
git commit -m "feat: parse parameter schema into optimization space"
```

---

### Task 10: OptimizationController（optimizer/controller.py）

**Files:**
- Create: `src/epcd_agent/optimizer/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: 任务 5 `ToolContext`；任务 6 `epcd_job`；任务 7 `epcd_run`；任务 9 `normalize_candidate`；任务 2 `LOOP_TRANSIENT_EXIT_CODES`
- Produces（计划 2 的 `optimization_*` 平台工具直接包装这些类型）：
  - `OptimizationBudget(max_rounds: int = 20, max_wall_seconds: float = 600.0, target_cost: float | None = None)`（frozen dataclass；三者先到即停，设计文档 §7.1）
  - `RoundRecord(round_no: int, request_id: str, parameters: dict, job_id: str | None, status: str, cost: float | None)`，status ∈ `{"succeeded","failed","canceled"}`
  - `OptimizationReport(best_job_id: str | None, best_cost: float | None, best_parameters: dict | None, rounds: tuple[RoundRecord, ...], stop_reason: str)`，stop_reason ∈ `{"target_reached","budget_rounds","budget_wall","canceled"}`（正常返回）；暂停时不返回，抛 `OptimizationPausedError`
  - `OptimizationPausedError(message, *, report: OptimizationReport, category: str, errors: tuple[dict, ...] = ())`：异常携带截至暂停时的部分报告；`category` 取暂停原因对应的退出码分类（`"needs_decision"` / `"transient"` / `"unknown"` 等）
  - `OptimizationController(ctx: ToolContext, specs: Iterable[ParamSpec], initial_candidates: Iterable[dict] = (), budget: OptimizationBudget = OptimizationBudget(), request_prefix: str = "iteration", poll_interval: float = 0.05, on_progress: Callable[[dict], None] | None = None, task_id: str | None = None)`，方法 `run() -> OptimizationReport`、`request_cancel() -> None`
  - 循环行为（设计文档 §7.2~7.3，release §4.11~4.13）：
    - 每轮 `request_id = f"{request_prefix}-{N}"`；候选先消费 `initial_candidates`（Optuna `enqueue_trial`，已按空间归一化），之后由 TPESampler（固定 seed=20260817，测试可复现）产出
    - 提交走 `epcd_run(task="simulation-evaluation", use_if_match=True, input_obj={"schemaVersion":"epcd-candidate/v1","parameters":...})`；退出码 ∈ `LOOP_TRANSIENT_EXIT_CODES` → 同 requestId 重试一次；4/5 类错误 → 立即暂停上报；退出码 11 → 用 `store.find_job_by_request` 接回原 Job，找不到才暂停
    - 轮询 `epcd_job(action="get")` 至终态；轮询期间响应 `request_cancel()`：调 `job cancel` 后继续轮询到 `canceled` 终态
    - Job succeeded → `job result` 读 `objectiveCost`（唯一评价字段，越小越好）回写 Store 并喂优化器；达到 `target_cost` → `stop_reason="target_reached"`
    - Job failed → 该轮记 failed、喂优化器 FAIL 状态；**连续 2 轮失败 → 暂停**（对应 LLM 异常诊断介入点），单次失败继续搜索
    - 每轮结束回调 `on_progress({"type":"round_finished", "round", "request_id", "job_id", "status", "cost", "best_cost", "best_job_id"})`
    - `task_id` 非空且 Store 中已有该 optimization_task 行时：启动置 `running`，每轮回写 `rounds/consumed/best_job_id`，终态置 `finished` / `paused` / `canceled`
  - 崩溃恢复：控制器自身无状态，重启后以相同 `request_prefix` 重新 `run()`；相同 requestId 提交返回原 Job（release §4.13），Store 中的 job 行被复用而非新增

- [ ] **Step 1: 写失败测试**

`tests/test_controller.py`：

```python
import dataclasses

import mock_cli
import pytest

from epcd_agent.optimizer.controller import (
    OptimizationBudget,
    OptimizationController,
    OptimizationPausedError,
)
from epcd_agent.optimizer.space import ParamSpec
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext

SPECS = [
    ParamSpec("width", "float", low=2.0, high=50.0),
    ParamSpec("numOfTurns", "int", low=1, high=12),
]


def make_ctx(tmp_path, routes):
    cli, calls = mock_cli.make_cli(tmp_path, routes)
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    store.set_project("s1", "/abs/proj")
    store.upsert_instance("s1", "m-1", template_id="t", name="n", project_dir="/abs/proj")
    store.set_active_instance("s1", "m-1")
    store.set_config_digest("s1", "sha256:d0")
    return ToolContext(cli=cli, store=store, session_id="s1"), calls, store


def ok_envelope(data):
    return {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
            "data": data, "errors": []}


def submit(job_id, status="queued", request_id=None):
    data = {"jobId": job_id, "requestId": request_id,
            "taskType": "simulation-evaluation", "status": status}
    return {"exitCode": 0, "envelope": ok_envelope(data)}


def fail_entry(code, exit_code):
    return {"exitCode": exit_code, "envelope": {
        "schemaVersion": "epcd-response/v1", "ok": False, "requestId": None,
        "data": None, "errors": [{"code": code, "path": None, "message": code}]}}


def job_get(status):
    return {"exitCode": 0, "envelope": ok_envelope({"jobId": "ignored", "status": status})}


def job_result(cost, job_id="j-x"):
    return {"exitCode": 0, "envelope": ok_envelope({
        "jobId": job_id, "taskType": "simulation-evaluation", "status": "succeeded",
        "objectiveCost": cost, "targetValues": [], "warnings": [], "artifacts": []})}


def controller(ctx, **kw):
    kw.setdefault("poll_interval", 0)
    return OptimizationController(ctx, SPECS, **kw)


def test_two_rounds_then_budget_rounds(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1"), submit("j-2")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded"), job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.5, "j-1"), job_result(0.2, "j-2")]},
    ])
    events = []
    c = controller(ctx, initial_candidates=[{"width": 10.0, "numOfTurns": 3}],
                   budget=OptimizationBudget(max_rounds=2),
                   on_progress=events.append, task_id="opt-1")
    store.create_optimization("s1", "opt-1", budget={"max_rounds": 2})
    report = c.run()
    assert report.stop_reason == "budget_rounds"
    assert report.best_job_id == "j-2"
    assert report.best_cost == pytest.approx(0.2)
    assert len(report.rounds) == 2
    assert report.rounds[0].parameters == {"width": 10.0, "numOfTurns": 3}  # initial candidate first
    assert [e["cost"] for e in events] == [pytest.approx(0.5), pytest.approx(0.2)]
    assert store.get_job("s1", "j-2")["objective_cost"] == pytest.approx(0.2)
    task = store.get_optimization("s1", "opt-1")
    assert task["status"] == "finished"
    assert task["best_job_id"] == "j-2"
    assert len(task["rounds"]) == 2


def test_target_reached_stops_early(tmp_path):
    ctx, calls, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1"), submit("j-2"), submit("j-3")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded"), job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.5, "j-1"), job_result(0.2, "j-2")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=5, target_cost=0.3))
    report = c.run()
    assert report.stop_reason == "target_reached"
    assert report.best_cost == pytest.approx(0.2)
    run_calls = [call for call in mock_cli.read_calls(calls) if call["argv"][0] == "run"]
    assert len(run_calls) == 2  # round 3 never submitted


def test_submit_business_error_pauses(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [fail_entry("BUSINESS_RULE_VIOLATION", 5)]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=3))
    with pytest.raises(OptimizationPausedError) as excinfo:
        c.run()
    assert excinfo.value.category == "needs_decision"
    assert excinfo.value.errors[0]["code"] == "BUSINESS_RULE_VIOLATION"
    assert excinfo.value.report.rounds == ()
    assert excinfo.value.report.stop_reason == "paused"


def test_submit_transient_retries_same_request_id_then_pauses(tmp_path):
    ctx, calls, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [fail_entry("SIM_EXEC_FAILED", 8),
                                              fail_entry("SIM_EXEC_FAILED", 8)]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=3))
    with pytest.raises(OptimizationPausedError) as excinfo:
        c.run()
    assert excinfo.value.category == "transient"
    run_calls = [call for call in mock_cli.read_calls(calls) if call["argv"][0] == "run"]
    assert len(run_calls) == 2
    for call in run_calls:  # both attempts use the SAME requestId (design doc section 7.3)
        assert call["argv"][call["argv"].index("--request-id") + 1] == "iteration-1"


def test_submit_transient_retry_then_success(tmp_path):
    ctx, _, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [fail_entry("RESULT_WRITE_FAILED", 9), submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.4, "j-1")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1))
    report = c.run()
    assert report.best_job_id == "j-1"
    assert report.best_cost == pytest.approx(0.4)


def test_request_id_conflict_reattaches_known_job(tmp_path):
    ctx, _, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [fail_entry("REQUEST_ID_CONFLICT", 11)]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.1, "j-7")]},
    ])
    store.add_job("s1", "j-7", request_id="iteration-1", task_type="simulation-evaluation",
                  status="running")
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1))
    report = c.run()
    assert report.best_job_id == "j-7"
    assert len(store.list_jobs("s1")) == 1


def test_failed_jobs_two_consecutive_pause(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1"), submit("j-2")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("failed"), job_get("failed")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=5))
    with pytest.raises(OptimizationPausedError) as excinfo:
        c.run()
    assert len(excinfo.value.report.rounds) == 2
    assert all(r.status == "failed" for r in excinfo.value.report.rounds)
    assert excinfo.value.category == "transient"


def test_cancel_before_round_boundary(tmp_path):
    ctx, calls, _ = make_ctx(tmp_path, [])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=3))
    c.request_cancel()
    report = c.run()
    assert report.stop_reason == "canceled"
    assert report.rounds == ()
    assert mock_cli.read_calls(calls) == []  # nothing was submitted


def test_cancel_during_poll_cancels_job(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("running"), job_get("canceled")]},
        {"argvPrefix": ["job", "cancel"], "responses": [{"exitCode": 0, "envelope": ok_envelope({})}]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=3))
    original_sleep = c._sleep
    c._sleep = lambda seconds: c.request_cancel()  # cancel right after the first poll
    report = c.run()
    assert report.stop_reason == "canceled"
    assert len(report.rounds) == 1
    assert report.rounds[0].status == "canceled"
    argvs = [call["argv"] for call in mock_cli.read_calls(calls)]
    assert ["job", "cancel", "--id", "j-1"] in argvs


def test_resume_after_crash_reuses_job_row(tmp_path):
    ctx, calls, store = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1", status="running")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.3, "j-1")]},
    ])
    # Simulate a controller that crashed right after submitting iteration-1:
    # the Store already holds the job row from the previous process.
    store.add_job("s1", "j-1", request_id="iteration-1", task_type="simulation-evaluation",
                  status="running")
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1))
    report = c.run()
    assert report.best_job_id == "j-1"
    assert report.best_cost == pytest.approx(0.3)
    jobs = store.list_jobs("s1")
    assert len(jobs) == 1                     # reused, not duplicated
    assert jobs[0]["status"] == "succeeded"
    submit_call = [call for call in mock_cli.read_calls(calls) if call["argv"][0] == "run"][0]
    assert submit_call["argv"][submit_call["argv"].index("--request-id") + 1] == "iteration-1"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_controller.py -q`
Expected: FAIL（`ModuleNotFoundError: epcd_agent.optimizer.controller`）

- [ ] **Step 3: 实现 controller.py**

```python
"""Deterministic optimization loop (design doc section 7).

Agentic trunk + deterministic island: this controller owns the 4.11-4.13
iteration loop entirely; the LLM only supplies initial candidates up front and
interprets the report afterwards. Resumability borrows the CLI's requestId
semantics: resubmitting the same requestId returns the original Job.
"""
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

import optuna

from ..exitcodes import LOOP_TRANSIENT_EXIT_CODES
from ..tools.base import ToolContext
from ..tools.read import epcd_job
from ..tools.write import epcd_run
from .space import ParamSpec, normalize_candidate

TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "canceled"})
_TPE_SEED = 20260817
_CONSECUTIVE_FAILURE_LIMIT = 2


@dataclass(frozen=True)
class OptimizationBudget:
    max_rounds: int = 20
    max_wall_seconds: float = 600.0
    target_cost: float | None = None


@dataclass(frozen=True)
class RoundRecord:
    round_no: int
    request_id: str
    parameters: dict
    job_id: str | None
    status: str  # "succeeded" | "failed" | "canceled"
    cost: float | None


@dataclass(frozen=True)
class OptimizationReport:
    best_job_id: str | None
    best_cost: float | None
    best_parameters: dict | None
    rounds: tuple[RoundRecord, ...]
    stop_reason: str  # target_reached | budget_rounds | budget_wall | canceled | paused


class OptimizationPausedError(Exception):
    """Loop paused for escalation (validation/business errors, repeated failures)."""

    def __init__(self, message: str, *, report: OptimizationReport,
                 category: str, errors: tuple[dict, ...] = ()):
        super().__init__(message)
        self.report = report
        self.category = category
        self.errors = errors


class OptimizationController:
    def __init__(self, ctx: ToolContext, specs: Iterable[ParamSpec],
                 initial_candidates: Iterable[dict] = (),
                 budget: OptimizationBudget = OptimizationBudget(),
                 request_prefix: str = "iteration", poll_interval: float = 0.05,
                 on_progress: Callable[[dict], None] | None = None,
                 task_id: str | None = None):
        self._ctx = ctx
        self._specs = tuple(specs)
        self._initial = [normalize_candidate(dict(c), self._specs) for c in initial_candidates]
        self._budget = budget
        self._prefix = request_prefix
        self._poll_interval = poll_interval
        self._on_progress = on_progress
        self._task_id = task_id
        self._cancel_requested = False
        self._failures = 0
        self._rounds: list[RoundRecord] = []
        self._best_job_id: str | None = None
        self._best_cost: float | None = None
        self._best_parameters: dict | None = None

    # -- public API ------------------------------------------------------
    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> OptimizationReport:
        study = optuna.create_study(
            direction="minimize", sampler=optuna.samplers.TPESampler(seed=_TPE_SEED))
        for candidate in self._initial:
            study.enqueue_trial(candidate)
        self._task_update(status="running")
        started = time.monotonic()
        stop_reason = "budget_rounds"
        for round_no in range(1, self._budget.max_rounds + 1):
            if self._cancel_requested:
                stop_reason = "canceled"
                break
            if time.monotonic() - started > self._budget.max_wall_seconds:
                stop_reason = "budget_wall"
                break
            request_id = f"{self._prefix}-{round_no}"
            trial = study.ask()
            params = self._suggest_params(trial)
            job_id = self._submit(params, request_id)
            status = self._poll(job_id)
            if status == "canceled":
                self._record_round(round_no, request_id, params, job_id, "canceled", None)
                stop_reason = "canceled"
                break
            if status == "failed":
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                self._record_round(round_no, request_id, params, job_id, "failed", None)
                self._failures += 1
                if self._failures >= _CONSECUTIVE_FAILURE_LIMIT:
                    self._task_update(status="paused")
                    raise OptimizationPausedError(
                        f"{self._failures} consecutive simulation jobs failed; "
                        "escalating for diagnosis (read logFile via job result)",
                        report=self._report("paused"), category="transient")
                continue
            # succeeded
            self._failures = 0
            cost = self._read_cost(job_id)
            study.tell(trial, cost)
            self._ctx.store.update_job(
                self._ctx.session_id, job_id, status="succeeded", objective_cost=cost)
            if self._best_cost is None or cost < self._best_cost:
                self._best_cost, self._best_job_id, self._best_parameters = cost, job_id, params
            self._record_round(round_no, request_id, params, job_id, "succeeded", cost)
            if self._budget.target_cost is not None and self._best_cost <= self._budget.target_cost:
                stop_reason = "target_reached"
                break
        report = self._report(stop_reason)
        self._task_update(status="finished", best_job_id=self._best_job_id,
                          rounds=[dataclasses.asdict(r) for r in self._rounds],
                          consumed={"rounds": len(self._rounds),
                                    "wall_seconds": round(time.monotonic() - started, 3)})
        return report

    # -- internals ---------------------------------------------------------
    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def _suggest_params(self, trial) -> dict:
        params: dict = {}
        for spec in self._specs:
            if spec.kind == "float":
                params[spec.name] = trial.suggest_float(spec.name, spec.low, spec.high,
                                                        step=spec.step)
            elif spec.kind == "int":
                step = int(spec.step) if spec.step else 1
                params[spec.name] = trial.suggest_int(spec.name, int(spec.low),
                                                      int(spec.high), step=step)
            else:
                params[spec.name] = trial.suggest_categorical(spec.name, list(spec.choices))
        return params

    def _submit(self, params: dict, request_id: str) -> str:
        candidate = {"schemaVersion": "epcd-candidate/v1", "parameters": params}
        for attempt in (1, 2):
            result = epcd_run(self._ctx, task="simulation-evaluation", request_id=request_id,
                              input_obj=candidate, use_if_match=True)
            if result.ok:
                return result.data["jobId"]
            if result.exit_code == 11:
                # requestId conflict: reattach the known Job for this request, if any
                known = self._ctx.store.find_job_by_request(self._ctx.session_id, request_id)
                if known is not None:
                    return known["job_id"]
                self._pause(f"request-id conflict on {request_id} with no known job", result)
            if result.exit_code in LOOP_TRANSIENT_EXIT_CODES and attempt == 1:
                continue  # retry once with the SAME requestId (design doc section 7.3)
            self._pause(f"submission failed on {request_id}", result)
        raise AssertionError("unreachable")

    def _poll(self, job_id: str) -> str:
        while True:
            if self._cancel_requested:
                epcd_job(self._ctx, action="cancel", job_id=job_id)
            result = epcd_job(self._ctx, action="get", job_id=job_id)
            if not result.ok:
                self._pause(f"polling failed for job {job_id}", result)
            status = (result.data or {}).get("status")
            if status in TERMINAL_JOB_STATUSES:
                return status
            self._sleep(self._poll_interval)

    def _read_cost(self, job_id: str) -> float:
        result = epcd_job(self._ctx, action="result", job_id=job_id)
        if not result.ok:
            self._pause(f"reading result failed for job {job_id}", result)
        cost = (result.data or {}).get("objectiveCost")
        if not isinstance(cost, (int, float)):
            self._pause(f"job {job_id} result missing objectiveCost", result)
        return float(cost)

    def _record_round(self, round_no: int, request_id: str, params: dict,
                      job_id: str | None, status: str, cost: float | None) -> None:
        record = RoundRecord(round_no, request_id, params, job_id, status, cost)
        self._rounds.append(record)
        if self._on_progress is not None:
            self._on_progress({
                "type": "round_finished", "round": round_no, "request_id": request_id,
                "job_id": job_id, "status": status, "cost": cost,
                "best_cost": self._best_cost, "best_job_id": self._best_job_id,
            })
        self._task_update(rounds=[dataclasses.asdict(r) for r in self._rounds],
                          best_job_id=self._best_job_id,
                          consumed={"rounds": len(self._rounds)})

    def _report(self, stop_reason: str) -> OptimizationReport:
        return OptimizationReport(
            best_job_id=self._best_job_id, best_cost=self._best_cost,
            best_parameters=self._best_parameters,
            rounds=tuple(self._rounds), stop_reason=stop_reason)

    def _pause(self, message: str, result) -> None:
        self._task_update(status="paused")
        raise OptimizationPausedError(
            message, report=self._report("paused"),
            category=result.category, errors=result.errors)

    def _task_update(self, **fields) -> None:
        if self._task_id is None:
            return
        if self._ctx.store.get_optimization(self._ctx.session_id, self._task_id) is None:
            return
        self._ctx.store.update_optimization(self._ctx.session_id, self._task_id, **fields)
```

注意：`run()` 中暂停路径直接 `raise`，`stop_reason="paused"` 只出现在异常携带的 report 中；正常返回的 report 不含 `"paused"`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/epcd_agent/optimizer/controller.py tests/test_controller.py
git commit -m "feat: deterministic optimization controller with resume and budgets"
```

---

### Task 11: Headless 全流程演示与端到端验收（demo/headless_flow.py + tests）

**Files:**
- Create: `demo/headless_flow.py`、`tests/e2e_scenario.py`、`tests/test_e2e_flow.py`

**Interfaces:**
- Consumes: 任务 2~10 全部模块
- Produces:
  - `demo/headless_flow.py`：`FlowAbortedError`（里程碑被拒或步骤终态失败）；`run_headless_flow(ctx: ToolContext, *, work_dir: str, technology: str, category: str, objectives_patch: dict, simulation_patch: dict, initial_candidates: list[dict], budget: OptimizationBudget, confirm: Callable[[str, dict], str], template_index: int = 0, instance_name: str | None = None) -> dict`。按 release §4.1~4.15 顺序执行，返回 `{"milestones": [已确认里程碑名序], "best_job_id", "best_cost", "stop_reason", "rounds": <轮数>, "final": <final run 的 data>}`。
    里程碑即设计文档 §8 的 M1/M2/M3/M4：每处调 `confirm(name, payload)`，将 `(name, choice, payload)` 记入 `store.record_milestone`；choice ≠ `"approved"` 抛 `FlowAbortedError`。
    步骤序列：4.1 `epcd_health`（失败/degraded 不阻断，degraded 仅透传）→ 4.2 `project init` + `describe` + `validate` → 4.3 `device-template list` + `describe` → **M1**（payload：templateId + 实例名）→ 4.4 `device add` → 4.5 `config schema --path /device/parameters` 并 `parse_parameter_schema` → 4.6 `config get`（取 digest）→ **M2**（payload：synthesisTargets + simulation + budget + 无界参数名单）→ `config patch` 目标 → `config get` 刷新 digest → `config patch` 仿真 → 4.7 预览 `run --task gds-generation --wait --request-id preview-001` → 4.11~4.13 `OptimizationController`（`task_id="opt-1"`，先 `create_optimization`；暂停异常转 `FlowAbortedError`）→ `job result` 读最优轮 targetValues → **M3**（payload：bestJobId/bestCost/targetValues/轮数）→ 4.14 `config apply-result` → **M4**（payload：写回后 digest）→ 4.15 final `run`（无 `--input`、`--wait`、`--request-id final-<best-job-id>`、`use_if_match=True`）。任何一步 `ok=False` → `FlowAbortedError`（含 errors 信息）。
  - `demo/headless_flow.py` 的 `main()`：argparse 参数 `--work-dir`、`--technology`、`--category`（默认 `inductor`）、`--db`（默认 `./epcd-agent-store.sqlite3`）；用真实 `EpcdCli()`（默认 binary `epcd-cli`）+ `SessionStore` 跑电感验收场景（目标 JSON 即 spec §1 的 2.4GHz L≈10nH/Q>20），confirm 用 `input()` 交互。这是计划 1 的人工冒烟入口。
  - `tests/e2e_scenario.py`：`build_routes() -> list[dict]`——电感验收场景的完整 mock 路由（覆盖上述全部命令），供 E2E 测试使用。
  - `tests/test_e2e_flow.py`：两个验收测试（见步骤 1）。

- [ ] **Step 1: 写失败测试（先写场景构造器与 E2E 断言）**

`tests/e2e_scenario.py`：

```python
"""Full mock route set for the inductor acceptance scenario (spec section 1)."""
from __future__ import annotations

PARAM_SCHEMA = {
    "type": "object",
    "properties": {
        "width": {"type": "number", "minimum": 2.0, "maximum": 50.0},
        "numOfTurns": {"type": "integer", "minimum": 1, "maximum": 12},
    },
    "additionalProperties": False,
}

FINAL_ARTIFACTS = [
    {"type": "gds", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/layout.gds"},
    {"type": "gtxt", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/layout.gtxt"},
    {"type": "layout-preview-image", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/layout.png"},
    {"type": "snp", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/graphs.s2p"},
    {"type": "target-values", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/target-values.json"},
    {"type": "target-chart", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/target-chart.png"},
    {"type": "manifest", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/manifest.json"},
]


def _ok(data):
    return {"exitCode": 0, "envelope": {
        "schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
        "data": data, "errors": []}}


def build_routes() -> list[dict]:
    return [
        {"argvPrefix": ["version"], "responses": [_ok({"version": "1.0.0"})]},
        {"argvPrefix": ["health"], "responses": [_ok({"status": "ok", "version": "1.0.0"})]},
        {"argvPrefix": ["project", "init"], "responses": [_ok({
            "created": True, "project": "/abs/proj", "libName": "demo_project",
            "technologyPath": "/abs/proj/technology/process.ptxt",
            "technologyDigest": "sha256:tech", "technologyCopied": True, "warnings": []})]},
        {"argvPrefix": ["project", "describe"], "responses": [_ok({"project": "/abs/proj"})]},
        {"argvPrefix": ["project", "validate"], "responses": [_ok({"valid": True})]},
        {"argvPrefix": ["device-template", "list"], "responses": [_ok({
            "templates": [{"templateId": "system.inductor.simple_inductor",
                           "category": "inductor", "name": "simple_inductor"}]})]},
        {"argvPrefix": ["device-template", "describe"], "responses": [_ok({
            "templateId": "system.inductor.simple_inductor", "namespace": "system",
            "category": "inductor", "name": "simple_inductor", "available": True,
            "parameterSchema": PARAM_SCHEMA, "builtInMetrics": ["L", "Q"],
            "previewArtifacts": []})]},
        {"argvPrefix": ["project", "device", "add"], "responses": [_ok({
            "created": True, "project": "/abs/proj", "instanceId": "m-1",
            "name": "simple_inductor1", "folderName": "simple_inductor1",
            "templateId": "system.inductor.simple_inductor", "warnings": []})]},
        {"argvPrefix": ["config", "schema"], "responses": [_ok({
            "project": "/abs/proj", "instanceId": "m-1",
            "templateId": "system.inductor.simple_inductor",
            "schemaVersion": "epcd-device-schema/v1", "path": "/device/parameters",
            "schema": PARAM_SCHEMA, "schemaDigest": "sha256:schema"})]},
        {"argvPrefix": ["config", "get"], "responses": [
            _ok({"project": "/abs/proj", "instanceId": "m-1", "path": None,
                 "value": {}, "configDigest": "sha256:d0"}),       # step 4.6
            _ok({"project": "/abs/proj", "instanceId": "m-1", "path": None,
                 "value": {}, "configDigest": "sha256:d1"}),       # refresh before simulation patch
        ]},
        {"argvPrefix": ["config", "patch"], "responses": [
            _ok({"changed": True, "configDigest": "sha256:d1"}),   # synthesisTargets
            _ok({"changed": True, "configDigest": "sha256:d2"}),   # simulation
        ]},
        {"argvPrefix": ["config", "apply-result"], "responses": [
            _ok({"applied": True, "configDigest": "sha256:post"})]},
        {"argvPrefix": ["run"], "responses": [
            _ok({"jobId": "j-preview", "requestId": "preview-001",
                 "taskType": "gds-generation", "status": "succeeded",
                 "artifacts": [{"type": "gds", "path": "/abs/p.gds"},
                               {"type": "gtxt", "path": "/abs/p.gtxt"},
                               {"type": "layout-preview-image", "path": "/abs/p.png"},
                               {"type": "manifest", "path": "/abs/m.json"}]}),
            _ok({"jobId": "j-1", "requestId": "iteration-1",
                 "taskType": "simulation-evaluation", "status": "queued",
                 "configDigestUsed": "sha256:d2"}),
            _ok({"jobId": "j-2", "requestId": "iteration-2",
                 "taskType": "simulation-evaluation", "status": "queued",
                 "configDigestUsed": "sha256:d2"}),
            _ok({"jobId": "j-final", "requestId": "final-j-2",
                 "taskType": "simulation-evaluation", "status": "succeeded",
                 "configDigestUsed": "sha256:post",
                 "artifacts": FINAL_ARTIFACTS,
                 "publication": {"directory": "/abs/dev/synthesis/RangeEM",
                                 "artifacts": [{"type": "snp", "path": "/abs/dev/synthesis/RangeEM/graphs.s2p"},
                                               {"type": "gds", "path": "/abs/dev/synthesis/RangeEM/run.gds"}]}}),
        ]},
        {"argvPrefix": ["job", "get"], "responses": [
            _ok({"jobId": "j-1", "status": "succeeded"}),
            _ok({"jobId": "j-2", "status": "succeeded"}),
        ]},
        {"argvPrefix": ["job", "result"], "responses": [
            _ok({"jobId": "j-1", "taskType": "simulation-evaluation", "status": "succeeded",
                 "objectiveCost": 0.6, "targetValues": [
                     {"metric": "L", "actualValue": 8.1, "targetValue": 10, "satisfied": False,
                      "relativeDeviation": 0.19, "objectiveCost": 0.6}],
                 "warnings": [], "artifacts": [], "logFile": "/abs/j-1.log"}),
            _ok({"jobId": "j-2", "taskType": "simulation-evaluation", "status": "succeeded",
                 "objectiveCost": 0.18, "targetValues": [
                     {"metric": "L", "actualValue": 9.9, "targetValue": 10, "satisfied": True,
                      "relativeDeviation": 0.01, "objectiveCost": 0.08},
                     {"metric": "Q", "actualValue": 22.0, "targetValue": 20, "satisfied": True,
                      "relativeDeviation": 0.0, "objectiveCost": 0.1}],
                 "warnings": [], "artifacts": [], "logFile": "/abs/j-2.log"}),
            # best-job result fetched for the M3 confirmation payload:
            _ok({"jobId": "j-2", "taskType": "simulation-evaluation", "status": "succeeded",
                 "objectiveCost": 0.18, "targetValues": [], "warnings": [], "artifacts": []}),
        ]},
    ]
```

`tests/test_e2e_flow.py`：

```python
import sys
from pathlib import Path

import mock_cli
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

from e2e_scenario import FINAL_ARTIFACTS, build_routes  # noqa: E402
from headless_flow import FlowAbortedError, run_headless_flow  # noqa: E402

from epcd_agent.optimizer.controller import OptimizationBudget  # noqa: E402
from epcd_agent.store import SessionStore  # noqa: E402
from epcd_agent.tools.base import ToolContext  # noqa: E402

OBJECTIVES = {
    "synthesisTargets": {
        "frequencyMode": "points",
        "customMetrics": [],
        "objectives": [
            {"metric": "L", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
             "comparison": "equal", "targetValue": 10, "unit": "nH", "weight": 5},
            {"metric": "Q", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
             "comparison": "greater-than", "targetValue": 20, "unit": "", "weight": 8},
        ],
    }
}
SIMULATION = {
    "simulation": {
        "solver": {"type": "em"},
        "execution": {"mode": "local"},
        "sweeps": [{"enabled": True, "type": "adaptive",
                    "start": {"value": 1, "unit": "GHz"},
                    "stop": {"value": 3, "unit": "GHz"},
                    "maximumStep": {"value": 10, "unit": "MHz"}}],
    }
}


def make_ctx(tmp_path):
    cli, calls = mock_cli.make_cli(tmp_path, build_routes())
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    return ToolContext(cli=cli, store=store, session_id="s1"), calls, store


def flow_kwargs(confirm):
    return dict(
        work_dir="/abs/proj", technology="/abs/process.ptxt", category="inductor",
        objectives_patch=OBJECTIVES, simulation_patch=SIMULATION,
        initial_candidates=[{"width": 10.0, "numOfTurns": 3}],
        budget=OptimizationBudget(max_rounds=2, target_cost=0.2),
        confirm=confirm, instance_name="L1",
    )


def test_end_to_end_acceptance(tmp_path):
    ctx, calls, store = make_ctx(tmp_path)
    asked = []

    def confirm(milestone, payload):
        asked.append(milestone)
        return "approved"

    summary = run_headless_flow(ctx, **flow_kwargs(confirm))

    # exactly the 4 mandatory confirmations, in order (design doc section 8)
    assert asked == ["M1", "M2", "M3", "M4"]
    assert [m["name"] for m in store.list_milestones("s1")] == ["M1", "M2", "M3", "M4"]

    # optimization delivered the best job within budget
    assert summary["best_job_id"] == "j-2"
    assert summary["best_cost"] == pytest.approx(0.18)
    assert summary["stop_reason"] == "target_reached"

    # final run used the post-apply digest and the fixed requestId scheme
    run_calls = [c for c in mock_cli.read_calls(calls) if c["argv"][0] == "run"]
    final_call = run_calls[-1]
    assert final_call["stdin"] is None              # no --input: post-apply parameters (release 4.15)
    assert "--input" not in final_call["argv"]
    assert final_call["argv"][final_call["argv"].index("--request-id") + 1] == "final-j-2"
    assert final_call["argv"][final_call["argv"].index("--if-match") + 1] == "sha256:post"

    # all 7 artifact types + RangeEM publication (release 4.15 / section 5)
    artifact_types = {a["type"] for a in summary["final"]["artifacts"]}
    assert artifact_types == {a["type"] for a in FINAL_ARTIFACTS}
    assert summary["final"]["publication"]["directory"].endswith("synthesis/RangeEM")

    # every job was ledgered into the Session Store
    job_ids = {j["job_id"] for j in store.list_jobs("s1")}
    assert {"j-preview", "j-1", "j-2", "j-final"} <= job_ids
    assert store.get_optimization("s1", "opt-1")["status"] == "finished"


def test_user_terminates_at_m2(tmp_path):
    ctx, _, store = make_ctx(tmp_path)

    def confirm(milestone, payload):
        return "approved" if milestone == "M1" else "terminate"

    with pytest.raises(FlowAbortedError):
        run_headless_flow(ctx, **flow_kwargs(confirm))
    rows = store.list_milestones("s1")
    assert [r["name"] for r in rows] == ["M1", "M2"]
    assert rows[1]["choice"] == "terminate"
    # no optimization task was started after rejection
    assert store.get_optimization("s1", "opt-1") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_e2e_flow.py -q`
Expected: FAIL（`ModuleNotFoundError: headless_flow`）

- [ ] **Step 3: 实现 demo/headless_flow.py**

```python
"""Headless end-to-end P0 flow (release doc sections 4.1-4.15), no LLM.

Plan 2 replaces the `confirm` callback with the Agent SDK's built-in
AskUserQuestion; everything else is reused unchanged.

CLI usage against a real epcd-cli:
    python demo/headless_flow.py --work-dir /path/proj --technology /path/process.ptxt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epcd_agent.cli_client import EpcdCli                    # noqa: E402
from epcd_agent.optimizer.controller import (                # noqa: E402
    OptimizationBudget,
    OptimizationController,
    OptimizationPausedError,
)
from epcd_agent.optimizer.space import parse_parameter_schema  # noqa: E402
from epcd_agent.store import SessionStore                     # noqa: E402
from epcd_agent.tools.base import ToolContext                 # noqa: E402
from epcd_agent.tools.config import epcd_config               # noqa: E402
from epcd_agent.tools.read import epcd_health, epcd_job, epcd_template  # noqa: E402
from epcd_agent.tools.write import epcd_device, epcd_project, epcd_run  # noqa: E402


class FlowAbortedError(Exception):
    """A milestone was rejected, or a step failed terminally."""


def _require(result, step: str):
    if not result.ok:
        codes = ",".join(e["code"] for e in result.errors) or "UNKNOWN"
        raise FlowAbortedError(f"{step} failed: {codes} (exit {result.exit_code})")
    return result


def run_headless_flow(ctx: ToolContext, *, work_dir: str, technology: str, category: str,
                     objectives_patch: dict, simulation_patch: dict,
                     initial_candidates: list[dict], budget: OptimizationBudget,
                     confirm: Callable[[str, dict], str],
                     template_index: int = 0, instance_name: str | None = None) -> dict:
    confirmed: list[str] = []

    def checkpoint(name: str, payload: dict) -> None:
        choice = confirm(name, payload)
        ctx.store.record_milestone(ctx.session_id, name, choice, snapshot=payload)
        confirmed.append(name)
        if choice != "approved":
            raise FlowAbortedError(f"milestone {name} rejected with choice {choice!r}")

    # 4.1 health check
    health = _require(epcd_health(ctx), "health check")
    if health.data["health"].get("status") == "degraded":
        print("[warn] epcd health degraded; continuing", file=sys.stderr)

    # 4.2 project init + describe + validate
    _require(epcd_project(ctx, action="init", work_dir=work_dir, technology=technology),
             "project init")
    _require(epcd_project(ctx, action="describe"), "project describe")
    _require(epcd_project(ctx, action="validate"), "project validate")

    # 4.3 template list + describe
    listing = _require(epcd_template(ctx, action="list", category=category), "template list")
    templates = listing.data.get("templates", [])
    if template_index >= len(templates):
        raise FlowAbortedError(f"template index {template_index} out of range ({len(templates)})")
    template_id = templates[template_index]["templateId"]
    describe = _require(epcd_template(ctx, action="describe", template_id=template_id),
                        "template describe")

    # M1: selection confirmation (design doc section 8)
    checkpoint("M1", {"templateId": template_id, "instanceName": instance_name,
                      "available": describe.data.get("available"),
                      "builtInMetrics": describe.data.get("builtInMetrics", [])})

    # 4.4 instantiate device
    _require(epcd_device(ctx, action="add", template_id=template_id, name=instance_name),
             "device add")

    # 4.5 parameter schema -> optimization space
    schema_result = _require(epcd_config(ctx, action="schema", path="/device/parameters"),
                             "config schema")
    space = parse_parameter_schema(schema_result.data["schema"])

    # 4.6 fetch current config + digest
    _require(epcd_config(ctx, action="get"), "config get")

    # M2: objectives + simulation + budget confirmed together (design doc section 8)
    checkpoint("M2", {"synthesisTargets": objectives_patch["synthesisTargets"],
                      "simulation": simulation_patch["simulation"],
                      "budget": {"max_rounds": budget.max_rounds,
                                 "max_wall_seconds": budget.max_wall_seconds,
                                 "target_cost": budget.target_cost},
                      "unboundedParameters": list(space.unbounded)})

    # 4.9 write objectives, 4.10 write simulation config
    _require(epcd_config(ctx, action="patch", patch_obj=objectives_patch), "patch objectives")
    _require(epcd_config(ctx, action="get"), "config get (refresh digest)")
    _require(epcd_config(ctx, action="patch", patch_obj=simulation_patch), "patch simulation")

    # 4.7 layout preview
    _require(epcd_run(ctx, task="gds-generation", request_id="preview-001", wait=True),
             "preview run")

    # 4.11-4.13 optimization loop (deterministic island)
    ctx.store.create_optimization(ctx.session_id, "opt-1",
                                  budget={"max_rounds": budget.max_rounds,
                                          "max_wall_seconds": budget.max_wall_seconds,
                                          "target_cost": budget.target_cost})
    controller = OptimizationController(ctx, space.specs, initial_candidates, budget,
                                        task_id="opt-1",
                                        on_progress=lambda e: print(f"[opt] {e}", file=sys.stderr))
    try:
        report = controller.run()
    except OptimizationPausedError as exc:
        raise FlowAbortedError(f"optimization paused: {exc} (category={exc.category})") from exc
    if report.best_job_id is None:
        raise FlowAbortedError(f"optimization finished without any succeeded job ({report.stop_reason})")

    # M3: write-back confirmation with achieved metrics
    best_result = _require(epcd_job(ctx, action="result", job_id=report.best_job_id),
                           "best job result")
    checkpoint("M3", {"bestJobId": report.best_job_id, "bestCost": report.best_cost,
                      "rounds": len(report.rounds), "stopReason": report.stop_reason,
                      "targetValues": best_result.data.get("targetValues", [])})

    # 4.14 apply best parameters
    _require(epcd_config(ctx, action="apply-result", job_id=report.best_job_id), "apply-result")

    # M4: final simulation confirmation
    checkpoint("M4", {"configDigest": ctx.store.get_config_digest(ctx.session_id),
                      "requestId": f"final-{report.best_job_id}"})

    # 4.15 final formal simulation (no --input: uses post-apply parameters)
    final = _require(epcd_run(ctx, task="simulation-evaluation",
                              request_id=f"final-{report.best_job_id}",
                              wait=True, use_if_match=True), "final run")
    return {"milestones": confirmed, "best_job_id": report.best_job_id,
            "best_cost": report.best_cost, "stop_reason": report.stop_reason,
            "rounds": len(report.rounds), "final": final.data}


def _interactive_confirm(milestone: str, payload: dict) -> str:
    print(f"\n=== milestone {milestone} ===")
    for key, value in payload.items():
        print(f"  {key}: {value}")
    answer = input("approve? [yes/no]: ").strip().lower()
    return "approved" if answer in ("y", "yes") else "terminate"


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless EPCD P0 flow (no LLM)")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--technology", required=True)
    parser.add_argument("--category", default="inductor")
    parser.add_argument("--db", default="./epcd-agent-store.sqlite3")
    args = parser.parse_args()

    store = SessionStore(args.db)
    store.create_session("headless-1")
    ctx = ToolContext(cli=EpcdCli(), store=store, session_id="headless-1")
    objectives = {
        "synthesisTargets": {
            "frequencyMode": "points", "customMetrics": [],
            "objectives": [
                {"metric": "L", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
                 "comparison": "equal", "targetValue": 10, "unit": "nH", "weight": 5},
                {"metric": "Q", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
                 "comparison": "greater-than", "targetValue": 20, "unit": "", "weight": 8},
            ],
        }
    }
    simulation = {
        "simulation": {
            "solver": {"type": "em"}, "execution": {"mode": "local"},
            "sweeps": [{"enabled": True, "type": "adaptive",
                        "start": {"value": 1, "unit": "GHz"},
                        "stop": {"value": 3, "unit": "GHz"},
                        "maximumStep": {"value": 10, "unit": "MHz"}}],
        }
    }
    try:
        summary = run_headless_flow(
            ctx, work_dir=args.work_dir, technology=args.technology, category=args.category,
            objectives_patch=objectives, simulation_patch=simulation,
            initial_candidates=[{"width": 10.0, "numOfTurns": 3}],
            budget=OptimizationBudget(max_rounds=10, max_wall_seconds=3600),
            confirm=_interactive_confirm, instance_name="L1")
    except FlowAbortedError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 1
    print(f"DONE: best={summary['best_job_id']} cost={summary['best_cost']} "
          f"rounds={summary['rounds']} artifacts={len(summary['final'].get('artifacts', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: 全部 PASS（含既有全部任务测试）

- [ ] **Step 5: 人工冒烟（对 mock）**

```bash
cd c:/Users/cube/Desktop/EPCD/epcd-agent
python - <<'EOF'
import json, os, subprocess, sys, tempfile, pathlib
sys.path.insert(0, "tests")
from e2e_scenario import build_routes
d = pathlib.Path(tempfile.mkdtemp())
(d / "scenario.json").write_text(json.dumps({"routes": build_routes()}), encoding="utf-8")
print("scenario:", d / "scenario.json")
EOF
```

验证 `build_routes()` 可序列化无异常即可（真实 `epcd-cli` 的冒烟放到集成环境，属计划 2 验收）。

- [ ] **Step 6: 提交**

```bash
git add demo/headless_flow.py tests/e2e_scenario.py tests/test_e2e_flow.py
git commit -m "feat: headless end-to-end P0 flow with milestone confirmations"
```

---

## 计划 1 边界说明（不在本计划内，属计划 2）

- `optimization_start/status/cancel` 与 `artifact_view` 两个平台工具：需要 Agent 运行时的任务注册与推送通道，计划 2 以本计划的 `OptimizationController`/Store 为内核实现。
- Claude Agent SDK 接入（`@tool` + `create_sdk_mcp_server` 包装本计划工具、`resume` 会话映射、`can_use_tool` 拦截 AskUserQuestion）、`.claude/skills/standard-optimize-flow/SKILL.md`、WebSocket/SSE 推送、Web 前端。
- 真实 epcd-cli 集成环境中的联调（本计划全部测试基于 mock，不依赖真实环境）。
  已知环境事实：EPCD 服务器为 `zhubo@192.168.20.243`（免密公钥已就绪），
  `epcd-cli` 将由服务器侧配置为全局命令；届时以
  `EpcdCli(argv_prefix=("ssh", "zhubo@192.168.20.243", "epcd-cli"))` 接入，
  零代码改动（stdin 管道透传已冒烟验证）。
- 实测（2026-08-20，服务器 build 0.1.0）与 release 契约的差异，已在计划 1 代码内兼容：
  `project init` 返回 `data.path`（非 `data.project`）且无 digest 字段；
  stdout 在 envelope 前有求解器 `Warning:` 行（`parse_envelope` 自首个 `{` 恢复）。
  遗留到计划 2：`parameterSchema` 为 basic/opt/synth 嵌套分组、数值边界为字符串，
  `optimizer/space.py` 需按真实 schema 形态适配。

## 计划自审记录（写计划者已执行）

1. **Spec 覆盖**：§4 工具层 → 任务 5~8；§4.1 三条硬规则 → 任务 5（注入）/7（记账）/8（digest 自动重试）；§7 优化控制器 → 任务 9~10（含 §7.3 失败分类与 requestId 恢复、预算停止）；§9 Store 表 → 任务 4；§8 里程碑留痕 → 任务 11（`record_milestone` 4 次）；§10 错误路由 → 任务 2 `classify_exit` + 任务 10 暂停分类；§11 三层测试 → 任务 3（mock 夹具）、6~8（工具单测）、10（控制器含崩溃恢复）、11（E2E 断言 4 次确认 + 7 类 artifacts + RangeEM 发布）；§14 无界参数 → 任务 9 `unbounded` + 任务 11 M2 payload 透传。
2. **占位符扫描**：无 TBD/TODO/“类似任务 N”；每个代码步骤均给出完整代码。
3. **类型一致性**：`ExecResult/ToolResult/ToolContext/inject_ids/require_digest`（任务 3/5）被任务 6~11 原样引用；`ParamSpec/ParsedSpace/normalize_candidate`（任务 9）被任务 10~11 原样引用；`OptimizationBudget/Controller/report 字段`（任务 10）被任务 11 原样引用；Store 方法名与任务 4 签名一致。
4. **已知风险**：Optuna `suggest_*` 与 `enqueue_trial` 混用为官方支持模式（dequeue 优先消费 enqueue 值）；若执行环境中 Optuna 版本行为不一致，以任务 10 测试失败信息为准修正 `_suggest_params`，不改接口。

---

## 执行交接

计划已保存。两种执行方式：

1. **Subagent-Driven（推荐）**：每个任务派发全新 subagent，任务间两阶段评审，快速迭代。
2. **Inline Execution**：本会话内按 executing-plans 批量执行，检查点处复核。

