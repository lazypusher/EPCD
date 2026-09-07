"""Probe the REAL run/job/apply-result contract on the server (Plan 2 Task 7).

Steps: config get (fresh digest) -> run one candidate (request-id probe-run-*)
-> job get until terminal -> job result -> config apply-result for that job.
Prints every raw envelope for evidence (release doc corrections follow).

    ./.venv/Scripts/python demo/probe_run_contract.py
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

cli = EpcdCli(argv_prefix=("ssh", "-o", "BatchMode=yes", HOST,
                           "source", f"{PKG}/user.bashrc.ePCD",
                           ">/dev/null", "2>&1;", "epcd-cli"),
              default_timeout=180.0)

IDS = ["--project", PROJECT, "--instance-id", INSTANCE]
CANDIDATE_PARAMS_NESTED = {"opt": {"trackWidth": 10.0, "trackSpace": 2.0,
                                   "numOfTurns": 3.0, "innerRadius": 40.0}}
CANDIDATE_PARAMS_FLAT = {"trackWidth": 10.0, "trackSpace": 2.0,
                         "numOfTurns": 3.0, "innerRadius": 40.0}


def show(name, res):
    print(f"=== {name}: exit={res.exit_code} timed_out={res.timed_out}")
    print(res.stdout[:6000] if res.stdout else "(empty stdout)")
    if res.parse_error:
        print(f"    parse_error={res.parse_error}")
    if res.stderr:
        print(f"    stderr(tail)={res.stderr[-400:]!r}")
    return res


def data_of(res):
    if res.response is not None and res.response.data is not None:
        return res.response.data
    return {}


# --- step 1: config get -> fresh digest -------------------------------------
get = show("config get", cli.exec(["config", "get"] + IDS))
digest = data_of(get).get("configDigest")
print(f">>> configDigest = {digest!r}")
if not digest:
    print(">>> no digest found; keys:", sorted(data_of(get).keys()))
    sys.exit(1)

# --- step 2: run one candidate (nested first, then flat) ---------------------
job_id = None
for shape, params, rid in (("nested", CANDIDATE_PARAMS_NESTED, "probe-run-1"),
                           ("flat", CANDIDATE_PARAMS_FLAT, "probe-run-2")):
    candidate = {"schemaVersion": "epcd-candidate/v1", "parameters": params}
    res = show(f"run candidate ({shape})", cli.exec(
        ["run", "--task", "simulation-evaluation"] + IDS +
        ["--input", "-", "--if-match", digest, "--request-id", rid],
        stdin_obj=candidate, timeout=300))
    if res.exit_code == 0 and res.response is not None and res.response.ok:
        job_id = data_of(res).get("jobId")
        print(f">>> accepted candidate shape: {shape}; jobId={job_id!r}")
        break
    print(f">>> candidate shape {shape} rejected (exit={res.exit_code})")
if not job_id:
    print(">>> neither candidate shape accepted; stopping (evidence above)")
    sys.exit(2)

# --- step 3: job get until terminal, then job result -------------------------
TERMINAL = {"succeeded", "failed", "canceled"}
status = None
deadline = time.time() + 600
id_flag = "--id"
while time.time() < deadline:
    res = cli.exec(["job", "get", id_flag, job_id] + IDS)
    if res.exit_code == 2 and id_flag == "--id":  # usage error: try alt flag
        id_flag = "--job-id"
        res = cli.exec(["job", "get", id_flag, job_id] + IDS)
    show("job get", res)
    status = data_of(res).get("status")
    print(f">>> status={status!r} (flag used: {id_flag})")
    if status in TERMINAL:
        break
    time.sleep(10)
else:
    print(">>> polling deadline reached; continuing to result step anyway")

result = show("job result", cli.exec(["job", "result", id_flag, job_id] + IDS,
                                     timeout=300))
rdata = data_of(result)
print(">>> result keys:", sorted(rdata.keys()))
print(">>> objectiveCost:", rdata.get("objectiveCost"))
print(">>> targetValues:", json.dumps(rdata.get("targetValues"), ensure_ascii=False)[:800])
print(">>> artifacts:", json.dumps(rdata.get("artifacts"), ensure_ascii=False)[:1200])

# --- step 4: config apply-result ---------------------------------------------
apply_res = show("config apply-result",
                 cli.exec(["config", "apply-result", "--job-id", job_id] + IDS,
                          timeout=300))
print(">>> apply-result exit:", apply_res.exit_code)
print("PROBE_DONE")
