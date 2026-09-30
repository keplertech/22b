---
name: 22b-orchestration
description: Coordinate open-source hardware design tools for backend optimization or RTL development, preserving baselines and connecting inspection, edits, SEC verification and measured results.
---

# Orchestrate A Design Task

## Select Context

- For a mapped design and physical reports, read [backend](flow/backend/SKILL.md).
- For RTL creation or changes, read [RTL](flow/rtl/SKILL.md).
- Select that flow's **managed** or **direct** skill before editing. Honor an
  explicitly requested mode; otherwise use managed for iterative structural
  work. Read only the selected mode, not both. Switching requires a deliberate
  handoff of inputs and evidence, not a silent fallback after a failure.
- Read [package setup](tools/README.md) only when a needed tool is absent or its
  version does not match the experiment. Check existing installations first.
- If Kepler tools are absent from the agent's own tool list, use
  [agent MCP setup](setup/README.md). Installing a Python package or calling
  the live helper's internal client does not register tools with the host app.

Load only the tool skill relevant to the next operation. A gate-replacement
task needs connectivity and replacement guidance, not constant-propagation
helpers or every available example. The model/provider is the caller's choice.

For a fresh example attempt, load its task and design/platform inputs, not its
`reference/` solution or regression scripts. References are for explicit replay
or comparison afterward, not hints for independent discovery.

## Run Contract

1. Establish the top, input files, libraries, constraints, tool versions and
   acceptance target. Record hashes before editing. Explain the planned change
   before execution; honor any approval checkpoint requested by the user.
2. Keep the baseline immutable. Create a new candidate workspace; never reuse
   stale output files as evidence for a new run.
3. Inspect using reports and, when structural connectivity matters,
   [Naja-Scope](tools/naja-scope/SKILL.md). Separate observations from hypotheses.
   Refresh Scope when the next decision needs a different numbered revision;
   do not reuse a stale or historical copy for a current-design question.
4. Use [NajaEDA](tools/najaeda/SKILL.md) for structural edits. Review and syntax
   check generated code before running it with only the needed file access.
5. Run [Kepler Formal SEC through MCP](tools/kepler-formal/SKILL.md) and retain
   actual outcomes and coverage. Managed mode enforces live SEC and separately
   checks exported checkpoints through its helper. Direct mode calls the tools
   explicitly; the skills require the checks but do not mechanically enforce
   them. Follow the shared [session policy](flow/session-policy.md). Never
   describe a live proof as proof of an exported file.
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
