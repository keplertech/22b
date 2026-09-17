"""Real Jupyter + NajaEDA + attached Kepler MCP regression, not an offline test."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
LIBERTY = '''library(test_cells) {
  cell(BUF) {
    pin(A) { direction: input; }
    pin(Y) { direction: output; function: "A"; }
  }
  cell(INV) {
    pin(A) { direction: input; }
    pin(Y) { direction: output; function: "!A"; }
  }
}
'''
FIRST = '''def edit(top):
    gate = top.get_child_instance("g")
    output = gate.get_term("Y").get_upper_net()
    stage = top.create_net("stage")
    gate.get_term("Y").connect_upper_net(stage)
    buf = top.create_child_instance(model="BUF", name="h")
    buf.get_term("A").connect_upper_net(stage)
    buf.get_term("Y").connect_upper_net(output)
'''
SECOND = '''def edit(top):
    old = top.get_child_instance("h")
    assert old is not None
    source = old.get_term("A").get_upper_net()
    output = old.get_term("Y").get_upper_net()
    middle = top.create_net("inverted")
    first = top.create_child_instance(model="INV", name="h1")
    second = top.create_child_instance(model="INV", name="h2")
    first.get_term("A").connect_upper_net(source)
    first.get_term("Y").connect_upper_net(middle)
    second.get_term("A").connect_upper_net(middle)
    second.get_term("Y").connect_upper_net(output)
    old.delete()
'''
DIFFERENT = '''def edit(top):
    top.get_child_instance("h2").get_term("A").connect_upper_net(top.get_net("stage"))
'''
REPAIR = '''def edit(top):
    top.get_child_instance("h2").get_term("A").connect_upper_net(top.get_net("inverted"))
'''


def run(work, checkout=None):
    from jupyter_client import KernelManager

    work.mkdir(parents=True, exist_ok=False)
    (work / "input.v").write_text('module top(input a, output y); BUF g(.A(a), .Y(y)); endmodule\n')
    (work / "cells.lib").write_text(LIBERTY)
    with tempfile.TemporaryDirectory(prefix="22b-kernel-", dir="/tmp") as private:
        manager = KernelManager(transport="ipc", connection_file=str(Path(private) / "connection.json"))
        manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("NAJAEDA_SRC", None)
        manager.start_kernel(cwd=str(ROOT), env=env)
        client = manager.blocking_client()
        client.start_channels()
        try:
            client.wait_for_ready(timeout=30)

            def cell(label, code):
                (work / f"{label}.py").write_text(code)
                request = client.execute(code, silent=False, store_history=False, allow_stdin=False)
                deadline = time.monotonic() + 120
                output = []
                error = None
                while True:
                    message = client.get_iopub_msg(timeout=max(0.1, deadline - time.monotonic()))
                    if message.get("parent_header", {}).get("msg_id") != request:
                        continue
                    kind, content = message["msg_type"], message["content"]
                    if kind == "stream":
                        output.append(content["text"])
                    elif kind == "error":
                        error = content["ename"] + ": " + content["evalue"]
                        output.append(error + "\n")
                    elif kind == "status" and content["execution_state"] == "idle":
                        break
                (work / f"{label}.log").write_text("".join(output))
                if error:
                    raise RuntimeError(f"Kernel cell {label}: {error}")
                print(f"PASS: {label}", flush=True)

            cell("01-open", f'''
import json, os
from pathlib import Path
from tools.live_session import LiveDesignSession
session = LiveDesignSession({str(work / 'input.v')!r}, [{str(work / 'cells.lib')!r}],
    {str(work / 'session')!r}, development_mcp_checkout={str(checkout) if checkout else None!r})
pid = os.getpid()
golden = session.status()["golden_sha256"]
assert session.verify()["proved_outputs"] == 1
''')
            cell("02-first-edit", f'''
result = session.apply_edit({FIRST!r})
assert result["status"] == "proved" and result["revision"] == 1
assert session.status()["golden_sha256"] == golden and os.getpid() == pid
''')
            cell("03-second-edit", f'''
result = session.apply_edit({SECOND!r})
assert result["status"] == "proved" and result["revision"] == 2
assert session.status()["golden_sha256"] == golden and os.getpid() == pid
''')
            cell("04-reject-difference", f'''
try:
    session.apply_edit({DIFFERENT!r})
except ValueError as error:
    assert "counterexample" in str(error)
else:
    raise AssertionError("Incorrect edit accepted")
assert session.status()["proof"] is None
assert session.status()["revision"] == 3 and session.status()["state"] == "rejected"
''')
            cell("05-repair-cumulative-candidate", f'''
result = session.apply_edit({REPAIR!r})
assert result["status"] == "proved" and result["revision"] == 4
assert session.status()["golden_sha256"] == golden and os.getpid() == pid
''')
            cell("06-reject-reset", '''
try:
    session.apply_edit("from najaeda import netlist\\nnetlist.reset()")
except ValueError:
    pass
else:
    raise AssertionError("Reset accepted")
assert session.status()["revision"] == 4
assert session.status()["proof"]["revision"] == 4
''')
            cell("07-detect-untracked-change", '''
from najaeda import netlist
netlist.get_top().create_net("outside_api")
try:
    session.status()
except RuntimeError as error:
    assert "outside the editing API" in str(error)
else:
    raise AssertionError("Stale proof remained valid")
assert session.proof is None
session.close()
''')
            if list((work / "session").rglob("*.v")):
                raise ValueError("Session unexpectedly exported a design")
            (work / "result.json").write_text(json.dumps({
                "status": "passed", "separate_notebook_cells": 7,
                "candidate_revisions": 4, "same_kernel": True,
                "golden_preserved": True, "difference_rejected": True,
                "untracked_mutation_rejected": True, "design_exports": 0,
            }, indent=2) + "\n")
        finally:
            client.stop_channels()
            manager.shutdown_kernel(now=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--development-mcp-checkout", type=Path)
    args = parser.parse_args()
    run(args.work_dir.resolve(), args.development_mcp_checkout.resolve() if args.development_mcp_checkout else None)
