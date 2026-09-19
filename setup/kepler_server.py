"""Agent stdio entry point: require the pinned package, then serve upstream MCP."""

import os
from pathlib import Path
import runpy
import sys


def main():
    for name in ("PYTHONPATH", "PYTHONHOME", "NAJAEDA_SRC", "EQUIVALENCE_CHECK"):
        os.environ.pop(name, None)
    root = Path(__file__).resolve().parents[1]
    verify = runpy.run_path(str(root / "tools/kepler-formal/verify.py"))
    verify["package_identity"]()
    # Reserve stdout exclusively for the upstream JSON-RPC transport.
    runpy.run_module("kepler_formal_mcp", run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ImportError) as error:
        print(f"Kepler MCP setup is not ready: {error}", file=sys.stderr)
        sys.exit(1)
