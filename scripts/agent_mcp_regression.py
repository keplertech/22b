"""Check direct agent MCP transport against the same live designs as the edit API."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.live_session_regression import LIBERTY, FIRST, SECOND, DIFFERENT
from tools.live_session import LiveDesignSession, SEC


async def run(work):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    work.mkdir(parents=True, exist_ok=False)
    source, library = work / "input.v", work / "cells.lib"
    source.write_text('module top(input a, output y); BUF g(.A(a), .Y(y)); endmodule\n')
    library.write_text(LIBERTY)
    setup = runpy.run_path(str(ROOT / "setup/mcp.py"))
    with LiveDesignSession(source, [library], work / "owner") as owner:
        coordinates = owner.mcp_attachment()
        original = owner.status()["golden_sha256"]
        # The generated client entries are tested outside any real agent config.
        with tempfile.TemporaryDirectory(prefix="22b-agent-config-") as temporary:
            project = Path(temporary)
            for client in ("codex", "claude-code"):
                entry = setup["configuration"](client, Path(sys.executable))
                path = setup["config_path"](project, client)
                config = setup["render_config"](None, client, "kepler-formal", entry)
                setup["write_config"](path, None, config)
                parsed = (setup["tomllib"].loads(path.read_text()) if client == "codex"
                          else json.loads(path.read_text()))
                key = "mcp_servers" if client == "codex" else "mcpServers"
                configured = parsed[key]["kepler-formal"]
                params = StdioServerParameters(command=configured["command"], args=configured["args"],
                                              env=setup["clean_env"](), cwd=str(work))
                with (work / f"{client}-server.log").open("w") as log:
                    async with stdio_client(params, errlog=log) as streams:
                        async with ClientSession(*streams) as agent:
                            await agent.initialize()
                            names = {tool.name for tool in (await agent.list_tools()).tools}
                            if not setup["REQUIRED_TOOLS"] <= names:
                                raise ValueError("Agent is missing direct Kepler tools")
                            attachment = SEC.payload(await agent.call_tool("attach_session", {
                                "connection_file": coordinates["connection_file"]}))
                            if attachment.get("session_id") != coordinates["session_id"] or attachment.get("pid") != os.getpid():
                                raise ValueError("Agent attached to a different live owner")

                            async def verify(label, *, different=False):
                                before = owner.mcp_attachment()
                                options = {key: before[key] for key in ("session_id", "design1", "design2")}
                                options.update(verification="sec", solver="kissat", max_k=32,
                                               sec_engine="pdr", sec_encoding="dual_rail_steady",
                                               report_skipped_outputs=True, timeout_seconds=60,
                                               allow_boundary_mismatch=False)
                                result = SEC.payload(await agent.call_tool("verify_session", options))
                                for key in ("session_id", "design1", "design2"):
                                    if result.get(key) != before[key]:
                                        raise ValueError("Proof identifies different designs")
                                reports = SEC.payload(await agent.call_tool("get_session_reports", {
                                    "session_id": before["session_id"], "report_id": result["report_id"]}))
                                for key in ("session_id", "design1", "design2", "report_id", "verification_result"):
                                    if reports.get(key) != result.get(key):
                                        raise ValueError("Reports do not match this direct proof")
                                if owner.mcp_attachment() != before:
                                    raise ValueError("Candidate revision changed during direct proof")
                                if different:
                                    if result.get("verdict") != "different":
                                        raise ValueError("Incorrect edit was not rejected by direct SEC")
                                else:
                                    SEC.require_full(SEC.summarize(result), 1)
                                    SEC.require_full(SEC.summarize(reports), 1)
                                SEC.save(work / f"{client}-{label}.json", result)
                                print(f"PASS: {client}: {label}", flush=True)

                            if client == "codex":
                                await verify("initial")
                                for number, script in enumerate((FIRST, SECOND), 1):
                                    SEC.require_full(owner.apply_edit(script), 1)
                                    await verify(f"edit-{number}")
                            else:
                                # A second independent server sees the already-edited design.
                                await verify("existing-candidate")
                                try:
                                    owner.apply_edit(DIFFERENT)
                                except ValueError as error:
                                    if "counterexample" not in str(error):
                                        raise
                                else:
                                    raise ValueError("Automatic SEC accepted the incorrect edit")
                                await verify("counterexample", different=True)
                            SEC.payload(await agent.call_tool("close_session", {
                                "session_id": coordinates["session_id"]}))
                            if owner.status()["golden_sha256"] != original:
                                raise ValueError("Detaching agent destroyed or changed owner's designs")
        if list((work / "owner").rglob("*.v")):
            raise ValueError("Live verification unexpectedly exported a design")
    SEC.save(work / "result.json", {"status": "passed", "direct_stdio_clients": 2,
             "equivalent_edits": 2, "counterexample_rejected": True, "design_exports": 0,
             "host_app_ui_tested": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.work_dir.resolve()))
