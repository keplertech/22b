"""Real file-based Scope checkpoints alongside cumulative live NajaEDA/SEC edits."""

import argparse
import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gcd_reference_regression import clean_env, save, scope_payload
from scripts.live_session_regression import LIBERTY, FIRST, SECOND
from tools.live_session import LiveDesignSession


async def run(work):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    work.mkdir(parents=True, exist_ok=False)
    source, library = work / "input.v", work / "cells.lib"
    source.write_text("module top(input a, output y); BUF g(.A(a), .Y(y)); endmodule\n")
    library.write_text(LIBERTY)
    params = StdioServerParameters(command=sys.executable, args=["-m", "naja_scope.server"],
                                  env=clean_env(), cwd=str(ROOT))
    with LiveDesignSession(source, [library], work / "session") as live:
        assert live.verify()["status"] == "proved"
        initial = live.status()
        with (work / "scope-server.log").open("w") as log:
            async with stdio_client(params, errlog=log) as streams:
                async with ClientSession(*streams) as scope:
                    await scope.initialize()
                    calls = []

                    async def call(name, arguments=None):
                        response = await scope.call_tool(name, arguments or {})
                        value = scope_payload(response)
                        calls.append({"tool": name, "arguments": arguments or {}, "result": value})
                        save(work / "scope-calls.json", calls)
                        return value

                    async def load(artifact):
                        assert live.inspection_status(artifact["manifest"])["current"]
                        await call("reset_universe")  # Only the separate Scope server.
                        await call("load_liberty", {"files": artifact["liberty_files"]})
                        await call("load_verilog", {"files": [artifact["verilog_file"]]})
                        loaded = await call("status")
                        assert loaded["loaded"] and loaded["top"]["name"] == artifact["top"]
                        assert artifact["verilog_file"] in loaded["loaded_files"]

                    async def names():
                        result = await call("get_hierarchy", {"depth": 1, "limit": 20})
                        assert not result["root"].get("has_more")
                        return {child["name"] for child in result["root"]["children"]}

                    old = live.export_inspection()
                    await load(old)
                    assert await names() == {"g"}
                    for script, expected in ((FIRST, {"g", "h"}), (SECOND, {"g", "h1", "h2"})):
                        before_names = await names()
                        proof = live.apply_edit(script)
                        assert proof["status"] == "proved" and proof["proved_outputs"] == 1
                        assert not live.inspection_status(old["manifest"])["current"]
                        # No automatic reset/reload: the old server copy really stays old.
                        assert await names() == before_names
                        before = live.status()
                        fresh = live.export_inspection()
                        assert live.status() == before
                        assert fresh["export_equivalence"] == "not_checked"
                        await load(fresh)
                        assert await names() == expected
                        assert await names() == expected  # Reuse without another load.
                        assert live.inspection_status(fresh["manifest"])["current"]
                        assert live.status()["golden_sha256"] == initial["golden_sha256"]
                        assert live.status()["candidate_reference"] == initial["candidate_reference"]
                        old = fresh
                        print(f"PASS: live SEC and separate Scope refresh for revision {proof['revision']}",
                              flush=True)
                    assert len(list((work / "session/inspections").glob("*/manifest.json"))) == 3
                    save(work / "result.json", {
                        "status": "passed", "candidate_revisions": 2,
                        "scope_loads": 3, "stale_copy_detected": True,
                        "fresh_queries_reused": True, "golden_preserved": True,
                        "live_sec_proved_outputs": 1, "live_sec_total_outputs": 1,
                        "export_equivalence": "not_checked",
                    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(run(args.work_dir.resolve()), timeout=180))
