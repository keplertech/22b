---
name: naja-scope
description: Inspect design connectivity through Naja-Scope MCP to establish drivers, loads and cone boundaries before a structural edit or to explain a reported timing path.
---

# Inspect Before Rewiring

Use the [package guide](install.md). Discover the installed typed-tool schemas,
then load Liberty and Verilog with `load_liberty` and `load_verilog`. Confirm the
top and loaded design with `status` before querying.

- Use `resolve` for exact hierarchical objects; retain underscores and bit indices.
- Use `get_drivers` to identify boundary input sources.
- Use `get_loads` on **every** output of the proposed replacement group. Include
  side consumers, top ports and fanout outside the reported critical path.
- Use `trace_cone` to inspect the surrounding logic and sequential frontier.

For the GCD example, `gcd._219_.X` is a fully qualified output pin. A verified
query shape is `trace_cone(direction="fanin", path="gcd._219_.X", max_frontier=20)`;
use the tool's actual JSON schema when making the MCP call. Other examples are
`get_loads(path="gcd._215_.X", limit=200)` and
`get_drivers(path="gcd._215_.C", limit=200)`.

Check truncation/limits before claiming complete connectivity. Save query inputs
and returned evidence with the analysis. Scope establishes structure, not delay
or functional equivalence: use OpenROAD for timing and Kepler for SEC.

Keep scope read-only for this flow. Send only necessary files and context to a
model, consistent with the user's permissions; loading a local design is not
authorization to upload it to an external service.
