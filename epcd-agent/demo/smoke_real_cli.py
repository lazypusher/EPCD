"""Real-environment smoke: EpcdCli over ssh against the actual epcd-cli.

The remote environment (PATH/NINECUBEHOME/license) is loaded by sourcing the
package's user.bashrc.ePCD inside the remote shell command group. Run:

    ./.venv/Scripts/python demo/smoke_real_cli.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epcd_agent.cli_client import EpcdCli
from epcd_agent.exitcodes import classify_exit

PKG = "/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default"
REMOTE_ENV = f"source {PKG}/user.bashrc.ePCD >/dev/null 2>&1"

cli = EpcdCli(argv_prefix=("ssh", "-o", "BatchMode=yes", "zhubo@192.168.20.243"))

failures = 0
for name, args in [("version", ["version"]), ("health", ["health"])]:
    # one shell-quoted remote command (ssh joins argv then re-parses remotely)
    remote_cmd = f"{REMOTE_ENV}; epcd-cli {args[0]}"
    result = cli.exec([remote_cmd])
    category = classify_exit(result.exit_code)
    print(f"--- {name}: exit={result.exit_code} category={category}")
    if result.response is None:
        print(f"    PARSE FAIL: {result.parse_error}")
        print(f"    stdout head: {result.stdout[:300]!r}")
        print(f"    stderr head: {result.stderr[:300]!r}")
        failures += 1
        continue
    print(f"    ok={result.response.ok} schema={result.response.schema_version}")
    print(f"    data={result.response.data}")
    if result.response.errors:
        print(f"    errors={[e.code for e in result.response.errors]}")
    if not (result.exit_code == 0 and result.response.ok):
        failures += 1

print("REAL_SMOKE_OK" if failures == 0 else f"REAL_SMOKE_FAILED ({failures})")
