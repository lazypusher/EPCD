"""Read-only tools: health, templates, formula validation, job queries."""
from __future__ import annotations

from .base import ToolContext, ToolInputError, ToolResult, inject_ids, result_from_exec

_JOB_ACTIONS = ("get", "result", "cancel")


def epcd_health(ctx: ToolContext) -> ToolResult:
    """Probe environment: epcd-cli version + health (release doc section 4.1)."""
    version_result = result_from_exec(ctx.cli.exec(["version"]))
    if not version_result.ok:
        return version_result
    health_result = result_from_exec(ctx.cli.exec(["health"]))
    if not health_result.ok:
        return health_result
    return ToolResult(ok=True, exit_code=0,
                      data={"version": version_result.data, "health": health_result.data})


def epcd_template(ctx: ToolContext, action: str,
                  category: str | None = None,
                  template_id: str | None = None) -> ToolResult:
    """device-template list/describe (release doc section 4.3)."""
    if action == "list":
        args = ["device-template", "list"]
        if category:
            args += ["--category", category]
        return result_from_exec(ctx.cli.exec(args))
    if action == "describe":
        if not template_id:
            raise ToolInputError("template_id is required for action='describe'")
        args = inject_ids(ctx, ["device-template", "describe", template_id], instance=False)
        return result_from_exec(ctx.cli.exec(args))
    raise ToolInputError(f"unsupported epcd_template action: {action!r}")


def epcd_formula(ctx: ToolContext, formula: dict) -> ToolResult:
    """formula validate with stdin JSON (release doc section 4.8)."""
    return result_from_exec(ctx.cli.exec(["formula", "validate", "--input", "-"], stdin_obj=formula))


def epcd_job(ctx: ToolContext, action: str, job_id: str) -> ToolResult:
    """job get/result/cancel (release doc sections 4.11-4.12)."""
    if action not in _JOB_ACTIONS:
        raise ToolInputError(f"unsupported epcd_job action: {action!r}")
    return result_from_exec(ctx.cli.exec(["job", action, "--id", job_id]))
