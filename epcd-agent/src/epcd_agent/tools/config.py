"""Config tools: schema/get/patch/apply-result (release doc sections 4.5-4.6, 4.14)."""
from __future__ import annotations

from .base import (
    ToolContext,
    ToolInputError,
    ToolResult,
    inject_ids,
    require_digest,
    result_from_exec,
)


def _ledger_digest(ctx: ToolContext, result: ToolResult) -> None:
    if result.ok and result.data and result.data.get("configDigest"):
        ctx.store.set_config_digest(ctx.session_id, result.data["configDigest"])


def epcd_config(ctx: ToolContext, action: str, path: str | None = None,
                patch_obj: dict | None = None, job_id: str | None = None) -> ToolResult:
    if action == "schema":
        args = inject_ids(ctx, ["config", "schema"])
        if path:
            args += ["--path", path]
        return result_from_exec(ctx.cli.exec(args))

    if action == "get":
        args = inject_ids(ctx, ["config", "get"])
        if path:
            args += ["--path", path]
        result = result_from_exec(ctx.cli.exec(args))
        _ledger_digest(ctx, result)
        return result

    if action == "patch":
        if patch_obj is None:
            raise ToolInputError("config patch requires patch_obj")
        result = _patch_once(ctx, patch_obj, require_digest(ctx))
        if not result.ok and any(e["code"] == "CONFIG_DIGEST_MISMATCH" for e in result.errors):
            # hard rule 2: auto-refresh digest via config get, retry once
            refresh = epcd_config(ctx, action="get")
            if not refresh.ok:
                return refresh
            result = _patch_once(ctx, patch_obj, require_digest(ctx))
        _ledger_digest(ctx, result)
        return result

    if action == "apply-result":
        if not job_id:
            raise ToolInputError("config apply-result requires job_id")
        args = inject_ids(ctx, ["config", "apply-result", "--job-id", job_id])
        result = result_from_exec(ctx.cli.exec(args))
        _ledger_digest(ctx, result)
        return result

    raise ToolInputError(f"unsupported epcd_config action: {action!r}")


def _patch_once(ctx: ToolContext, patch_obj: dict, digest: str) -> ToolResult:
    args = inject_ids(ctx, ["config", "patch"])
    args += ["--input", "-", "--if-match", digest]
    return result_from_exec(ctx.cli.exec(args, stdin_obj=patch_obj))
