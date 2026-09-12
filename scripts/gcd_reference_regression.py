"""Deterministic packaged-tool replay, not an independent model attempt."""

import argparse
import ast
import asyncio
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/backend/gcd"
REFERENCE = EXAMPLE / "reference"
PLATFORM = EXAMPLE / "platform"
STAGES = ("prepare", "baseline", "inspect", "edit", "proof", "candidate", "compare")
REPORTS = ("setup", "hold", "electrical", "power", "worst_setup", "worst_hold", "tns", "area")
EXPECTED_OUTPUTS = 18


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def clean_env():
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "NAJAEDA_SRC", "EQUIVALENCE_CHECK"):
        env.pop(name, None)
    env["NAJA_SCOPE_ENABLE_PYTHON"] = "0"
    return env


def run_command(directory, command, *, timeout, env=None, accept_nonzero=False):
    directory.mkdir()
    save(directory / "command.json", {"argv": [str(x) for x in command], "cwd": str(directory)})
    start = time.monotonic()
    code = None
    try:
        with (directory / "tool.log").open("w") as log:
            process = subprocess.run(command, cwd=directory, env=env or clean_env(),
                                     stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, timeout=timeout)
            code = process.returncode
    finally:
        save(directory / "execution.json", {"exit_code": code, "seconds": time.monotonic() - start})
        if code != 0 and (directory / "tool.log").is_file():
            with (directory / "tool.log").open("rb") as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 8192))
                tail = log.read().decode("utf-8", errors="replace")
            print(f"--- Tool output tail: {directory / 'tool.log'} ---\n{tail}", flush=True)
    if code != 0 and not accept_nonzero:
        raise RuntimeError(f"Tool exited {code}; see {directory / 'tool.log'}")
    return code


def require_openroad_revision(version, revision):
    if not re.search(r"(?<![0-9a-f])" + re.escape(revision) + r"(?![0-9a-f])", version):
        raise ValueError(f"OpenROAD version does not match the flow source revision {revision}: {version.strip()}")


def require_full_sec(log, exit_code):
    coverage = re.findall(
        r"SEC checked-output coverage:\s*([\d.]+)%\s*\((\d+)/(\d+) covered/existing outputs\)", log)
    if exit_code != 0 or len(coverage) != 1:
        raise ValueError(f"SEC tool error or missing/ambiguous coverage (exit {exit_code})")
    percent = float(coverage[0][0])
    covered, total = map(int, coverage[0][1:])
    if re.search(r"SEC (?:partially proved|verification did not prove|cannot run)|counterexample", log, re.I):
        raise ValueError("Reference regression requires full SEC proof; partial proof is not a mismatch but is insufficient here")
    if (not re.search(r"SEC proved equivalence\b", log) or percent != 100
            or covered != total or total != EXPECTED_OUTPUTS):
        raise ValueError("Reference regression requires explicit full SEC proof covering all 18 GCD outputs")
    return {"status": "proved", "covered_outputs": covered, "existing_outputs": total,
            "proved_outputs": total, "log": "proof/tool.log"}


def physical_summary(directory):
    log = (directory / "tool.log").read_text()
    for marker in ("GCD_COMPLETE=1", "GCD_ROUTED=1", "GCD_FINAL_DRC=0"):
        if not re.search(r"(?m)^" + re.escape(marker) + r"\s*$", log):
            raise ValueError(f"Missing {marker}: {directory}")
    for name in REPORTS:
        path = directory / "reports" / (name + ".rpt")
        # A violations-only report can be empty when the checks are clean.
        if not path.is_file() or (name != "electrical" and not path.read_text().strip()):
            raise ValueError(f"Missing/empty report: {path}")
    for suffix in ("odb", "def", "v", "sdc"):
        path = directory / "results" / ("gcd_final." + suffix)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing physical output: {path}")
    metrics = json.loads((directory / "metrics.json").read_text())
    result = {"routing_drc": 0}
    for label, key in (("setup_ns", "DRT::worst_slack_max"), ("hold_ns", "DRT::worst_slack_min"),
                       ("tns_ns", "DRT::tns_max"), ("area_um2", "DPL::design_area")):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Missing/non-finite metric {key}")
        result[label] = value
    # Preserve the power report verbatim rather than guessing units or activity.
    result["power_report"] = (directory / "reports/power.rpt").read_text()
    return result


def compare(baseline, candidate):
    gain = candidate["setup_ns"] - baseline["setup_ns"]
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError("Candidate did not improve setup timing against this run's baseline")
    if not math.isfinite(candidate["hold_ns"]) or candidate["hold_ns"] < 0:
        raise ValueError("Candidate has a hold violation")
    if baseline["routing_drc"] != 0 or candidate["routing_drc"] != 0:
        raise ValueError("Routing DRC violations")
    return {"setup_gain_ns": gain, "setup_met": candidate["setup_ns"] >= 0,
            "baseline": baseline, "candidate": candidate}


def scope_payload(result):
    if result.isError:
        raise ValueError("Naja-Scope MCP tool failed")
    value = result.structuredContent
    if value is None:
        value = json.loads(next(c.text for c in result.content if c.type == "text"))
    if not isinstance(value, dict) or "error" in value:
        raise ValueError(f"Naja-Scope error: {value}")
    return value


def validate_scope_query(name, value):
    if name == "status" and (not value.get("loaded") or value.get("top", {}).get("name") != "gcd"):
        raise ValueError("Naja-Scope did not load the GCD design")
    if value.get("truncated"):
        raise ValueError("Naja-Scope boundary query was truncated")
    if name in ("get_drivers", "get_loads"):
        kind = name.removeprefix("get_")
        if not (value.get(f"leaf_{kind}") or value.get(f"top_{kind}")):
            raise ValueError(f"Naja-Scope returned no {kind} for the reference boundary")


async def inspect_scope(directory, design, liberty):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    directory.mkdir()
    params = StdioServerParameters(command=sys.executable,
                                  args=["-m", "naja_scope.server"], env=clean_env())
    with (directory / "server.log").open("w") as log:
        async with stdio_client(params, errlog=log) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                schemas = await session.list_tools()
                save(directory / "tool-schemas.json", schemas.model_dump(mode="json"))
                names = {tool.name for tool in schemas.tools}
                if not {"load_liberty", "load_verilog", "status", "get_drivers", "get_loads"} <= names:
                    raise ValueError("Missing required Naja-Scope MCP tools")
                calls = [("load_liberty", {"files": [str(liberty)]}),
                         ("load_verilog", {"files": [str(design)]}), ("status", {})]
                for index in range(215, 220):
                    calls.append(("get_loads", {"path": f"gcd._{index}_.X", "limit": 200}))
                    for pin in ("A", "B", "C"):
                        calls.append(("get_drivers", {"path": f"gcd._{index}_.{pin}", "limit": 200}))
                for index, (name, arguments) in enumerate(calls):
                    response = await session.call_tool(name, arguments)
                    save(directory / f"{index:02}-{name}.json",
                         {"tool": name, "arguments": arguments, "response": response.model_dump(mode="json")})
                    value = scope_payload(response)
                    validate_scope_query(name, value)


def input_hashes():
    return {str(path.relative_to(ROOT)): digest(path) for path in
            (EXAMPLE / "input.v", EXAMPLE / "constraints.sdc", REFERENCE / "edit.py",
             PLATFORM / "run.tcl", ROOT / "toolchain.json", ROOT / "tools/python-requirements.txt")}


def prepare(work, fixture):
    work.mkdir(parents=True, exist_ok=False)
    pins = json.loads((ROOT / "toolchain.json").read_text())
    packages = {name: importlib.metadata.version(name) for name in pins["python_packages"]}
    if packages != pins["python_packages"]:
        raise ValueError(f"Python packages do not match toolchain.json: {packages}")
    tools = {name: shutil.which(name) for name in ("openroad", "kepler-formal")}
    if not all(tools.values()):
        raise ValueError("Install the pinned OpenROAD and Kepler Formal packages first")
    run_command(work / "openroad-version", [tools["openroad"], "-version"], timeout=30)
    version = (work / "openroad-version/tool.log").read_text()
    require_openroad_revision(version, pins["openroad"]["source_revision"])
    spec = importlib.util.spec_from_file_location("gcd_fixture", PLATFORM / "fetch_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.fetch(fixture)
    (work / "inputs").mkdir()
    for name in ("input.v", "constraints.sdc"):
        destination = work / "inputs" / name
        shutil.copyfile(EXAMPLE / name, destination)
        destination.chmod(0o444)
    shutil.copyfile(fixture / "manifest.json", work / "fixture-manifest.json")
    metadata = {"kind": "deterministic_reference_replay_no_model", "completed": [],
                "source_hashes": input_hashes(), "fixture": str(fixture),
                "fixture_manifest_sha256": digest(fixture / "manifest.json"),
                "tools": tools, "openroad_version": version.strip(),
                "python": sys.version, "python_packages": packages,
                "toolchain": pins}
    save(work / "metadata.json", metadata)
    return metadata


def validate_inputs(work, metadata):
    if metadata["source_hashes"] != input_hashes():
        raise ValueError("Inputs, reference script or tool configuration changed during the run")
    for name in ("input.v", "constraints.sdc"):
        if digest(work / "inputs" / name) != digest(EXAMPLE / name):
            raise ValueError("Read-only baseline inputs were modified")
    fixture = Path(metadata["fixture"])
    if digest(fixture / "manifest.json") != metadata["fixture_manifest_sha256"]:
        raise ValueError("Fixture manifest changed during the run")
    manifest = json.loads((fixture / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if digest(fixture / name) != expected:
            raise ValueError(f"Fixture modified: {name}")
    if "edit" in metadata["completed"] and digest(work / "candidate.v") != metadata["candidate_sha256"]:
        raise ValueError("Candidate changed after the recorded edit/proof")


def stage(name, work, fixture, timeout):
    print(f"GCD reference: {name}", flush=True)
    if name == "prepare":
        metadata = prepare(work, fixture)
    else:
        metadata = json.loads((work / "metadata.json").read_text())
        if metadata["completed"] != list(STAGES[:STAGES.index(name)]):
            raise ValueError(f"Stage {name} requires successful earlier stages, in order")
        validate_inputs(work, metadata)
    fixture = Path(metadata["fixture"])
    liberty = fixture / "test/sky130hd/sky130hd_tt.lib"
    design = work / "inputs/input.v"
    directory = work / name
    if name in ("baseline", "candidate"):
        env = clean_env()
        env.update(GCD_RUN_DIR=str(directory), GCD_TEST_DIR=str(fixture / "test"),
                   GCD_INPUT=str(design if name == "baseline" else work / "candidate.v"),
                   GCD_SDC=str(work / "inputs/constraints.sdc"))
        run_command(directory, [metadata["tools"]["openroad"], "-no_init", "-exit", "-metrics",
                                str(directory / "metrics.json"), str(PLATFORM / "run.tcl")],
                    timeout=timeout, env=env)
        save(directory / "summary.json", physical_summary(directory))
    elif name == "inspect":
        asyncio.run(asyncio.wait_for(inspect_scope(directory, design, liberty), timeout=timeout))
    elif name == "edit":
        ast.parse((REFERENCE / "edit.py").read_text())
        run_command(directory, [sys.executable, str(REFERENCE / "edit.py"), "--liberty", str(liberty),
                                "--input", str(design), "--output", str(work / "candidate.v")], timeout=timeout)
        if not (work / "candidate.v").is_file():
            raise ValueError("Edit did not export a candidate")
        metadata["candidate_sha256"] = digest(work / "candidate.v")
    elif name == "proof":
        code = run_command(directory, [metadata["tools"]["kepler-formal"], "-verilog", "--verification", "sec",
                                       "--report-skipped-pos", str(design), str(work / "candidate.v"), str(liberty)],
                           timeout=timeout, accept_nonzero=True)
        save(directory / "summary.json", require_full_sec((directory / "tool.log").read_text(), code))
    elif name == "compare":
        result = compare(*(json.loads((work / part / "summary.json").read_text())
                           for part in ("baseline", "candidate")))
        result["proof"] = json.loads((work / "proof/summary.json").read_text())
        save(work / "comparison.json", result)
        print(f"Setup gain: {result['setup_gain_ns']:.9f} ns; setup met: {result['setup_met']}", flush=True)
        if not result["setup_met"]:
            print("::warning::Setup improved but remains negative; the timing target is not met.", flush=True)
    validate_inputs(work, metadata)
    metadata["completed"].append(name)
    save(work / "metadata.json", metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--fixture-dir", type=Path, default=ROOT / ".cache/gcd-fixture-v2")
    parser.add_argument("--stage", choices=(*STAGES, "all"), default="all")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    try:
        for name in STAGES if args.stage == "all" else (args.stage,):
            stage(name, args.work_dir.resolve(), args.fixture_dir.resolve(), args.timeout_seconds)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, TimeoutError) as error:
        parser.exit(1, f"GCD reference failed: {error}\n")


if __name__ == "__main__":
    main()
