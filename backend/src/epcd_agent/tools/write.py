"""Write tools with automatic ledgering into the Session Store (hard rule 3)."""
from __future__ import annotations

from .base import (
    ToolContext,
    ToolInputError,
    ToolResult,
    inject_ids,
    require_digest,
    result_from_exec,
)

_RUN_TASKS = ("gds-generation", "simulation-evaluation")


def epcd_project(ctx: ToolContext, action: str, work_dir: str | None = None,
                 technology: str | None = None, password: str | None = None) -> ToolResult:
    """project init/describe/validate (release doc section 4.2)."""
    if action == "init":
        # technology 缺省时从 active config 自动带出；work_dir 仍必填（skill 拼好）。
        technology = technology or getattr(ctx, "technology", None)
        if not work_dir or not technology:
            raise ToolInputError("project init requires work_dir and technology")
        args = ["project", "init", "--work-dir", work_dir, "--technology", technology]
        if password:
            args += ["--password", password]
        result = result_from_exec(ctx.cli.exec(args))
        if result.ok and result.data:
            # Release contract uses "project"; observed server build 0.1.0
            # returns "path" instead — accept both, ledger what is present.
            ctx.store.set_project(
                ctx.session_id,
                project_dir=result.data.get("project") or result.data["path"],
                lib_name=result.data.get("libName"),
                technology_digest=result.data.get("technologyDigest"),
            )
        return result
    if action in ("describe", "validate"):
        args = inject_ids(ctx, ["project", action], instance=False)
        return result_from_exec(ctx.cli.exec(args))
    raise ToolInputError(f"unsupported epcd_project action: {action!r}")


def epcd_device(ctx: ToolContext, action: str, template_id: str | None = None,
                name: str | None = None, instance_id: str | None = None) -> ToolResult:
    """project device add/list/describe/remove (release doc section 4.4)."""
    if action == "add":
        if not template_id:
            raise ToolInputError("device add requires template_id")
        args = ["project", "device", "add", "--template-id", template_id]
        if name:
            args += ["--name", name]
        args = inject_ids(ctx, args, instance=False)
        result = result_from_exec(ctx.cli.exec(args))
        if result.ok and result.data:
            new_id = result.data["instanceId"]
            ctx.store.upsert_instance(
                ctx.session_id, new_id,
                template_id=result.data.get("templateId") or template_id,
                name=result.data.get("name"),
                project_dir=result.data.get("project")
                or (ctx.store.get_project(ctx.session_id) or {}).get("project_dir", ""),
            )
            ctx.store.set_active_instance(ctx.session_id, new_id)
        return result
    if action == "list":
        return result_from_exec(ctx.cli.exec(inject_ids(ctx, ["project", "device", "list"], instance=False)))
    if action in ("describe", "remove"):
        if not instance_id:
            raise ToolInputError(f"device {action} requires instance_id")
        args = inject_ids(ctx, ["project", "device", action, "--instance-id", instance_id], instance=False)
        return result_from_exec(ctx.cli.exec(args))
    raise ToolInputError(f"unsupported epcd_device action: {action!r}")


def epcd_run(ctx: ToolContext, task: str, request_id: str,
             input_obj: dict | None = None, wait: bool = False,
             timeout_seconds: float | None = None, use_if_match: bool = False) -> ToolResult:
    """run --task ... (release doc sections 4.7 / 4.11 / 4.15)."""
    if task not in _RUN_TASKS:
        raise ToolInputError(f"unsupported run task: {task!r}")
    args = inject_ids(ctx, ["run", "--task", task])
    stdin_obj = None
    if input_obj is not None:
        args += ["--input", "-"]
        stdin_obj = input_obj
    if use_if_match:
        args += ["--if-match", require_digest(ctx)]
    args += ["--request-id", request_id]
    if wait:
        args += ["--wait"]
        if timeout_seconds is not None:
            args += ["--timeout", str(int(timeout_seconds))]
    result = result_from_exec(ctx.cli.exec(args, stdin_obj=stdin_obj))
    if result.ok and result.data and result.data.get("jobId"):
        _ledger_job(ctx, result.data, request_id, task, input_obj)
    return result


def _ledger_job(ctx: ToolContext, data: dict, request_id: str,
                task: str, input_obj: dict | None) -> None:
    job_id = data["jobId"]
    status = data.get("status", "queued")
    if ctx.store.get_job(ctx.session_id, job_id) is None:
        ctx.store.add_job(
            ctx.session_id, job_id,
            request_id=request_id,
            task_type=task,
            status=status,
            parameters=(input_obj or {}).get("parameters"),
        )
    else:
        # requestId resume returned the original Job (release doc section 4.13)
        ctx.store.update_job(ctx.session_id, job_id, status=status)
    if data.get("configDigestUsed"):
        ctx.store.set_config_digest(ctx.session_id, data["configDigestUsed"])
