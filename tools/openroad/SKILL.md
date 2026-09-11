---
name: openroad
description: Run a packaged OpenROAD physical-design flow on a mapped design, preserve timing and physical reports, and compare baseline and edited results with matching constraints and tool settings.
---

# Physical Design And Reports

Use the [package guide](install.md). Confirm mapped Verilog, top, Liberty,
technology/cell LEF, RC/extraction data, SDC and floorplan settings. OpenROAD is
not an implicit RTL synthesizer; missing cells/macros or constraints are blockers.

Run a pinned Tcl flow in a fresh artifact directory:

```sh
openroad -no_init -exit -metrics metrics.json flow.tcl > openroad.log 2>&1
```

Record the command, version, wall time and exit status. A successful process
exit alone does not establish routed completion or timing closure.

Preserve final setup/hold paths with slew, capacitance and fanout, worst slack,
TNS, area, estimated power and activity assumptions, electrical violations,
routing status and DRC count. Save the final database, DEF, Verilog and SDC when
the selected flow supports them. Do not treat pre-route timing as final timing.

When a visual explanation is requested, open the saved database with the matching
technology data in OpenROAD's GUI. Show the full layout and a separately focused
critical path. Capture actual tool output, not a synthetic drawing presented as
physical evidence. Label baseline/candidate, corner, period and slack; retain
the scripts/commands needed to recreate the images.

Compare runs only with the same constraints, libraries, flow, package and
thread/seed settings. Check hold and routing as well as setup. Cell area and
estimated power may trade off against timing. The [GCD example](../../examples/backend/gcd/README.md)
provides a small physical flow and a known structural rewrite.
