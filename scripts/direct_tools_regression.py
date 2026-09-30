"""Real file-based edit/inspect/SEC/undo without importing 22b flow helpers.

This is a deterministic structural fixture replay, not an agent implementation
or an RTL elaboration test. Only stdlib and the installed tool APIs are used.
"""

import argparse
import ast
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


LIBERTY = '''library(cells) {
  cell(BUF) { pin(A) { direction: input; }
    pin(Y) { direction: output; function: "A"; } }
  cell(INV) { pin(A) { direction: input; }
    pin(Y) { direction: output; function: "!A"; } }
}
'''
BASELINE = '''module top(input a, output y);
wire stage;
BUF g(.A(a), .Y(stage));
BUF h(.A(stage), .Y(y));
endmodule
'''
EDIT = '''from najaeda import netlist
import sys

netlist.load_liberty([sys.argv[1]])
top = netlist.load_verilog([sys.argv[2]])
assert top is not None
old = top.get_child_instance("h")
driver = top.get_child_instance("g")
assert old is not None and driver is not None
output = old.get_term("Y").get_upper_net()
driver.get_term("Y").connect_upper_net(output)
old.delete()
top.dump_verilog(sys.argv[3])
'''


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(reply):
    if reply.isError:
        raise ValueError("MCP tool error")
    texts = [item.text for item in reply.content if item.type == "text"]
    if len(texts) != 1:
        raise ValueError("Missing unambiguous MCP response")
    value = json.loads(texts[0])
    if not isinstance(value, dict) or value.get("status") == "error" or value.get("error"):
        raise ValueError("Tool returned an error or malformed result")
    return value


def require_proof(result, different=False):
    proof = result.get("verification_result", {})
    verdict = "different" if different else "equivalent"
    if (result.get("status") != "success" or result.get("verdict") != verdict
            or proof.get("status") != verdict or proof.get("verification") != "sec"
            or type(result.get("exit_code")) is not int
            or proof.get("exit_code") != result["exit_code"]):
        raise ValueError("Missing or contradictory SEC outcome")
    if not different and (result["exit_code"] != 0
            or any(type(proof.get(k)) is not int or proof[k] != 1
                   for k in ("total_outputs", "covered_outputs", "proven_outputs"))
            or proof.get("coverage_percent") != 100
            or proof.get("equivalent") is not True or proof.get("conclusive") is not True
            or proof.get("unproven_outputs") != [] or proof.get("skipped_observed_outputs") != []):
        raise ValueError("Fixture requires full one-output SEC proof")
    reports = result.get("reports")
    expected = {"skipped_multi_driver_pos.txt", "skipped_no_driver_pos.txt",
                "skipped_logical_loop_pos.txt"}
    if (not isinstance(reports, dict) or set(reports) != expected
            or not all(isinstance(text, str) for text in reports.values())
            or (not different and any(text.strip() for text in reports.values()))):
        raise ValueError("Missing or contradictory extraction reports")


@asynccontextmanager
async def server(module, work):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    work.mkdir()
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "NAJAEDA_SRC", "EQUIVALENCE_CHECK"):
        env.pop(key, None)
    env.update(NAJA_SCOPE_ENABLE_PYTHON="0", KEPLER_FORMAL_AI_OUTPUT_DIR=str(work))
    params = StdioServerParameters(command=sys.executable, args=["-m", module],
                                  cwd=str(work), env=env)
    with (work / "server.log").open("w") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                save(work / "schemas.json", (await client.list_tools()).model_dump(mode="json"))
                yield client


async def run(work):
    work.mkdir(parents=True, exist_ok=False)
    inputs = work / "inputs"
    inputs.mkdir()
    golden, library = inputs / "golden.v", inputs / "cells.lib"
    golden.write_text(BASELINE)
    library.write_text(LIBERTY)
    golden.chmod(0o400)
    library.chmod(0o400)
    hashes = {str(p): digest(p) for p in (golden, library)}
    baseline = work / "versions/revision-0000"
    baseline.mkdir(parents=True)
    shutil.copyfile(golden, baseline / "design.v")
    state = {"mode": "direct", "current": 0, "next_attempt": 1, "retention": 10,
             "input_hashes": hashes, "objective": "minimize measured instance count (not PPA)"}
    save(work / "session.json", state)
    async with server("kepler_formal_mcp", work / "kepler") as formal, \
            server("naja_scope.server", work / "scope") as scope:
        info = payload(await formal.call_tool("get_kepler_formal_info", {}))
        if info.get("status") != "success":
            raise ValueError("Native Kepler capability check failed")
        save(work / "kepler-info.json", info)

        async def prove(label, candidate, different=False):
            output = work / label
            output.mkdir()
            request = {"input_paths": [str(golden), str(candidate)],
                       "liberty_files": [str(library)], "allowed_output_dir": str(output),
                       "verification": "sec", "solver": "kissat", "max_k": 32,
                       "sec_engine": "pdr", "sec_encoding": "dual_rail_steady",
                       "allow_boundary_mismatch": False, "report_skipped_outputs": True,
                       "cnf_export": False, "timeout_seconds": 60,
                       "yaml_output_path": "config.yaml", "log_file_name": "kepler.log"}
            save(output / "request.json", request)
            before = {str(p): digest(p) for p in (golden, library, candidate)}
            reply = await formal.call_tool("create_yaml_and_run_kepler_formal", request)
            save(output / "mcp-result.json", reply.model_dump(mode="json"))
            result = payload(reply)
            save(output / "result.json", result)
            require_proof(result, different)
            if before != {str(p): digest(p) for p in (golden, library, candidate)}:
                raise ValueError("Verification changed its inputs")
            save(output / "input-hashes.json", before)
            return result

        async def inspect(label, design):
            payload(await scope.call_tool("reset_universe", {}))
            payload(await scope.call_tool("load_liberty", {"files": [str(library)]}))
            payload(await scope.call_tool("load_verilog", {"files": [str(design)]}))
            status = payload(await scope.call_tool("status", {}))
            if (not status.get("loaded") or status.get("top", {}).get("name") != "top"
                    or str(design) not in status.get("loaded_files", [])):
                raise ValueError("Scope loaded a different design")
            response = payload(await scope.call_tool("find", {
                "pattern": "*", "kind": "instance", "limit": 100}))
            if response.get("has_more") or response.get("truncated"):
                raise ValueError("Incomplete Scope observations")
            names = sorted(item["path"] for item in response["matches"])
            save(work / f"scope-{label}.json", {"input_sha256": digest(design),
                 "status": status, "response": response})
            return names

        original = await inspect("baseline", baseline / "design.v")
        await prove("baseline-proof", baseline / "design.v")
        if original != ["top.g", "top.h"]:
            raise ValueError("Unexpected baseline connectivity")
        staging = work / "attempt-0001"
        staging.mkdir()
        script = staging / "edit.py"
        script.write_text(EDIT)
        ast.parse(EDIT)  # Reviewed fixture code; direct mode has no helper validator.
        candidate = staging / "design.v"
        state["next_attempt"] = 2
        save(work / "session.json", state)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("NAJAEDA_SRC", None)
        with (staging / "edit.log").open("w") as log:
            subprocess.run([sys.executable, str(script), str(library), str(baseline / "design.v"),
                            str(candidate)], cwd=staging, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=60)
        proof = await prove("edit-proof", candidate)
        save(staging / "manifest.json", {"revision": 1, "parent": 0,
             "sha256": digest(candidate), "proof": proof})
        edited = work / "versions/revision-0001"
        staging.rename(edited)
        state["current"] = 1
        save(work / "session.json", state)
        after = await inspect("edited", edited / "design.v")
        if after != ["top.g"]:
            raise ValueError("Scope did not observe the direct edit")
        # Real structural measurement, explicitly not an area/timing claim.
        save(edited / "measurement.json", {"instance_count": len(after),
             "baseline_instance_count": len(original), "evidence": "scope-edited.json"})
        shutil.copytree(edited, work / "best")
        shutil.copyfile(work / "scope-edited.json", work / "best/scope-edited.json")
        best_hash = digest(work / "best/design.v")
        await inspect("historical", baseline / "design.v")
        if await inspect("current", edited / "design.v") != after:
            raise ValueError("Scope failed to switch back to current")
        wrong = work / "attempt-0002"
        wrong.mkdir()
        (wrong / "design.v").write_text("module top(input a, output y); INV bad(.A(a), .Y(y)); endmodule\n")
        await prove("counterexample-proof", wrong / "design.v", different=True)
        state["next_attempt"] = 3
        save(work / "session.json", state)
        if state["current"] != 1:
            raise ValueError("Rejected edit changed current")
        await prove("restore-proof", baseline / "design.v")
        restored = await inspect("restored", baseline / "design.v")
        if restored != original:
            raise ValueError("Undo did not restore Scope observations")
        state["current"] = 0
        save(work / "session.json", state)
        shutil.rmtree(edited)  # Only our isolated, now discarded test checkpoint.
        if digest(work / "best/design.v") != best_hash:
            raise ValueError("Undo corrupted best")
    if hashes != {str(p): digest(p) for p in (golden, library)}:
        raise ValueError("Golden or libraries changed")
    forbidden = {"tools.live_session", "tools.versioned_session", "tools.session_history",
                 "tools.scope_checkpoints"}
    if forbidden & set(sys.modules):
        raise ValueError("Direct replay imported a flow helper")
    save(work / "result.json", {"status": "passed", "flow_helper_imports": [],
         "scope_before": original, "scope_after": after, "scope_restored": restored,
         "full_sec_outputs": 1, "counterexample_rejected": True, "best_preserved": True,
         "current": state["current"], "next_attempt": state["next_attempt"],
         "rtl_elaboration_tested": False, "model_reasoning_tested": False})
    print("PASS: helper-free NajaEDA edit, Scope switching, SEC, counterexample and undo", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(run(args.work_dir.resolve()), timeout=300))
