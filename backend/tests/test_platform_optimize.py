import mock_cli
import pytest

from epcd_agent.platform.optimize_tools import (
    optimization_cancel,
    optimization_start,
    optimization_status,
)
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext, ToolInputError

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


def test_optimization_start_requires_optimizable_params(tmp_path):
    ctx, _ = make_ctx(tmp_path, [])
    empty = {"type": "object", "properties": {"opt": {"type": "object", "properties": {}}}}
    with pytest.raises(ToolInputError):
        optimization_start(ctx, parameter_schema=empty)


def test_optimization_start_falls_back_to_describe_addin(tmp_path):
    """Legacy last resort: addinParams only when describe().parameterSchema 缺失.

    只有老 build 的 describe() 不带 parameterSchema 时才退回 addinParams；当前 build
    parameterSchema 已返回真实优化参数，必须优先走 parameterSchema（见下一条回归测试）。
    """
    addin = [[
        {"jsonKeyStr": "trackWidth", "fieldType": "0", "enableWhole": "1",
         "defValue": "10", "min": "6", "max": "20", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "numOfTurns", "fieldType": "0", "enableWhole": "1",
         "defValue": "3", "min": "1", "max": "8", "stepValue": "0.25",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "joinSimulation", "fieldType": "2", "enableWhole": "1",
         "defValue": "0", "min": "None", "max": "None", "stepValue": "None",
         "visibleControlKey": "None"},
    ]]
    routes = [
        {"argvPrefix": ["device-template", "describe"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({"addinParams": addin})}]},
        *job_routes(2),
    ]
    ctx, _ = make_ctx(tmp_path, routes)
    empty = {"type": "object", "properties": {"opt": {"type": "object", "properties": {}}}}
    r = optimization_start(ctx, parameter_schema=empty,
                           initial_candidates=[{"trackWidth": 10.0, "numOfTurns": 3.0}],
                           max_rounds=2)
    assert r.ok is True
    assert r.data["report"]["stop_reason"] == "budget_rounds"
    assert r.data["report"]["best_job_id"] == "j-2"
    rounds = r.data["report"]["rounds"]
    assert all(round["status"] == "succeeded" for round in rounds)


def test_optimization_start_prefers_parameter_schema_over_addin(tmp_path):
    """回归：优化空间必须取自 describe().parameterSchema，而非 addinParams。

    addinParams 是面板参数堆（shielding / metal-fill / guard-ring / pin），服务器会
    忽略这些键、每轮都跑默认几何。此前 _space_from_schema 在调用方 schema 解析不到时
    直接落到 addinParams，导致 TPE 在 offset/width/spacing/shape/... 上瞎跑。
    """
    parameter_schema = {
        "type": "object",
        "properties": {
            "opt": {"type": "object", "properties": {
                "trackWidth": {"type": "number", "minimum": 6.0, "maximum": 20.0,
                               "x-epcd-enabled": True, "x-epcd-locked": False},
                "numOfTurns": {"type": "number", "minimum": 0.5, "maximum": 8.0,
                               "multipleOf": 0.5, "x-epcd-enabled": True,
                               "x-epcd-locked": False},
            }},
        },
    }
    panel_dump = [[
        {"jsonKeyStr": "offset", "fieldType": "0", "enableWhole": "1",
         "defValue": "0", "min": "-100.0", "max": "100.0", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "width", "fieldType": "0", "enableWhole": "1",
         "defValue": "1", "min": "0.2", "max": "10.0", "stepValue": "None",
         "visibleControlKey": "None"},
    ]]
    routes = [
        {"argvPrefix": ["device-template", "describe"], "responses": [
            {"exitCode": 0, "envelope": ok_envelope({
                "parameterSchema": parameter_schema, "addinParams": panel_dump})}]},
        *job_routes(2),
    ]
    ctx, _ = make_ctx(tmp_path, routes)
    empty = {"type": "object",
             "properties": {"opt": {"type": "object", "properties": {}}}}
    r = optimization_start(ctx, parameter_schema=empty, max_rounds=2)
    assert r.ok is True
    rounds = r.data["report"]["rounds"]
    assert all(rd["status"] == "succeeded" for rd in rounds)
    # 参数键必须来自 parameterSchema（trackWidth/numOfTurns），而非 addinParams
    for rd in rounds:
        assert set(rd["parameters"]) == {"trackWidth", "numOfTurns"}


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


def test_optimization_start_resume_warm_starts_from_prior_rounds(tmp_path):
    """继续优化不复现：resume_from 把上一 task 的成功轮喂回 TPE 作为已观测样本。

    用户「追加轮次」时不应从头（round 1）再烧种子；warm_started_rounds 应等于上一
    task 的成功轮数，且新一轮以唯一 request prefix 继续（不会 requestId 冲突）。
    """
    ctx, store = make_ctx(tmp_path, job_routes(4))
    r1 = optimization_start(ctx, parameter_schema=SCHEMA,
                            initial_candidates=[{"trackWidth": 10.0}],
                            max_rounds=2)
    assert r1.ok is True
    task1 = r1.data["task_id"]
    assert store.get_optimization("s1", task1)["status"] == "finished"

    r2 = optimization_start(ctx, parameter_schema=SCHEMA,
                            initial_candidates=[{"trackWidth": 10.0}],
                            max_rounds=2, resume_from=task1)
    assert r2.ok is True
    assert r2.data["resume_from"] == task1
    assert r2.data["warm_started_rounds"] == 2          # 上一 task 的 2 个成功轮
    assert r2.data["report"]["best_job_id"] == "j-4"     # cost 递减，j-4 最优
    assert r2.data["task_id"] != task1
    task2 = store.get_optimization("s1", r2.data["task_id"])
    assert task2["status"] == "finished"
    assert len(task2["rounds"]) == 2                     # 新一轮自身 2 轮（非复刻）


def test_optimization_start_resume_unknown_task_degrades_to_fresh(tmp_path):
    ctx, _ = make_ctx(tmp_path, job_routes(2))
    r = optimization_start(ctx, parameter_schema=SCHEMA,
                           initial_candidates=[{"trackWidth": 10.0}],
                           max_rounds=2, resume_from="opt-nonexistent")
    assert r.ok is True
    assert r.data["resume_from"] == "opt-nonexistent"
    assert r.data["warm_started_rounds"] == 0            # 未知 task → 空历史，不报错
    assert r.data["report"]["stop_reason"] == "budget_rounds"


def test_optimization_cancel_sets_flag_and_status_reads_task(tmp_path):
    ctx, store = make_ctx(tmp_path, job_routes(1))
    store.create_optimization("s1", "opt-1", {"max_rounds": 3})
    assert optimization_cancel(ctx, "opt-1").ok is True
    assert store.get_state("s1", "opt-cancel:opt-1") is True
    st = optimization_status(ctx, "opt-1")
    assert st.ok is True and st.data["task_id"] == "opt-1"
    assert st.data["cancel_requested"] is True
    assert optimization_status(ctx, "nope").ok is False
    assert optimization_cancel(ctx, "nope").ok is False


# ── per-template TPE settings resolution ────────────────────────────────────

def test_optimization_start_applies_template_tpe_settings(tmp_path, monkeypatch):
    """Template table overrides the built-in defaults when no explicit arg.

    stack_inductor is a "hard" template → startup_trials=10, max_rounds=20.
    The resolution must surface in the returned data and drive the sampler.
    """
    import optuna.samplers

    schema = dict(SCHEMA, template_id="system.inductor.stack_inductor")
    captured = {}
    real = optuna.samplers.TPESampler

    class Spy(real):
        def __init__(self, *a, **kw):
            captured.update(kw)
            super().__init__(*a, **kw)

    monkeypatch.setattr(optuna.samplers, "TPESampler", Spy)
    ctx, _ = make_ctx(tmp_path, job_routes(20))
    r = optimization_start(ctx, parameter_schema=schema,
                           initial_candidates=[{"trackWidth": 10.0}])
    assert r.ok is True
    assert r.data["startup_trials"] == 10
    assert r.data["max_rounds"] == 20
    assert captured.get("n_startup_trials") == 10


def test_optimization_start_explicit_args_beat_template(tmp_path):
    """Explicit max_rounds/startup_trials win over the per-template table."""
    schema = dict(SCHEMA, template_id="system.inductor.stack_inductor")
    ctx, _ = make_ctx(tmp_path, job_routes(3))
    r = optimization_start(ctx, parameter_schema=schema,
                           initial_candidates=[{"trackWidth": 10.0}],
                           max_rounds=3, startup_trials=7)
    assert r.ok is True
    assert r.data["max_rounds"] == 3
    assert r.data["startup_trials"] == 7


def test_optimization_start_defaults_when_unknown_template(tmp_path):
    """Unknown template (no table entry) falls back to 5 / 15 built-ins."""
    schema = dict(SCHEMA, template_id="system.inductor.unknown_template")
    ctx, _ = make_ctx(tmp_path, job_routes(15))
    r = optimization_start(ctx, parameter_schema=schema,
                           initial_candidates=[{"trackWidth": 10.0}])
    assert r.ok is True
    assert r.data["startup_trials"] == 5
    assert r.data["max_rounds"] == 15
