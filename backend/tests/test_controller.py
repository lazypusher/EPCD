import dataclasses

import mock_cli
import pytest

from epcd_agent.optimizer.controller import (
    OptimizationBudget,
    OptimizationController,
    OptimizationPausedError,
    _TPE_SEED,
    _TPE_STARTUP_TRIALS,
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


# --- real server job-result shape: no top-level objectiveCost ----------------
# Observed on epcd-cli 0.1.0 (release §4.12 corrected): the result carries
# targetValues entries; the scalar must be derived when objectiveCost is absent.

def job_result_targets(targets, job_id="j-1"):
    return {"exitCode": 0, "envelope": ok_envelope({
        "jobId": job_id, "taskType": "simulation-evaluation", "status": "succeeded",
        "targetValues": targets, "warnings": [], "artifacts": []})}


def test_cost_falls_back_to_per_target_objective_cost(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result_targets(
            [{"metric": "inductance", "objectiveCost": 0.2},
             {"metric": "minQFactor", "objectiveCost": 0.1}], "j-1")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1))
    report = c.run()
    assert report.best_cost == pytest.approx(0.3)


def test_cost_falls_back_to_relative_deviation(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result_targets(
            [{"metric": "inductance", "satisfied": True, "relativeDeviation": 0.05},
             {"metric": "minQFactor", "satisfied": False, "relativeDeviation": 0.2}],
            "j-1")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1))
    report = c.run()
    assert report.best_cost == pytest.approx(0.25)


def test_no_objective_data_at_all_pauses(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result_targets([], "j-1")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=3))
    with pytest.raises(OptimizationPausedError):
        c.run()


def test_resume_observations_seed_study_before_first_round(monkeypatch, tmp_path):
    """resume_observations 必须作为已观测 trial 注入 Optuna study（warm start）。

    回归：追加轮次时若不复用上一 task 的成功样本，TPE 从空后验重来，等于白烧种子。
    这里窥探 optuna.trial.create_trial 的调用次数，确认每个观测都真正落进 study。
    """
    import optuna.trial

    created = {"n": 0}
    real = optuna.trial.create_trial

    def spy(*a, **kw):
        created["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(optuna.trial, "create_trial", spy)

    ctx, calls, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.3, "j-1")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1),
                   resume_observations=[
                       {"parameters": {"width": 10.0, "numOfTurns": 3}, "cost": 0.9},
                       {"parameters": {"width": 12.0, "numOfTurns": 4}, "cost": 0.7},
                   ])
    report = c.run()
    assert created["n"] == 2          # 两条历史都通过 create_trial 注入
    assert report.best_job_id == "j-1"


def test_resume_observations_skip_malformed_entries(monkeypatch, tmp_path):
    """坏历史（缺 cost / 越界参数）不得中断优化，只跳过。"""
    ctx, _, _ = make_ctx(tmp_path, [
        {"argvPrefix": ["run"], "responses": [submit("j-1")]},
        {"argvPrefix": ["job", "get"], "responses": [job_get("succeeded")]},
        {"argvPrefix": ["job", "result"], "responses": [job_result(0.3, "j-1")]},
    ])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1),
                   resume_observations=[
                       {"parameters": {"width": 10.0, "numOfTurns": 3}, "cost": None},
                       {"parameters": {"width": "abc", "numOfTurns": 3}, "cost": 0.5},
                       "not-a-dict",
                       {"parameters": {"width": 11.0, "numOfTurns": 4}, "cost": 0.4},
                   ])
    report = c.run()  # 不能抛异常
    assert report.best_job_id == "j-1"


def test_tpe_sampler_uses_configured_startup(monkeypatch, tmp_path):
    """TPE's n_startup_trials must equal the controller's startup_trials.

    Default is 5 (not Optuna's 10): the sampler should start learning from
    observed costs after a short random warm-up, not burn 10 rounds on seeded
    pseudo-random exploration. The value is overridable per-template/arg.
    """
    import optuna.samplers

    captured = {}
    real = optuna.samplers.TPESampler

    class Spy(real):
        def __init__(self, *a, **kw):
            captured.update(kw)
            super().__init__(*a, **kw)

    monkeypatch.setattr(optuna.samplers, "TPESampler", Spy)
    ctx, _, _ = make_ctx(tmp_path, [])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1))
    c.request_cancel()  # build the study/sampler, then stop before any submission
    report = c.run()
    assert report.rounds == ()
    assert captured.get("seed") == _TPE_SEED
    assert captured.get("n_startup_trials") == _TPE_STARTUP_TRIALS
    assert _TPE_STARTUP_TRIALS < 10  # must stay below optuna's default


def test_startup_trials_override(monkeypatch, tmp_path):
    """startup_trials passed to the controller must reach TPESampler."""
    import optuna.samplers

    captured = {}
    real = optuna.samplers.TPESampler

    class Spy(real):
        def __init__(self, *a, **kw):
            captured.update(kw)
            super().__init__(*a, **kw)

    monkeypatch.setattr(optuna.samplers, "TPESampler", Spy)
    ctx, _, _ = make_ctx(tmp_path, [])
    c = controller(ctx, budget=OptimizationBudget(max_rounds=1), startup_trials=10)
    c.request_cancel()
    c.run()
    assert captured.get("n_startup_trials") == 10
