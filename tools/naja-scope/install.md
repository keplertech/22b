# Install Naja-Scope

Use the [shared Python environment](../README.md). The initial pair is
`naja-scope==0.1.11` with `najaeda==0.7.20`; see the
[published scope package](https://pypi.org/project/naja-scope/0.1.11/).

```sh
. .venv/bin/activate
python -m pip install --only-binary=:all: 'najaeda==0.7.20' 'naja-scope==0.1.11'
python -m pip check
NAJA_SCOPE_ENABLE_PYTHON=0 naja-scope-mcp
```

The last command starts the stdio MCP server and waits for a client. Configure
your MCP client to launch the venv's absolute `naja-scope-mcp` path with that
environment variable. Do not mistake waiting for stdin for a hung install.
Use typed inspection tools; arbitrary Python execution is not needed for this
flow. No unauthenticated network listener is required.
