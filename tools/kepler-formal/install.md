# Install The Python-Backed Kepler Formal MCP

22b uses [kepler-formal-mcp](https://github.com/keplertech/kepler-formal-mcp)
to call the `kepler-formal` Python library. It no longer launches the Nix CLI
or depends on `keplertech` Cachix for verification. OpenROAD still uses Nix.

Use the [shared Python environment](../README.md). Check existing versions and
the MCP commit before installing; `kepler-formal-mcp==0.1.0` alone does not
distinguish the new Python server from the older CLI wrapper.

For Codex or Claude Code, [agent setup](../../setup/README.md) installs these
pins, checks discovery and safely adds project-scoped MCP configuration. The
generic JSON below is not Codex's configuration format.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --only-binary=:all: -r tools/python-requirements.txt
python -m pip install --no-deps -r tools/kepler-formal/mcp-requirements.txt
python -m pip check
python -m pip freeze > .venv/resolved-packages.txt
```

For an existing MCP installation at a different Git revision, add
`--force-reinstall` to the wrapper-only `pip install --no-deps` command above.
Pip may otherwise retain the old revision because both use version `0.1.0`.
Reuse an installation whose Git revision already matches the requirement.

The native dependencies are published wheels: `kepler-formal==0.5.0` requires
`najaeda==0.7.24`. Python 3.13 is used by the regression. If a compatible native
wheel is unavailable, stop; never compile Kepler or Naja as a fallback.

The MCP wrapper has no published PyPI package at this pin. Its separate
[requirement](mcp-requirements.txt) explicitly packages pure Python from an
immutable Git revision; this is not a native compilation or source submodule.
`--no-deps` keeps the previously installed native wheel versions unchanged.
The commit and distribution versions are checked before each verification.
Record the resolved dependency list: transitive dependencies are not fully locked.

Configure the MCP client with the absolute path to this environment's Python:

```json
{
  "mcpServers": {
    "kepler-formal": {
      "command": "/absolute/venv/bin/python",
      "args": ["-m", "kepler_formal_mcp"]
    }
  }
}
```

The stdio server waits for a client; waiting for stdin is not an installation
failure. No network listener, API token, Kepler CLI or source-build paths are
needed. Do not set `PYTHONPATH` to a different Naja build. Call
`get_kepler_formal_info` to record the native version/hash and supported options;
the native version string need not equal the Python distribution's version.

Validate a known equivalent and inequivalent pair with the
[SEC procedure](SKILL.md) before relying on a new platform or package revision.
