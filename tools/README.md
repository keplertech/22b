# Packaged Tool Setup

Check `command -v`, tool help/version and Python package versions before
installing. Reuse a compatible installation. Do not change global configuration,
delete caches or upgrade working tools as an incidental part of an experiment.

Package references are pinned in [toolchain.json](../toolchain.json).

| Tool | Installation | Purpose |
| --- | --- | --- |
| Kepler Formal | [Python-backed MCP + native wheels](kepler-formal/install.md) | SEC verification |
| OpenROAD | [Nixpkgs package](openroad/install.md) | Physical design and reports |
| NajaEDA | [Published Python wheel](najaeda/install.md) | Structural editing |
| Naja-Scope | [Published Python wheel](naja-scope/install.md) | Read-only structural inspection through MCP |

Nix supplies OpenROAD and, optionally, Python. Kepler Formal, NajaEDA and
Naja-Scope use published wheels in a shared project-local virtual environment.
The pure-Python Kepler MCP wrapper is packaged from a pinned Git revision until
upstream publishes a distribution. This is not a fully Nix-locked Python
environment. No 22b source submodules or native source builds are used.

## Nix Prerequisites

Install Nix following the [official installation guide](https://nix.dev/install-nix).
The workflow uses Nix 2.35 with `nix-command` and `flakes` for OpenROAD.
Pass `--extra-experimental-features 'nix-command flakes'` if those features are
not enabled. Check `nix --version` and available disk space first.

The install commands use `--max-jobs 0 --builders ''`: use cached packages or
fail without a local or remote source build. A pinned package reference does
not guarantee the corresponding binary is currently cached on every platform.
Do not disable signature verification to work around a cache miss.

CI uses [install-cached-package.sh](install-cached-package.sh) to check the exact
native output in the local store or designated cache before installing. Cache
misses fail early, with package references, logs and exit codes retained. Each
Nix installable is pinned in `toolchain.json`; the general Nixpkgs pin below is
for Python and auxiliary tools, not an implicit OpenROAD version.

For an isolated Python interpreter:

```sh
nix shell --max-jobs 0 --builders '' \
  github:NixOS/nixpkgs/8ce4ef6cb6f871616146b9fe26d2a5ae594e94fe#python313
# Inside that shell, at the repository root:
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --only-binary=:all: -r tools/python-requirements.txt
python -m pip install --no-deps -r tools/kepler-formal/mcp-requirements.txt
python -m pip check
python -m pip freeze > .venv/resolved-packages.txt
```

An existing Python 3.13 interpreter with a compatible wheel can also create the
venv. The requirement pins identify the tool releases, not every transitive
dependency; retain the resolved package list with each experiment.

Package installation accesses public registries; design files do not need to
leave the machine. Configuring an external model is separate and remains the
caller's choice. No Ollama service or model is installed by this repository.
