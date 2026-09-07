#!/usr/bin/env python
"""Config-driven batch collection of optimizer simulation data.

All configurable inputs come from ONE TOML config file (default collect.toml):
  [server]        ssh_host / pkg_root (or EPCD_SSH_HOST/EPCD_PKG_ROOT env),
                  technology (remote .ptxt path), work_dir_root
  [[templates]]   numeric id <-> real templateId (1:1 mapping); --template
                  takes the id (number) or the name/templateId
  [optimizer]     max_rounds, startup_trials (ARRAY → one full run per value,
                  batch-validate the TPE startup setting), seed
  [objectives]    defaults are the epcd-cli interface built-ins (read live from
                  `config schema`); config items are an optional override.
                  [[objectives.custom_metrics]] optional L/Q-formula injection
                      (2026-09-04 实证：须放 /synthesisTargets/customMetrics 下，勿与内置名同名).
  [output]        out_dir, tag
  [cleanup]       delete_run_dirs (default true) — remove each job's remote
                  runDirectory after fetching its result; results are captured
                  locally so the server keeps nothing (req #3).

Sweep derivation (req #2): only range-mode objectives (frequency.mode=range)
produce a top-level sweep covering their range; all-point-mode objectives get
NO sweep.

Outputs are grouped by objectives (req #4): under each group, one per-round
CSV+JSONL per startup_trials run, plus a cross-run comparison table (markdown +
CSV) — one row per startup_trials value, comparing best_cost / best params /
best L/Q@obj-freq / satisfied / elapsed.

Usage (from epcd-agent/, Git Bash on Windows):
  MSYS_NO_PATHCONV=1 ./.venv/Scripts/python scripts/collect_sim_data.py \
      --config scripts/collect.toml --template 1

MSYS_NO_PATHCONV=1 is REQUIRED under Git Bash (see [server] note). The config
may set ssh_host/pkg_root directly; env vars override when present.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import tomllib
import uuid

# Git Bash (MSYS) rewrites /package/... and /home/... into Windows paths and
# breaks the remote ssh argv (exit 127 epcd-cli not found). Set before any
# subprocess call; also export it in the shell before assigning EPCD_PKG_ROOT.
os.environ.setdefault("MSYS_NO_PATHCONV", "1")

# Resolve the epcd-agent repo root by walking UP from this file until
# <root>/src/epcd_agent exists — the script is symlink/copy portable (it now
# lives under skills/device-design-flow/scripts/), so a fixed parents[]
# offset would break. _REPO_ROOT also anchors _CACHE_ROOT below.
_REPO_ROOT = pathlib.Path(__file__).resolve()
for _ancestor in _REPO_ROOT.parents:
    if (_ancestor / "src" / "epcd_agent").is_dir():
        sys.path.insert(0, str(_ancestor / "src"))
        _REPO_ROOT = _ancestor
        break
else:
    raise SystemExit("cannot locate epcd_agent/src above " + str(_REPO_ROOT))
del _ancestor

from epcd_agent.cli import build_argv_prefix                       # noqa: E402
from epcd_agent.cli_client import EpcdCli                          # noqa: E402
from epcd_agent.optimizer import controller as opt_controller     # noqa: E402
from epcd_agent.optimizer.space import parse_real_parameter_schema  # noqa: E402
from epcd_agent.platform.optimize_tools import optimization_start   # noqa: E402
from epcd_agent.store import SessionStore                          # noqa: E402
from epcd_agent.tools.base import ToolContext                      # noqa: E402
from epcd_agent.tools.config import epcd_config                     # noqa: E402
from epcd_agent.tools.read import epcd_health, epcd_job, epcd_template  # noqa: E402
from epcd_agent.tools.write import epcd_device, epcd_project      # noqa: E402

_CACHE_ROOT = _REPO_ROOT / "docs" / "template-library"


class RetryingCli:
    """Bounded-retry wrapper around EpcdCli.exec for transient host crashes.

    A long optimization spawns ~80 ssh subprocesses; occasionally one fails to
    start on the Windows side (observed ENVELOPE_PARSE_ERROR with exit
    3221225794 = 0xC0000142 STATUS_DLL_INIT_FAILED) — pure transience, and the
    idempotent setup/read calls (project init, device add, config get/schema,
    health, template list) are safe to re-run. Business failures return a
    parseable envelope and are NEVER retried (a retry would hide a real
    server-side answer). Retry only when we got no envelope at all.
    """
    _TRANSIENT_EXIT_CODES = frozenset((127,))  # ssh/remote command not found

    def __init__(self, cli: EpcdCli, attempts: int = 3, backoff: float = 2.0):
        self._cli = cli
        self._attempts = max(1, attempts)
        self._backoff = backoff

    def __getattr__(self, name):
        # delegate the rest of the EpcdCli surface (argv_prefix etc.)
        return getattr(self._cli, name)

    def exec(self, args, stdin_obj=None, timeout=None):
        last = None
        for attempt in range(1, self._attempts + 1):
            last = self._cli.exec(args, stdin_obj=stdin_obj, timeout=timeout)
            if last.parse_error is None and last.exit_code not in self._TRANSIENT_EXIT_CODES:
                return last  # valid envelope — business answer, do not retry
            if attempt < self._attempts:
                print(f"[retry] {' '.join(map(str, args[-3:]))} → transient "
                      f"(exit={last.exit_code} {last.parse_error or ''}); "
                      f"attempt {attempt + 1}/{self._attempts} in {self._backoff}s",
                      file=sys.stderr)
                time.sleep(self._backoff)
        return last


class CollectError(Exception):
    """Terminal setup/collection failure."""


def _require(result, step: str):
    if not result.ok:
        codes = ",".join(e.get("code", "UNKNOWN") for e in result.errors) or "UNKNOWN"
        raise CollectError(f"{step} failed: {codes} (exit {result.exit_code})")
    return result


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def load_config(path: str) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except OSError as exc:
        raise CollectError(f"cannot read config {path}: {exc}")
    except tomllib.TOMLDecodeError as exc:
        raise CollectError(f"invalid TOML in {path}: {exc}")


def _cfg_get(cfg: dict, *path, default=None):
    node = cfg
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _default_tpe_settings_path() -> pathlib.Path:
    """references/tpe-settings.toml — sibling of this script's parent's sibling."""
    return pathlib.Path(__file__).resolve().parent.parent / "references" / "tpe-settings.toml"


def _load_tpe_settings(path: str | pathlib.Path) -> dict:
    """Load the per-template TPE settings file → {templateId: {startup_trials,
    max_rounds}}. Empty dict when missing/unparseable (auto-config degrades
    silently to the caller's fallback)."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        print(f"[warn] invalid tpe-settings {path}: {exc}", file=sys.stderr)
        return {}
    out: dict = {}
    def _flatten(node, prefix=""):
        for k, v in node.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                if "startup_trials" in v or "max_rounds" in v:
                    out[key] = {kk: v[kk] for kk in ("startup_trials", "max_rounds") if kk in v}
                else:
                    _flatten(v, key)
    _flatten(data)
    return out


# --------------------------------------------------------------------------
# Template resolution (numeric id <-> real templateId, 1:1)
# --------------------------------------------------------------------------

def _live_template_ids(ctx: ToolContext, category: str) -> dict[str, str]:
    """Return {templateId: name} from the live `device-template list`."""
    listing = _require(epcd_template(ctx, action="list", category=category), "template list")
    data = listing.data or {}
    out: dict[str, str] = {}
    cats = data.get("categories")
    if isinstance(cats, dict):
        entries = cats.get(category, []) if category else [e for v in cats.values() for e in v]
    else:
        entries = [t for t in data.get("templates", [])
                   if not category or t.get("category") == category]
    for t in entries:
        tid = t.get("templateId")
        if tid:
            out[tid] = t.get("name") or t.get("moduleName") or ""
    return out


def resolve_template(ctx: ToolContext, cfg: dict, category: str, spec: str) -> str:
    """Map a config numeric id (or name/templateId) to a real templateId.

    The config's [[templates]] entries define the 1:1 id<->name mapping (req
    1a). The chosen entry must also exist in the live template list.
    """
    entries = _cfg_get(cfg, "templates", default=[]) or []
    by_id: dict[int, dict] = {}
    by_name: dict[str, dict] = {}
    for e in entries:
        try:
            by_id[int(e["id"])] = e
        except (KeyError, TypeError, ValueError):
            pass
        if "name" in e:
            by_name[e["name"]] = e
        if "template_id" in e:
            by_name[e["template_id"]] = e

    chosen = None
    s = str(spec).strip()
    if s.lstrip("0").isdigit() or s.isdigit():
        n = int(s)
        if n not in by_id:
            raise CollectError(f"template id {n} not in config [[templates]] "
                               f"(known: {sorted(by_id)})")
        chosen = by_id[n]
    elif s in by_name:
        chosen = by_name[s]
    else:
        raise CollectError(f"template {spec!r} not in config [[templates]] by id/name; "
                           f"known ids: {sorted(by_id)}, names: {sorted(set(by_name))}")
    template_id = chosen.get("template_id")
    name = chosen.get("name") or ""
    if not template_id:
        raise CollectError(f"config template entry {chosen!r} missing template_id")

    live = _live_template_ids(ctx, category)
    print(f"=== {category} templates, {len(live)} live ===", file=sys.stderr)
    for i, (tid, nm) in enumerate(sorted(live.items()), 1):
        mark = "  *" if tid == template_id else ""
        print(f"  #{i:>2}  {tid:<42} {nm}{mark}", file=sys.stderr)
    if template_id not in live:
        raise CollectError(f"config template_id {template_id!r} ({name}) not available "
                           f"on the live server; available: {', '.join(sorted(live))}")
    if name and live.get(template_id) and name != live[template_id]:
        print(f"[warn] config name {name!r} != live name {live[template_id]!r} for "
              f"{template_id}", file=sys.stderr)
    return template_id


# --------------------------------------------------------------------------
# Objectives + sweep derivation
# --------------------------------------------------------------------------

def _obj_freq(freq: dict) -> float | None:
    """Objective frequency value (GHz) from a frequency sub-dict (point value
    or range midpoint)."""
    if not isinstance(freq, dict):
        return None
    if freq.get("mode") == "range":
        lo, hi = freq.get("minimum"), freq.get("maximum")
        if _is_num(lo) and _is_num(hi):
            return round((float(lo) + float(hi)) / 2, 6)
        return _num(freq.get("minimum"))
    return _num(freq.get("value") if "value" in freq else freq.get("freq"))


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _num(v) -> float | None:
    if not _is_num(v):
        return None
    return float(v)


def _objective_point_freqs(objectives: list[dict]) -> list[float]:
    """Freqs worth flattening in the CSV (point values + range min/mid/max)."""
    freqs: list[float] = []
    for obj in objectives:
        f = obj.get("frequency") or {}
        if f.get("mode") == "range":
            for k in ("minimum", "maximum"):
                v = _num(f.get(k))
                if v is not None and v not in freqs:
                    freqs.append(round(v, 6))
            mid = _obj_freq(f)
            if mid is not None and mid not in freqs:
                freqs.append(mid)
        else:
            v = _obj_freq(f)
            if v is not None and v not in freqs:
                freqs.append(v)
    return sorted(freqs)


def _build_sweeps(objectives: list[dict]) -> list[dict]:
    """Top-level sweeps derived ONLY from range-mode objectives (req #2).
    Point-mode objectives produce no sweep. One sweep per range objective's
    [minimum, maximum] with its step."""
    sweeps = []
    for obj in objectives:
        f = obj.get("frequency") or {}
        if f.get("mode") != "range":
            continue
        lo, hi, step = _num(f.get("minimum")), _num(f.get("maximum")), _num(f.get("step"))
        if lo is None or hi is None:
            continue
        unit = f.get("unit") or "GHz"
        # step as a unit-string scalar (manual §4.10); default 10MHz
        step_str = f"{step}{unit}" if step else "10MHz"
        sweeps.append({"enabled": True, "type": "adaptive",
                       "start": f"{lo}{unit}", "stop": f"{hi}{unit}",
                       "step": step_str, "points": ""})
    return sweeps


def resolve_objectives(ctx: ToolContext, cfg: dict) -> tuple[dict | None, dict | None, dict | None, list[float], list[dict]]:
    """Return (objectives_patch, custom_metrics_patch, sweeps_patch, obj_freqs,
    resolved_objectives).

    objectives_patch: synthesisTargets patch, or None to use server built-ins.
        - if config [objectives].items present → build patch from them
        - else → None (use epcd-cli interface defaults, req #1b)
    custom_metrics_patch: synthesisTargets.customMetrics patch, or None.
    sweeps_patch: top-level sweeps patch derived from range objectives, or None.
    obj_freqs: freqs to flatten in CSV.
    resolved_objectives: the objectives list used (config or live defaults).
    """
    obj_cfg = _cfg_get(cfg, "objectives", default={}) or {}
    items = obj_cfg.get("items")

    if items:
        objectives = items
        freq_mode = obj_cfg.get("frequency_mode", "points")
        objectives_patch = {
            "synthesisTargets": {
                "frequencyMode": freq_mode,
                "customMetrics": [],
                "objectives": [_normalize_objective(o) for o in objectives],
            }
        }
    else:
        # Use the live interface built-in defaults (req #1b): read them from
        # `config schema` so the defaults always match the server.
        schema = _require(epcd_config(ctx, action="schema"), "config schema (defaults)").data["schema"]
        st = schema.get("synthesisTargets") or {}
        objectives = st.get("objectives") or []
        objectives_patch = None  # do not patch; use built-ins as-is
        print(f"[objectives] using {len(objectives)} built-in default objective(s) "
              f"from config schema (no patch)", file=sys.stderr)

    custom_metrics = obj_cfg.get("custom_metrics")
    # 2026-09-04 实证：customMetrics 放 /synthesisTargets/customMetrics 下才被
    # 服务端接受并使用（顶层 /customMetrics 注入已无意义；与内置指标同名会报
    # CUSTOM_METRIC_CONFLICT）。配合 [objectives].items 时并入同一 synthesisTargets
    # patch；单独给直接用内置目标（不 patch objectives）的场景兜底。
    if custom_metrics:
        cm_patch = {"synthesisTargets": {"customMetrics": list(custom_metrics)}}
        if items and objectives_patch:
            objectives_patch["synthesisTargets"]["customMetrics"] = list(custom_metrics)
            custom_metrics_patch = None
        else:
            custom_metrics_patch = cm_patch
    else:
        custom_metrics_patch = None

    # Sweep policy. Default (req #2): only range-mode objectives produce a
    # sweep; point-mode → none. Two config overrides in [simulation]:
    #   sweep = {start, stop, step}  → exact top-level sweep (explicit).
    #   force_sweep = true           → derive a MINIMAL coverage window when
    #       point-mode objectives would otherwise get none. Some templates
    #       (stack_inductor verified) run EM but emit NO targetValues from a
    #       zero-width/point evaluation (paused scoring-unavailable); a window
    #       of objective-freq ±0.1GHz (3 points) is enough — NOT the default
    #       1-3GHz band (too many points, too slow).
    sim_cfg = _cfg_get(cfg, "simulation", default={}) or {}
    explicit = sim_cfg.get("sweep")
    force = sim_cfg.get("force_sweep") in (True, "true", "True", "1", 1)
    if explicit and isinstance(explicit, dict):
        sweep = dict(explicit)
        sweep.setdefault("type", "adaptive")
        sweep.setdefault("step", "10MHz")
        sweeps = [{"enabled": True, "type": sweep["type"], "start": sweep["start"],
                   "stop": sweep["stop"], "step": sweep["step"], "points": ""}]
        sweeps_patch = {"sweeps": sweeps}
        print(f"[sweeps] explicit top-level sweep {sweep['start']}..{sweep['stop']} "
              f"(config [simulation].sweep)", file=sys.stderr)
    else:
        sweeps = _build_sweeps(objectives)
        if not sweeps and force:
            freqs = sorted(_objective_point_freqs(objectives))
            if freqs:
                lo, hi = freqs[0], freqs[-1]
                if len(freqs) == 1:
                    # single point → tiny ±0.1GHz window (Range EM needs start<stop)
                    lo, hi, stepv = lo - 0.1, hi + 0.1, 0.1
                else:
                    # coarsest step that lands EXACTLY on the objective points:
                    # 1.5/2.0/2.5/3.0 → 1.5..3.0GHz step 0.5GHz (4 points)
                    stepv = max(0.05, round((hi - lo) / (len(freqs) - 1), 4))
                sweeps = [{"enabled": True, "type": "adaptive",
                           "start": f"{lo:g}GHz", "stop": f"{hi:g}GHz",
                           "step": f"{stepv:g}GHz", "points": ""}]
                print(f"[sweeps] minimal window {lo:g}..{hi:g}GHz step {stepv:g}GHz forced "
                      f"([simulation].force_sweep — template EM needs a sweep)",
                      file=sys.stderr)
        sweeps_patch = {"sweeps": sweeps} if sweeps else None
        if not sweeps:
            print(f"[sweeps] none (objectives are point-mode; no sweep per req #2)",
                  file=sys.stderr)

    obj_freqs = _objective_point_freqs(objectives)
    for o in objectives:
        f = o.get("frequency") or {}
        m = o.get("metric", "?")
        print(f"[objective] {m:<24} {f.get('mode','point')} "
              f"{_obj_freq(f)}GHz {o.get('comparison','')} {o.get('targetValue')}",
              file=sys.stderr)
    return objectives_patch, custom_metrics_patch, sweeps_patch, obj_freqs, objectives


def _normalize_objective(o: dict) -> dict:
    """Normalize a config objective to the config-patch input shape (§4.9)."""
    f = o.get("frequency") or {}
    freq = {"mode": f.get("mode", "point")}
    if f.get("mode") == "range":
        for k in ("minimum", "step", "maximum"):
            if k in f:
                freq[k] = f[k]
        freq["unit"] = f.get("unit", "GHz")
    else:
        freq["value"] = f.get("value")
        freq["unit"] = f.get("unit", "GHz")
    return {
        "metric": o["metric"],
        "frequency": freq,
        "comparison": o["comparison"],
        "targetValue": o["targetValue"],
        "unit": o.get("unit", ""),
        "weight": o.get("weight", 1),
    }


# --------------------------------------------------------------------------
# Parameter space (live config schema -> parse_real_parameter_schema shape)
# --------------------------------------------------------------------------

def build_param_schema(ctx: ToolContext, template_id: str, category: str) -> tuple[dict, dict]:
    """Build the optimization parameter_schema from the LIVE `config schema`:
    device.parameters.opt gives {param:{min,max,step,locked,enabled}} (§4.5).

    The optimizable space is ALL `enabled` opt parameters. We deliberately
    IGNORE the `locked` flag: a controlled A/B on the real server (identical
    trackWidth/numOfTurns/innerRadius, trackSpace 2.0 vs 4.8) showed the
    candidate value IS applied (L 2.331→2.297, Q 12.388→12.482, cost
    −0.438→−0.466) — `locked` is an instance/UI state, not a simulation-
    eligibility gate, so simple_inductor's trackSpace joins the TPE space.

    Returns (parameter_schema, device_opt) where device_opt is the FULL
    opt-parameter map {name: {value,min,max,step,enabled,locked}} of the
    instance config — used to record fixed (non-optimized / locked) params in
    the results so the table always shows every core param with its effective
    value. cache.json is a fallback for builds whose live opt is empty."""
    schema = _require(epcd_config(ctx, action="schema"), "config schema (params)").data["schema"]
    opt_params = (((schema.get("device") or {}).get("parameters") or {}).get("opt") or {})
    props: dict[str, dict] = {}
    device_opt: dict[str, dict] = {}
    for name, p in opt_params.items():
        if not isinstance(p, dict):
            continue
        enabled = p.get("enabled") in (True, "true", "True", "1", 1)
        props[name] = {
            "minimum": p.get("min"),
            "maximum": p.get("max"),
            "step": p.get("step"),
            "enabled": "1" if enabled else "0",
        }
        device_opt[name] = {"value": p.get("value"), "min": p.get("min"),
                            "max": p.get("max"), "step": p.get("step"),
                            "enabled": enabled, "locked": p.get("locked")}
    tunable = {k: v for k, v in props.items() if v["enabled"] == "1"}
    if tunable:
        schema_out = {"type": "object",
                      "properties": {"opt": {"properties": props}},
                      "template_id": template_id}
        _preview_space(schema_out, "live config schema")
        return schema_out, device_opt

    # fallback: cache.json curated opt.properties (describe shape)
    curated = _curated_schema_from_cache(category, template_id)
    if curated is not None:
        _preview_space(curated, "cache.json fallback")
        return curated, {}
    raise CollectError("no tunable opt parameters: live config schema opt empty and "
                      "no cache fallback for this template")


def _curated_schema_from_cache(category: str, template_id: str) -> dict | None:
    candidates = []
    if category:
        candidates.append(_CACHE_ROOT / category / "cache.json")
    candidates.append(_CACHE_ROOT / "inductor" / "cache.json")
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entry = (data.get("templates") or {}).get(template_id)
        if not isinstance(entry, dict):
            continue
        schema = entry.get("parameterSchema") or {}
        if schema.get("type") != "object":
            continue
        opt_props = (((schema.get("properties") or {}).get("opt") or {}).get("properties") or {})
        enabled = {k: v for k, v in opt_props.items()
                   if str(v.get("enabled", "1")) == "1"}
        if not enabled or not all(_is_num(v.get("minimum")) and _is_num(v.get("maximum"))
                                  for v in enabled.values()):
            continue
        return {**schema, "template_id": template_id}
    return None


def _preview_space(schema: dict, source: str) -> None:
    opt_props = (((schema.get("properties") or {}).get("opt") or {}).get("properties") or {})
    enabled = {k: v for k, v in opt_props.items() if str(v.get("enabled", "1")) == "1"}
    disabled = {k: v for k, v in opt_props.items() if str(v.get("enabled", "1")) != "1"}
    print(f"[opt] parameter space: {source} — {len(enabled)} tunable, "
          f"{len(disabled)} disabled", file=sys.stderr)
    for name, spec in sorted(enabled.items()):
        print(f"        {name:<14} [{spec.get('minimum')}..{spec.get('maximum')}] "
              f"step={spec.get('step')}", file=sys.stderr)
    for name in sorted(disabled):
        print(f"        {name:<14} (disabled — fixed at default)", file=sys.stderr)


# --------------------------------------------------------------------------
# Server cleanup (req #3): delete each job's remote runDirectory
# --------------------------------------------------------------------------

def cleanup_run_dir(ssh_host: str, run_dir: str) -> bool:
    """SSH `rm -rf` the job's runDirectory on the server. Returns success."""
    if not ssh_host or not run_dir:
        return False
    argv = ["ssh", "-o", "BatchMode=yes", ssh_host, "rm", "-rf", "--", run_dir]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[cleanup] {run_dir}: ssh failed ({exc})", file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f"[cleanup] {run_dir}: rm rc={proc.returncode} {proc.stderr.strip()}",
              file=sys.stderr)
        return False
    return True


# --------------------------------------------------------------------------
# Per-run optimization + per-round result collection
# --------------------------------------------------------------------------

def run_one(ctx: ToolContext, *, cfg: dict, template_id: str, instance_name: str,
            startup_trials: int, max_rounds: int, seed: int,
            max_wall_seconds: float, tag: str, work_dir: str,
            delete_run_dirs: bool, ssh_host: str,
            resolved: tuple | None) -> tuple[dict, tuple]:
    """One full TPE optimization run for a given startup_trials value.

    `resolved` caches the (objectives_patch, custom_metrics_patch, sweeps_patch,
    obj_freqs, objectives) tuple across runs: objectives are resolved on the
    first run (after device add, so a live instance exists for reading the
    built-in defaults) and reused for subsequent runs. Returns (run, resolved).
    """
    opt_controller._TPE_SEED = seed
    opt_controller._TPE_STARTUP_TRIALS = startup_trials

    # setup (project + device) — per run (fresh project). resolve_objectives
    # for the built-in case reads `config schema`, which needs an active
    # instance, so it must run AFTER device add (not in main).
    _require(epcd_project(ctx, action="init", work_dir=work_dir,
                          technology=cfg["server"]["technology"]), "project init")
    _require(epcd_project(ctx, action="describe"), "project describe")
    _require(epcd_project(ctx, action="validate"), "project validate")
    _require(epcd_device(ctx, action="add", template_id=template_id, name=instance_name),
             "device add")

    if resolved is None:
        resolved = resolve_objectives(ctx, cfg)
    objectives_patch, custom_metrics_patch, sweeps_patch, obj_freqs, objectives = resolved

    # config: get initial digest, then patches (objectives → simulation/sweeps
    # → customMetrics). Each patch auto-refreshes the digest on mismatch.
    _require(epcd_config(ctx, action="get"), "config get (initial)")
    if objectives_patch:
        _require(epcd_config(ctx, action="patch", patch_obj=objectives_patch), "patch objectives")
    if sweeps_patch:
        _require(epcd_config(ctx, action="patch", patch_obj=sweeps_patch), "patch sweeps")
    if custom_metrics_patch:
        _require(epcd_config(ctx, action="patch", patch_obj=custom_metrics_patch),
                 "patch customMetrics")
    _require(epcd_config(ctx, action="get"), "config get (final)")

    # parameter_schema for THIS instance (opt params are per-instance). The
    # 4 core params (incl. trackSpace, whose `locked` flag is a UI state, not
    # a simulation gate) are all in the TPE space; disabled params keep their
    # config value and are merged into every round below so the results table
    # always shows every core parameter.
    parameter_schema, device_opt = build_param_schema(
        ctx, template_id,
        cfg.get("category") or (cfg.get("server") or {}).get("category") or "inductor")
    fixed_params = {k: p.get("value") for k, p in device_opt.items()
                    if not p.get("enabled")}

    print(f"\n[opt] startup_trials={startup_trials} max_rounds={max_rounds} "
          f"tag={tag} ...", file=sys.stderr)
    started = time.time()
    out = optimization_start(
        ctx, parameter_schema=parameter_schema, initial_candidates=(),
        max_rounds=max_rounds, max_wall_seconds=max_wall_seconds, request_prefix=tag)
    elapsed = time.time() - started

    if out.ok:
        report = out.data["report"]
        print(f"[opt] st={startup_trials} finished in {elapsed:.0f}s: "
              f"stop={report.get('stop_reason')} best_cost={report.get('best_cost')}",
              file=sys.stderr)
    else:
        report = (out.data or {}).get("report", {})
        codes = ",".join(e.get("code", "UNKNOWN") for e in out.errors) or "UNKNOWN"
        print(f"[opt] st={startup_trials} did not complete cleanly ({codes}); "
              f"salvaging {len(report.get('rounds', []))} rounds", file=sys.stderr)

    # per-round lean result fetch + cleanup. We keep ONLY the data that can
    # drive optimizer tuning: the candidate parameters, the scalar
    # objective_cost, and the per-target L/Q values at the OBJECTIVE
    # frequencies (targetValues full per-frequency dump stays on the server,
    # which we delete anyway). Everything else (job ids, request ids, file
    # paths, sha digests, timestamps, artifacts) is noise for tuning and is
    # not carried into the round records.
    rounds_results: list[dict] = []
    cleaned = 0
    for r in report.get("rounds", []):
        job_id = r.get("job_id")
        result_data: dict = {}
        run_dir = ""
        if job_id:
            jr = epcd_job(ctx, action="result", job_id=job_id)
            if jr.ok:
                result_data = jr.data or {}
                run_dir = result_data.get("runDirectory") or ""
            else:
                print(f"[collect] round {r.get('round_no')}: job result fetch failed "
                      f"for {job_id}", file=sys.stderr)
        tvs = result_data.get("targetValues") or []
        if obj_freqs:
            keep = {round(float(f), 6) for f in obj_freqs}
            tvs = [tv for tv in tvs if isinstance(tv, dict)
                   and isinstance((tv.get("frequency") or {}).get("value"), (int, float))
                   and round(float(tv["frequency"]["value"]), 6) in keep]
        objective_cost = result_data.get("objectiveCost")
        if objective_cost is None:
            objective_cost = r.get("cost")
        rounds_results.append({
            "round_no": r.get("round_no"),
            "parameters": {**fixed_params, **(r.get("parameters") or {})},
            "status": r.get("status"),
            "objective_cost": objective_cost,
            "targetValues": [_lean_tv(tv) for tv in tvs],
        })
        if delete_run_dirs and run_dir:
            if cleanup_run_dir(ssh_host, run_dir):
                cleaned += 1

    if delete_run_dirs:
        print(f"[cleanup] removed {cleaned}/{len(rounds_results)} run dirs on server",
              file=sys.stderr)

    run = {
        "startup_trials": startup_trials,
        "tag": tag,
        "template_id": template_id,
        "best_cost": report.get("best_cost"),
        "best_parameters": report.get("best_parameters"),
        "stop_reason": report.get("stop_reason"),
        "rounds": rounds_results,
        "device_opt": device_opt,
        "objective_freqs": obj_freqs,
        "elapsed_seconds": round(elapsed, 1),
        "optimizer_settings": {
            "tpe_seed": seed,
            "tpe_startup_trials": startup_trials,
            "max_rounds": max_rounds,
            "max_wall_seconds": max_wall_seconds,
        },
    }
    return run, resolved


# --------------------------------------------------------------------------
# Output (grouped by objectives; comparison table across startup_trials)
# --------------------------------------------------------------------------

def _objectives_hash(objectives: list[dict]) -> str:
    raw = json.dumps(objectives, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def _objectives_label(objectives: list[dict]) -> str:
    if not objectives:
        return "none"
    parts = []
    for o in objectives:
        f = o.get("frequency") or {}
        parts.append(f"{o.get('metric','?')}@{_obj_freq(f)}GHz:{o.get('comparison','')}{o.get('targetValue')}")
    return " | ".join(parts)


def _run_best(rounds: list[dict]) -> tuple[float | None, dict | None, dict | None]:
    """(best_cost, best_parameters, best_round) by objective_cost — no job ids."""
    best_rr, best_cost = None, None
    for rr in rounds:
        c = rr.get("objective_cost")
        if not isinstance(c, (int, float)):
            continue
        if best_cost is None or c < best_cost:
            best_cost, best_rr = float(c), rr
    if best_rr is not None:
        return best_cost, best_rr.get("parameters") or {}, best_rr
    return None, None, None


def write_per_run(run: dict, out_dir: pathlib.Path) -> dict:
    """Per-run raw output: ONE lean JSONL record per round (parameters being
    the optimizable core set, objective_cost, status, per-target L/Q at the
    objective freqs) plus a meta summary. This is the raw material; the single
    human/LLM-facing table lives in write_results (group dir)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = run["tag"]
    rounds = run["rounds"]
    best_cost, best_params, _ = _run_best(rounds)
    run["best_cost"] = best_cost
    run["best_parameters"] = best_params
    obj_freqs = run.get("objective_freqs") or []

    jsonl_path = out_dir / f"{tag}.jsonl"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as fh:
        for rr in rounds:
            fh.write(json.dumps({
                "run_id": tag,
                "startup_trials": run["startup_trials"],
                "template_id": run["template_id"],
                "round_no": rr["round_no"],
                "status": rr.get("status") or "",
                "objective_cost": rr.get("objective_cost"),
                "is_best": (best_cost is not None and rr.get("objective_cost") == best_cost),
                "parameters": rr.get("parameters") or {},
                "targetValues": [_lean_tv(tv) for tv in rr.get("targetValues") or []],
            }, ensure_ascii=False) + "\n")

    summary_path = out_dir / f"{tag}.summary.json"
    top = {k: run[k] for k in ("tag", "startup_trials", "template_id",
                              "best_cost", "best_parameters",
                              "stop_reason", "elapsed_seconds", "optimizer_settings")}
    top["rounds_collected"] = len(rounds)
    top["objective_freqs"] = obj_freqs
    top["device_opt"] = run.get("device_opt") or {}
    top["jsonl"] = str(jsonl_path)
    top["summary"] = str(summary_path)
    summary_path.write_text(json.dumps(top, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"jsonl": str(jsonl_path), "summary": str(summary_path),
            "rounds": len(rounds), "best_cost": best_cost, "best_parameters": best_params}


def _metric_bases(runs: list[dict]) -> tuple[list[str], dict]:
    """(bases, unit_map): ordered {metric}@{freq}GHz bases across the runs and
    the per-base unit label (e.g. "(nH)") taken from the tv `unit` field."""
    bases: list[str] = []
    units: dict[str, str] = {}
    for run in runs:
        for rr in run["rounds"]:
            for tv in rr.get("targetValues") or []:
                if not isinstance(tv, dict) or not isinstance(tv.get("frequency_GHz"), (int, float)):
                    continue
                base = f"{tv.get('metric', '?')}@{tv['frequency_GHz']}GHz"
                if base not in bases:
                    bases.append(base)
                u = tv.get("unit") or ""
                if not units.get(base) and u:
                    units[base] = u
    return bases, units


_CANONICAL_PARAM_ORDER = ["trackWidth", "trackSpace", "numOfTurns", "innerRadius"]
_COMPARISON_SYM = {"equal": "=", "greater-than": ">", "less-than": "<"}
# Physical units of the sim parameters (from the template geometry docs):
# the inductor tracks/radius are in um; numOfTurns is dimensionless.
_PARAM_UNITS = {"trackWidth": "um", "trackSpace": "um", "innerRadius": "um",
                "numOfTurns": ""}
# Fallback display units by output metric (built-in objectives carry unit "-"):
# nH for inductance, um for size, dimensionless for Q. Stored WITHOUT parens.
_INFER_UNIT = {"L": "nH", "Size": "um", "Q": ""}


def _norm_unit(u) -> str:
    """Normalize a unit to bare form ('(nH)'/'nH' → 'nH'; ''/'-' → '')."""
    u = (u or "").strip().strip("()")
    return u if u not in ("", "-") else ""


def _target_unit(objective: dict | None, metric: str) -> str:
    """Effective unit for a target/objective label: the objective's unit when
    meaningful (""/"-" → skip), else inferred from the metric name."""
    if objective:
        u = _norm_unit(objective.get("unit"))
        if u:
            return u
    return _INFER_UNIT.get(metric, "")


def _param_sort_key(name: str) -> tuple:
    if name in _CANONICAL_PARAM_ORDER:
        return (0, _CANONICAL_PARAM_ORDER.index(name))
    return (1, name)


def _tv_metric_for(objective_metric: str) -> str | None:
    """SynthesisTargets objective metric name → the targetValue metric the
    server reports (built-ins: Inductance Value(nH)→L, Min Q Factor→Q,
    Max Size(um)→Size)."""
    m = (objective_metric or "").lower()
    if "inductance" in m or "l" == m.strip().lower():
        return "L"
    if "q factor" in m or "qfactor" in m or m.strip().lower().startswith("q"):
        return "Q"
    if "size" in m:
        return "Size"
    return None


def _match_objective(objectives: list[dict], metric: str, freq: float) -> dict | None:
    """Pair a targetValue (metric, freq) with the synthesisTargets objective it
    is scored against — match by frequency, preferring a metric-name match."""
    cands = [o for o in objectives
             if (f := _obj_freq(o.get("frequency") or {})) is not None
             and abs(round(float(f), 6) - round(float(freq), 6)) < 1e-9]
    if not cands:
        return None
    for o in cands:
        if _tv_metric_for(o.get("metric")) == metric:
            return o
    return cands[0]


def _colspecs(objectives: list[dict], bases: list[str], units: dict) -> list[tuple]:
    """Per metric-col (base) the three display columns (internal_key, header):
    actual carries the unit, `_satisfied` header carries the REAL scoring
    objective ("L@2.5GHz =2.1nH"). Unit comes from the tv `unit` field when
    present (old jsonl may lack it); else inferred from the metric name."""
    specs: list[tuple] = []
    for base in bases:
        metric, freq_gz = base.split("@", 1)
        freq = float(freq_gz[:-3])
        tv_unit = units.get(base, "")
        disp_unit = _norm_unit(tv_unit) or _INFER_UNIT.get(metric, "")
        obj = _match_objective(objectives, metric, freq)
        lbl = ""
        if obj:
            t, c = obj.get("targetValue"), obj.get("comparison") or ""
            lbl = f"{_COMPARISON_SYM.get(c, '')}{t}{_target_unit(obj, metric)}"
        specs.append((f"{base}_actual", f"{base} ({disp_unit})" if disp_unit else base))
        specs.append((f"{base}_deviation", f"{base} deviation"))
        specs.append((f"{base}_satisfied",
                      f"{base} {lbl}".strip() if lbl else f"{base} satisfied"))
    return specs


def _objectives_line(objectives: list[dict]) -> str:
    """Human/LLM summary of the synthesisTargets objectives, e.g.
    'L@2.5GHz =2.1nH | Q@2.5GHz >8 | Size@2.5GHz <300um'."""
    parts = []
    for o in objectives:
        f = _obj_freq(o.get("frequency") or {})
        m = _tv_metric_for(o.get("metric")) or o.get("metric", "?")
        c = _COMPARISON_SYM.get(o.get("comparison") or "", "")
        parts.append(f"{m}@{f}GHz {c}{o.get('targetValue')}{_target_unit(o, m)}")
    return " | ".join(parts)


def _run_table(run: dict, param_keys: list[str],
               colspecs: list[tuple]) -> tuple[list[str], list[dict]]:
    """One configuration's table: SINGLE header — round_no, status → sim
    params (headers carry their unit, e.g. 'trackWidth (nm)') → metric columns
    (actual with unit, `_satisfied` header is the real scoring objective) →
    cost. best_so_far is gone."""
    param_cols = [f"{k} ({_PARAM_UNITS.get(k)})" if _PARAM_UNITS.get(k) else k
                  for k in param_keys]
    cols = ["round_no", "status"] + param_cols \
        + [hdr for _, hdr in colspecs] + ["objective_cost"]
    device_opt = run.get("device_opt") or {}
    rows: list[dict] = []
    for rr in sorted(run["rounds"], key=lambda x: x["round_no"]):
        cost = rr.get("objective_cost")
        row = {"round_no": rr["round_no"], "status": rr.get("status") or ""}
        params = rr.get("parameters") or {}
        for k, hdr in zip(param_keys, param_cols):
            row[hdr] = (params.get(k) if k in params
                        else (device_opt.get(k) or {}).get("value", ""))
        idx = {}
        for tv in rr.get("targetValues") or []:
            if not isinstance(tv, dict) or not isinstance(tv.get("frequency_GHz"), (int, float)):
                continue
            base = f"{tv.get('metric', '?')}@{tv['frequency_GHz']}GHz"
            idx[base] = {"actual": tv.get("actual"), "deviation": tv.get("deviation"),
                         "satisfied": tv.get("satisfied")}
        for key, hdr in colspecs:
            base, suffix = key.rsplit("_", 1)
            v = (idx.get(base) or {}).get(suffix, "")
            row[hdr] = "" if v is None else v
        row["objective_cost"] = cost if isinstance(cost, (int, float)) else ""
        rows.append(row)
    return cols, rows


def _md_table(cols: list[str], rows: list[dict]) -> list[str]:
    """Pure-markdown single-header table, one row per round."""
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return lines


def write_results(runs: list[dict], objectives: list[dict], group_dir: pathlib.Path) -> dict:
    """Per-CONFIGURATION results (confirmed design):
    - results.md : one section per TPE configuration; heading keeps the TPE
      parameters, plus a synthesisTargets line describing the optimization
      objectives. Each table is a SINGLE-header pure-markdown table: round_no,
      status → sim params → metric columns (actual header carries the unit,
      `_satisfied` header is the real objective, e.g. 'L@2.5GHz =2.1nH') →
      cost.
    - <tag>.csv  : the SAME table as its own CSV file (single header). One
      independent file per independent TPE configuration.
    best_so_far is removed. Prunes the obsolete combined results.csv,
    comparison.* and per-run *.csv.
    """
    group_dir.mkdir(parents=True, exist_ok=True)
    opt_names = set()
    for run in runs:
        opt_names |= {k for rr in run["rounds"] for k in (rr.get("parameters") or {})}
        opt_names |= set((run.get("device_opt") or {}).keys())
    param_keys = sorted(opt_names, key=_param_sort_key)
    bases, units = _metric_bases(runs)
    colspecs = _colspecs(objectives, bases, units)

    md_lines = ["# Simulation results — objectives: " + _objectives_label(objectives), "",
                f"- runs: {len(runs)} | parameter space: {', '.join(param_keys)}", ""]
    total_rounds = 0
    csv_paths: list[str] = []

    for run in sorted(runs, key=lambda r: (r["startup_trials"], r["tag"])):
        n = run["startup_trials"]
        m = (run.get("optimizer_settings") or {}).get("max_rounds", "?")
        tag = run["tag"]
        tpe_cell = f"TPE parameters (startup_trials = {n}, max_rounds = {m})"
        cols, rows = _run_table(run, param_keys, colspecs)
        total_rounds += len(rows)

        # independent CSV per configuration (single header)
        csv_path = group_dir / f"{tag}.csv"
        with csv_path.open("w", encoding="utf-8", newline="\n") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])
        csv_paths.append(str(csv_path))

        md_lines.append(f"## Configuration: {tpe_cell} — run `{tag}`")
        md_lines.append("")
        md_lines.append(f"- **objectives (synthesisTargets):** {_objectives_line(objectives)}")
        md_lines.append("")
        md_lines.extend(_md_table(cols, rows))
        md_lines.append("")

    md_path = group_dir / "results.md"
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    # prune the obsolete combined file + scattered tables
    for old in ("results.csv", "comparison.csv", "comparison.md"):
        p = group_dir / old
        if p.exists():
            p.unlink()
    for sub in group_dir.glob("st*/*.csv"):
        sub.unlink()

    return {"results_md": str(md_path), "config_csv": csv_paths,
            "runs": len(runs), "rounds": total_rounds}


def _lean_tv(tv: dict) -> dict:
    """Normalize a raw server target-value (or an already-lean one) to the
    single lean shape every writer/reader uses: {metric, frequency_GHz, target,
    actual, deviation, satisfied}. Idempotent.
    Server raw: {metric, frequency:{value,unit,valueHz}, targetValue,
                 actualValue, relativeDeviation, satisfied}.
    Lean:       {metric, frequency_GHz, target, actual, deviation, satisfied}.
    """
    f = tv.get("frequency")
    if isinstance(f, dict):
        freq_g = f.get("value")
    else:
        freq_g = tv.get("frequency_GHz")
    return {
        "metric": tv.get("metric"),
        "frequency_GHz": freq_g,
        "unit": tv.get("unit") or tv.get("unitStr") or "",
        "target": tv.get("targetValue", tv.get("target")),
        "actual": tv.get("actualValue", tv.get("actual")),
        "deviation": tv.get("relativeDeviation", tv.get("deviation")),
        "satisfied": tv.get("satisfied"),
    }


def _normalize_round(rr: dict, obj_freqs: list[float]) -> dict:
    """Normalize a jsonl round record to the lean tuning shape. Handles both
    the current writer (objective_cost) and earlier verbose writer
    (objectiveCost/cost + full per-frequency targetValues), so group dirs
    produced before the lean rewrite can still be re-rendered."""
    if "objective_cost" not in rr:
        cost = rr.get("objectiveCost")
        if cost is None:
            cost = rr.get("cost")
        tvs = rr.get("targetValues") or []
        if obj_freqs:
            keep = {round(float(f), 6) for f in obj_freqs}
            tvs = [tv for tv in tvs if isinstance(tv, dict)
                   and isinstance((tv.get("frequency") or {}).get("value"), (int, float))
                   and round(float(tv["frequency"]["value"]), 6) in keep]
        rr = {"round_no": rr["round_no"], "parameters": rr.get("parameters") or {},
              "status": rr.get("status"), "objective_cost": cost,
              "targetValues": [_lean_tv(tv) for tv in tvs]}
    else:
        # already-lean records may still carry lean targetValues — normalize
        # them (idempotent) so every downstream reader sees one tv shape.
        rr = {**rr, "targetValues": [_lean_tv(tv) for tv in rr.get("targetValues") or []]}
    return rr


def _load_group_runs(group_dir: pathlib.Path) -> list[dict]:
    """Reconstruct run dicts from earlier partial invocations in a group dir
    (st*/<tag>.summary.json + its jsonl), so comparison tables can merge
    across --only re-runs. Runs are deduped by tag at the call site."""
    runs: list[dict] = []
    if not group_dir.exists():
        return runs
    for sub in sorted(p for p in group_dir.iterdir() if p.is_dir() and p.name.startswith("st")):
        for meta_path in sorted(sub.glob("*.summary.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            jsonl = pathlib.Path(meta.get("jsonl", ""))
            if not jsonl.exists():
                continue
            obj_freqs = meta.get("objective_freqs", [])
            rounds = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()
                      if line.strip()]
            rounds = [_normalize_round(rr, obj_freqs) for rr in rounds]
            runs.append({
                "startup_trials": meta["optimizer_settings"]["tpe_startup_trials"],
                "tag": meta["tag"],
                "template_id": meta["template_id"],
                "best_cost": meta.get("best_cost"),
                "best_parameters": meta.get("best_parameters"),
                "stop_reason": meta.get("stop_reason"),
                "elapsed_seconds": meta.get("elapsed_seconds"),
                "objective_freqs": obj_freqs,
                "optimizer_settings": meta.get("optimizer_settings") or {},
                "device_opt": meta.get("device_opt") or {},
                "rounds": rounds,
            })
    return runs


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Config-driven batch collection of optimizer simulation data.")
    ap.add_argument("--config", default=str(pathlib.Path(__file__).resolve().parent / "collect.toml"),
                    help="path to the TOML config file (default: scripts/collect.toml)")
    ap.add_argument("--template", required=True,
                    help="config template id (number) or name/templateId")
    ap.add_argument("--db", default="epcd-agent-session.sqlite3")
    ap.add_argument("--session", default=f"collect-{uuid.uuid4().hex[:8]}")
    ap.add_argument("--out", default=None, help="override config [output].out_dir")
    ap.add_argument("--tag", default=None, help="run id (default: collect-<ts>-<rand>)")
    ap.add_argument("--max-wall-seconds", type=float, default=None,
                    help="override config [optimizer].max_wall_seconds")
    ap.add_argument("--max-rounds", type=int, default=None,
                    help="override config [optimizer].max_rounds (smoke-test with few rounds)")
    ap.add_argument("--only", type=int, default=None,
                    help="run only this one startup_trials value (skip the rest)")
    ap.add_argument("--startup-trials", default=None,
                    help="comma-separated startup_trials values, highest precedence "
                         "(e.g. '3,5,10' to batch-validate); overrides config + tpe-settings")
    ap.add_argument("--tpe-settings", default=None,
                    help="path to the per-template TPE settings TOML (default: "
                         "references/tpe-settings.toml beside this script; the chosen "
                         "template's startup_trials/max_rounds are auto-applied unless "
                         "explicitly overridden)")
    ap.add_argument("--no-tpe-settings", action="store_true",
                    help="disable auto per-template TPE settings")
    ap.add_argument("--no-cleanup", action="store_true",
                    help="do not delete remote run dirs (override config)")
    ap.add_argument("--render-only", default=None, metavar="GROUP_DIR",
                    help="do not run anything; re-render an existing objectives_* "
                         "group dir to the LEAN output format (regenerates each "
                         "st*/ run CSV+JSONL+summary and the comparison table "
                         "from the jsonl data). Use to migrate old verbose runs.")
    args = ap.parse_args()

    cfg = load_config(args.config)
    srv = cfg.get("server", {})
    ssh = os.environ.get("EPCD_SSH_HOST") or srv.get("ssh_host")
    pkg = os.environ.get("EPCD_PKG_ROOT") or srv.get("pkg_root")
    if bool(ssh) != bool(pkg):
        print("server.ssh_host and server.pkg_root must be set together (or via "
              "EPCD_SSH_HOST/EPCD_PKG_ROOT env, or neither for a local epcd-cli).",
              file=sys.stderr)
        return 2
    if "technology" not in srv:
        print("config [server].technology is required (remote .ptxt path)", file=sys.stderr)
        return 2
    if "work_dir_root" not in srv:
        print("config [server].work_dir_root is required", file=sys.stderr)
        return 2

    cli = RetryingCli(EpcdCli(argv_prefix=build_argv_prefix(ssh, pkg), default_timeout=300.0))
    store = SessionStore(args.db)
    if store.get_session(args.session) is None:
        store.create_session(args.session)
    ctx = ToolContext(cli=cli, store=store, session_id=args.session)

    if args.render_only:
        # Re-render an existing objectives_* group dir to the LEAN output
        # format without touching the server (migrates old verbose runs).
        group_dir = pathlib.Path(args.render_only)
        manifests = list(group_dir.glob("objectives.json"))
        if not manifests:
            print(f"--render-only: no objectives.json in {group_dir}", file=sys.stderr)
            return 2
        objectives = json.loads(manifests[0].read_text(encoding="utf-8"))["objectives"]
        runs = _load_group_runs(group_dir)
        for run in runs:
            write_per_run(run, group_dir / f"st{run['startup_trials']}")
        res = write_results(runs, objectives, group_dir) if runs else {}
        print(json.dumps({"ok": True, "rendered_runs": len(runs),
                          "group_dir": str(group_dir), **res}, ensure_ascii=False))
        return 0

    # category may live at the config TOP level or inside a [server]-section
    # (older configs put it there — it only worked because the default was
    # "inductor"). Resolve both so tcoil etc. validate against the right list.
    category = (cfg.get("category")
                or (cfg.get("server") or {}).get("category") or "inductor")
    opt_cfg = cfg.get("optimizer", {})
    # startup_trials precedence is resolved AFTER template_id (per-template auto
    # config needs to know which template). Preliminary values here; final step
    # below.
    if args.startup_trials is not None:
        startup_values = [int(v.strip()) for v in str(args.startup_trials).split(",") if v.strip()]
    elif "startup_trials" in opt_cfg:
        raw = opt_cfg["startup_trials"]
        startup_values = raw if isinstance(raw, list) else [raw]
    else:
        startup_values = None  # -> per-template tpe-settings, else [3]
    if startup_values is not None and not startup_values:
        print("[optimizer].startup_trials must be a non-empty array "
              "(or leave it unset for the per-template tpe-settings)", file=sys.stderr)
        return 2
    max_rounds = int(opt_cfg.get("max_rounds", 20))
    if args.max_rounds is not None:
        max_rounds = args.max_rounds
    seed = int(opt_cfg.get("seed", opt_controller._TPE_SEED))
    max_wall = (args.max_wall_seconds if args.max_wall_seconds is not None
                else float(opt_cfg.get("max_wall_seconds", 3600.0)))
    delete_run_dirs = (not args.no_cleanup) and bool(cfg.get("cleanup", {}).get("delete_run_dirs", True))

    out_cfg = cfg.get("output", {})
    out_dir = pathlib.Path(args.out or out_cfg.get("out_dir", "collect-out"))
    tag_root = args.tag or out_cfg.get("tag") or f"collect-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    # resolve template (shared across runs). Objectives are resolved INSIDE
    # run_one on the first run, because reading the built-in defaults needs a
    # live device instance (config schema requires --instance-id). The group
    # directory (by objectives hash) is therefore created lazily after the
    # first run resolves objectives.
    template_id = resolve_template(ctx, cfg, category, args.template)

    # ---- per-template auto TPE settings (references/tpe-settings.toml) ----
    # startup_trials auto-applied UNLESS explicitly set (--startup-trials or
    # config [optimizer].startup_trials). max_rounds is USER's call: the
    # reference only seeds it when nothing set it, and always reports the
    # recommendation.
    if not args.no_tpe_settings:
        tpe_path = pathlib.Path(args.tpe_settings) if args.tpe_settings else _default_tpe_settings_path()
        tpe = _load_tpe_settings(tpe_path)
        entry = tpe.get(template_id)
        if entry:
            if args.startup_trials is None and "startup_trials" not in opt_cfg and entry.get("startup_trials") is not None:
                auto = entry["startup_trials"]
                startup_values = [int(auto)] if not isinstance(auto, (list, tuple)) else [int(v) for v in auto]
                print(f"[tpe] auto startup_trials={startup_values} for {template_id} "
                      f"({tpe_path.name})", file=sys.stderr)
            if args.max_rounds is None and "max_rounds" not in opt_cfg and entry.get("max_rounds"):
                max_rounds = int(entry["max_rounds"])
                print(f"[tpe] recommended max_rounds={max_rounds} applied for {template_id} "
                      f"(user may override via config/--max-rounds)", file=sys.stderr)
            elif entry.get("max_rounds"):
                print(f"[tpe] {template_id}: recommended max_rounds={entry['max_rounds']} "
                      f"(current={max_rounds})", file=sys.stderr)
    if startup_values is None:
        startup_values = [3]
        print("[tpe] no per-template setting; default startup_trials=[3]",
              file=sys.stderr)
    if args.only is not None:
        startup_values = [args.only] if args.only in startup_values else [args.only]

    resolved: tuple | None = None
    group_dir: pathlib.Path | None = None
    runs: list[dict] = []
    print(f"\n=== batch: {len(startup_values)} startup_trials value(s) "
          f"{startup_values} × {max_rounds} rounds ===", file=sys.stderr)

    for st in startup_values:
        run_tag = f"{tag_root}-st{st}"
        # project init on the real server is NOT idempotent (re-init on an
        # existing dir → PROJECT_ALREADY_EXISTS, exit 5). A clean re-run of the
        # same tag would otherwise collide with stale dirs, so add a
        # per-invocation suffix (default session ids are per-invocation UUIDs).
        work_dir = f"{srv['work_dir_root']}/{run_tag}-{args.session[-6:]}"
        instance_name = f"inst-{run_tag}"
        try:
            run, resolved = run_one(
                ctx, cfg=cfg, template_id=template_id, instance_name=instance_name,
                startup_trials=int(st), max_rounds=max_rounds,
                seed=seed, max_wall_seconds=max_wall, tag=run_tag, work_dir=work_dir,
                delete_run_dirs=delete_run_dirs, ssh_host=ssh or "",
                resolved=resolved)
        except CollectError as exc:
            print(f"ABORTED run st={st}: {exc}", file=sys.stderr)
            continue
        # lazily create the objectives-grouped directory after first resolution
        if group_dir is None:
            objectives = resolved[4]
            sweeps_patch = resolved[2]
            custom_metrics_patch = resolved[1]
            group_dir = out_dir / f"objectives_{_objectives_hash(objectives)}"
            group_dir.mkdir(parents=True, exist_ok=True)
            (group_dir / "objectives.json").write_text(
                json.dumps({"objectives": objectives, "label": _objectives_label(objectives),
                            "template_id": template_id, "sweeps": sweeps_patch,
                            "custom_metrics": custom_metrics_patch},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        paths = write_per_run(run, group_dir / f"st{st}")
        run["out_paths"] = paths
        runs.append(run)
        print(json.dumps({"run": run_tag, "startup_trials": st,
                          "best_cost": run.get("best_cost"),
                          "stop_reason": run.get("stop_reason"),
                          "rounds": len(run["rounds"]),
                          "jsonl": paths["jsonl"]}, ensure_ascii=False))

    if runs:
        # Merge runs from earlier partial invocations in the same group dir so
        # a re-run (e.g. --only 5 after st=3 already completed) still produces
        # the single results table covering every startup_trials value.
        prior = _load_group_runs(group_dir)
        seen = {r["tag"] for r in runs}
        merged = [r for r in prior if r["tag"] not in seen] + runs
        res = write_results(merged, objectives, group_dir)
        print(json.dumps({"ok": True, "runs": len(merged),
                          "group_dir": str(group_dir),
                          "objectives": _objectives_label(objectives),
                          **res}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "runs": 0, "group_dir": str(group_dir)},
                     ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
