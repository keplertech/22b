"""Install pinned tools and register Kepler MCP with a local agent project."""

import argparse
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import tomllib
import venv


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
LAUNCHER = SCRIPT.with_name("kepler_server.py")
REQUIRED_TOOLS = {"get_kepler_formal_info", "create_yaml_and_run_kepler_formal",
                  "attach_session", "verify_session", "get_session_reports"}


def clean_env():
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "NAJAEDA_SRC", "EQUIVALENCE_CHECK"):
        env.pop(key, None)
    return env


def identity():
    pins = json.loads((ROOT / "toolchain.json").read_text())
    requirements = dict(pins["python_packages"])
    for line in (ROOT / "tools/session-requirements.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==")
            requirements[name] = version
    versions = {}
    for name in requirements:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    pin = pins["kepler_formal_mcp"]
    try:
        dist = importlib.metadata.distribution("kepler-formal-mcp")
        origin = json.loads(dist.read_text("direct_url.json") or "{}")
        wrapper = (dist.version == pin["version"] and origin.get("url") == pin["repository"]
                   and origin.get("vcs_info", {}).get("commit_id") == pin["revision"])
    except (importlib.metadata.PackageNotFoundError, ValueError):
        wrapper = False
    return {"packages_match": versions == requirements, "wrapper_match": wrapper,
            "versions": versions}


def run(command, *, capture=False, timeout=600):
    return subprocess.run([str(arg) for arg in command], check=True, env=clean_env(),
                          text=True, capture_output=capture, timeout=timeout)


def python_in(directory):
    # Do not resolve the executable symlink: Python needs the venv path.
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install(directory):
    python = python_in(directory)
    if directory.exists():
        if not (directory / "pyvenv.cfg").is_file() or not python.is_file():
            raise ValueError("Existing environment is not a usable venv; choose another --venv")
    else:
        venv.EnvBuilder(with_pip=True).create(directory)
    state = json.loads(run([python, "-I", SCRIPT, "identity"], capture=True).stdout)
    if not state["packages_match"]:
        run([python, "-I", "-m", "pip", "install", "--only-binary=:all:",
             "-r", ROOT / "tools/python-requirements.txt",
             "-r", ROOT / "tools/session-requirements.txt"])
    if not state["wrapper_match"]:
        run([python, "-I", "-m", "pip", "install", "--no-deps", "--force-reinstall",
             "-r", ROOT / "tools/kepler-formal/mcp-requirements.txt"])
    if state["packages_match"] and state["wrapper_match"]:
        print("Reusing the matching pinned installation.", flush=True)
    run([python, "-I", "-m", "pip", "check"])
    return python


def configuration(client, python):
    config = {"command": str(python), "args": ["-I", str(LAUNCHER)]}
    if client == "codex":
        config.update(startup_timeout_sec=60, tool_timeout_sec=660)
    else:
        config["type"] = "stdio"
    return config


def config_path(project, client):
    return project / (".codex/config.toml" if client == "codex" else ".mcp.json")


def read_config(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Refusing to change a symlinked agent configuration")
    return path.read_bytes() if path.exists() else None


def render_config(old, client, name, entry):
    text = (old or b"").decode("utf-8")
    if client == "codex":
        data = tomllib.loads(text)
        key = "mcp_servers"
    else:
        data = json.loads(text) if old is not None else {}
        key = "mcpServers"
    if not isinstance(data, dict) or not isinstance(data.get(key, {}), dict):
        raise ValueError("Invalid existing MCP configuration; it was not changed")
    servers = data.setdefault(key, {})
    if name in servers:
        if servers[name] != entry:
            raise ValueError(f"MCP server '{name}' already has different settings; "
                             "choose --name or review the existing entry manually")
        return old
    servers[name] = entry
    if client == "codex":
        addition = f"\n[mcp_servers.{name}]\n" + "".join(
            f"{key} = {json.dumps(value)}\n" for key, value in entry.items())
        result = text + addition
        if tomllib.loads(result) != data:
            raise ValueError("Cannot safely extend this TOML layout; no configuration changed")
    else:
        result = json.dumps(data, indent=2) + "\n"
    return result.encode("utf-8")


def write_config(path, old, new):
    if old == new:
        if read_config(path) != old:
            raise ValueError("Agent configuration changed during setup; rerun without overwriting it")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Coordinate setup invocations and reject changes since the initial read.
    lock = path.with_name(path.name + ".22b-lock")
    with lock.open("x"):
        try:
            if read_config(path) != old:
                raise ValueError("Agent configuration changed during setup; rerun without overwriting it")
            if old is not None:
                fd, backup = tempfile.mkstemp(prefix=path.name + ".22b-backup-", dir=path.parent)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(old)
                print(f"Previous config saved: {backup}", flush=True)
            fd, temporary = tempfile.mkstemp(prefix=path.name + ".22b-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(new)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        finally:
            lock.unlink()


async def probe():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    state = identity()
    if not state["packages_match"] or not state["wrapper_match"]:
        raise ValueError("Environment does not match the toolchain and session pins")
    sec = runpy.run_path(str(ROOT / "tools/kepler-formal/verify.py"))
    with tempfile.TemporaryDirectory(prefix="22b-mcp-probe-") as work:
        params = StdioServerParameters(command=sys.executable, args=["-I", str(LAUNCHER)],
                                      env=clean_env(), cwd=work)
        async with asyncio.timeout(90):
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    if not REQUIRED_TOOLS <= names:
                        raise ValueError(f"Missing MCP tools: {sorted(REQUIRED_TOOLS - names)}")
                    info = sec["payload"](await session.call_tool("get_kepler_formal_info", {}))
                    if info.get("status") != "success":
                        raise ValueError("Kepler Python library capability check failed")
    return {"status": "ready", "tools": sorted(names), "native_import": "passed",
            "host_tool_visibility": "requires host reload and approval"}


def check(python):
    reply = run([python, "-I", SCRIPT, "probe"], capture=True, timeout=120)
    result = json.loads(reply.stdout)
    if result.get("status") != "ready":
        raise ValueError("MCP probe did not establish readiness")
    print(json.dumps(result, indent=2), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "check", "identity", "probe"))
    parser.add_argument("--client", choices=("codex", "claude-code"))
    parser.add_argument("--project", type=Path, default=ROOT)
    parser.add_argument("--venv", type=Path, help="Existing/new dedicated venv (default: PROJECT/.venv)")
    parser.add_argument("--name", default="kepler-formal")
    parser.add_argument("--apply", action="store_true", help="Install and write project config; otherwise preview only")
    args = parser.parse_args(argv)
    if args.action == "identity":
        print(json.dumps(identity()))
        return
    if args.action == "probe":
        print(json.dumps(asyncio.run(probe())))
        return
    project = args.project.resolve(strict=True)
    directory = args.venv.resolve() if args.venv else project / ".venv"
    python = python_in(directory)
    if args.action == "check":
        check(python)
        return
    if not args.client:
        parser.error("configure requires --client")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        parser.error("--name must contain only letters, numbers, underscores and hyphens")
    path = config_path(project, args.client)
    entry = configuration(args.client, python)
    old = read_config(path)
    new = render_config(old, args.client, args.name, entry)
    print(json.dumps({"client": args.client, "scope": "project", "config": str(path),
                      "environment": str(directory), "server": entry,
                      "apply": args.apply}, indent=2), flush=True)
    if not args.apply:
        print("Preview only. Add --apply to install, test MCP discovery, and register.")
        return
    install(directory)
    check(python)
    write_config(path, old, new)
    print("Registered. Reload the agent and approve the trusted project/server. "
          "Confirm Kepler tools in its MCP tool list; host visibility is not tested by this probe.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ExceptionGroup) as error:
        print(f"MCP setup failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr or error.stdout or "", file=sys.stderr)
        sys.exit(1)
