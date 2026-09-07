"""Probe part 3: configure synthesisTargets + simulation sweep, then run.

Decides whether objectiveCost/targetValues appear once objectives exist,
and re-checks config patch persistence (the earlier patch anomaly).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epcd_agent.cli_client import EpcdCli

HOST = "zhubo@192.168.20.243"
PKG = ("/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-"
       "NINECUBE-2026-08-07-linux-x86-64-default")
PROJECT = "/home/zhubo/epcd-agent-smoke"
INSTANCE = "20260820030940000"
IDS = ["--project", PROJECT, "--instance-id", INSTANCE]

cli = EpcdCli(argv_prefix=("ssh", "-o", "BatchMode=yes", HOST,
                           "source", f"{PKG}/user.bashrc.ePCD",
                           ">/dev/null", "2>&1;", "epcd-cli"),
              default_timeout=180.0)

TERMINAL = {"succeeded", "failed", "canceled"}


def show(name, res):
    print(f"=== {name}: exit={res.exit_code}")
    print(res.stdout[:5000] if res.stdout else "(empty stdout)")
    if res.parse_error:
        print(f"    parse_error={res.parse_error}")
    return res


def data_of(res):
    if res.response is not None and res.response.data is not None:
        return res.response.data
    return {}


def get_digest():
    res = cli.exec(["config", "get"] + IDS)
    return data_of(res).get("configDigest"), res


def patch(patch_obj, digest):
    return cli.exec(["config", "patch"] + IDS + ["--input", "-", "--if-match", digest],
                    stdin_obj=patch_obj)


digest, _ = get_digest()
print(f">>> digest0={digest!r}")

targets = {"synthesisTargets": {
    "frequencyMode": "points",
    "customMetrics": [],
    "objectives": [
        {"metric": "inductance",
         "frequency": {"mode": "point", "value": 2.0, "unit": "GHz"},
         "comparison": "equal", "targetValue": 2.1, "unit": "nH", "weight": 5},
        {"metric": "minQFactor",
         "frequency": {"mode": "point", "value": 2.0, "unit": "GHz"},
         "comparison": "greater-than", "targetValue": 8.0, "unit": "", "weight": 3},
    ],
}}
show("patch synthesisTargets", patch(targets, digest))

digest, res = get_digest()
print(f">>> digest after targets patch={digest!r}")
print(">>> objectives readback:",
      json.dumps(data_of(res).get("value", {}).get("synthesisTargets"), ensure_ascii=False)[:600])

sim = {"simulation": {
    "solver": {"type": "em"},
    "execution": {"mode": "local"},
    "sweeps": [
        {"enabled": True, "type": "adaptive",
         "start": {"value": 1, "unit": "GHz"},
         "stop": {"value": 3, "unit": "GHz"},
         "maximumStep": {"value": 10, "unit": "MHz"}},
    ],
}}
show("patch simulation", patch(sim, digest))

digest, res = get_digest()
print(f">>> digest after sim patch={digest!r}")
print(">>> simulation readback:",
      json.dumps(data_of(res).get("value", {}).get("simulation"), ensure_ascii=False)[:600])

# --- run with configured objectives -------------------------------------------
candidate = {"schemaVersion": "epcd-candidate/v1",
             "parameters": {"trackWidth": 10.0, "trackSpace": 2.0,
                            "numOfTurns": 3.0, "innerRadius": 40.0}}
res = show("run (objectives configured)", cli.exec(
    ["run", "--task", "simulation-evaluation"] + IDS +
    ["--input", "-", "--if-match", digest, "--request-id", "probe-run-3"],
    stdin_obj=candidate, timeout=300))
job_id = data_of(res).get("jobId") if res.exit_code == 0 else None
print(f">>> jobId={job_id!r}")
if job_id:
    deadline = time.time() + 600
    status = None
    while time.time() < deadline:
        gres = cli.exec(["job", "get", "--id", job_id])
        status = data_of(gres).get("status")
        print(f">>> status={status!r}")
        if status in TERMINAL:
            break
        time.sleep(10)
    rres = show("job result", cli.exec(["job", "result", "--id", job_id], timeout=300))
    rdata = data_of(rres)
    print(">>> objectiveCost:", rdata.get("objectiveCost"))
    print(">>> targetValues:", json.dumps(rdata.get("targetValues"), ensure_ascii=False)[:1500])
    print(">>> warnings:", json.dumps(rdata.get("warnings"), ensure_ascii=False)[:600])
print("PROBE3_DONE")
