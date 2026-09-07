"""Platform tools: optimization_start/status/cancel (design doc section 7).

optimization_start BLOCKS for the whole loop (CLI usage: one call, one
report). Cross-process cancel goes through the Store kv_state.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from epcd_agent.optimizer.controller import (
    OptimizationBudget,
    OptimizationController,
    OptimizationPausedError,
)
from epcd_agent.optimizer.space import (
    ParsedSpace,
    parse_addin_params,
    parse_real_parameter_schema,
)
from epcd_agent.tools.base import ToolContext, ToolInputError, ToolResult
from epcd_agent.tools.read import epcd_template


def _cancel_key(task_id: str) -> str:
    return f"opt-cancel:{task_id}"


def _report_dict(report) -> dict:
    return {
        "best_job_id": report.best_job_id,
        "best_cost": report.best_cost,
        "best_parameters": report.best_parameters,
        "stop_reason": report.stop_reason,
        "rounds": [asdict(r) for r in report.rounds],
    }


def _space_from_schema(parameter_schema: dict, ctx: ToolContext) -> ParsedSpace:
    """Build the optimization space from the caller-provided parameter schema.

    Since 2026-08-27 server builds, ``describe().parameterSchema`` returns
    empty basic/opt/synth objects and the real parameters live in
    ``addinParams`` — so when the classic ``opt.properties`` path yields no
    specs, fall back to the live template's describe().addinParams.
    """
    # primary: classic nested basic/opt/synth schema path
    try:
        space = parse_real_parameter_schema(parameter_schema)
    except ValueError:
        space = ParsedSpace(specs=(), unbounded=())
    if space.specs:
        return space

    # fallback: describe().addinParams (panel groups of paramItems)
    template_id = parameter_schema.get("template_id") or parameter_schema.get("templateId")
    if not template_id:
        inst = ctx.store.get_active_instance(ctx.session_id)
        if inst:
            template_id = inst.get("template_id")
    if template_id:
        describe = epcd_template(ctx, action="describe", template_id=str(template_id))
        if describe.ok:
            addin = (describe.data or {}).get("addinParams")
            if addin is not None:
                by_addin = parse_addin_params(addin)
                if by_addin.specs:
                    return by_addin
    return space


def _space_or_raise(ctx: ToolContext, parameter_schema: dict) -> ParsedSpace:
    space = _space_from_schema(parameter_schema, ctx)
    if not space.specs:
        raise ToolInputError(
            "parameter schema yields no optimizable opt parameters "
            "(neither parameterSchema.opt.properties nor describe.addinParams "
            "produced an optimizable space)")
    return space


def optimization_start(ctx: ToolContext, *, parameter_schema: dict,
                       initial_candidates: Iterable[dict] = (),
                       max_rounds: int = 20, max_wall_seconds: float = 600.0,
                       target_cost: float | None = None,
                       request_prefix: str = "iteration") -> ToolResult:
    space = _space_or_raise(ctx, parameter_schema)
    if not space.specs:
        raise ToolInputError("parameter schema yields no optimizable opt parameters")
    task_id = f"opt-{len(ctx.store.list_jobs(ctx.session_id)) + 1}"
    budget_dict = {"max_rounds": max_rounds, "max_wall_seconds": max_wall_seconds,
                   "target_cost": target_cost}
    ctx.store.create_optimization(ctx.session_id, task_id, budget_dict)
    controller = OptimizationController(
        ctx, space.specs,
        initial_candidates=initial_candidates,
        budget=OptimizationBudget(max_rounds=max_rounds,
                                  max_wall_seconds=max_wall_seconds,
                                  target_cost=target_cost),
        request_prefix=request_prefix,
        task_id=task_id,
        cancel_probe=lambda: bool(ctx.store.get_state(ctx.session_id, _cancel_key(task_id))))
    try:
        report = controller.run()
    except OptimizationPausedError as exc:
        ctx.store.update_optimization(ctx.session_id, task_id, status="paused")
        return ToolResult(ok=False,
                          errors=({"code": "OPTIMIZATION_PAUSED", "path": None,
                                   "message": str(exc)},),
                          category=exc.category,
                          data={"task_id": task_id, "category": exc.category,
                                "report": _report_dict(exc.report),
                                "errors": list(exc.errors)})
    ctx.store.update_optimization(ctx.session_id, task_id, status="finished")
    return ToolResult(ok=True, data={"task_id": task_id, "report": _report_dict(report)})


def optimization_status(ctx: ToolContext, task_id: str) -> ToolResult:
    task = ctx.store.get_optimization(ctx.session_id, task_id)
    if task is None:
        return ToolResult(ok=False,
                          errors=({"code": "OPTIMIZATION_TASK_NOT_FOUND", "path": "/task_id",
                                   "message": f"unknown optimization task: {task_id}"},))
    cancel_flag = bool(ctx.store.get_state(ctx.session_id, _cancel_key(task_id)))
    return ToolResult(ok=True, data={**task, "cancel_requested": cancel_flag})


def optimization_cancel(ctx: ToolContext, task_id: str) -> ToolResult:
    task = ctx.store.get_optimization(ctx.session_id, task_id)
    if task is None:
        return ToolResult(ok=False,
                          errors=({"code": "OPTIMIZATION_TASK_NOT_FOUND", "path": "/task_id",
                                   "message": f"unknown optimization task: {task_id}"},))
    ctx.store.set_state(ctx.session_id, _cancel_key(task_id), True)
    return ToolResult(ok=True, data={"task_id": task_id, "cancel_requested": True})
