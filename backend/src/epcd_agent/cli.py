"""Single CLI entry point for every epcd-agent tool.

Usage: python -m epcd_agent.cli [global options] <tool>
Tool arguments: one UTF-8 JSON object on stdin.
stdout: exactly one JSON line: {"ok": bool, "data": ..., "error": ...}.
Exit codes: 0 success; 1 tool/business failure (structured output still on
stdout); 2 usage error. Mirrors epcd-cli's own calling discipline so the
Plan-3 SDK can reuse this entry unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from epcd_agent.cli_client import EpcdCli
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext, ToolInputError, ToolResult
from epcd_agent.tools.read import epcd_health, epcd_template, epcd_formula, epcd_job
from epcd_agent.tools.write import epcd_project, epcd_device, epcd_run
from epcd_agent.tools.config import epcd_config
from epcd_agent.platform.optimize_tools import (
    optimization_cancel, optimization_start, optimization_status)
from epcd_agent.platform.artifact_view import artifact_view


def build_argv_prefix(ssh_host: str | None = None, pkg_root: str | None = None,
                      cli_bin: str = "epcd-cli") -> tuple[str, ...]:
    if ssh_host is None and pkg_root is None:
        return (cli_bin,)
    # 远端先 source 用户级环境（~/.epcd-env，存 NINECUBE_LICENSE_FILE 等
    # 不进 pkg 安装树的变量），再 source pkg 的 user.bashrc.ePCD。
    return ("ssh", "-o", "BatchMode=yes", ssh_host,
            "source", f"{pkg_root}/user.bashrc.ePCD", ">/dev/null", "2>&1;",
            "[", "-f", "~/.epcd-env", "]", "&&", "source", "~/.epcd-env", ";",
            cli_bin)


def _apply_server(args, servers_file: str | None) -> str | None:
    """Resolve ``--server`` into ``--ssh``/``--pkg`` (explicit flags win).

    Returns an error message (usage error) or ``None`` on success.
    """
    if args.server is None:
        return None
    path = servers_file or os.environ.get("EPCD_SERVERS_FILE") or "servers.json"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        return f"cannot load servers file {path!r}: {exc}"
    servers = cfg.get("servers") if isinstance(cfg, dict) else None
    entry = servers.get(args.server) if isinstance(servers, dict) else None
    if entry is None or not isinstance(entry, dict):
        return f"unknown server {args.server!r} (servers file: {path})"
    if args.ssh is None:
        args.ssh = entry.get("ssh")
    if args.pkg is None:
        args.pkg = entry.get("pkg")
    return None


def default_registry() -> dict:
    return {
        "epcd_health": lambda ctx, **kw: epcd_health(ctx),
        "epcd_template": epcd_template,
        "epcd_project": epcd_project,
        "epcd_device": epcd_device,
        "epcd_config": epcd_config,
        "epcd_formula": epcd_formula,
        "epcd_run": epcd_run,
        "epcd_job": epcd_job,
        "optimization_start": optimization_start,
        "optimization_status": optimization_status,
        "optimization_cancel": optimization_cancel,
        "artifact_view": artifact_view,
    }


def _build_ctx(args) -> ToolContext:
    prefix = build_argv_prefix(args.ssh, args.pkg)
    cli = EpcdCli(argv_prefix=prefix)
    store = SessionStore(args.db)
    if store.get_session(args.session) is None:  # create_session 非幂等，需先查
        store.create_session(args.session)
    return ToolContext(cli=cli, store=store, session_id=args.session)


def _emit(ok: bool, data=None, error: dict | None = None) -> str:
    return json.dumps({"ok": ok, "data": data, "error": error}, ensure_ascii=False)


def main(argv: list[str], stdin_text: str, build_ctx=None,
         registry_override: dict | None = None) -> tuple[int, str]:
    parser = argparse.ArgumentParser(prog="epcd-agent-cli", add_help=True)
    parser.add_argument("--db", default=os.environ.get(
        "EPCD_AGENT_DB", "epcd-agent-session.sqlite3"))
    parser.add_argument("--session", default=os.environ.get("EPCD_AGENT_SESSION", "default"))
    parser.add_argument("--ssh", default=os.environ.get("EPCD_SSH_HOST"))
    parser.add_argument("--pkg", default=os.environ.get("EPCD_PKG_ROOT"))
    parser.add_argument("--server", default=os.environ.get("EPCD_SERVER"))
    parser.add_argument("--servers-file", default=os.environ.get("EPCD_SERVERS_FILE"))
    parser.add_argument("tool", nargs="?", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2, _emit(False, error={"type": "USAGE", "message": "bad arguments"})
    server_err = _apply_server(args, args.servers_file)
    if server_err is not None:
        return 2, _emit(False, error={"type": "USAGE", "message": server_err})
    if args.tool is None or bool(args.ssh) != bool(args.pkg):
        return 2, _emit(False, error={
            "type": "USAGE",
            "message": "tool name required; --ssh and --pkg must be given together"})
    registry = registry_override or default_registry()
    fn = registry.get(args.tool)
    if fn is None:
        return 2, _emit(False, error={"type": "USAGE",
                                      "message": f"unknown tool: {args.tool}"})
    try:
        kwargs = json.loads(stdin_text) if stdin_text.strip() else {}
        if not isinstance(kwargs, dict):
            raise ValueError("stdin JSON must be an object")
    except (json.JSONDecodeError, ValueError) as exc:
        return 2, _emit(False, error={"type": "USAGE",
                                      "message": f"invalid stdin JSON: {exc}"})
    ctx = (build_ctx or _build_ctx)(args)
    try:
        result = fn(ctx, **kwargs)
    except ToolInputError as exc:
        return 1, _emit(False, error={"type": "ToolInputError", "message": str(exc)})
    except TypeError as exc:
        return 2, _emit(False, error={"type": "USAGE", "message": f"bad tool args: {exc}"})
    if isinstance(result, ToolResult):
        if result.ok:
            return 0, _emit(True, data=result.data)
        first = result.errors[0] if result.errors else {
            "code": "TOOL_FAILED", "path": None, "message": ""}
        return 1, _emit(False, data=result.data, error={
            "type": first.get("code") or "TOOL_FAILED",
            "message": first.get("message") or ""})
    return 1, _emit(False, error={"type": "INTERNAL", "message": "tool returned no result"})


def cli_main() -> None:
    code, out = main(sys.argv[1:], sys.stdin.read())
    sys.stdout.write(out + "\n")
    sys.exit(code)


if __name__ == "__main__":  # 支持 python -m epcd_agent.cli
    cli_main()
