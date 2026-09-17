---
name: najaeda
description: Inspect and edit structural hardware connectivity with NajaEDA, preserving boundary nets and interfaces, using a persistent candidate session or a separately exported candidate for formal verification.
---

# Structural Editing

Use the [package guide](install.md). For incremental edits in one Python/Jupyter
kernel, read [persistent sessions](../live-session.md). Supply only `edit(top)`
and pure helpers to `session.apply_edit(script)`; do not import, reset, load or
dump designs inside the script. The session owns loading and automatically runs
SEC against golden. Each edit starts from the previous candidate, including a
partially executed edit that needs repair after an exception.

For a separate, file-based process, load Liberty before mapped Verilog:

```python
from najaeda import netlist

netlist.reset()
netlist.load_liberty([liberty_path])
top = netlist.load_verilog([input_path])
if top is None:
    raise RuntimeError("No top loaded")
```

For local gate replacements read [the boundary-preserving recipe](gate-replacement.md).
Do not copy unrelated constant-source or traversal helpers into an editing script.
Use the installed API and explicit pin directions; do not guess method signatures.

Before executing a generated script, syntax check it, review its imports and file
access, and verify that named instances, models, pins and connections exist.
Run in a fresh candidate workspace with baseline files read-only where the
execution environment supports that. A Python syntax check is not a sandbox.

In the file-based flow, dump to a new output path with `top.dump_verilog(output_path)`. Do not overwrite
the reference or export intermediate multi-driver states. Reload the result and
run [Kepler SEC](../kepler-formal/SKILL.md); cell-count changes are diagnostics,
not a correctness proof. Detect internal-net/port naming collisions when signals
have been disconnected; Verilog names in one module can re-alias separate objects.

The [GCD reference script](../../examples/backend/gcd/reference/edit.py) is a
design-specific worked solution, not a generic optimization pass. Read it only
for explicit replay or comparison, not when solving the GCD task independently.
