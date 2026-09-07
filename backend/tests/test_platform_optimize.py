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
    """P0: empty opt schema + active-instance template_id → addinParams space.

    2026-08-27 起服务器 describe 的 parameterSchema.opt.properties 为空，真实参数
    在 addinParams；optimization_start 应解析 describe().addinParams 而非报错。
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
    assert optimization_cancel(ctx, "nope").ok is False
