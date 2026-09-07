#!/usr/bin/env python
"""Cache EPCD device-template descriptions locally and build a comparison table.

Reason: avoid re-reading the same template payloads from the remote epcd-cli
on every session. Writes two artifacts:

  <out_dir>/cache.json        raw describe payloads, keyed by templateId
  <out_dir>/comparison.md     human-readable candidate comparison table

Usage (from backend/):
  EPCD_SSH_HOST=... EPCD_PKG_ROOT=/package/... \
    ./.venv/Scripts/python scripts/template_cache.py \
      [--session inductor] [--db epcd-agent-session.sqlite3] \
      [--out ../../docs/template-library/inductor] \
      [--category inductor] [--extra system.tcoil.tcoil_inductor_oct,system.tcoil.tcoil_inductor_rec]

Fetched templates can be refreshed any time by re-running; cache.json is
overwritten atomically.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

CATEGORY_EXTRA = {
    "inductor": ["system.tcoil.tcoil_inductor_oct",
                 "system.tcoil.tcoil_inductor_rec"],
}


def run_tool(args_env: dict, db: str, session: str, tool: str,
             payload: dict | None = None) -> dict:
    """Invoke epcd_agent.cli the same way the skill does."""
    cmd = [str(pathlib.Path(args_env["repo"]) / ".venv" / "Scripts" / "python.exe"),
           "-m", "epcd_agent.cli", "--db", db, "--session", session, tool]
    env = dict(os.environ, EPCD_SSH_HOST=args_env["ssh"],
               EPCD_PKG_ROOT=args_env["pkg"], MSYS_NO_PATHCONV="1")
    proc = subprocess.run(cmd, input=json.dumps(payload or {}),
                          capture_output=True, text=True, env=env,
                          cwd=args_env["repo"])
    if proc.returncode not in (0, 1):
        sys.exit(f"{tool} failed rc={proc.returncode}: {proc.stderr}")
    try:
        out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        sys.exit(f"{tool} bad stdout: {proc.stdout!r}")
    if not out.get("ok"):
        sys.exit(f"{tool} business failure: {out.get('error')}")
    return out["data"]


def summarize(raw: dict) -> dict:
    """Flatten a describe payload into the comparison-row fields."""
    schema = raw.get("parameterSchema", {}).get("properties", {})
    opt = schema.get("opt", {}).get("properties", {})
    synth = schema.get("synth", {}).get("properties", {})
    # Range separator is EN DASH (–), NOT tilde: tildes render like a
    # strikethrough line (~) in some markdown renderers and mislead readers.
    opt_rows = {k: f"{v.get('minimum')}–{v.get('maximum')}"
                + (f" @{v.get('step','').lstrip('@')}" if (v.get('step') or '').startswith('@') else "")
                for k, v in opt.items()}
    synth_rows = {k: f"{v.get('default')} ({v.get('suffix')})" for k, v in synth.items()}
    metrics = [f"{m.get('key')}={m.get('default')}(w{m.get('weight')})"
               for m in raw.get("builtInMetrics", [])]
    return {
        "templateId": raw.get("templateId"),
        "moduleName": raw.get("moduleName"),
        "category": raw.get("category"),
        "available": raw.get("available"),
        "opt": opt_rows,
        "synth": synth_rows,
        "metrics": metrics,
    }


def row_table(rows: list[dict]) -> str:
    """Render summary rows as a compact markdown table."""
    opt_keys = ["trackWidth", "trackSpace", "numOfTurns", "innerRadius",
                "layer1Width", "layer2Width"]
    synth_keys = ["inductance", "Ld", "minQFactor", "Qd", "maxSize"]
    header = ["templateId", "moduleName", "opt 参数(um/圈)", "synth 默认目标", "内置指标"]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        opt_bits = [f"{k}:{r['opt'][k]}" for k in opt_keys if k in r["opt"]]
        syn_bits = [f"{k}:{r['synth'][k]}" for k in synth_keys if k in r["synth"]]
        lines.append(
            f"| `{r['templateId']}` | {r['moduleName']} | "
            f"{', '.join(opt_bits) or '—'} | {', '.join(syn_bits) or '—'} | "
            f"{', '.join(r['metrics']) or '—'} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="template-lib")
    ap.add_argument("--db", default="epcd-agent-session.sqlite3")
    ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parents[2]
                                         / "docs" / "template-library" / "inductor"))
    ap.add_argument("--category", default="inductor")
    ap.add_argument("--extra", default="")
    args = ap.parse_args()

    repo = str(pathlib.Path(__file__).resolve().parents[1])  # backend/
    env = {"repo": repo,
           "ssh": os.environ["EPCD_SSH_HOST"],
           "pkg": os.environ["EPCD_PKG_ROOT"]}

    listing = run_tool(env, args.db, args.session, "epcd_template",
                       {"action": "list"})
    ids = [t["templateId"] for t in listing.get("templates", [])
           if t.get("category") == args.category]
    ids += [x for x in (args.extra.split(",") if args.extra else
                        CATEGORY_EXTRA.get(args.category, [])) if x]

    raw_keep: dict[str, dict] = {}
    summaries = []
    for tid in ids:
        data = run_tool(env, args.db, args.session, "epcd_template",
                        {"action": "describe", "template_id": tid})
        raw_keep[tid] = data
        summaries.append(summarize(data))

    summaries.sort(key=lambda r: r["templateId"])
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cache = {"fetched_at": None,  # Date.now not allowed in scripts; filled below
             "session": args.session,
             "category": args.category,
             "templates": raw_keep,
             "summaries": summaries}
    cache_path = out_dir / "cache.json"
    tmp = cache_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_path)

    md = (f"# EPCD inductor 模板对比\n\n"
          f"> 本地快照，由 `backend/scripts/template_cache.py` 生成；"
          f"原始 describe 载荷见 [cache.json](cache.json)。\n\n"
          f"> **图例**：opt 参数形如 `线宽 6–20` 表示最小值–最大值（单位 µm，"
          f"numOfTurns 圈数无单位）；`@0.25` 表示该参数优化步进；"
          f"synth 目标形如 `L=2.1 (Equal)` 表示默认值 2.1 用相等比较，"
          f"`Q≥8 (Greater)` 表示下限，`maxSize≤300 (Less)` 表示上限。\n\n")
    md += row_table(summaries) + "\n"
    (out_dir / "comparison.md").write_text(md, encoding="utf-8")

    print(json.dumps({"ok": True, "count": len(ids),
                      "templates": [s["templateId"] for s in summaries],
                      "cache": str(cache_path),
                      "table": str(out_dir / "comparison.md")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())