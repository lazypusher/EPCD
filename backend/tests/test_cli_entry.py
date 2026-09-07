import json

import pytest

from epcd_agent.cli import build_argv_prefix, main


def test_build_argv_prefix_local():
    assert build_argv_prefix() == ("epcd-cli",)


def test_build_argv_prefix_ssh():
    prefix = build_argv_prefix(ssh_host="zhubo@192.168.20.243", pkg_root="/package/PKG")
    assert prefix == (
        "ssh", "-o", "BatchMode=yes", "zhubo@192.168.20.243",
        "source", "/package/PKG/user.bashrc.ePCD", ">/dev/null", "2>&1;",
        "[", "-f", "~/.epcd-env", "]", "&&", "source", "~/.epcd-env", ";",
        "epcd-cli")


def test_unknown_tool_is_usage_error(tmp_path):
    code, out = main(["--db", str(tmp_path / "s.db"), "nope"], stdin_text="{}")
    assert code == 2
    assert json.loads(out)["error"]["type"] == "USAGE"


def test_invalid_stdin_json_is_usage_error(tmp_path):
    code, out = main(["--db", str(tmp_path / "s.db"), "epcd_health"], stdin_text="not json")
    assert code == 2


def test_ssh_without_pkg_is_usage_error(tmp_path):
    code, out = main(["--db", str(tmp_path / "s.db"), "--ssh", "h", "epcd_health"],
                     stdin_text="{}")
    assert code == 2


def test_tool_result_envelope_and_exit_code(tmp_path):
    # 注入假 ctx 工厂：返回 ok 的 ToolResult
    from epcd_agent.tools.base import ToolResult

    def fake_build_ctx(args):
        class _Ctx:  # 仅本测试使用
            session_id = "default"
        return _Ctx()

    def fake_health(ctx, **kwargs):
        return ToolResult(ok=True, data={"status": "ok"})

    code, out = main(["--db", str(tmp_path / "s.db"), "epcd_health"], stdin_text="{}",
                     build_ctx=fake_build_ctx,
                     registry_override={"epcd_health": fake_health})
    assert code == 0
    doc = json.loads(out)
    assert doc == {"ok": True, "data": {"status": "ok"}, "error": None}


def test_server_profile_resolves_ssh_pkg(tmp_path):
    from epcd_agent.tools.base import ToolResult

    servers = tmp_path / "servers.json"
    servers.write_text(json.dumps({
        "servers": {"s1": {"ssh": "myhost", "pkg": "/pkg/X"}}
    }), encoding="utf-8")
    seen = {}

    def fake_build_ctx(args):
        seen["ssh"] = args.ssh
        seen["pkg"] = args.pkg

        class _Ctx:
            session_id = "default"
        return _Ctx()

    def fake_health(ctx, **kwargs):
        return ToolResult(ok=True, data={"status": "ok"})

    code, out = main(["--servers-file", str(servers), "--server", "s1",
                      "--db", str(tmp_path / "s.db"), "epcd_health"], stdin_text="{}",
                     build_ctx=fake_build_ctx,
                     registry_override={"epcd_health": fake_health})
    assert code == 0
    assert seen["ssh"] == "myhost"
    assert seen["pkg"] == "/pkg/X"
    assert json.loads(out)["ok"] is True


def test_unknown_server_is_usage_error(tmp_path):
    servers = tmp_path / "servers.json"
    servers.write_text(json.dumps({"servers": {}}), encoding="utf-8")
    code, out = main(["--servers-file", str(servers), "--server", "nope",
                      "--db", str(tmp_path / "s.db"), "epcd_health"], stdin_text="{}")
    assert code == 2
    assert json.loads(out)["error"]["type"] == "USAGE"
