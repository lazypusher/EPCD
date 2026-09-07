"""Shared plumbing for the epcd tool layer (design doc section 4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..cli_client import EpcdCli, ExecResult
from ..exitcodes import classify_exit
from ..store import SessionStore


class ToolInputError(Exception):
    """Tool arguments invalid, or Session Store prerequisites not met."""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    errors: tuple[dict, ...] = ()
    exit_code: int | None = None
    category: str = "success"


@dataclass
class ToolContext:
    cli: EpcdCli
    store: SessionStore
    session_id: str


def result_from_exec(result: ExecResult) -> ToolResult:
    if result.timed_out:
        return ToolResult(
            ok=False,
            errors=({"code": "CLI_TIMEOUT", "path": None,
                     "message": "epcd-cli execution timed out"},),
            exit_code=result.exit_code,
            category="transient",
        )
    if result.response is None:
        return ToolResult(
            ok=False,
            errors=({"code": "ENVELOPE_PARSE_ERROR", "path": None,
                     "message": result.parse_error},),
            exit_code=result.exit_code,
            category="unknown",
        )
    errors = tuple(
        {"code": e.code, "path": e.path, "message": e.message}
        for e in result.response.errors
    )
    category = "success" if result.response.ok else classify_exit(result.exit_code)
    return ToolResult(
        ok=result.response.ok,
        data=result.response.data,
        errors=errors,
        exit_code=result.exit_code,
        category=category,
    )


def inject_ids(ctx: ToolContext, args: list[str], *,
               project: bool = True, instance: bool = True) -> list[str]:
    """Append --project / --instance-id from the Session Store (hard rule 2).

    The LLM never supplies these values; they always come from prior
    command responses recorded in the Store.
    """
    out = list(args)
    if project:
        proj = ctx.store.get_project(ctx.session_id)
        if not proj:
            raise ToolInputError(
                "no project in session store yet; call epcd_project(action='init') first"
            )
        out += ["--project", proj["project_dir"]]
    if instance:
        inst = ctx.store.get_active_instance(ctx.session_id)
        if not inst:
            raise ToolInputError(
                "no active device instance in session store; call epcd_device(action='add') first"
            )
        out += ["--instance-id", inst["instance_id"]]
    return out


def require_digest(ctx: ToolContext) -> str:
    digest = ctx.store.get_config_digest(ctx.session_id)
    if not digest:
        raise ToolInputError(
            "no config digest in session store; call epcd_config(action='get') first"
        )
    return digest
