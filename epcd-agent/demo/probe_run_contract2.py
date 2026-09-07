"""Probe part 2: job get/result without IDS, flat-vs-nested candidate, apply-result.

Uses the job submitted by probe_run_contract.py (nested candidate accepted,
jobId printed there) and submits ONE flat candidate for comparison.
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
    print(res.stdout[:6000] if res.stdout else "(empty stdout)")
    if res.parse_error:
        print(f"    parse_error={res.parse_error}")
    return res


def data_of(res):
    if res.response is not None and res.response.data is not None:
        return res.response.data
    return {}


def poll_until_terminal(job_id, deadline_seconds=600):
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        res = cli.exec(["job", "get", "--id", job_id])
        status = data_of(res).get("status")
        print(f">>> job {job_id} status={status!r} exit={res.exit_code}")
        if res.exit_code != 0:
            show("job get (failed)", res)
            return None
        if status in TERMINAL:
            return status
        time.sleep(10)
    return None


def run_candidate(shape, params, request_id, digest):
    candidate = {"schemaVersion": "epcd-candidate/v1", "parameters": params}
    res = show(f"run candidate ({shape})", cli.exec(
        ["run", "--task", "simulation-evaluation"] + IDS +
        ["--input", "-", "--if-match", digest, "--request-id", request_id],
        stdin_obj=candidate, timeout=300))
    if res.exit_code == 0 and res.response is not None and res.response.ok:
        return data_of(res).get("jobId")
    return None


def job_result(job_id):
    res = show("job result", cli.exec(["job", "result", "--id", job_id], timeout=300))
    rdata = data_of(res)
    print(">>> result keys:", sorted(rdata.keys()))
    print(">>> objectiveCost:", rdata.get("objectiveCost"))
    print(">>> targetValues:", json.dumps(rdata.get("targetValues"), ensure_ascii=False)[:800])
    print(">>> artifacts:", json.dumps(rdata.get("artifacts"), ensure_ascii=False)[:1500])
    return rdata


# --- fresh digest -------------------------------------------------------------
get = show("config get", cli.exec(["config", "get"] + IDS))
digest = data_of(get).get("configDigest")
print(f">>> digest={digest!r}")

# --- nested job from part 1 ---------------------------------------------------
NESTED_JOB = "9490e87f-0285-4cfa-a630-975ad5eb47c4"
show("job get (nested job)", cli.exec(["job", "get", "--id", NESTED_JOB]))
status = poll_until_terminal(NESTED_JOB)
print(f">>> nested job terminal status: {status!r}")
nested_result = None
if status == "succeeded":
    nested_result = job_result(NESTED_JOB)

# --- flat candidate comparison -------------------------------------------------
flat_job = run_candidate("flat", {"trackWidth": 10.0, "trackSpace": 2.0,
                                  "numOfTurns": 3.0, "innerRadius": 40.0},
                         "probe-run-flat", digest)
flat_result = None
if flat_job:
    print(f">>> flat candidate accepted, jobId={flat_job}")
    fstatus = poll_until_terminal(flat_job)
    print(f">>> flat job terminal status: {fstatus!r}")
    if fstatus == "succeeded":
        flat_result = job_result(flat_job)
    if nested_result and flat_result:
        print(f">>> COST COMPARISON nested={nested_result.get('objectiveCost')} "
              f"flat={flat_result.get('objectiveCost')}")
else:
    print(">>> flat candidate REJECTED (evidence above)")

# --- apply-result: help then real ----------------------------------------------
show("config apply-result --help", cli.exec(["config", "apply-result", "--help"]))
if nested_result is not None:
    show("config apply-result (nested job)",
         cli.exec(["config", "apply-result", "--job-id", NESTED_JOB] + IDS, timeout=300))
print("PROBE2_DONE")
