import sys
from pathlib import Path

import mock_cli
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

from e2e_scenario import FINAL_ARTIFACTS, build_routes  # noqa: E402
from headless_flow import FlowAbortedError, run_headless_flow  # noqa: E402

from epcd_agent.optimizer.controller import OptimizationBudget  # noqa: E402
from epcd_agent.store import SessionStore  # noqa: E402
from epcd_agent.tools.base import ToolContext  # noqa: E402

OBJECTIVES = {
    "synthesisTargets": {
        "frequencyMode": "points",
        "customMetrics": [],
        "objectives": [
            {"metric": "L", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
             "comparison": "equal", "targetValue": 10, "unit": "nH", "weight": 5},
            {"metric": "Q", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
             "comparison": "greater-than", "targetValue": 20, "unit": "", "weight": 8},
        ],
    }
}
SIMULATION = {
    "simulation": {
        "solver": {"type": "em"},
        "execution": {"mode": "local"},
        "sweeps": [{"enabled": True, "type": "adaptive",
                    "start": {"value": 1, "unit": "GHz"},
                    "stop": {"value": 3, "unit": "GHz"},
                    "maximumStep": {"value": 10, "unit": "MHz"}}],
    }
}


def make_ctx(tmp_path):
    cli, calls = mock_cli.make_cli(tmp_path, build_routes())
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    return ToolContext(cli=cli, store=store, session_id="s1"), calls, store


def flow_kwargs(confirm):
    return dict(
        work_dir="/abs/proj", technology="/abs/process.ptxt", category="inductor",
        objectives_patch=OBJECTIVES, simulation_patch=SIMULATION,
        initial_candidates=[{"width": 10.0, "numOfTurns": 3}],
        budget=OptimizationBudget(max_rounds=2, target_cost=0.2),
        confirm=confirm, instance_name="L1",
    )


def test_end_to_end_acceptance(tmp_path):
    ctx, calls, store = make_ctx(tmp_path)
    asked = []

    def confirm(milestone, payload):
        asked.append(milestone)
        return "approved"

    summary = run_headless_flow(ctx, **flow_kwargs(confirm))

    # exactly the 4 mandatory confirmations, in order (design doc section 8)
    assert asked == ["M1", "M2", "M3", "M4"]
    assert [m["name"] for m in store.list_milestones("s1")] == ["M1", "M2", "M3", "M4"]

    # optimization delivered the best job within budget
    assert summary["best_job_id"] == "j-2"
    assert summary["best_cost"] == pytest.approx(0.18)
    assert summary["stop_reason"] == "target_reached"

    # final run used the post-apply digest and the fixed requestId scheme
    run_calls = [c for c in mock_cli.read_calls(calls) if c["argv"][0] == "run"]
    final_call = run_calls[-1]
    assert final_call["stdin"] is None              # no --input: post-apply parameters (release 4.15)
    assert "--input" not in final_call["argv"]
    assert final_call["argv"][final_call["argv"].index("--request-id") + 1] == "final-j-2"
    assert final_call["argv"][final_call["argv"].index("--if-match") + 1] == "sha256:post"

    # all 7 artifact types + RangeEM publication (release 4.15 / section 5)
    artifact_types = {a["type"] for a in summary["final"]["artifacts"]}
    assert artifact_types == {a["type"] for a in FINAL_ARTIFACTS}
    assert summary["final"]["publication"]["directory"].endswith("synthesis/RangeEM")

    # every job was ledgered into the Session Store
    job_ids = {j["job_id"] for j in store.list_jobs("s1")}
    assert {"j-preview", "j-1", "j-2", "j-final"} <= job_ids
    assert store.get_optimization("s1", "opt-1")["status"] == "finished"


def test_user_terminates_at_m2(tmp_path):
    ctx, _, store = make_ctx(tmp_path)

    def confirm(milestone, payload):
        return "approved" if milestone == "M1" else "terminate"

    with pytest.raises(FlowAbortedError):
        run_headless_flow(ctx, **flow_kwargs(confirm))
    rows = store.list_milestones("s1")
    assert [r["name"] for r in rows] == ["M1", "M2"]
    assert rows[1]["choice"] == "terminate"
    # no optimization task was started after rejection
    assert store.get_optimization("s1", "opt-1") is None
