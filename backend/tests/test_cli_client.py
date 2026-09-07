import mock_cli

from epcd_agent.cli_client import EpcdCli

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


def test_exec_missing_binary_returns_structured_failure():
    # A missing epcd-cli binary must not raise: the CLI entry's discipline is
    # a structured failure (exit_code -1, no traceback), same shape as timeout.
    cli = EpcdCli(argv_prefix=("definitely-not-a-real-binary-xyz",))
    result = cli.exec(["health"])
    assert result.exit_code == -1
    assert result.response is None
    assert result.parse_error is None
    assert result.stderr  # carries the exec error message
