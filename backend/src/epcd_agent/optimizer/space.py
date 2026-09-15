"""Parse config-schema parameter definitions into an optimization space.

Inputs come from epcd_config(action="schema") responses (release doc section
4.5). Parameters without usable bounds are reported in `unbounded`; per design
doc section 7.1 the agent asks the user for an empirical range at milestone M2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import optuna


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str  # "float" | "int" | "categorical"
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple = ()


@dataclass(frozen=True)
class ParsedSpace:
    specs: tuple[ParamSpec, ...]
    unbounded: tuple[str, ...]


def parse_parameter_schema(schema: dict) -> ParsedSpace:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter schema root must be an object schema")
    properties = schema.get("properties") or {}
    specs: list[ParamSpec] = []
    unbounded: list[str] = []
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            unbounded.append(name)
            continue
        if "enum" in prop:
            specs.append(ParamSpec(name, "categorical", choices=tuple(prop["enum"])))
            continue
        low, high = prop.get("minimum"), prop.get("maximum")
        if low is None or high is None:
            unbounded.append(name)
            continue
        step = prop.get("step")
        if prop.get("type") == "integer":
            specs.append(ParamSpec(name, "int", low=float(low), high=float(high),
                                   step=float(step) if step is not None else None))
        else:
            specs.append(ParamSpec(name, "float", low=float(low), high=float(high),
                                   step=float(step) if step is not None else None))
    return ParsedSpace(specs=tuple(specs), unbounded=tuple(unbounded))


def _align_step(value: float, step: float | None) -> float:
    """Round a float onto the nearest step grid (P2, optimizer-eval 2026-08-27).

    optuna suggest_float(h, low, high, step=0.25) already lands on the grid, but
    LLM/initial candidates (normalize_candidate) and hand-written candidates may
    not.  Snap to the nearest multiple of step, preserving low-phase alignment.
    """
    if step is None or step <= 0:
        return value
    return round(round((value) / step) * step, 9)


def normalize_candidate(params: dict, specs: Iterable[ParamSpec]) -> dict:
    """Keep only known keys, clip numerics into bounds, validate choices."""
    by_name = {s.name: s for s in specs}
    out: dict = {}
    for key, value in params.items():
        spec = by_name.get(key)
        if spec is None:
            continue
        if spec.kind == "categorical":
            if value not in spec.choices:
                raise ValueError(f"{key}: {value!r} not in choices {spec.choices}")
            out[key] = value
        elif spec.kind == "int":
            v = _align_step(float(value), spec.step)
            clipped = min(max(v, spec.low), spec.high)
            out[key] = int(round(clipped))
        else:
            v = _align_step(float(value), spec.step)
            out[key] = float(min(max(v, spec.low), spec.high))
    return out


def to_optuna_distributions(specs: Iterable[ParamSpec]) -> dict:
    dists: dict = {}
    for spec in specs:
        if spec.kind == "float":
            if spec.step is not None:
                dists[spec.name] = optuna.distributions.FloatDistribution(
                    spec.low, spec.high, step=spec.step)
            else:
                dists[spec.name] = optuna.distributions.FloatDistribution(spec.low, spec.high)
        elif spec.kind == "int":
            step = int(spec.step) if spec.step is not None else 1
            dists[spec.name] = optuna.distributions.IntDistribution(
                int(spec.low), int(spec.high), step=step)
        else:
            dists[spec.name] = optuna.distributions.CategoricalDistribution(spec.choices)
    return dists


# --- real server builds: nested basic/opt/synth parameterSchema ------------
# Two formats have been observed in the wild and BOTH must parse:
#
#   legacy (epcd-cli built ~2026-08-27): every bound/default/step is a string —
#     "None" = unbounded, "@0.25" = discrete step, comma-separated ``default``
#     = enumeration candidates, ``enabled`` = "1"/"0", ``suffix`` = "Equal".
#
#   current (epcd-cli 0.1.0 as of 2026-09): bounds are numeric
#     ``minimum``/``maximum``, discrete steps are JSON-Schema ``multipleOf``,
#     enable/lock are ``x-epcd-enabled`` / ``x-epcd-locked`` booleans,
#     categoricals use ``enum``, and objectives carry ``x-epcd-suffix``.
#
# The earlier parser only understood the legacy spelling, so against the
# current build it produced an EMPTY space and the caller fell back to
# describe() ``addinParams``. ``addinParams`` is the *panel* dump (shielding,
# metal fill, guard ring, pin geometry — offset/width/spacing/shape/...), NOT
# the template's optimization parameters. The optimizer therefore walked every
# low-level panel field while the server silently ran the default geometry.
# Only the template's ``parameterSchema`` opt group is authoritative.

_SUFFIX_TO_COMPARISON = {"Equal": "equal", "Greater": "greater-than", "Less": "less-than"}

_FALSY_STRINGS = frozenset(("", "0", "false", "none", "null"))
_TRUTHY_STRINGS = frozenset(("1", "true", "yes"))


def _to_bound(value) -> float | None:
    if value is None or str(value).strip() in ("", "None"):
        return None
    return float(value)


def _real_group(schema: dict, group: str) -> dict:
    properties = schema.get("properties") or {}
    node = properties.get(group) or {}
    return node.get("properties") or {}


def _is_enabled(prop: dict) -> bool:
    """True unless explicitly disabled (current ``x-epcd-enabled`` boolean or
    legacy ``enabled`` "1"/"0"); absent means enabled."""
    for key in ("x-epcd-enabled", "enabled"):
        value = prop.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in _FALSY_STRINGS
    return True


def _is_locked(prop: dict) -> bool:
    """True when ``x-epcd-locked`` (design-fixed → excluded from the opt space)."""
    value = prop.get("x-epcd-locked")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUTHY_STRINGS


def _step_or_multiple_of(prop: dict) -> float | None:
    """Discrete step from ``step`` (legacy "@0.5"/"0.5") or ``multipleOf``."""
    step_raw = str(prop.get("step") or "None").strip()
    if step_raw not in ("", "None"):
        return float(step_raw.lstrip("@"))
    multiple = _to_bound(prop.get("multipleOf"))
    return multiple if multiple is not None and multiple > 0 else None


# ---------------------------------------------------------------------------
# 跨参数几何约束（成对约束，模板元数据之外的控制侧硬规则）
# ---------------------------------------------------------------------------
# stack 家族（stack_inductor / stack_inductor_overlapped）是上下两层金属同心
# 堆叠：两层线圈宽度必须接近，否则几何无法闭合 → 服务端 GDS 生成报
# 「Layer1/Layer2 Width is too great, decrease the greater one or increase spacing」。
# 实测（2026-09-14，demo_revised.ptxt，真实 EM）：
#   |layer1Width - layer2Width| ≤ 3  → GDS 正常生成（18/15、18/16、18/18…全成功）
#   |layer1Width - layer2Width| ≥ 4  → GDS_NOT_FOUND（18/14、18/6、20/6、19/14…全失败）
# 且该阈值与 innerRadius（22~90）、numOfTurns（3~7）、trackSpace（0.85~4.5）无关，
# 是全局稳定约束。约束仅作用于含 layer1Width/layer2Width 参数对的模板（stack 家族）。

_STACK_LAYER_WIDTH_MAX_ABS_DIFF = 3.0
# 层宽差还应随 trackSpace 收紧：间距越小，两层层宽越需要接近，否则上下两层几何无法闭合。
# 实测（2026-09-14）：diff ≤ trackSpace 的 2 倍，是覆盖全部已知样本的安全界。
#   例：ts=0.73 时 diff=1.12 成功、diff=2.32 失败（2*0.73=1.46 恰在两者之间）。
_STACK_LAYER_DIFF_TO_SPACE_RATIO = 2.0


def stack_layer_width_violation(params: dict) -> tuple[str, str] | None:
    """Return (why, detail) when the stack layer-width pairing constraint is violated.

    Only fires when the candidate carries BOTH ``layer1Width`` and ``layer2Width``
    (stack family); other templates are unaffected. The stack geometry requires the
    two metal layers to be near-equal width — a difference of >= 4 um (or, more
    tightly, exceeding 2× the track space) makes the concentric two-layer winding
    non-manifold and fails GDS generation. The two conditions are independent:

      1. ``|layer1Width - layer2Width| > 3``            (absolute mismatch)
      2. ``|layer1Width - layer2Width| > 2 * trackSpace`` (spacing-relative mismatch)
    """
    if not isinstance(params, dict):
        return None
    if "layer1Width" not in params or "layer2Width" not in params:
        return None
    w1 = params.get("layer1Width")
    w2 = params.get("layer2Width")
    try:
        w1f = float(w1)
        w2f = float(w2)
    except (TypeError, ValueError):
        return None
    diff = abs(w1f - w2f)
    if diff > _STACK_LAYER_WIDTH_MAX_ABS_DIFF:
        return ("stack-layer-width-mismatch",
                f"|layer1Width - layer2Width| = {diff:.3f} > "
                f"{_STACK_LAYER_WIDTH_MAX_ABS_DIFF} (stack 两层层宽必须接近)")
    ts = params.get("trackSpace")
    try:
        tsf = float(ts)
    except (TypeError, ValueError):
        return None
    if tsf > 0 and diff > _STACK_LAYER_DIFF_TO_SPACE_RATIO * tsf:
        return ("stack-layer-width-mismatch",
                f"|layer1Width - layer2Width| = {diff:.3f} > "
                f"{_STACK_LAYER_DIFF_TO_SPACE_RATIO} * trackSpace = {_STACK_LAYER_DIFF_TO_SPACE_RATIO * tsf:.3f} "
                f"(间距过小时两层层宽需更接近)")
    return None


def parse_real_parameter_schema(schema: dict) -> ParsedSpace:
    """Parse the nested basic/opt/synth parameterSchema of real builds.

    Only the opt group feeds the optimization space; basic parameters are
    fixed at instantiation and synth parameters are design objectives (see
    parse_synth_targets). ``x-epcd-locked`` parameters are design-fixed and
    therefore excluded (e.g. adv_simple_inductor locks trackSpace).
    """
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter schema root must be an object schema")
    specs: list[ParamSpec] = []
    unbounded: list[str] = []
    for name, prop in _real_group(schema, "opt").items():
        if not isinstance(prop, dict) or not _is_enabled(prop) or _is_locked(prop):
            continue
        enum = prop.get("enum")
        if isinstance(enum, (list, tuple)) and len(enum) >= 2:
            specs.append(ParamSpec(name, "categorical",
                                   choices=tuple(str(x) for x in enum)))
            continue
        low, high = _to_bound(prop.get("minimum")), _to_bound(prop.get("maximum"))
        if low is None or high is None:
            if low is None and high is None:
                default = str(prop.get("default") or "")
                choices = tuple(p.strip() for p in default.split(",") if p.strip())
                if len(choices) >= 2:
                    specs.append(ParamSpec(name, "categorical", choices=choices))
                else:
                    unbounded.append(name)
            else:
                unbounded.append(name)
            continue
        specs.append(ParamSpec(name, "float", low=low, high=high,
                               step=_step_or_multiple_of(prop)))
    return ParsedSpace(specs=tuple(specs), unbounded=tuple(unbounded))


def parse_synth_targets(schema: dict) -> tuple[dict, ...]:
    """Default design objectives from the synth group (suffix + default)."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter schema root must be an object schema")
    targets: list[dict] = []
    for name, prop in _real_group(schema, "synth").items():
        if not isinstance(prop, dict) or not _is_enabled(prop):
            continue
        comparison = _SUFFIX_TO_COMPARISON.get(
            str(prop.get("x-epcd-suffix") or prop.get("suffix") or ""))
        target_value = _to_bound(prop.get("default"))
        if comparison is None or target_value is None:
            continue
        targets.append({"metric": name, "comparison": comparison,
                        "targetValue": target_value, "unit": ""})
    return tuple(targets)


# ---------------------------------------------------------------------------
# Real server builds (2026-08-27): parameterSchema/properties.{basic,opt,synth}
# come back EMPTY; the parameters live in describe.addinParams — a list of
# panel groups, each a list of paramItems with jsonKeyStr/min/max/stepValue/
# defValue/enableWhole/fieldType/visibleControlKey.  parse_real_parameter_schema
# can no longer drive the optimizer, so parse_addin_params is now the primary
# input source (see docs/inductor-delivery/optimizer-evaluation-20260827.md P0).
#
# fieldType semantics observed on simple_inductor (0.1.0):
#   0 = scalar number (min/max/stepValue bounded)      → float
#   3 = scalar number (bounded, "valueType":3 offset)  → float
#   1 = enum (defValue is comma-separated candidates)   → categorical
#   2 = switch/bool (enable noise, e.g. joinSimulation) → excluded
#   6 = layer multi-select (metal1,metal2)              → excluded
#   other/None = ambiguous                              → excluded
# Parameters gated by visibleControlKey (conditional visibility) are excluded
# so TPE never proposes combinations the panel would not surface.
# ---------------------------------------------------------------------------
_NUMERIC_FIELDTYPES = frozenset(map(str, (0, 3)))
_CATEGORICAL_FIELDTYPES = frozenset(map(str, (1,)))
_SKIP_FIELDTYPES = frozenset(map(str, (2, 6)))


def _addin_to_bound(value) -> float | None:
    if value is None or str(value).strip() in ("", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_addin_params(addin_params: Iterable[Iterable[dict]]) -> ParsedSpace:
    """Build the optimization space from describe().addinParams.

    The descriptor is a list of panel groups, each group a list of parameter
    items (jsonKeyStr/tagStr/min/max/stepValue/defValue/...).  Numeric params
    become float/int specs (step honored), enum params become categorical;
    bools, layer picks and conditionally-visible params are skipped.
    """
    specs: list[ParamSpec] = []
    seen: set[str] = set()
    for group in addin_params or []:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("jsonKeyStr") or "").strip()
            if not name or name in seen:
                continue
            if str(item.get("enableWhole", "1")) != "1":
                continue
            # skip parameters that only appear under some visibility condition
            vck = str(item.get("visibleControlKey") or "None")
            if vck != "None" and vck != name:
                continue
            ftype = str(item.get("fieldType") or "")
            if ftype in _SKIP_FIELDTYPES:
                continue
            is_num = ftype in _NUMERIC_FIELDTYPES
            is_cat = ftype in _CATEGORICAL_FIELDTYPES
            if not (is_num or is_cat):
                continue  # becomes treated as constant at run time
            low = _addin_to_bound(item.get("min"))
            high = _addin_to_bound(item.get("max"))
            if is_cat:
                default = str(item.get("defValue") or "")
                choices = tuple(
                    part for part in (p.strip() for p in default.split(",")) if part)
                if len(choices) >= 2:
                    specs.append(ParamSpec(name, "categorical", choices=choices))
                    seen.add(name)
                continue
            if low is None or high is None:
                continue
            step_raw = str(item.get("stepValue") or "None").strip()
            step = _addin_to_bound(step_raw) if step_raw not in ("", "None") else None
            specs.append(ParamSpec(name, "float", low=low, high=high, step=step))
            seen.add(name)
    return ParsedSpace(specs=tuple(specs), unbounded=())
