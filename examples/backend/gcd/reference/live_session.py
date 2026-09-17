"""Explicit reference replay: two cumulative edits, same in-memory GCD candidate."""

import argparse
import ast
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.live_session import LiveDesignSession, SEC


# This second edit exercises cumulative state, not another timing optimization.
SECOND = '''def edit(top):
    gate = top.get_child_instance("ppa_cla_x4")
    assert gate is not None
    assert top.get_net("session_buffer_stage") is None
    assert top.get_child_instance("session_buffer") is None
    output = gate.get_term("X").get_upper_net()
    stage = top.create_net("session_buffer_stage")
    gate.get_term("X").connect_upper_net(stage)
    buf = top.create_child_instance(model="sky130_fd_sc_hd__buf_1", name="session_buffer")
    buf.get_term("A").connect_upper_net(stage)
    buf.get_term("X").connect_upper_net(output)
'''


def run(directory, liberty, checkout=None):
    # Reuse only the reviewed functions; the standalone CLI loads/dumps files
    # and must never execute in a persistent session.
    tree = ast.parse(Path(__file__).with_name("edit.py").read_text())
    script = ast.unparse(ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
        type_ignores=[]))
    proofs = []
    with LiveDesignSession(
        ROOT / "examples/backend/gcd/input.v", [liberty], directory,
        development_mcp_checkout=checkout,
    ) as session:
        golden = session.status()["golden_sha256"]
        for revision, source in enumerate((script, SECOND), 1):
            proof = SEC.require_full(session.apply_edit(source), 18)
            if proof["revision"] != revision or session.status()["golden_sha256"] != golden:
                raise ValueError("Cumulative revision or golden integrity changed")
            proofs.append(proof)
            print(f"PASS: cumulative GCD revision {revision}, SEC proved 18/18, no skips", flush=True)
    if list(directory.rglob("*.v")):
        raise ValueError("Live session unexpectedly exported a design")
    (directory / "reference-result.json").write_text(json.dumps({
        "status": "passed", "cumulative_proofs": proofs, "golden_preserved": True,
        "design_exports": 0, "timing_measured": False,
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--liberty", type=Path, required=True)
    parser.add_argument("--development-mcp-checkout", type=Path)
    args = parser.parse_args()
    run(args.work_dir.resolve(), args.liberty.resolve(), args.development_mcp_checkout)
