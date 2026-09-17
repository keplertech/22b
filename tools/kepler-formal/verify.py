"""Verify exported mapped designs through the pinned Python-backed MCP server."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[2]
VERIFY_TOOL = "create_yaml_and_run_kepler_formal"
REPORTS = ("skipped_multi_driver_pos.txt", "skipped_no_driver_pos.txt",
           "skipped_logical_loop_pos.txt")


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def package_identity():
    pins = json.loads((ROOT / "toolchain.json").read_text())
    versions = {name: importlib.metadata.version(name) for name in pins["python_packages"]}
    if versions != pins["python_packages"]:
        raise ValueError(f"Python package versions differ from toolchain.json: {versions}")
    pin = pins["kepler_formal_mcp"]
    dist = importlib.metadata.distribution("kepler-formal-mcp")
    origin = json.loads(dist.read_text("direct_url.json") or "{}")
    if (dist.version != pin["version"] or origin.get("url") != pin["repository"]
            or origin.get("vcs_info", {}).get("commit_id") != pin["revision"]):
        raise ValueError("Install the pinned kepler-formal-mcp Git package; version 0.1.0 alone is not sufficient")
    return {"python_packages": versions, "kepler_formal_mcp": origin,
            "mcp_version": dist.version, "python": sys.version}


def payload(response):
    if response.isError:
        raise ValueError("Kepler Formal MCP tool returned an error")
    # The upstream tools return JSON strings inside MCP text, not typed results.
    texts = [item.text for item in response.content if item.type == "text"]
    if len(texts) != 1:
        raise ValueError("Missing or ambiguous MCP JSON response")
    value = json.loads(texts[0])
    if not isinstance(value, dict):
        raise ValueError("MCP response must be a JSON object")
    return value


def summarize(result):
    """Execution success, checked coverage and proof coverage are separate facts."""
    if result.get("status") != "success":
        raise ValueError("Kepler Formal execution failed; inspect result.json and server.log")
    proof = result.get("verification_result")
    if not isinstance(proof, dict) or proof.get("verification") != "sec":
        raise ValueError("Missing structured SEC result (LEC is not accepted)")
    status = proof.get("status")
    if (result.get("verdict") != status or type(result.get("exit_code")) is not int
            or type(proof.get("exit_code")) is not int
            or result["exit_code"] != proof["exit_code"]):
        raise ValueError("Contradictory SEC outcome")
    if status == "different":
        raise ValueError("SEC found a counterexample; reject the candidate")
    if status not in ("equivalent", "partially_proved", "inconclusive"):
        raise ValueError(f"SEC did not complete a supported proof: {status}")
    counts = [proof.get(key) for key in ("total_outputs", "covered_outputs", "proven_outputs")]
    if (any(type(value) is not int for value in counts)
            or not 0 <= counts[2] <= counts[1] <= counts[0] or counts[0] == 0 or counts[1] == 0):
        raise ValueError("Invalid or zero observed-output coverage")
    total, covered, proven = counts
    coverage = proof.get("coverage_percent")
    if (type(coverage) not in (int, float) or not math.isfinite(coverage)
            or not math.isclose(coverage, 100 * covered / total)):
        raise ValueError("Contradictory checked-output coverage")
    for key in ("unproven_outputs", "skipped_observed_outputs"):
        if not isinstance(proof.get(key), list) or not all(isinstance(x, str) for x in proof[key]):
            raise ValueError(f"Missing or invalid {key}")
    reports = result.get("reports")
    if (not isinstance(reports, dict) or set(reports) != set(REPORTS)
            or not all(isinstance(value, str) for value in reports.values())):
        raise ValueError("Missing or invalid skipped-output reports")
    full = status == "equivalent"
    if proof.get("equivalent") is not full or proof.get("conclusive") is not full:
        raise ValueError("Contradictory equivalence flags")
    if full and (proof["exit_code"] != 0 or covered != total or proven != total
                 or proof["unproven_outputs"] or proof["skipped_observed_outputs"]
                 or any(text.strip() for text in reports.values())):
        raise ValueError("Equivalence claim lacks full, unskipped SEC proof")
    return {"status": "proved" if full else "warning", "verdict": status,
            "covered_outputs": covered, "existing_outputs": total,
            "proved_outputs": proven, "coverage_percent": coverage,
            "proof_coverage_percent": 100 * proven / total,
            "unproven_outputs": proof["unproven_outputs"],
            "skipped_observed_outputs": proof["skipped_observed_outputs"],
            "bound": proof.get("bound"), "reason": proof.get("reason"),
            "verification": "sec", "engine": "pdr", "encoding": "dual_rail_steady",
            "log": "kepler.log"}


def require_full(summary, expected_outputs):
    if (summary["status"] != "proved" or summary["existing_outputs"] != expected_outputs
            or summary["proved_outputs"] != expected_outputs):
        raise ValueError(f"Reference requires full SEC proof of {expected_outputs} outputs; "
                         "partial proof is not a mismatch but is insufficient here")
    return summary


async def call_server(directory, arguments):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "NAJAEDA_SRC", "EQUIVALENCE_CHECK"):
        env.pop(key, None)
    env["KEPLER_FORMAL_AI_OUTPUT_DIR"] = str(directory)
    params = StdioServerParameters(command=sys.executable,
                                  args=["-m", "kepler_formal_mcp"],
                                  cwd=str(directory), env=env)
    with (directory / "server.log").open("w") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                schemas = await session.list_tools()
                save(directory / "tool-schemas.json", schemas.model_dump(mode="json"))
                if not {VERIFY_TOOL, "get_kepler_formal_info"} <= {t.name for t in schemas.tools}:
                    raise ValueError("The installed MCP lacks the Python-backed verification tools")
                for name, args, filename in (("get_kepler_formal_info", {}, "info"),
                                              (VERIFY_TOOL, arguments, "result")):
                    reply = await session.call_tool(name, args)
                    save(directory / f"{filename}-mcp.json", reply.model_dump(mode="json"))
                    value = payload(reply)
                    save(directory / f"{filename}.json", value)
                    if filename == "info" and value.get("status") != "success":
                        raise ValueError("Kepler Formal Python library failed its capability check")
                return value


def run_sec(directory, reference, candidate, libraries, *, timeout=600):
    if type(timeout) is not int or timeout <= 0:
        raise ValueError("Timeout must be a positive integer")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / "packages.json", package_identity())
    inputs = directory / "inputs"
    inputs.mkdir()
    snapshots = []
    hashes = {}
    for index, source in enumerate([reference, candidate, *libraries]):
        source = Path(source).resolve(strict=True)
        destination = inputs / f"{index:02}-{source.name}"
        shutil.copyfile(source, destination)
        destination.chmod(0o444)
        snapshots.append(str(destination))
        for path in (source, destination):
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[str(source)] != hashes[str(destination)]:
            raise ValueError("Verification input changed while snapshotting")
    save(directory / "input-hashes.json", hashes)
    arguments = {"input_paths": snapshots[:2], "liberty_files": snapshots[2:],
                 "verification": "sec", "solver": "kissat", "max_k": 32,
                 "sec_engine": "pdr", "sec_encoding": "dual_rail_steady",
                 "allow_boundary_mismatch": False, "report_skipped_outputs": True,
                 "cnf_export": False, "timeout_seconds": timeout,
                 "allowed_output_dir": str(directory), "yaml_output_path": "config.yaml",
                 "log_file_name": "kepler.log"}
    save(directory / "request.json", {"tool": VERIFY_TOOL, "arguments": arguments})
    try:
        # The native worker has its own hard timeout; also bound MCP startup/transport.
        try:
            result = asyncio.run(asyncio.wait_for(call_server(directory, arguments), timeout + 60))
        finally:
            if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha for path, sha in hashes.items()):
                raise ValueError("Verification inputs changed during SEC")
        for name, contents in result.get("reports", {}).items():
            if name in REPORTS and isinstance(contents, str):
                (directory / name).write_text(contents)
        summary = summarize(result)
        save(directory / "summary.json", summary)
        return summary
    except Exception as error:
        save(directory / "error.json", {"error": str(error), "type": type(error).__name__})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--liberty", required=True, nargs="+", type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--require-full-outputs", type=int)
    args = parser.parse_args()
    try:
        summary = run_sec(args.work_dir, args.reference, args.candidate, args.liberty,
                          timeout=args.timeout_seconds)
        if args.require_full_outputs is not None:
            require_full(summary, args.require_full_outputs)
    except Exception as error:
        parser.exit(1, f"SEC failed: {error}\n")
    if summary["status"] == "warning":
        print("::warning::SEC is incomplete/inconclusive, not fully equivalent.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
