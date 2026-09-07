"""Full mock route set for the inductor acceptance scenario (spec section 1)."""
from __future__ import annotations

PARAM_SCHEMA = {
    "type": "object",
    "properties": {
        "width": {"type": "number", "minimum": 2.0, "maximum": 50.0},
        "numOfTurns": {"type": "integer", "minimum": 1, "maximum": 12},
    },
    "additionalProperties": False,
}

FINAL_ARTIFACTS = [
    {"type": "gds", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/layout.gds"},
    {"type": "gtxt", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/layout.gtxt"},
    {"type": "layout-preview-image", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/layout.png"},
    {"type": "snp", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/graphs.s2p"},
    {"type": "target-values", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/target-values.json"},
    {"type": "target-chart", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/target-chart.png"},
    {"type": "manifest", "path": "/abs/dev/.epcd-cli/runs/j-final/artifacts/manifest.json"},
]


def _ok(data):
    return {"exitCode": 0, "envelope": {
        "schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
        "data": data, "errors": []}}


def build_routes() -> list[dict]:
    return [
        {"argvPrefix": ["version"], "responses": [_ok({"version": "1.0.0"})]},
        {"argvPrefix": ["health"], "responses": [_ok({"status": "ok", "version": "1.0.0"})]},
        {"argvPrefix": ["project", "init"], "responses": [_ok({
            "created": True, "project": "/abs/proj", "libName": "demo_project",
            "technologyPath": "/abs/proj/technology/process.ptxt",
            "technologyDigest": "sha256:tech", "technologyCopied": True, "warnings": []})]},
        {"argvPrefix": ["project", "describe"], "responses": [_ok({"project": "/abs/proj"})]},
        {"argvPrefix": ["project", "validate"], "responses": [_ok({"valid": True})]},
        {"argvPrefix": ["device-template", "list"], "responses": [_ok({
            "templates": [{"templateId": "system.inductor.simple_inductor",
                           "category": "inductor", "name": "simple_inductor"}]})]},
        {"argvPrefix": ["device-template", "describe"], "responses": [_ok({
            "templateId": "system.inductor.simple_inductor", "namespace": "system",
            "category": "inductor", "name": "simple_inductor", "available": True,
            "parameterSchema": PARAM_SCHEMA, "builtInMetrics": ["L", "Q"],
            "previewArtifacts": []})]},
        {"argvPrefix": ["project", "device", "add"], "responses": [_ok({
            "created": True, "project": "/abs/proj", "instanceId": "m-1",
            "name": "simple_inductor1", "folderName": "simple_inductor1",
            "templateId": "system.inductor.simple_inductor", "warnings": []})]},
        {"argvPrefix": ["config", "schema"], "responses": [_ok({
            "project": "/abs/proj", "instanceId": "m-1",
            "templateId": "system.inductor.simple_inductor",
            "schemaVersion": "epcd-device-schema/v1", "path": "/device/parameters",
            "schema": PARAM_SCHEMA, "schemaDigest": "sha256:schema"})]},
        {"argvPrefix": ["config", "get"], "responses": [
            _ok({"project": "/abs/proj", "instanceId": "m-1", "path": None,
                 "value": {}, "configDigest": "sha256:d0"}),       # step 4.6
            _ok({"project": "/abs/proj", "instanceId": "m-1", "path": None,
                 "value": {}, "configDigest": "sha256:d1"}),       # refresh before simulation patch
        ]},
        {"argvPrefix": ["config", "patch"], "responses": [
            _ok({"changed": True, "configDigest": "sha256:d1"}),   # synthesisTargets
            _ok({"changed": True, "configDigest": "sha256:d2"}),   # simulation
        ]},
        {"argvPrefix": ["config", "apply-result"], "responses": [
            _ok({"applied": True, "configDigest": "sha256:post"})]},
        {"argvPrefix": ["run"], "responses": [
            _ok({"jobId": "j-preview", "requestId": "preview-001",
                 "taskType": "gds-generation", "status": "succeeded",
                 "artifacts": [{"type": "gds", "path": "/abs/p.gds"},
                               {"type": "gtxt", "path": "/abs/p.gtxt"},
                               {"type": "layout-preview-image", "path": "/abs/p.png"},
                               {"type": "manifest", "path": "/abs/m.json"}]}),
            _ok({"jobId": "j-1", "requestId": "iteration-1",
                 "taskType": "simulation-evaluation", "status": "queued",
                 "configDigestUsed": "sha256:d2"}),
            _ok({"jobId": "j-2", "requestId": "iteration-2",
                 "taskType": "simulation-evaluation", "status": "queued",
                 "configDigestUsed": "sha256:d2"}),
            _ok({"jobId": "j-final", "requestId": "final-j-2",
                 "taskType": "simulation-evaluation", "status": "succeeded",
                 "configDigestUsed": "sha256:post",
                 "artifacts": FINAL_ARTIFACTS,
                 "publication": {"directory": "/abs/dev/synthesis/RangeEM",
                                 "artifacts": [{"type": "snp", "path": "/abs/dev/synthesis/RangeEM/graphs.s2p"},
                                               {"type": "gds", "path": "/abs/dev/synthesis/RangeEM/run.gds"}]}}),
        ]},
        {"argvPrefix": ["job", "get"], "responses": [
            _ok({"jobId": "j-1", "status": "succeeded"}),
            _ok({"jobId": "j-2", "status": "succeeded"}),
        ]},
        {"argvPrefix": ["job", "result"], "responses": [
            _ok({"jobId": "j-1", "taskType": "simulation-evaluation", "status": "succeeded",
                 "objectiveCost": 0.6, "targetValues": [
                     {"metric": "L", "actualValue": 8.1, "targetValue": 10, "satisfied": False,
                      "relativeDeviation": 0.19, "objectiveCost": 0.6}],
                 "warnings": [], "artifacts": [], "logFile": "/abs/j-1.log"}),
            _ok({"jobId": "j-2", "taskType": "simulation-evaluation", "status": "succeeded",
                 "objectiveCost": 0.18, "targetValues": [
                     {"metric": "L", "actualValue": 9.9, "targetValue": 10, "satisfied": True,
                      "relativeDeviation": 0.01, "objectiveCost": 0.08},
                     {"metric": "Q", "actualValue": 22.0, "targetValue": 20, "satisfied": True,
                      "relativeDeviation": 0.0, "objectiveCost": 0.1}],
                 "warnings": [], "artifacts": [], "logFile": "/abs/j-2.log"}),
            # best-job result fetched for the M3 confirmation payload:
            _ok({"jobId": "j-2", "taskType": "simulation-evaluation", "status": "succeeded",
                 "objectiveCost": 0.18, "targetValues": [], "warnings": [], "artifacts": []}),
        ]},
    ]
