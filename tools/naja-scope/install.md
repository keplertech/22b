# Install Naja-Scope

Naja-Scope has its own virtual environment, `.venv-scope`, beside the
[editing environment](../README.md). It runs only as a separate MCP server that
loads files, and its releases require a newer NajaEDA than the exact build
Kepler Formal pins. The [pinned set](requirements.txt) is `naja-scope==0.1.26`,
`najaeda==0.7.35` and `mcp==1.30.0`; see the
[published scope package](https://pypi.org/project/naja-scope/0.1.26/).

```sh
python3 -m venv .venv-scope
.venv-scope/bin/python -m pip install --only-binary=:all: -r tools/naja-scope/requirements.txt
.venv-scope/bin/python -m pip check
NAJA_SCOPE_ENABLE_PYTHON=0 .venv-scope/bin/naja-scope-mcp
```

[Agent setup](../../setup/README.md) creates the same environment. The
regressions look for it at the editing venv's path plus `-scope`; set
`NAJA_SCOPE_PYTHON` to its interpreter for any other location. Do not install
Naja-Scope into the editing environment or import it in the editing kernel.

The last command starts the stdio MCP server and waits for a client. Configure
your MCP client to launch that environment's absolute `naja-scope-mcp` path with
that environment variable. Do not mistake waiting for stdin for a hung install.
Use typed inspection tools; arbitrary Python execution is not needed for this
flow. No unauthenticated network listener is required.
