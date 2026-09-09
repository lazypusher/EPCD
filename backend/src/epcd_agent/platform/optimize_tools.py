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
from epcd_agent.optimizer.tpe_settings import (
    DEFAULT_MAX_ROUNDS,
    DEFAULT_STARTUP_TRIALS,
    template_tpe_settings,
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


def _resolve_template_id(parameter_schema: dict, ctx: ToolContext) -> str | None:
    """Resolve the active template_id (from the schema or the session store).

    Shared by space resolution and TPE settings lookup so both derive the
    template from the same source.
    """
    template_id = parameter_schema.get("template_id") or parameter_schema.get("templateId")
    if not template_id:
        inst = ctx.store.get_active_instance(ctx.session_id)
        if inst:
            template_id = inst.get("template_id")
    return str(template_id) if template_id else None


def _space_from_schema(parameter_schema: dict, ctx: ToolContext) -> ParsedSpace:
    """Build the optimization space, most authoritative source first.

    Resolution order:

    1. Parse the caller-supplied ``parameter_schema`` (any nested format
       understood by :func:`parse_real_parameter_schema`).
    2. Ask the live template ``describe()`` and parse its ``parameterSchema``
       — the ONLY place the template's real optimization bounds live (config
       ``schema``/``get`` expose a value/min/max shape, not the typed
       parameterSchema).
    3. Last resort: ``describe().addinParams``, only for legacy server builds
       whose ``parameterSchema`` comes back empty.

    The previous code skipped step 2 and jumped straight to ``addinParams``.
    ``addinParams`` is the raw *panel* dump (shielding, metal fill, guard ring,
    pin geometry — offset/width/spacing/shape/…), NOT the template's
    optimization parameters, so the optimizer TPE-walked every low-level panel
    field while the server silently ran the default geometry. Preferring
    ``parameterSchema`` fixes that recurring bug.
    """
    template_id = _resolve_template_id(parameter_schema, ctx)

    # 1. caller-supplied schema (covers callers that pass the template
    #    parameterSchema or the legacy string schema directly)
    try:
        space = parse_real_parameter_schema(parameter_schema)
    except ValueError:
        space = ParsedSpace(specs=(), unbounded=())
    if space.specs:
        return space

    if not template_id:
        return space

    describe = epcd_template(ctx, action="describe", template_id=str(template_id))
    if not describe.ok:
        return space
    describe_data = describe.data or {}

    # 2. authoritative: describe().parameterSchema (nested basic/opt/synth)
    desc_schema = describe_data.get("parameterSchema")
    if isinstance(desc_schema, dict):
        try:
            by_schema = parse_real_parameter_schema(desc_schema)
        except ValueError:
            by_schema = ParsedSpace(specs=(), unbounded=())
        if by_schema.specs:
            return by_schema

    # 3. legacy-only fallback: describe().addinParams
    addin = describe_data.get("addinParams")
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


def _observations_from_rounds(rounds: Iterable[dict]) -> list[dict]:
    """Warm-start observations from a prior task's finished rounds.

    Only SUCCEEDED rounds with a numeric cost and a parameters dict are kept:
    those are the (parameters, cost) samples the TPE sampler can continue from.
    """
    observations: list[dict] = []
    for round_ in rounds or []:
        if not isinstance(round_, dict):
            continue
        if round_.get("status") != "succeeded":
            continue
        cost = round_.get("cost")
        if not isinstance(cost, (int, float)):
            continue
        params = round_.get("parameters")
        if not isinstance(params, dict) or not params:
            continue
        observations.append({"parameters": params, "cost": cost})
    return observations


def optimization_start(ctx: ToolContext, *, parameter_schema: dict,
                       initial_candidates: Iterable[dict] = (),
                       max_rounds: int | None = None,
                       max_wall_seconds: float = 600.0,
                       target_cost: float | None = None,
                       startup_trials: int | None = None,
                       request_prefix: str | None = None,
                       resume_from: str | None = None) -> ToolResult:
    space = _space_or_raise(ctx, parameter_schema)
    if not space.specs:
        raise ToolInputError("parameter schema yields no optimizable opt parameters")
    # Resolve TPE settings: explicit arg > per-template table > built-in default.
    # max_rounds/startup_trials default to None so "not passed" can be told apart
    # from "explicitly 0"; both then fall back through the same priority chain.
    template_id = _resolve_template_id(parameter_schema, ctx)
    tpe_tbl = template_tpe_settings(template_id) or {}
    if max_rounds is None:
        max_rounds = tpe_tbl.get("max_rounds", DEFAULT_MAX_ROUNDS)
    if startup_trials is None:
        startup_trials = tpe_tbl.get("startup_trials", DEFAULT_STARTUP_TRIALS)
    n = len(ctx.store.list_jobs(ctx.session_id)) + 1
    task_id = f"opt-{n}"
    if request_prefix is None:
        # Unique per task by default. Reusing a fixed prefix (the old
        # "iteration") across two runs collides on requestId and silently
        # reattaches stale jobs to new candidates, corrupting the TPE mapping.
        request_prefix = f"itr-{n}"
    resume_observations: list[dict] = []
    if resume_from is not None:
        prior = ctx.store.get_optimization(ctx.session_id, resume_from)
        if prior is not None:
            resume_observations = _observations_from_rounds(prior.get("rounds"))
    budget_dict = {"max_rounds": max_rounds, "max_wall_seconds": max_wall_seconds,
                   "target_cost": target_cost, "startup_trials": startup_trials}
    ctx.store.create_optimization(ctx.session_id, task_id, budget_dict)
    controller = OptimizationController(
        ctx, space.specs,
        initial_candidates=initial_candidates,
        budget=OptimizationBudget(max_rounds=max_rounds,
                                  max_wall_seconds=max_wall_seconds,
                                  target_cost=target_cost),
        request_prefix=request_prefix,
        task_id=task_id,
        cancel_probe=lambda: bool(ctx.store.get_state(ctx.session_id, _cancel_key(task_id))),
        resume_observations=resume_observations,
        startup_trials=startup_trials)
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
    return ToolResult(ok=True, data={"task_id": task_id, "report": _report_dict(report),
                                     "resume_from": resume_from,
                                     "warm_started_rounds": len(resume_observations),
                                     "startup_trials": startup_trials,
                                     "max_rounds": max_rounds})


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
