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
