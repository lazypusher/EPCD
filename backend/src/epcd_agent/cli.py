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


def _expand_user(path: str) -> str:
    """Cross-platform home expansion.

    os.path.expanduser works on both POSIX and Windows (Windows reads
    USERPROFILE); we use it explicitly so ``~/.ssh/...`` in config files
    resolves to the right location on every OS.
    """
    return os.path.expanduser(path)


def _inline_ssh_config_path() -> str:
    """Return the path to EPCD's own empty ssh config, creating it if needed.

    OpenSSH on *both* POSIX and Windows reads the system ``ssh_config`` (and
    ``ssh_config.d/*``) even when every connection option is passed via ``-o``;
    the only way to bypass that is ``-F <file>``, and ``-F`` requires the file
    to exist. We point ``-F`` at our own *empty* config so the invocation never
    depends on the OS-specific ssh config path nor on user ``~/.ssh/config``
    (whose alias entries vary across machines/OSes, and whose parent dir may be
    read-only). It lives under the OS temp dir (``tempfile.gettempdir()``, e.g.
    /tmp or %TEMP%), which is writable on every platform and independent of the
    user home; the file is empty, reused idempotently, and carries no secrets.
    """
    try:
        from tempfile import gettempdir
        path = os.path.join(gettempdir(), "epcd-inline-ssh-config")
        with open(path, "a", encoding="utf-8"):
            pass  # ensure existence; keep existing content untouched
        return path
    except OSError:
        # Temp dir not writable (extremely rare): still return a path; ssh will
        # report its own error, and legacy alias mode remains available.
        return os.path.join(gettempdir(), "epcd-inline-ssh-config")


def _ssh_connect_args(target: str, host: str | None, user: str | None,
                      port: str | int | None, identity_file: str | None) -> tuple[str, ...]:
    """Build the ssh connection args, decoupled from the local ssh config path.

    Explicit ``host``/``user``/``port``/``identity_file`` are passed via
    ``-o``/``-i``, and ``-F`` points at EPCD's own empty config so ssh reads
    neither the system ``ssh_config`` nor the user ``~/.ssh/config``. This is
    the platform-independent mode: the same args run on Windows and Linux
    regardless of where the OS keeps its ssh config.

    When the explicit fields are absent, fall back to ``target`` as an ssh host
    *alias* (legacy behaviour) resolved from the local config.
    """
    explicit = bool(host or user or port or identity_file)
    if not explicit:
        # Legacy: no explicit params — depend on the local config to resolve
        # the alias. No -F here so the alias resolution still works.
        if target is None:
            return ()
        return ("ssh", "-o", "BatchMode=yes", target)
    # Platform-independent explicit mode: -F(empty) + -o/-i.
    args: list[str] = ["ssh", "-F", _inline_ssh_config_path(), "-o", "BatchMode=yes"]
    if host:
        args += ["-o", f"HostName={host}"]
    if user:
        args += ["-o", f"User={user}"]
    if port:
        args += ["-o", f"Port={port}"]
    if identity_file:
        args += ["-i", _expand_user(identity_file)]
    if target is None:
        return ()
    args.append(target)
    return tuple(args)


def build_argv_prefix(ssh_host: str | None = None, pkg_root: str | None = None,
                      cli_bin: str = "epcd-cli",
                      *, host: str | None = None, user: str | None = None,
                      port: str | int | None = None,
                      identity_file: str | None = None) -> tuple[str, ...]:
    if ssh_host is None and pkg_root is None:
        return (cli_bin,)
    # 远端先 source 用户级环境（~/.epcd-env，存 NINECUBE_LICENSE_FILE 等
    # 不进 pkg 安装树的变量），再 source pkg 的 user.bashrc.ePCD。
    connect = _ssh_connect_args(ssh_host, host, user, port, identity_file)
    return connect + (
        "source", f"{pkg_root}/user.bashrc.ePCD", ">/dev/null", "2>&1;",
        "[", "-f", "~/.epcd-env", "]", "&&", "source", "~/.epcd-env", ";",
        cli_bin)


def _load_configs(config_file: str | None) -> tuple[dict | None, str | None]:
    """Load ``epcd-configs.json`` and resolve the active (flat) config.

    Returns ``(active_config, error_message)``. The config file is:

        {"active": "<name>", "configs": {"<name>": {host, port, user,
         identityFile, pkg, technology, workDirRoot}, ...}}

    Each named config is a flat set of attributes — connection params, EPCD
    package root, technology file and work dir root are all peers (no
    servers/profiles nesting). The ``active`` key selects which one is in effect.
    """
    if config_file is None:
        return None, "missing --config-file (path to epcd-configs.json)"
    try:
        with open(config_file, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"cannot load configs file {config_file!r}: {exc}"
    if not isinstance(cfg, dict):
        return None, f"configs file {config_file!r} must be a JSON object"
    active = cfg.get("active")
    configs = cfg.get("configs")
    if not isinstance(active, str) or not active:
        return None, f"configs file {config_file!r} missing string 'active'"
    if not isinstance(configs, dict):
        return None, f"configs file {config_file!r} missing object 'configs'"
    entry = configs.get(active)
    if not isinstance(entry, dict):
        return None, (f"unknown config {active!r} (configs file: {config_file!r})")
    return {"name": active, **entry}, None


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


def _build_ctx(args, active_config: dict | None = None) -> ToolContext:
    cfg = active_config or {}
    host = cfg.get("host")
    user = cfg.get("user")
    port = cfg.get("port")
    identity_file = cfg.get("identityFile") or cfg.get("identity_file")
    pkg = cfg.get("pkg")
    target = cfg.get("name") or (host or "epcd")
    connect = _ssh_connect_args(target, host, user, port, identity_file)
    prefix = build_argv_prefix(target, pkg,
                               host=host, user=user,
                               port=port, identity_file=identity_file)
    cli = EpcdCli(argv_prefix=prefix)
    store = SessionStore(args.db)
    if store.get_session(args.session) is None:  # create_session 非幂等，需先查
        store.create_session(args.session)
    return ToolContext(cli=cli, store=store, session_id=args.session,
                       ssh_connect=connect,
                       technology=cfg.get("technology"),
                       work_dir_root=cfg.get("workDirRoot"))


def _emit(ok: bool, data=None, error: dict | None = None) -> str:
    return json.dumps({"ok": ok, "data": data, "error": error}, ensure_ascii=False)


def main(argv: list[str], stdin_text: str, build_ctx=None,
         registry_override: dict | None = None) -> tuple[int, str]:
    parser = argparse.ArgumentParser(prog="epcd-agent-cli", add_help=True)
    parser.add_argument("--db", default=os.environ.get(
        "EPCD_AGENT_DB", "epcd-agent-session.sqlite3"))
    parser.add_argument("--session", default=os.environ.get("EPCD_AGENT_SESSION", "default"))
    parser.add_argument("--config-file", default=os.environ.get("EPCD_CONFIG_FILE"))
    parser.add_argument("tool", nargs="?", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2, _emit(False, error={"type": "USAGE", "message": "bad arguments"})
    active_config, config_err = _load_configs(args.config_file)
    if config_err is not None:
        return 2, _emit(False, error={"type": "USAGE", "message": config_err})
    if args.tool is None:
        return 2, _emit(False, error={
            "type": "USAGE",
            "message": "tool name required"})
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
    if build_ctx is not None:
        # 自定义 ctx 工厂（测试注入）：仍走单参数约定，active_config 由调用方自取。
        ctx = build_ctx(args)
    else:
        ctx = _build_ctx(args, active_config)
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
