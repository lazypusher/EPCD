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
