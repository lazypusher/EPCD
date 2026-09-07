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


if __name__ == "__main__":
    sys.exit(main())
