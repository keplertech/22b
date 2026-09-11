---
name: 22b-orchestration
description: Coordinate open-source hardware design tools for backend optimization or RTL development, preserving baselines and connecting inspection, edits, SEC verification and measured results.
---

# Orchestrate A Design Task

## Select Context

- For a mapped design and physical reports, read [backend](flow/backend/SKILL.md).
- For RTL creation or changes, read [RTL](flow/rtl/SKILL.md).
- Read [package setup](tools/README.md) only when a needed tool is absent or its
  version does not match the experiment. Check existing installations first.

Load only the tool skill relevant to the next operation. A gate-replacement
task needs connectivity and replacement guidance, not constant-propagation
helpers or every available example. The model/provider is the caller's choice.

## Run Contract

1. Establish the top, input files, libraries, constraints, tool versions and
   acceptance target. Record hashes before editing. Explain the planned change
   before execution; honor any approval checkpoint requested by the user.
2. Keep the baseline immutable. Create a new candidate workspace; never reuse
   stale output files as evidence for a new run.
3. Inspect using reports and, when structural connectivity matters,
   [Naja-Scope](tools/naja-scope/SKILL.md). Separate observations from hypotheses.
4. Use [NajaEDA](tools/najaeda/SKILL.md) for structural edits. Review and syntax
   check generated code before running it with only the needed file access.
5. Run [Kepler Formal SEC](tools/kepler-formal/SKILL.md) on the exported candidate,
   not only an in-memory representation. Preserve proof logs and output coverage.
6. For backend tasks, rerun [OpenROAD](tools/openroad/SKILL.md) with the same
   physical setup. Compare timing, area, estimated power, hold and routing checks.

Full proof supports an equivalence claim only within the reported assumptions
and coverage. Partial/inconclusive proof permits continued measurement with an
explicit unproven warning. Counterexamples or execution errors stop the flow.
Missing reports, skipped stages and timeouts are not successes.

## Handoff

Keep `baseline/`, `candidate/`, `analysis.md`, the actual edit script, `proof/`,
commands, versions and checksums under a unique `runs/<experiment>/` directory.
Record what was measured, what remains unproven, and whether the acceptance
target was met. Bound retries; after repeated identical failures, inspect the
cause rather than quietly looping or weakening checks.
