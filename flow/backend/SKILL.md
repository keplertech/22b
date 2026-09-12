---
name: backend-design
description: Improve a synthesized design using OpenROAD physical reports, Naja-Scope connectivity inspection, NajaEDA structural edits and Kepler Formal SEC, then compare physical results under unchanged constraints.
---

# Backend Improvement

Read the [parent contract](../../SKILL.md). Start from mapped Verilog, Liberty,
LEF/technology data and an SDC; RTL synthesis is not implicit in this flow.

1. Run the baseline through [OpenROAD](../../tools/openroad/SKILL.md), preserving
   setup/hold paths, electrical violations, area, power, route status and DRCs.
2. Read the worst path in detail: startpoint, endpoint, clock, cell and net delay,
   slew, capacitance and fanout. Check that constraints and units are meaningful.
3. Use [Naja-Scope](../../tools/naja-scope/SKILL.md) to establish the target cone
   and all boundary consumers. A timing path is not the complete connectivity.
4. Propose a specific Boolean or architectural transformation, with expected
   benefit and area/power/hold risks. Do not describe cell sizing as logic
   restructuring. If the rewrite is already specified, skip new model analysis.
5. Apply it with [NajaEDA](../../tools/najaeda/SKILL.md), then run
   [SEC](../../tools/kepler-formal/SKILL.md). Keep registers, resets and cycle
   boundaries unchanged unless the requested change explicitly includes them.
6. Rerun the candidate with the same tool package, corner, constraints, floorplan,
   flow scripts and thread/seed settings. An edited design can have a different
   critical path; inspect that path too.

Show baseline and candidate setup slack, hold slack, cell area, estimated power,
routing DRCs and proof coverage. Label units and power assumptions. Do not change
the clock period to manufacture an improvement. If tools or settings change,
rerun the baseline and keep the earlier results as a separate experiment.

Use the [GCD task](../../examples/backend/gcd/task.md) for an independent attempt.
Keep its `reference/` solution out of the initial model context.
