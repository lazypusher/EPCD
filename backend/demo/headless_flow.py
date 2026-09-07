"""Headless end-to-end P0 flow (release doc sections 4.1-4.15), no LLM.

Plan 2 replaces the `confirm` callback with the Agent SDK's built-in
AskUserQuestion; everything else is reused unchanged.

CLI usage against a real epcd-cli:
    python demo/headless_flow.py --work-dir /path/proj --technology /path/process.ptxt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epcd_agent.cli_client import EpcdCli                    # noqa: E402
from epcd_agent.optimizer.controller import (                # noqa: E402
    OptimizationBudget,
    OptimizationController,
    OptimizationPausedError,
)
from epcd_agent.optimizer.space import parse_parameter_schema  # noqa: E402
from epcd_agent.store import SessionStore                     # noqa: E402
from epcd_agent.tools.base import ToolContext                 # noqa: E402
from epcd_agent.tools.config import epcd_config               # noqa: E402
from epcd_agent.tools.read import epcd_health, epcd_job, epcd_template  # noqa: E402
from epcd_agent.tools.write import epcd_device, epcd_project, epcd_run  # noqa: E402


class FlowAbortedError(Exception):
    """A milestone was rejected, or a step failed terminally."""


def _require(result, step: str):
    if not result.ok:
        codes = ",".join(e["code"] for e in result.errors) or "UNKNOWN"
        raise FlowAbortedError(f"{step} failed: {codes} (exit {result.exit_code})")
    return result


def run_headless_flow(ctx: ToolContext, *, work_dir: str, technology: str, category: str,
                     objectives_patch: dict, simulation_patch: dict,
                     initial_candidates: list[dict], budget: OptimizationBudget,
                     confirm: Callable[[str, dict], str],
                     template_index: int = 0, instance_name: str | None = None) -> dict:
    confirmed: list[str] = []

    def checkpoint(name: str, payload: dict) -> None:
        choice = confirm(name, payload)
        ctx.store.record_milestone(ctx.session_id, name, choice, snapshot=payload)
        confirmed.append(name)
        if choice != "approved":
            raise FlowAbortedError(f"milestone {name} rejected with choice {choice!r}")

    # 4.1 health check
    health = _require(epcd_health(ctx), "health check")
    if health.data["health"].get("status") == "degraded":
        print("[warn] epcd health degraded; continuing", file=sys.stderr)

    # 4.2 project init + describe + validate
    _require(epcd_project(ctx, action="init", work_dir=work_dir, technology=technology),
             "project init")
    _require(epcd_project(ctx, action="describe"), "project describe")
    _require(epcd_project(ctx, action="validate"), "project validate")

    # 4.3 template list + describe
    listing = _require(epcd_template(ctx, action="list", category=category), "template list")
    templates = listing.data.get("templates", [])
    if template_index >= len(templates):
        raise FlowAbortedError(f"template index {template_index} out of range ({len(templates)})")
    template_id = templates[template_index]["templateId"]
    describe = _require(epcd_template(ctx, action="describe", template_id=template_id),
                        "template describe")

    # M1: selection confirmation (design doc section 8)
    checkpoint("M1", {"templateId": template_id, "instanceName": instance_name,
                      "available": describe.data.get("available"),
                      "builtInMetrics": describe.data.get("builtInMetrics", [])})

    # 4.4 instantiate device
    _require(epcd_device(ctx, action="add", template_id=template_id, name=instance_name),
             "device add")

    # 4.5 parameter schema -> optimization space
    schema_result = _require(epcd_config(ctx, action="schema", path="/device/parameters"),
                             "config schema")
    space = parse_parameter_schema(schema_result.data["schema"])

    # 4.6 fetch current config + digest
    _require(epcd_config(ctx, action="get"), "config get")

    # M2: objectives + simulation + budget confirmed together (design doc section 8)
    checkpoint("M2", {"synthesisTargets": objectives_patch["synthesisTargets"],
                      "simulation": simulation_patch["simulation"],
                      "budget": {"max_rounds": budget.max_rounds,
                                 "max_wall_seconds": budget.max_wall_seconds,
                                 "target_cost": budget.target_cost},
                      "unboundedParameters": list(space.unbounded)})

    # 4.9 write objectives, 4.10 write simulation config
    _require(epcd_config(ctx, action="patch", patch_obj=objectives_patch), "patch objectives")
    _require(epcd_config(ctx, action="get"), "config get (refresh digest)")
    _require(epcd_config(ctx, action="patch", patch_obj=simulation_patch), "patch simulation")

    # 4.7 layout preview
    _require(epcd_run(ctx, task="gds-generation", request_id="preview-001", wait=True),
             "preview run")

    # 4.11-4.13 optimization loop (deterministic island)
    ctx.store.create_optimization(ctx.session_id, "opt-1",
                                  budget={"max_rounds": budget.max_rounds,
                                          "max_wall_seconds": budget.max_wall_seconds,
                                          "target_cost": budget.target_cost})
    controller = OptimizationController(ctx, space.specs, initial_candidates, budget,
                                        task_id="opt-1",
                                        on_progress=lambda e: print(f"[opt] {e}", file=sys.stderr))
    try:
        report = controller.run()
    except OptimizationPausedError as exc:
        raise FlowAbortedError(f"optimization paused: {exc} (category={exc.category})") from exc
    if report.best_job_id is None:
        raise FlowAbortedError(f"optimization finished without any succeeded job ({report.stop_reason})")

    # M3: write-back confirmation with achieved metrics
    best_result = _require(epcd_job(ctx, action="result", job_id=report.best_job_id),
                           "best job result")
    checkpoint("M3", {"bestJobId": report.best_job_id, "bestCost": report.best_cost,
                      "rounds": len(report.rounds), "stopReason": report.stop_reason,
                      "targetValues": best_result.data.get("targetValues", [])})

    # 4.14 apply best parameters
    _require(epcd_config(ctx, action="apply-result", job_id=report.best_job_id), "apply-result")

    # M4: final simulation confirmation
    checkpoint("M4", {"configDigest": ctx.store.get_config_digest(ctx.session_id),
                      "requestId": f"final-{report.best_job_id}"})

    # 4.15 final formal simulation (no --input: uses post-apply parameters)
    final = _require(epcd_run(ctx, task="simulation-evaluation",
                              request_id=f"final-{report.best_job_id}",
                              wait=True, use_if_match=True), "final run")
    return {"milestones": confirmed, "best_job_id": report.best_job_id,
            "best_cost": report.best_cost, "stop_reason": report.stop_reason,
            "rounds": len(report.rounds), "final": final.data}


def _interactive_confirm(milestone: str, payload: dict) -> str:
    print(f"\n=== milestone {milestone} ===")
    for key, value in payload.items():
        print(f"  {key}: {value}")
    answer = input("approve? [yes/no]: ").strip().lower()
    return "approved" if answer in ("y", "yes") else "terminate"


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless EPCD P0 flow (no LLM)")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--technology", required=True)
    parser.add_argument("--category", default="inductor")
    parser.add_argument("--db", default="./epcd-agent-store.sqlite3")
    args = parser.parse_args()

    store = SessionStore(args.db)
    store.create_session("headless-1")
    ctx = ToolContext(cli=EpcdCli(), store=store, session_id="headless-1")
    objectives = {
        "synthesisTargets": {
            "frequencyMode": "points", "customMetrics": [],
            "objectives": [
                {"metric": "L", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
                 "comparison": "equal", "targetValue": 10, "unit": "nH", "weight": 5},
                {"metric": "Q", "frequency": {"mode": "point", "value": 2.4, "unit": "GHz"},
                 "comparison": "greater-than", "targetValue": 20, "unit": "", "weight": 8},
            ],
        }
    }
    simulation = {
        "simulation": {
            "solver": {"type": "em"}, "execution": {"mode": "local"},
            "sweeps": [{"enabled": True, "type": "adaptive",
                        "start": {"value": 1, "unit": "GHz"},
                        "stop": {"value": 3, "unit": "GHz"},
                        "maximumStep": {"value": 10, "unit": "MHz"}}],
        }
    }
    try:
        summary = run_headless_flow(
            ctx, work_dir=args.work_dir, technology=args.technology, category=args.category,
            objectives_patch=objectives, simulation_patch=simulation,
            initial_candidates=[{"width": 10.0, "numOfTurns": 3}],
            budget=OptimizationBudget(max_rounds=10, max_wall_seconds=3600),
            confirm=_interactive_confirm, instance_name="L1")
    except FlowAbortedError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 1
    print(f"DONE: best={summary['best_job_id']} cost={summary['best_cost']} "
          f"rounds={summary['rounds']} artifacts={len(summary['final'].get('artifacts', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
