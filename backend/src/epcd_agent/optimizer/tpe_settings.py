"""Per-template TPE optimizer settings (auto-config source).

Single source of truth for mapping ``template_id`` -> TPE ``startup_trials`` /
recommended ``max_rounds``. This module ships inside the package so the
production optimizer can resolve settings without reaching outside the source
tree (the skill-side ``references/tpe-settings.toml`` is documentation only and
must stay in sync with this table, not the other way around).

Evidence base: 9 templates x startup_trials[3,5,10] x 20 rounds = 540 real EM
runs (2026-09-03). Two-band classification, per the current toml:

  * band "5"  (startup_trials=5,  max_rounds=15)\u2014easy/fast-converging templates
  * band "10" (startup_trials=10, max_rounds=20)\u2014hard templates (stack family,
    small valid-geometry domain, tcoil_oct) needing more exploration budget

Mechanism note (TPE): ``n_startup_trials`` controls how many leading rounds
sample pseudo-randomly WITHOUT consuming observed costs before TPE starts the
good/bad split. 5 leaves a 2-point "good" group (gamma*5) instead of the
degenerate 1-point group at 3, while 10 stays well below Optuna's default only
when the budget is tight; hard templates get 10 for a wider exploration front.

Resolution priority (applied in ``optimize_tools.optimization_start``):
  explicit caller arg > per-template table > built-in default (5 / 15).
"""

from __future__ import annotations

# Built-in fallbacks when neither the caller nor the table specifies a value.
DEFAULT_STARTUP_TRIALS = 5
DEFAULT_MAX_ROUNDS = 15

# template_id -> (startup_trials, max_rounds). Band boundaries mirror
# references/tpe-settings.toml (two-band classification).
_TPE_TABLE: dict[str, tuple[int, int]] = {
    # ── band 5 / 15 ────────────────────────────────────────────────────────
    "system.inductor.simple_inductor": (5, 15),
    "system.inductor.adv_simple_inductor": (5, 15),
    "system.inductor.bowtie_inductor": (5, 10),
    "system.tcoil.tcoil_inductor_rec": (5, 15),
    # ── band 10 / 20 ──────────────────────────────────────────────────────
    "system.inductor.stack_inductor": (10, 20),
    "system.inductor.differential_inductor": (10, 20),
    "system.inductor.differential_inductor_step": (10, 20),
    "system.inductor.stack_inductor_overlapped": (10, 20),
    "system.tcoil.tcoil_inductor_oct": (10, 20),
}


def template_tpe_settings(template_id: str | None) -> dict[str, int] | None:
    """Return ``{"startup_trials": int, "max_rounds": int}`` for a template.

    ``None`` when the template is unknown \u2014 the caller then falls back to the
    built-in defaults (DEFAULT_STARTUP_TRIALS / DEFAULT_MAX_ROUNDS).
    """
    if not template_id:
        return None
    pair = _TPE_TABLE.get(str(template_id))
    if pair is None:
        return None
    return {"startup_trials": pair[0], "max_rounds": pair[1]}