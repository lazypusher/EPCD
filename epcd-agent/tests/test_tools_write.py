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


def test_project_init_accepts_legacy_path_shape(tmp_path):
    # Observed server build 0.1.0 returns data.path instead of data.project
    # and omits technologyDigest/created/warnings.
    ctx, _, store = make_ctx(tmp_path, [
        {"argvPrefix": ["project", "init"], "responses": [{"exitCode": 0, "envelope": ok_envelope({
            "path": "/abs/proj", "libName": "epcd-agent-smoke",
            "techFile": "/abs/proj/demo.ptxt", "technologyPath": "/abs/proj/demo.ptxt",
            "modules": []})}]},
    ])
    r = epcd_project(ctx, action="init", work_dir="/abs/proj", technology="/abs/demo.ptxt")
    assert r.ok is True
    p = store.get_project("s1")
    assert p["project_dir"] == "/abs/proj"
    assert p["lib_name"] == "epcd-agent-smoke"
    assert p["technology_digest"] is None


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
