"""Exit-code routing (design doc section 10, release doc section 2)."""
from __future__ import annotations

SUCCESS = 0

_CATEGORIES: dict[int, str] = {
    0: "success",
    2: "agent_retryable",    # command argument error: agent fixes input and retries
    3: "agent_retryable",    # JSON/YAML input format error
    4: "agent_retryable",    # schema validation error
    5: "needs_decision",     # business rule error: escalate to user decision
    6: "blocking",           # technology error
    7: "blocking",           # license unavailable: blocking at conversation layer
    8: "transient",          # GDS/simulation execution failure
    9: "transient",          # result write failure
    10: "canceled",
    11: "request_id_conflict",
}

# Within the optimization loop (design doc section 7.3) exit codes 7/8/9 are
# all treated as transient: retry once with the identical requestId.
LOOP_TRANSIENT_EXIT_CODES = frozenset({7, 8, 9})


def classify_exit(exit_code: int) -> str:
    return _CATEGORIES.get(exit_code, "unknown")
