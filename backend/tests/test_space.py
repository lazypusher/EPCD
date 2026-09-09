import optuna
import pytest

from epcd_agent.optimizer.space import (
    ParamSpec,
    parse_addin_params,
    parse_parameter_schema,
    parse_real_parameter_schema,
    parse_synth_targets,
    normalize_candidate,
    to_optuna_distributions,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "width": {"type": "number", "minimum": 2.0, "maximum": 50.0},
        "numOfTurns": {"type": "integer", "minimum": 1, "maximum": 12, "step": 1},
        "shape": {"type": "string", "enum": ["square", "octagon"]},
        "innerRadius": {"type": "number"},
        "numOfSlots": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}


def test_parse_parameter_schema():
    space = parse_parameter_schema(SCHEMA)
    by_name = {s.name: s for s in space.specs}
    assert by_name["width"] == ParamSpec("width", "float", low=2.0, high=50.0)
    assert by_name["numOfTurns"] == ParamSpec("numOfTurns", "int", low=1, high=12, step=1)
    assert by_name["shape"] == ParamSpec("shape", "categorical", choices=("square", "octagon"))
    # unbounded: no bounds at all, or only one bound present
    assert set(space.unbounded) == {"innerRadius", "numOfSlots"}


def test_parse_rejects_non_object_root():
    with pytest.raises(ValueError):
        parse_parameter_schema({"type": "array"})


def test_normalize_candidate_clips_and_filters():
    space = parse_parameter_schema(SCHEMA)
    out = normalize_candidate({"width": 999, "numOfTurns": -3, "shape": "square", "bogus": 1},
                              space.specs)
    assert out == {"width": 50.0, "numOfTurns": 1, "shape": "square"}


def test_normalize_candidate_rejects_unknown_choice():
    space = parse_parameter_schema(SCHEMA)
    with pytest.raises(ValueError):
        normalize_candidate({"shape": "triangle"}, space.specs)


def test_to_optuna_distributions():
    space = parse_parameter_schema(SCHEMA)
    dists = to_optuna_distributions(space.specs)
    assert isinstance(dists["width"], optuna.distributions.FloatDistribution)
    assert dists["width"].low == 2.0 and dists["width"].high == 50.0
    assert isinstance(dists["numOfTurns"], optuna.distributions.IntDistribution)
    assert dists["numOfTurns"].step == 1
    assert isinstance(dists["shape"], optuna.distributions.CategoricalDistribution)
    assert dists["shape"].choices == ("square", "octagon")


# --- real server build shapes (release doc section 4.3 corrected) ----------

REAL_SCHEMA = {
    "type": "object",
    "properties": {
        "basic": {"type": "object", "properties": {
            "shape": {"default": "Rectangular,Hexagonal,Octagonal,Circular,",
                      "minimum": "None", "maximum": "None", "step": "None", "enabled": "1"},
        }},
        "opt": {"type": "object", "properties": {
            "trackWidth": {"minimum": "6.0", "maximum": "20.0", "step": "None", "enabled": "1"},
            "numOfTurns": {"minimum": "0.25", "maximum": "8.0", "step": "@0.25", "enabled": "1"},
            "innerRadius": {"minimum": "None", "maximum": "None", "step": "None", "enabled": "1"},
            "shape": {"default": "Rectangular,Circular,",
                      "minimum": "None", "maximum": "None", "step": "None", "enabled": "1"},
        }},
        "synth": {"type": "object", "properties": {
            "inductance": {"default": "2.1", "minimum": "None", "maximum": "None",
                           "step": "None", "suffix": "Equal", "enabled": "1"},
            "minQFactor": {"default": "8", "minimum": "None", "maximum": "None",
                           "step": "None", "suffix": "Greater", "enabled": "1"},
            "maxSize": {"default": "300", "minimum": "None", "maximum": "None",
                        "step": "None", "suffix": "Less", "enabled": "1"},
        }},
    },
}


def test_parse_real_schema_opt_space():
    space = parse_real_parameter_schema(REAL_SCHEMA)
    by = {s.name: s for s in space.specs}
    assert set(by) == {"trackWidth", "numOfTurns", "shape"}
    assert by["trackWidth"].kind == "float"
    assert by["trackWidth"].low == 6.0 and by["trackWidth"].high == 20.0
    assert by["trackWidth"].step is None
    assert by["numOfTurns"].step == 0.25
    assert by["shape"].kind == "categorical"
    assert by["shape"].choices == ("Rectangular", "Circular")
    assert space.unbounded == ("innerRadius",)


def test_parse_real_schema_disabled_param_skipped():
    schema = {"type": "object", "properties": {"opt": {"type": "object", "properties": {
        "w": {"minimum": "1", "maximum": "2", "step": "None", "enabled": "0"}}}}}
    assert parse_real_parameter_schema(schema).specs == ()


def test_parse_synth_targets_from_real_schema():
    targets = parse_synth_targets(REAL_SCHEMA)
    assert targets == (
        {"metric": "inductance", "comparison": "equal", "targetValue": 2.1, "unit": ""},
        {"metric": "minQFactor", "comparison": "greater-than", "targetValue": 8.0, "unit": ""},
        {"metric": "maxSize", "comparison": "less-than", "targetValue": 300.0, "unit": ""},
    )


def test_parse_real_schema_rejects_non_object_root():
    with pytest.raises(ValueError):
        parse_real_parameter_schema({"properties": {}})


# --- current build (epcd-cli 0.1.0 as of 2026-09): numeric bounds -----------
# The old parser only understood the legacy string spelling; the current build
# uses numeric minimum/maximum, ``multipleOf`` for the discrete step, and
# ``x-epcd-enabled``/``x-epcd-locked`` booleans. Errors here caused the
# optimizer to fall back to describe().addinParams (the panel dump).

CURRENT_SCHEMA = {
    "type": "object",
    "properties": {
        "basic": {"type": "object", "properties": {
            "layer": {"type": "string", "enum": ["metal1", "metal2"],
                      "x-epcd-enabled": True},
        }},
        "opt": {"type": "object", "properties": {
            "trackWidth": {"type": "number", "default": 10.0, "minimum": 6.0,
                           "maximum": 20.0, "x-epcd-enabled": True,
                           "x-epcd-locked": False},
            "trackSpace": {"type": "number", "default": 2.0, "minimum": 1.5,
                           "maximum": 5.0, "x-epcd-enabled": True,
                           "x-epcd-locked": True},
            "numOfTurns": {"type": "number", "default": 2.5, "minimum": 0.5,
                           "maximum": 8.0, "multipleOf": 0.5,
                           "x-epcd-enabled": True, "x-epcd-locked": False},
            "innerRadius": {"type": "number", "default": 60.0, "minimum": 20.0,
                            "maximum": 80.0, "x-epcd-enabled": True,
                            "x-epcd-locked": False},
        }},
        "synth": {"type": "object", "properties": {
            "inductance": {"type": "number", "default": 2.1, "x-epcd-suffix": "Equal",
                           "x-epcd-enabled": True},
            "minQFactor": {"type": "number", "default": 8.0, "x-epcd-suffix": "Greater",
                           "x-epcd-enabled": True},
            "maxSize": {"type": "number", "default": 300.0, "x-epcd-suffix": "Less",
                        "x-epcd-enabled": True},
        }},
    },
}


def test_parse_real_schema_current_build_format():
    space = parse_real_parameter_schema(CURRENT_SCHEMA)
    by = {s.name: s for s in space.specs}
    # x-epcd-locked trackSpace is design-fixed → excluded from the opt space
    assert set(by) == {"trackWidth", "numOfTurns", "innerRadius"}
    assert by["trackWidth"].kind == "float"
    assert (by["trackWidth"].low, by["trackWidth"].high) == (6.0, 20.0)
    # multipleOf drives the discrete step in the current build
    assert by["numOfTurns"].step == 0.5
    assert (by["innerRadius"].low, by["innerRadius"].high) == (20.0, 80.0)
    assert space.unbounded == ()


def test_parse_synth_targets_current_build_format():
    targets = parse_synth_targets(CURRENT_SCHEMA)
    assert targets == (
        {"metric": "inductance", "comparison": "equal", "targetValue": 2.1, "unit": ""},
        {"metric": "minQFactor", "comparison": "greater-than", "targetValue": 8.0, "unit": ""},
        {"metric": "maxSize", "comparison": "less-than", "targetValue": 300.0, "unit": ""},
    )


# --- describe().addinParams (2026-08-27 builds): optimizer-eval P0 -----------
# fieldType semantics: 0/3 numeric scalar, 1 enum, 2 switch, 6 layer multi-select.
# visibleControlKey != "None" means the parameter only appears under a condition
# (we exclude those so TPE never proposes a panel-invisible combination).
REAL_ADDIN = [
    [
        {"jsonKeyStr": "joinSimulation", "fieldType": "2", "enableWhole": "1",
         "defValue": "0", "min": "None", "max": "None", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "aspectRatio", "fieldType": "0", "enableWhole": "1",
         "defValue": "1", "min": "0.1", "max": "10.0", "stepValue": "None",
         "visibleControlKey": "shape"},
        {"jsonKeyStr": "offset", "fieldType": "0", "enableWhole": "1",
         "defValue": "0", "min": "-100.0", "max": "100.0", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "layer", "fieldType": "6", "enableWhole": "1",
         "defValue": "metal1,metal2,", "min": "None", "max": "None",
         "stepValue": "None", "visibleControlKey": "None"},
        {"jsonKeyStr": "width", "fieldType": "0", "enableWhole": "1",
         "defValue": "1", "min": "0.2", "max": "10.0", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "spacing", "fieldType": "0", "enableWhole": "1",
         "defValue": "1", "min": "0.2", "max": "10.0", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "shape", "fieldType": "1", "enableWhole": "1",
         "defValue": "Rectangular,Octagonal,Circular,", "min": "None",
         "max": "None", "stepValue": "None", "visibleControlKey": "None"},
        {"jsonKeyStr": "pinWidth", "fieldType": "0", "enableWhole": "1",
         "defValue": "1", "min": "0.05", "max": "10.0", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "pinExt", "fieldType": "3", "enableWhole": "1",
         "defValue": "0", "min": "0.0", "max": "100.0", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "pinDir", "fieldType": "1", "enableWhole": "1",
         "defValue": "top,bottom,right,left,", "min": "None", "max": "None",
         "stepValue": "None", "visibleControlKey": "None"},
        {"jsonKeyStr": "rotation", "fieldType": "1", "enableWhole": "1",
         "defValue": "0,90,", "min": "None", "max": "None", "stepValue": "None",
         "visibleControlKey": "None"},
        {"jsonKeyStr": "port", "fieldType": "0", "enableWhole": "1",
         "defValue": "GND", "value": "GND", "min": "None", "max": "None",
         "stepValue": "None", "visibleControlKey": "None"},
        {"jsonKeyStr": "withPort", "fieldType": "2", "enableWhole": "1",
         "defValue": "1", "min": "None", "max": "None", "stepValue": "None",
         "visibleControlKey": "None"},
    ],
]


def test_parse_addin_params_real_shape():
    space = parse_addin_params(REAL_ADDIN)
    by = {s.name: s for s in space.specs}
    assert by["width"].kind == "float"
    assert (by["width"].low, by["width"].high) == (0.2, 10.0)
    assert by["width"].step is None
    assert by["offset"].low == -100.0
    assert by["pinExt"].kind == "float"  # fieldType 3 is numeric too
    # enum (fieldType 1) from comma-separated defValue
    assert by["shape"].kind == "categorical"
    assert by["shape"].choices == ("Rectangular", "Octagonal", "Circular")
    assert by["pinDir"].choices == ("top", "bottom", "right", "left")
    assert by["rotation"].choices == ("0", "90")
    # excluded: switches (2), layer picks (6), conditionally-visible (aspectRatio),
    #           non-numeric scalar without bounds (port), disabled params
    for name in ("joinSimulation", "layer", "aspectRatio", "port", "withPort"):
        assert name not in by, name


def test_parse_addin_params_skips_disabled_and_conditional():
    ap = [[
        {"jsonKeyStr": "w", "fieldType": "0", "enableWhole": "0",
         "min": "1", "max": "9", "stepValue": "None", "visibleControlKey": "None"},
        {"jsonKeyStr": "x", "fieldType": "0", "enableWhole": "1",
         "min": "1", "max": "9", "stepValue": "None", "visibleControlKey": "x"},
        {"jsonKeyStr": "y", "fieldType": "0", "enableWhole": "1",
         "min": "1", "max": "9", "stepValue": "None", "visibleControlKey": "other"},
        {"jsonKeyStr": "z", "fieldType": "0", "enableWhole": "1",
         "min": "1", "max": "9", "stepValue": "0.25", "visibleControlKey": "None"},
    ]]
    space = parse_addin_params(ap)
    by = {s.name: s for s in space.specs}
    assert set(by) == {"x", "z"}  # w disabled, y conditionally visible
    assert by["z"].step == 0.25


def test_parse_addin_params_edge_inputs():
    assert parse_addin_params(None).specs == ()
    assert parse_addin_params([]).specs == ()
    assert parse_addin_params([[None, "junk"]]).specs == ()


def test_parse_addin_params_deduplicates_across_groups():
    ap = [[{"jsonKeyStr": "w", "fieldType": "0", "enableWhole": "1",
            "min": "1", "max": "2", "stepValue": "None", "visibleControlKey": "None"}],
          [{"jsonKeyStr": "w", "fieldType": "0", "enableWhole": "1",
            "min": "5", "max": "9", "stepValue": "None", "visibleControlKey": "None"}]]
    space = parse_addin_params(ap)
    assert len(space.specs) == 1
    assert (space.specs[0].low, space.specs[0].high) == (1, 2)  # first wins


def test_normalize_candidate_aligns_to_step():
    """P2: off-grid float candidates snap to the step grid before clipping."""
    specs = (ParamSpec("turns", "float", low=0.25, high=8.0, step=0.25),
             ParamSpec("w", "float", low=1.0, high=9.0, step=None))
    assert normalize_candidate({"turns": 3.17, "w": 4.6}, specs) == {"turns": 3.25, "w": 4.6}
    assert normalize_candidate({"turns": 0.0}, specs) == {"turns": 0.25}  # clipped back in
    assert normalize_candidate({"turns": 9.0}, specs) == {"turns": 8.0}   # clipped at high
