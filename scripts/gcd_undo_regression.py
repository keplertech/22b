"""Packaged GCD baseline -> edit -> undo, with real Scope, SEC and OpenROAD."""

import argparse
import ast
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import gcd_reference_regression as reference
from tools.live_session import _McpClient, SEC
from tools.scope_checkpoints import ScopeCheckpoints
from tools.versioned_session import VersionedDesignSession


class ScopeClient(_McpClient):
    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=sys.executable, args=["-m", "naja_scope.server"],
                                      env=reference.clean_env(), cwd=str(ROOT))
        with (self.directory / "scope-server.log").open("w") as log:
            async with stdio_client(params, errlog=log) as streams:
                async with ClientSession(*streams) as session:
                    await asyncio.wait_for(session.initialize(), 30)
                    schemas = await session.list_tools()
                    reference.save(self.directory / "scope-tools.json", schemas.model_dump(mode="json"))
                    self.ready.set_result({tool.name for tool in schemas.tools})
                    index = 0
                    while True:
                        request = await asyncio.to_thread(self.requests.get)
                        if request is None:
                            return
                        name, arguments, future = request
                        try:
                            response = await session.call_tool(name, arguments)
                            index += 1
                            reference.save(self.directory / f"scope-{index:04d}.json", {
                                "tool": name, "arguments": arguments,
                                "response": response.model_dump(mode="json")})
                            future.set_result(reference.scope_payload(response))
                        except Exception as error:
                            future.set_exception(error)


def observations(scope, revision=None):
    result = {}
    for name, pattern in (("original_gates", "_21[5-9]_"), ("replacement_gates", "ppa_cla_*")):
        response = scope.query("find", {"pattern": pattern, "kind": "instance", "limit": 200},
                               revision=revision)["result"]
        if response.get("has_more") or response.get("truncated"):
            raise ValueError("Scope query did not cover the complete replacement boundary")
        result[name] = sorted(response["matches"], key=lambda item: item["path"])
    # An unchanged downstream net exposes the changed driver, not just cell counts.
    result["boundary"] = scope.query("get_drivers", {"path": "gcd._057_", "limit": 200},
                                    revision=revision)["result"]
    if result["boundary"].get("truncated"):
        raise ValueError("Truncated Scope connectivity evidence")
    return result


def require_restored(baseline, restored):
    # Identical bytes, package and setup: demand the same results, not improvement.
    for key in ("setup_ns", "hold_ns", "tns_ns", "area_um2", "routing_drc", "power_report"):
        if baseline[key] != restored[key]:
            raise ValueError(f"Restored OpenROAD result differs from baseline: {key}")


def live_cells(session):
    # Check actual live objects too: selecting an old file alone is not undo.
    with session._inspection_access():
        return sorted((cell.getName(), cell.getModel().getName())
                      for cell in session._candidate.getInstances())


def run(work, fixture, timeout):
    metadata = reference.prepare(work, fixture)
    liberty = fixture / "test/sky130hd/sky130hd_tt.lib"
    script_tree = ast.parse((reference.REFERENCE / "edit.py").read_text())
    script = ast.unparse(ast.Module(body=[n for n in script_tree.body if isinstance(n, ast.FunctionDef)],
                                   type_ignores=[]))
    objective = {"weights": {"setup_ns": -1},
                 "bounds": {"hold_ns": {"min": 0}, "routing_drc": {"max": 0}}}
    session = VersionedDesignSession(work / "inputs/input.v", [liberty], sessions_root=work,
                                     objective=objective, timeout=timeout)
    client = None
    try:
        client = ScopeClient(work, timeout)
        scope = ScopeCheckpoints(session, client.call)
        golden_hash = session.status()["golden_sha256"]
        baseline_cells = live_cells(session)
        original_attachment = session.mcp_attachment()
        context = {"openroad": metadata["openroad_version"],
                   "sdc": reference.digest(work / "inputs/constraints.sdc"),
                   "flow": reference.digest(reference.PLATFORM / "run.tcl"),
                   "fixture": metadata["fixture_manifest_sha256"]}

        def physical(label, measure=True):
            print(f"OpenROAD: {label}", flush=True)
            directory = work / label
            with session.use_checkpoint() as checkpoint:
                SEC.require_full(checkpoint["export_proof"], reference.EXPECTED_OUTPUTS)
                env = reference.clean_env()
                env.update(GCD_RUN_DIR=str(directory), GCD_TEST_DIR=str(fixture / "test"),
                           GCD_INPUT=checkpoint["verilog_file"], GCD_SDC=str(work / "inputs/constraints.sdc"))
                reference.run_command(directory, [metadata["tools"]["openroad"], "-no_init", "-exit", "-metrics",
                                      str(directory / "metrics.json"), str(reference.PLATFORM / "run.tcl")],
                                      timeout=timeout, env=env)
                summary = reference.physical_summary(directory)
                reference.save(directory / "summary.json", dict(summary, revision=checkpoint["revision"],
                               input_sha256=checkpoint["files"]["design.v"]))
                if measure:
                    session.record_measurement({k: v for k, v in summary.items() if k != "power_report"},
                                               context=context, evidence=[directory / "summary.json",
                                               directory / "metrics.json", directory / "reports/power.rpt"])
            return summary

        print("Naja-Scope: baseline revision zero", flush=True)
        before = observations(scope)
        assert len(before["original_gates"]) == 5 and not before["replacement_gates"]
        baseline = physical("baseline")
        print("NajaEDA: reference edit, live SEC, checkpoint SEC", flush=True)
        SEC.require_full(session.apply_edit(script), reference.EXPECTED_OUTPUTS)
        assert live_cells(session) != baseline_cells
        edited = session.checkpoint()
        after = observations(scope)
        assert not after["original_gates"] and len(after["replacement_gates"]) == 31
        assert before["boundary"] != after["boundary"]
        assert observations(scope, revision=0) == before  # Explicit historical selection.
        assert observations(scope) == after              # Default returns to current.
        candidate = physical("candidate")
        gain = reference.compare(baseline, candidate)
        assert session.history.best["revision"] == edited["revision"]
        best_hash = reference.digest(session.directory / "best/design.v")
        print("Undo: restore previous netlist, SEC, then delete discarded revision", flush=True)
        undo = session.undo()
        SEC.require_full(undo["proof"], reference.EXPECTED_OUTPUTS)
        assert undo["restored_revision"] == 0
        assert not Path(edited["directory"]).exists()
        assert session.status()["golden_sha256"] == golden_hash
        assert live_cells(session) == baseline_cells
        assert session.mcp_attachment()["session_id"] != original_attachment["session_id"]
        assert reference.digest(session.directory / "best/design.v") == best_hash
        restored_observations = observations(scope)
        assert restored_observations == before
        restored = physical("restored", measure=False)
        require_restored(baseline, restored)
        assert session.checkpoint()["files"]["design.v"] == reference.digest(work / "inputs/input.v")
        reference.validate_inputs(work, metadata)
        reference.save(work / "scope-comparison.json", {"baseline": before, "candidate": after,
                                                       "restored": restored_observations})
        reference.save(work / "comparison.json", dict(gain, restored=restored, undo=undo,
                       status="passed", scope_restored=True, physical_restored=True,
                       live_candidate_restored=True, best_preserved=True, discarded_netlist_deleted=True))
        print(f"PASS: Scope and OpenROAD restored; edit gained {gain['setup_gain_ns']:.9f} ns; "
              "18/18 outputs proved after edit and undo", flush=True)
    finally:
        if client is not None:
            client.close()
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, default=ROOT / ".cache/gcd-fixture-v2")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    run(args.work_dir.resolve(), args.fixture_dir.resolve(), args.timeout_seconds)
