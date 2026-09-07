import pytest

from epcd_agent.exitcodes import LOOP_TRANSIENT_EXIT_CODES, classify_exit


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "success"),
        (2, "agent_retryable"),
        (3, "agent_retryable"),
        (4, "agent_retryable"),
        (5, "needs_decision"),
        (6, "blocking"),
        (7, "blocking"),
        (8, "transient"),
        (9, "transient"),
        (10, "canceled"),
        (11, "request_id_conflict"),
        (1, "unknown"),
        (99, "unknown"),
        (-1, "unknown"),
    ],
)
def test_classify_exit(code, expected):
    assert classify_exit(code) == expected


def test_loop_transient_set():
    # design doc section 7.3: within the optimization loop,
    # exit codes 7/8/9 are retried once with the same requestId.
    assert LOOP_TRANSIENT_EXIT_CODES == frozenset({7, 8, 9})
