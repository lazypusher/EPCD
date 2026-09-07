import json

import pytest

from epcd_agent.envelope import (
    EnvelopeParseError,
    EpcdResponse,
    parse_envelope,
)

OK_ENVELOPE = {
    "schemaVersion": "epcd-response/v1",
    "ok": True,
    "requestId": None,
    "data": {"created": True},
    "errors": [],
}


def test_parse_success_envelope():
    resp = parse_envelope(json.dumps(OK_ENVELOPE))
    assert isinstance(resp, EpcdResponse)
    assert resp.schema_version == "epcd-response/v1"
    assert resp.ok is True
    assert resp.request_id is None
    assert resp.data == {"created": True}
    assert resp.errors == ()


def test_parse_failure_envelope_with_errors():
    doc = dict(
        OK_ENVELOPE,
        ok=False,
        data=None,
        errors=[
            {"code": "CONFIG_DIGEST_MISMATCH", "path": "/device", "message": "digest mismatch"},
            {"code": "OTHER", "path": None, "message": None},
        ],
    )
    resp = parse_envelope(json.dumps(doc))
    assert resp.ok is False
    assert resp.data is None
    assert resp.error_codes() == ["CONFIG_DIGEST_MISMATCH", "OTHER"]
    assert resp.has_error_code("CONFIG_DIGEST_MISMATCH") is True
    assert resp.has_error_code("NOPE") is False
    assert resp.errors[0].path == "/device"
    assert resp.errors[0].message == "digest mismatch"


def test_parse_tolerates_surrounding_whitespace():
    resp = parse_envelope("  " + json.dumps(OK_ENVELOPE) + "\n")
    assert resp.ok is True


def test_parse_tolerates_warning_preamble_before_envelope():
    # Observed on real server builds: solver warnings leak to stdout ahead of
    # the JSON envelope (e.g. device-template describe).
    noisy = (
        "Warning:layerUnderPath initialized with invalid valueIndex...\n"
        "Warning:groundLayer initialized with invalid valueIndex...\n"
        + json.dumps(OK_ENVELOPE)
    )
    resp = parse_envelope(noisy)
    assert resp.ok is True
    assert resp.data == {"created": True}


def test_parse_rejects_preamble_without_envelope():
    with pytest.raises(EnvelopeParseError):
        parse_envelope("Warning: something broke\nstill no json here")


@pytest.mark.parametrize(
    "bad_stdout",
    [
        "",                                   # 空输出
        "not json at all",                    # 非 JSON
        "[1, 2, 3]",                          # 根不是对象
        json.dumps({"ok": True}),             # 缺 schemaVersion
        json.dumps(dict(OK_ENVELOPE, schemaVersion="epcd-response/v2")),  # 版本不符
        json.dumps(dict(OK_ENVELOPE, ok="yes")),                          # ok 非布尔
        json.dumps(dict(OK_ENVELOPE, errors={"code": "X"})),              # errors 非列表
        json.dumps(dict(OK_ENVELOPE, data="plain")),                      # data 非对象
    ],
)
def test_parse_rejects_invalid_envelope(bad_stdout):
    with pytest.raises(EnvelopeParseError):
        parse_envelope(bad_stdout)
