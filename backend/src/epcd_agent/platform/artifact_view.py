"""artifact_view: job result artifacts -> UI-renderable preview cards.

Remote (ssh) deployments fetch artifact bytes into a local cache so the
agent/user side can open them; local deployments just copy.
"""
from __future__ import annotations

import base64
import pathlib
import shutil
import subprocess

from epcd_agent.tools.base import ToolContext, ToolResult
from epcd_agent.tools.read import epcd_job

_TITLES = {
    "gds": "GDS",
    "gtxt": "Gtxt",
    "layout-preview-image": "Layout preview",
    "snp": "S-parameters",
    "objective-values": "Objective values",
    "objective-chart": "Objective chart",
    "manifest": "Manifest",
    "range-em": "RangeEM publication",
}


def build_artifact_cards(job_result_data: dict) -> list[dict]:
    cards = []
    for item in job_result_data.get("artifacts") or []:
        artifact_type = str(item.get("type"))
        cards.append({
            "type": artifact_type,
            "title": _TITLES.get(artifact_type, artifact_type),
            "remotePath": item.get("path"),
            "localPath": None,
        })
    return cards


def _fetch_remote(ssh_connect: tuple, remote_path: str, local_path: pathlib.Path) -> bool:
    """ssh joins argv tokens with spaces; the base64 command must be ONE token.
    Returns False when the fetch fails (card keeps localPath=None).

    ``ssh_connect`` is the same platform-independent connect argv used to run
    epcd-cli (``ssh -o BatchMode=yes [-o HostName=...] [-o User=...] [-i ...] <target>``),
    so artifact downloads never depend on the local ssh config path either.
    """
    proc = subprocess.run(list(ssh_connect) + [f"base64 -w0 {remote_path}"],
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        return False
    local_path.write_bytes(base64.b64decode(proc.stdout.strip()))
    return True


def artifact_view(ctx: ToolContext, job_id: str, fetch_dir: str | None = None) -> ToolResult:
    result = epcd_job(ctx, action="result", job_id=job_id)
    if not result.ok:
        return result
    cards = build_artifact_cards(result.data or {})
    if fetch_dir:
        target_dir = pathlib.Path(fetch_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        # Prefer the explicit ssh connect args carried on ctx (platform-independent);
        # fall back to the legacy heuristic (argv_prefix[0] == "ssh") for callers
        # that predate ToolContext.ssh_connect.
        ssh_connect = getattr(ctx, "ssh_connect", ())
        remote_mode = bool(ssh_connect) or (
            bool(ctx.cli.argv_prefix) and ctx.cli.argv_prefix[0] == "ssh")
        for card in cards:
            remote = card["remotePath"]
            if not remote:
                continue
            # PurePath (platform-dependent) also splits "/" on Windows, so it
            # handles both POSIX remote paths and local Windows paths.
            local = target_dir / pathlib.PurePath(remote).name
            if remote_mode:
                connect = ssh_connect if ssh_connect else ("ssh", "-o", "BatchMode=yes",
                                                           ctx.cli.argv_prefix[3])
                if not _fetch_remote(connect, remote, local):
                    continue  # 单件失败不阻塞清单
            else:
                shutil.copy(remote, local)
            card["localPath"] = str(local)
    return ToolResult(ok=True, data={"job_id": job_id, "cards": cards})
