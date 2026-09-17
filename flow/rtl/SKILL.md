---
name: rtl-design
description: Author or modify RTL with explicit interface and cycle-level behavior, and use Kepler Formal SEC to verify revisions against an existing reference before handing mapped designs to the backend flow.
---

# RTL Design

Read the [parent contract](../../SKILL.md). Establish the interface, clock/reset
behavior, widths, signedness, latency, throughput and parameter configuration.

For an existing design, preserve the reference files and record the exact tops,
file lists, include paths, defines and parameters used for both versions. Explain
whether state, reset or cycle behavior changes. Use the caller's installed RTL
parser/linter and simulation tests; keep their commands and logs.

Run [Kepler SEC](../../tools/kepler-formal/SKILL.md) on the reference and candidate
with matched elaboration settings. The current Python-backed MCP loads mapped
structural Verilog and Liberty, not behavioral RTL/SystemVerilog. An explicitly
configured frontend must provide supported structural inputs; otherwise report
that verification is unsupported rather than claiming an RTL proof. A
pipeline-latency change needs an explicitly supported comparison contract; do
not assume ordinary cycle-aligned equivalence.

For a new design with no reference, record that SEC against a specification is
not available. Establish functional tests or a trusted executable reference;
self-comparison is only a tool smoke test, not proof of intended behavior.

Use [Naja-Scope](../../tools/naja-scope/SKILL.md) and
[NajaEDA](../../tools/najaeda/SKILL.md) when working with a supported elaborated
structural representation, not as a substitute for understanding RTL semantics.

Hand a synthesized, technology-mapped design and its constraints to the
[backend flow](../backend/SKILL.md) for physical measurements. This initial
repository does not provide a synthesis-tool package or a complete RTL example;
see [example conventions](../../examples/rtl/README.md).
