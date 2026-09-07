"""epcd-cli subprocess wrapper (release doc section 2 calling conventions)."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Sequence

from .envelope import EnvelopeParseError, EpcdResponse, parse_envelope


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    response: EpcdResponse | None
    stdout: str
    stderr: str
    timed_out: bool = False
    parse_error: str | None = None


def _as_text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


class EpcdCli:
    """Runs epcd-cli as a subprocess.

    argv_prefix lets tests point the client at the mock
    (e.g. (sys.executable, "tests/mock_cli.py")).
    """

    def __init__(self, argv_prefix: Sequence[str] = ("epcd-cli",), default_timeout: float = 120.0):
        self.argv_prefix = tuple(argv_prefix)
        self.default_timeout = default_timeout

    def exec(
        self,
        args: Sequence[str],
        stdin_obj: Any = None,
        timeout: float | None = None,
    ) -> ExecResult:
        argv = list(self.argv_prefix) + list(args)
        stdin_bytes = (
            json.dumps(stdin_obj, ensure_ascii=False).encode("utf-8")
            if stdin_obj is not None
            else None
        )
        effective_timeout = timeout if timeout is not None else self.default_timeout
        try:
            proc = subprocess.run(argv, input=stdin_bytes, capture_output=True, timeout=effective_timeout)
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                exit_code=-1,
                response=None,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                timed_out=True,
            )
        except OSError as exc:
            # Missing/unexecutable binary (e.g. epcd-cli not on PATH): report
            # a structured failure like timeout instead of raising, so the CLI
            # entry keeps its one-line-envelope discipline.
            return ExecResult(
                exit_code=-1,
                response=None,
                stdout="",
                stderr=f"exec failed: {exc}",
            )
        stdout = _as_text(proc.stdout)
        stderr = _as_text(proc.stderr)
        try:
            response: EpcdResponse | None = parse_envelope(stdout)
            parse_error = None
        except EnvelopeParseError as exc:
            response, parse_error = None, str(exc)
        return ExecResult(
            exit_code=proc.returncode,
            response=response,
            stdout=stdout,
            stderr=stderr,
            parse_error=parse_error,
        )
