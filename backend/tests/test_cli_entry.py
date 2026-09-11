import json
import os

import pytest

from epcd_agent.cli import build_argv_prefix, main


def test_build_argv_prefix_local():
    assert build_argv_prefix() == ("epcd-cli",)


def test_build_argv_prefix_ssh_legacy_alias():
    # 只有 ssh 别名、无显式连接字段时：回退为 legacy——让 ssh 自己读本机 config 解析别名。
    prefix = build_argv_prefix(ssh_host="epcd-primary", pkg_root="/package/PKG")
    assert prefix == (
        "ssh", "-o", "BatchMode=yes", "epcd-primary",
        "source", "/package/PKG/user.bashrc.ePCD", ">/dev/null", "2>&1;",
        "[", "-f", "~/.epcd-env", "]", "&&", "source", "~/.epcd-env", ";",
        "epcd-cli")


def test_build_argv_prefix_ssh_explicit_connect():
    # 显式 host/user/port/identity_file：-F 指到 temp 目录下的 EPCD 自有空 config
    # （跳过系统/用户 config），连接参数全走 -o/-i，跨平台。
    import tempfile
    prefix = build_argv_prefix(
        ssh_host="epcd-primary", pkg_root="/package/PKG",
        host="192.168.20.243", user="zhubo", port="22",
        identity_file="~/.ssh/id_rsa_epcdB")
    # connect 部分：ssh -F <temp inline config> -o BatchMode=yes -o HostName=... -o User=... -o Port=... -i <key> <target>
    connect = prefix[:14]
    assert connect[0] == "ssh"
    assert connect[1] == "-F"
    assert connect[2] == os.path.join(tempfile.gettempdir(), "epcd-inline-ssh-config")
    assert connect[3:] == (
        "-o", "BatchMode=yes",
        "-o", "HostName=192.168.20.243",
        "-o", "User=zhubo",
        "-o", "Port=22",
        "-i", os.path.expanduser("~/.ssh/id_rsa_epcdB"),
        "epcd-primary")
    # source/pkg/cli_bin 尾巴不变
    assert prefix[14:] == (
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
