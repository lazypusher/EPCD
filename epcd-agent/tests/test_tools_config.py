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
