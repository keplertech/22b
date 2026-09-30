---
name: naja-scope
description: Inspect design connectivity through Naja-Scope MCP to establish drivers, loads and cone boundaries before a structural edit or to explain a reported timing path.
---

# Inspect Before Rewiring

Keep the selected execution mode. In **managed mode**, resolve the saved file
and libraries through the [session guide](../session-history.md). In **direct
mode**, resolve them from the [revision manifest](../../flow/direct-revisions.md)
without a Python flow helper or Scope adapter. Reload Scope when that selection
changes, including after undo; reuse an unchanged loaded copy.

Use the [package guide](install.md). Discover the installed typed-tool schemas,
then load Liberty and Verilog with `load_liberty` and `load_verilog`. Confirm the
top and loaded design with `status` before querying.

The pinned MCP server owns a separate loaded copy, not the live editing
candidate. Load original files once for standalone baseline analysis. In the
explicit managed no-export compatibility mode only, use
[on-demand inspection](checkpoints.md): export when needed and check freshness
before using its answers. Unlike versioned mode, this compatibility mode does
not save after every edit. In both modes, reload Scope only when the next query
needs a different revision, not before every query.

- Use `resolve` for exact hierarchical objects; retain underscores and bit indices.
- Use `get_drivers` to identify boundary input sources.
- Use `get_loads` on **every** output of the proposed replacement group. Include
  side consumers, top ports and fanout outside the reported critical path.
- Use `trace_cone` to inspect the surrounding logic and sequential frontier.

Use fully qualified paths discovered in the loaded design. Query shapes are
`trace_cone(direction="fanin", path="<top>.<instance>.<output>", max_frontier=20)`,
`get_loads(path="<top>.<instance>.<output>", limit=200)`, and
`get_drivers(path="<top>.<instance>.<input>", limit=200)`.
Replace the placeholders with observed names and use the installed tool's JSON
schema. Design-specific target pins belong to an analysis or reference, not this
shared skill.

Check truncation/limits before claiming complete connectivity. Save query inputs
and returned evidence with the analysis. Scope establishes structure, not delay
or functional equivalence: use OpenROAD for timing and Kepler for SEC.

Keep scope read-only for this flow. Send only necessary files and context to a
model, consistent with the user's permissions; loading a local design is not
authorization to upload it to an external service.
