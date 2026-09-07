"""Smoke check: EpcdCli over ssh — stdin JSON piped to remote, envelope comes back.

Stand-in for the future global `epcd-cli`: a remote python3 one-liner reads the
candidate JSON from stdin and echoes a valid epcd-response/v1 envelope. Run:

    ./.venv/Scripts/python demo/smoke_remote_ssh.py

Note on ssh prefixes: ssh joins the command argv with spaces and re-parses it
through the remote shell, so the remote command must be passed as ONE
shell-quoted argument. Plain epcd-cli tokens (ids, digests, flags) are safe;
values containing spaces or shell metacharacters would need escaping (plan 2).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epcd_agent.cli_client import EpcdCli
from epcd_agent.exitcodes import classify_exit

REMOTE_CMD = (
    "python3 -c '"
    "import json,sys; "
    "payload=json.load(sys.stdin); "
    "print(json.dumps({\"schemaVersion\":\"epcd-response/v1\",\"ok\":True,\"requestId\":\"r-1\","
    "\"data\":{\"echo\":payload,\"jobId\":\"j-remote-1\",\"status\":\"queued\"},\"errors\":[]}))"
    "'"
)

cli = EpcdCli(argv_prefix=("ssh", "-o", "BatchMode=yes",
                           "zhubo@192.168.20.243", REMOTE_CMD))
result = cli.exec([], stdin_obj={"schemaVersion": "epcd-candidate/v1",
                                 "parameters": {"width": 11, "numOfTurns": 3}})
print("exit_code:", result.exit_code, "->", classify_exit(result.exit_code))
assert result.response is not None, f"parse_error={result.parse_error} stderr={result.stderr}"
print("ok:", result.response.ok)
print("data.echo.parameters:", result.response.data["echo"]["parameters"])
print("jobId:", result.response.data["jobId"])
assert result.exit_code == 0 and result.response.ok
assert result.response.data["echo"]["parameters"] == {"width": 11, "numOfTurns": 3}
print("REMOTE_PIPE_OK")
