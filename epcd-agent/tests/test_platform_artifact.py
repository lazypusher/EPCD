import base64
import pathlib

import mock_cli

from epcd_agent.platform.artifact_view import artifact_view, build_artifact_cards
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext

RESULT_ENVELOPE = {"schemaVersion": "epcd-response/v1", "ok": True, "requestId": None,
                   "data": {"jobId": "j-1", "artifacts": [
                       {"type": "gds", "path": "/abs/proj/out/L1.gds"},
                       {"type": "layout-preview-image", "path": "/abs/proj/out/L1.png"},
                   ]}, "errors": []}


def test_build_cards_titles_and_paths():
    cards = build_artifact_cards(RESULT_ENVELOPE["data"])
    assert cards == [
        {"type": "gds", "title": "GDS", "remotePath": "/abs/proj/out/L1.gds", "localPath": None},
        {"type": "layout-preview-image", "title": "Layout preview",
         "remotePath": "/abs/proj/out/L1.png", "localPath": None},
    ]


def test_artifact_view_local_copy(tmp_path):
    src = tmp_path / "L1.gds"
    src.write_bytes(b"GDSDATA")
    cli, _ = mock_cli.make_cli(tmp_path, [
        {"argvPrefix": ["job", "result"], "responses": [
            {"exitCode": 0, "envelope": {"schemaVersion": "epcd-response/v1", "ok": True,
             "requestId": None, "data": {"jobId": "j-1", "artifacts": [
                 {"type": "gds", "path": str(src)}]}, "errors": []}}]}])
    store = SessionStore(tmp_path / "store.sqlite3")
    store.create_session("s1")
    ctx = ToolContext(cli=cli, store=store, session_id="s1")
    fetch = tmp_path / "cache"
    r = artifact_view(ctx, "j-1", fetch_dir=str(fetch))
    assert r.ok is True
    card = r.data["cards"][0]
    assert pathlib.Path(card["localPath"]).read_bytes() == b"GDSDATA"
