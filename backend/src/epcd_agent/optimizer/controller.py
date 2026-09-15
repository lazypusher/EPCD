"""Deterministic optimization loop (design doc section 7).

Agentic trunk + deterministic island: this controller owns the 4.11-4.13
iteration loop entirely; the LLM only supplies initial candidates up front and
interprets the report afterwards. Resumability borrows the CLI's requestId
semantics: resubmitting the same requestId returns the original Job.
"""
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

import optuna

from ..exitcodes import LOOP_TRANSIENT_EXIT_CODES
from ..tools.base import ToolContext
from ..tools.read import epcd_job
from ..tools.write import epcd_run
from .space import (ParamSpec, normalize_candidate, to_optuna_distributions,
                     stack_layer_width_violation)
from .tpe_settings import DEFAULT_STARTUP_TRIALS

TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "canceled"})
_TPE_SEED = 20260817
# TPE 的启动期轮数（默认值，可被调用方/模板表覆盖）。optuna 默认 10：启动期是固定
# 种子的纯随机游走、不消费观测，对 25s/轮的 EM 任务会白烧 10 轮且无学习。5 是机制上
# 的下限（能让"好组"凑出 2 个点、KDE 拟合不退化），困难模板由模板表上调到 10。
_TPE_STARTUP_TRIALS = DEFAULT_STARTUP_TRIALS
_CONSECUTIVE_FAILURE_LIMIT = 2
# 约束重采样上限：违反几何约束时在同一轮内最多重试这么多次，超限则放弃约束
# 直接提交（让服务端按自身规则报错），避免极端采样空间下死循环。
_MAX_REROLL = 50


@dataclass(frozen=True)
class OptimizationBudget:
    max_rounds: int = 15
    max_wall_seconds: float = 600.0
    target_cost: float | None = None


@dataclass(frozen=True)
class RoundRecord:
    round_no: int
    request_id: str
    parameters: dict
    job_id: str | None
    status: str  # "succeeded" | "failed" | "canceled"
    cost: float | None


@dataclass(frozen=True)
class OptimizationReport:
    best_job_id: str | None
    best_cost: float | None
    best_parameters: dict | None
    rounds: tuple[RoundRecord, ...]
    stop_reason: str  # target_reached | budget_rounds | budget_wall | canceled | paused


class OptimizationPausedError(Exception):
    """Loop paused for escalation (validation/business errors, repeated failures)."""

    def __init__(self, message: str, *, report: OptimizationReport,
                 category: str, errors: tuple[dict, ...] = ()):
        super().__init__(message)
        self.report = report
        self.category = category
        self.errors = errors


def cost_from_result(data: dict) -> float | None:
    """Extract the scalar optimization cost from a job-result payload.

    The release contract (section 4.12) promises a top-level ``objectiveCost``;
    the real 0.1.0 server omits it, so fall back to the per-target entries:
    per-target objectiveCost, else relativeDeviation, else 0/1 by satisfied.
    Returns None when no objective data exists at all (caller pauses).
    """
    cost = data.get("objectiveCost")
    if isinstance(cost, (int, float)):
        return float(cost)
    targets = data.get("targetValues") or []
    if not targets:
        return None
    total = 0.0
    for target in targets:
        if not isinstance(target, dict):
            continue
        item_cost = target.get("objectiveCost")
        if isinstance(item_cost, (int, float)):
            total += float(item_cost)
            continue
        deviation = target.get("relativeDeviation")
        if isinstance(deviation, (int, float)):
            total += float(deviation)
            continue
        total += 0.0 if target.get("satisfied") else 1.0
    return total


class OptimizationController:
    def __init__(self, ctx: ToolContext, specs: Iterable[ParamSpec],
                 initial_candidates: Iterable[dict] = (),
                 budget: OptimizationBudget = OptimizationBudget(),
                 request_prefix: str = "iteration", poll_interval: float = 2.0,
                 on_progress: Callable[[dict], None] | None = None,
                 task_id: str | None = None,
                 cancel_probe: Callable[[], bool] | None = None,
                 resume_observations: Iterable[dict] = (),
                 startup_trials: int = _TPE_STARTUP_TRIALS):
        self._ctx = ctx
        self._specs = tuple(specs)
        self._initial = [normalize_candidate(dict(c), self._specs) for c in initial_candidates]
        # Warm-start observations: (parameters, cost) pairs from a prior task.
        # Seeded into the Optuna study as completed trials so the TPE sampler
        # continues from the prior posterior instead of re-exploring from round 1.
        self._resume_observations = tuple(resume_observations)
        self._budget = budget
        self._prefix = request_prefix
        self._poll_interval = poll_interval
        self._on_progress = on_progress
        self._task_id = task_id
        self._cancel_probe = cancel_probe
        self._startup_trials = startup_trials
        self._cancel_requested = False
        self._failures = 0
        self._filtered = 0
        self._rounds: list[RoundRecord] = []
        self._best_job_id: str | None = None
        self._best_cost: float | None = None
        self._best_parameters: dict | None = None

    # -- public API ------------------------------------------------------
    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _probe_cancel(self) -> None:
        """Cross-process cancel: an external probe (e.g. a Store flag set by
        optimization_cancel in another process) can request cancellation."""
        if not self._cancel_requested and self._cancel_probe is not None:
            if self._cancel_probe():
                self._cancel_requested = True

    def run(self) -> OptimizationReport:
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=_TPE_SEED,
                                               n_startup_trials=self._startup_trials))
        if self._resume_observations:
            distributions = to_optuna_distributions(self._specs)
            for obs in self._resume_observations:
                if not isinstance(obs, dict):
                    continue
                cost = obs.get("cost")
                if not isinstance(cost, (int, float)):
                    continue
                try:
                    params = normalize_candidate(obs.get("parameters") or {}, self._specs)
                    trial = optuna.trial.create_trial(
                        params=params, distributions=distributions, value=float(cost))
                    study.add_trial(trial)
                except (ValueError, TypeError):
                    # A malformed/out-of-space observation must never abort the
                    # whole optimization; skip it and keep the valid history.
                    continue
        for candidate in self._initial:
            study.enqueue_trial(candidate)
        self._task_update(status="running")
        started = time.monotonic()
        stop_reason = "budget_rounds"
        round_no = 0
        while round_no < self._budget.max_rounds:
            self._probe_cancel()
            if self._cancel_requested:
                stop_reason = "canceled"
                break
            if time.monotonic() - started > self._budget.max_wall_seconds:
                stop_reason = "budget_wall"
                break
            # 跨参数几何约束（硬规则，提交前过滤）：stack 家族两层层宽必须接近。
            # 违反则把该 trial 记为 FAIL 喂回 TPE（让它学习避开无效组合），并**在同一轮内
            # 重新采样**，直到采到合法组合——不推进 round_no、不消耗 max_rounds 预算、
            # 不计入 rounds。这样「N 轮」始终等于「N 次有效仿真」，约束只用于把无效采样
            # 重新 roll，不会因此牺牲有效探索预算。
            trial = study.ask()
            params = self._suggest_params(trial)
            rerolls = 0
            while stack_layer_width_violation(params) and rerolls < _MAX_REROLL:
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                self._filtered += 1
                rerolls += 1
                trial = study.ask()
                params = self._suggest_params(trial)
            round_no += 1
            request_id = f"{self._prefix}-{round_no}"
            job_id = self._submit(params, request_id)
            status = self._poll(job_id)
            if status == "canceled":
                self._record_round(round_no, request_id, params, job_id, "canceled", None)
                stop_reason = "canceled"
                break
            if status == "failed":
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                self._record_round(round_no, request_id, params, job_id, "failed", None)
                self._failures += 1
                if self._failures >= _CONSECUTIVE_FAILURE_LIMIT:
                    self._task_update(status="paused")
                    raise OptimizationPausedError(
                        f"{self._failures} consecutive simulation jobs failed; "
                        "escalating for diagnosis (read logFile via job result)",
                        report=self._report("paused"), category="transient")
                continue
            # succeeded
            self._failures = 0
            cost, sim_failed = self._read_cost(job_id, round_no, request_id, params)
            if sim_failed:
                # Job was "succeeded" but carried simulation-failure warnings
                # (SIMULATION_FAILED / GDS_NOT_FOUND …) with no targetValues —
                # the geometry/params were invalid (stack_inductor verified).
                # Treat as a FAILED round (TPE learns to avoid it) instead of a
                # scoring-unavailable pause. §4.12: warnings empty && targetValues
                # present is the REAL success criterion.
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                self._record_round(round_no, request_id, params, job_id, "failed", None)
                self._failures += 1
                if self._failures >= _CONSECUTIVE_FAILURE_LIMIT:
                    self._task_update(status="paused")
                    raise OptimizationPausedError(
                        f"{self._failures} consecutive simulation jobs failed "
                        "(invalid parameter combinations); escalating for diagnosis",
                        report=self._report("paused"), category="transient")
                continue
            study.tell(trial, cost)
            self._ctx.store.update_job(
                self._ctx.session_id, job_id, status="succeeded", objective_cost=cost)
            if self._best_cost is None or cost < self._best_cost:
                self._best_cost, self._best_job_id, self._best_parameters = cost, job_id, params
            self._record_round(round_no, request_id, params, job_id, "succeeded", cost)
            if self._budget.target_cost is not None and self._best_cost <= self._budget.target_cost:
                stop_reason = "target_reached"
                break
        report = self._report(stop_reason)
        self._task_update(status="finished", best_job_id=self._best_job_id,
                          rounds=[dataclasses.asdict(r) for r in self._rounds],
                          consumed={"rounds": len(self._rounds),
                                    "wall_seconds": round(time.monotonic() - started, 3)})
        return report

    # -- internals ---------------------------------------------------------
    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def _suggest_params(self, trial) -> dict:
        params: dict = {}
        for spec in self._specs:
            if spec.kind == "float":
                params[spec.name] = trial.suggest_float(spec.name, spec.low, spec.high,
                                                        step=spec.step)
            elif spec.kind == "int":
                step = int(spec.step) if spec.step else 1
                params[spec.name] = trial.suggest_int(spec.name, int(spec.low),
                                                      int(spec.high), step=step)
            else:
                params[spec.name] = trial.suggest_categorical(spec.name, list(spec.choices))
        return params

    def _submit(self, params: dict, request_id: str) -> str:
        candidate = {"schemaVersion": "epcd-candidate/v1", "parameters": params}
        for attempt in (1, 2):
            result = epcd_run(self._ctx, task="simulation-evaluation", request_id=request_id,
                              input_obj=candidate, use_if_match=True)
            if result.ok:
                return result.data["jobId"]
            if result.exit_code == 11:
                # requestId conflict: reattach the known Job for this request, if any
                known = self._ctx.store.find_job_by_request(self._ctx.session_id, request_id)
                if known is not None:
                    return known["job_id"]
                self._pause(f"request-id conflict on {request_id} with no known job", result)
            if result.exit_code in LOOP_TRANSIENT_EXIT_CODES and attempt == 1:
                continue  # retry once with the SAME requestId (design doc section 7.3)
            self._pause(f"submission failed on {request_id}", result)
        raise AssertionError("unreachable")

    def _poll(self, job_id: str) -> str:
        while True:
            self._probe_cancel()
            if self._cancel_requested:
                epcd_job(self._ctx, action="cancel", job_id=job_id)
            result = epcd_job(self._ctx, action="get", job_id=job_id)
            if not result.ok:
                self._pause(f"polling failed for job {job_id}", result)
            status = (result.data or {}).get("status")
            if status in TERMINAL_JOB_STATUSES:
                return status
            self._sleep(self._poll_interval)

    def _read_cost(self, job_id: str, round_no: int, request_id: str,
                   params: dict) -> tuple[float | None, bool]:
        result = epcd_job(self._ctx, action="result", job_id=job_id)
        if not result.ok:
            self._pause(f"reading result failed for job {job_id}", result)
        data = result.data or {}
        # §4.12: "succeeded" + empty warnings + non-empty targetValues is the
        # real success criterion. A job that returns warnings with no
        # targetValues (e.g. SIMULATION_FAILED / GDS_NOT_FOUND) is a failed
        # parameter combination, NOT a scoring gap — report (None, sim_failed).
        if not (data.get("targetValues") or []) and (data.get("warnings") or []):
            return None, True
        cost = cost_from_result(data)
        if cost is None:
            # 服务器未产出评分（缺陷1: targetValues 恒空）。先保留本轮真实仿真
            # 记录再暂停，让 report 至少含已完成的轮次（job/参数），便于诊断与交接。
            self._record_round(round_no, request_id, params, job_id, "succeeded", None)
            raise OptimizationPausedError(
                f"job {job_id} result has no objectiveCost/targetValues "
                "(server scoring unavailable: target-values.json is a constant stub "
                "sha256:714907cb...; see manual section 5, defect 1)",
                report=self._report("paused"), category="scoring-unavailable")
        return float(cost), False

    def _record_round(self, round_no: int, request_id: str, params: dict,
                      job_id: str | None, status: str, cost: float | None) -> None:
        record = RoundRecord(round_no, request_id, params, job_id, status, cost)
        self._rounds.append(record)
        if self._on_progress is not None:
            self._on_progress({
                "type": "round_finished", "round": round_no, "request_id": request_id,
                "job_id": job_id, "status": status, "cost": cost,
                "best_cost": self._best_cost, "best_job_id": self._best_job_id,
            })
        self._task_update(rounds=[dataclasses.asdict(r) for r in self._rounds],
                          best_job_id=self._best_job_id,
                          consumed={"rounds": len(self._rounds)})

    def _report(self, stop_reason: str) -> OptimizationReport:
        return OptimizationReport(
            best_job_id=self._best_job_id, best_cost=self._best_cost,
            best_parameters=self._best_parameters,
            rounds=tuple(self._rounds), stop_reason=stop_reason)

    def _pause(self, message: str, result) -> None:
        self._task_update(status="paused")
        raise OptimizationPausedError(
            message, report=self._report("paused"),
            category=result.category, errors=result.errors)

    def _task_update(self, **fields) -> None:
        if self._task_id is None:
            return
        if self._ctx.store.get_optimization(self._ctx.session_id, self._task_id) is None:
            return
        self._ctx.store.update_optimization(self._ctx.session_id, self._task_id, **fields)
