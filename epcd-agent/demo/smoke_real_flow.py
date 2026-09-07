"""Real-environment flow test: our tool layer over ssh against actual epcd-cli.

Exercises EpcdCli + SessionStore + tool functions (health / project init /
describe / validate / device-template list) using the package environment
sourced inside the remote shell. The remote command is assembled from plain
argv tokens (ssh joins them with spaces), so argument values must not contain
spaces or shell metacharacters.

    ./.venv/Scripts/python demo/smoke_real_flow.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epcd_agent.cli_client import EpcdCli
from epcd_agent.store import SessionStore
from epcd_agent.tools.base import ToolContext
from epcd_agent.tools.read import epcd_health, epcd_template
from epcd_agent.tools.write import epcd_project

PKG = ("/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-"
       "NINECUBE-2026-08-07-linux-x86-64-default")
HOST = "zhubo@192.168.20.243"
TECH = f"{PKG}/tutorial/command_use/transmission_line/demo.ptxt"
WORK_DIR = "/home/zhubo/epcd-agent-smoke"

# source the package env, then run epcd-cli — all as argv tokens; ssh joins
# them into one remote shell line: "source ... >/dev/null 2>&1; epcd-cli ..."
cli = EpcdCli(argv_prefix=("ssh", "-o", "BatchMode=yes", HOST,
                           "source", f"{PKG}/user.bashrc.ePCD",
                           ">/dev/null", "2>&1;", "epcd-cli"),
              default_timeout=180.0)
store = SessionStore(Path(tempfile.mkdtemp()) / "store.sqlite3")
store.create_session("s1")
ctx = ToolContext(cli=cli, store=store, session_id="s1")

failures = []


def step(name, result):
    print(f"--- {name}: ok={result.ok} exit={result.exit_code} category={result.category}")
    if result.errors:
        print(f"    errors={[(e['code'], e['message'][:120]) for e in result.errors]}")
    if not result.ok:
        failures.append(name)
    return result


health = step("health", epcd_health(ctx))
print(f"    status={health.data['health']['status'] if health.ok else '-'}")

init = step("project init", epcd_project(ctx, action="init",
                                         work_dir=WORK_DIR, technology=TECH))
if init.ok:
    print(f"    created={init.data.get('created')} lib={init.data.get('libName')} "
          f"techDigest={init.data.get('technologyDigest')}")
    print(f"    warnings={init.data.get('warnings')}")

step("project describe", epcd_project(ctx, action="describe"))
step("project validate", epcd_project(ctx, action="validate"))

listing = step("device-template list", epcd_template(ctx, action="list"))
if listing.ok:
    templates = listing.data.get("templates", [])
    print(f"    {len(templates)} templates: "
          f"{[t.get('templateId') for t in templates][:10]}")
    if templates:
        first = templates[0]["templateId"]
        desc = step(f"device-template describe {first}",
                    epcd_template(ctx, action="describe", template_id=first))
        if desc.ok:
            schema = desc.data.get("parameterSchema") or {}
            props = schema.get("properties") or {}
            print(f"    category={desc.data.get('category')} available={desc.data.get('available')} "
                  f"metrics={desc.data.get('builtInMetrics')} params={list(props)[:12]}")

proj = store.get_project("s1")
print(f"--- store ledger: project={proj['project_dir'] if proj else None} "
      f"lib={proj['lib_name'] if proj else None} techDigest={proj['technology_digest'] if proj else None}")

print("REAL_FLOW_OK" if not failures else f"REAL_FLOW_FAILED at: {failures}")
