"""epcd-response/v1 envelope parsing (release doc section 2)."""
from __future__ import annotations

import json
from dataclasses import dataclass

ENVELOPE_SCHEMA = "epcd-response/v1"


class EnvelopeParseError(Exception):
    """stdout is not a valid epcd-response/v1 envelope."""


@dataclass(frozen=True)
class EpcdErrorItem:
    code: str
    path: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class EpcdResponse:
    schema_version: str
    ok: bool
    request_id: str | None = None
    data: dict | None = None
    errors: tuple[EpcdErrorItem, ...] = ()

    def error_codes(self) -> list[str]:
        return [e.code for e in self.errors]

    def has_error_code(self, code: str) -> bool:
        return any(e.code == code for e in self.errors)


def parse_envelope(stdout: str) -> EpcdResponse:
    text = stdout.strip()
    if not text:
        raise EnvelopeParseError("empty stdout: no envelope")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        # Observed server builds leak solver warnings to stdout before the
        # envelope. Recover by parsing from the first "{".
        start = text.find("{")
        if start < 0:
            raise EnvelopeParseError("stdout is not JSON: no envelope object found")
        try:
            doc = json.loads(text[start:])
        except json.JSONDecodeError as exc:
            raise EnvelopeParseError(f"stdout is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise EnvelopeParseError("envelope root must be a JSON object")
    schema = doc.get("schemaVersion")
    if schema != ENVELOPE_SCHEMA:
        raise EnvelopeParseError(f"unexpected schemaVersion: {schema!r}")
    if not isinstance(doc.get("ok"), bool):
        raise EnvelopeParseError("envelope.ok missing or not a boolean")
    errors_raw = doc.get("errors") or []
    if not isinstance(errors_raw, list):
        raise EnvelopeParseError("envelope.errors must be a list")
    errors = tuple(
        EpcdErrorItem(code=str(item.get("code")), path=item.get("path"), message=item.get("message"))
        for item in errors_raw
    )
    data = doc.get("data")
    if data is not None and not isinstance(data, dict):
        raise EnvelopeParseError("envelope.data must be an object or null")
    return EpcdResponse(
        schema_version=schema,
        ok=doc["ok"],
        request_id=doc.get("requestId"),
        data=data,
        errors=errors,
    )
