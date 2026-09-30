---
name: rtl-direct
description: Coordinate RTL revisions, frontend runs and supported structural inspection and SEC directly through tools, without the 22b session helper. Preserve source-to-structural provenance and explicit verification limits.
---

# Direct RTL

Follow [RTL design guidance](../SKILL.md),
[shared session policy](../../session-policy.md) and
[direct revision recipe](../../direct-revisions.md). Do not instantiate the
22b flow helper, including for checkpoint selection or undo.

1. Save the original RTL and exact file list, parameters, includes, defines,
   top, clock/reset and frontend settings. Keep candidate source files in a
   separate numbered workspace. Review source edits and run the chosen RTL
   parser/linter and simulation tests directly.
2. Use an explicitly configured frontend when structural tools are needed.
   Preserve the command, version, source hashes and generated structural files
   for reference and candidate. No synthesis package is supplied by this mode.
3. Inspect supported structural files with
   [Scope MCP](../../../tools/naja-scope/SKILL.md). If structurally editing them,
   use [NajaEDA Python](../../../tools/najaeda/SKILL.md) in a separate candidate
   process. A structural rewrite does not automatically update the RTL source.
4. Call [Kepler MCP](../../../tools/kepler-formal/SKILL.md) directly for SEC on
   supported structural reference/candidate files. State exactly which objects
   were verified and how they relate to the RTL. Unsupported elaboration or
   latency changes are blockers, not warning-level successful proofs.
5. Record source and structural revision identities, actual proof coverage,
   tests and measurements. Apply retention and best selection to complete
   bundles, not a netlist detached from its source/configuration.
6. Undo by selecting a previous retained bundle, restoring its source and
   structural artifacts together, rerunning applicable checks, and refreshing
   Scope. Discard the latest version only after the restore is validated.

For source-only work without a supported frontend, keep lint/simulation evidence
and explicitly mark structural SEC unavailable; do not imply equivalence. Keep
new-design functional tests distinct from reference-based verification. When
handing off to backend, keep direct mode unless the caller requests a switch.
