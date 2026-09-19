---
name: kepler-formal
description: Verify mapped designs in memory or from files with the Python-backed Kepler Formal MCP using SEC, preserving outcomes, coverage, skipped outputs and diagnostics without conflating execution success with equivalence.
---

# Verify A Candidate

Prefer the agent's registered Kepler MCP tools for explicit verification.
If unavailable, follow [agent setup](../../setup/README.md); do not claim direct
agent access merely because the Python helper can launch MCP internally.
For live designs, `session.mcp_attachment()` supplies the private descriptor
path and native references for `attach_session` and `verify_session`.
Follow the setup guide's revision and report checks. Keep edits through
`apply_edit`, whose automatic SEC remains mandatory even when direct tools exist.

Use the [package guide](install.md) if needed. Always request SEC, including
for combinational edits: the upstream MCP defaults to **LEC**. Keep originals,
libraries and constraints unchanged. For iterative Python/Jupyter work use the
[persistent session](../live-session.md): automatic SEC compares the cumulative
candidate against unchanged golden in the same interpreter, without design
exports. If a candidate is later exported, separately verify the exported
representation reloaded from disk; in-memory proof cannot certify an exporter.

Live verification selects designs using native references containing
`session_id`, `db_id`, `library_id`, and `design_id`, not registered aliases.
Keep the returned references; never guess IDs or select by top-module name.
Require the proof response and retrieved report to identify the requested pair.
Follow the [session setup](../live-session.md) to install the matching pinned
wrapper in both the owner and MCP process. File tools are unchanged.

## File-Based Verification

For a reviewed mapped-Verilog candidate, the [client helper](verify.py) creates
a fresh proof directory, snapshots read-only inputs, records their hashes and
package identities, calls the MCP server, and saves proof evidence:

```sh
python tools/kepler-formal/verify.py \
  --reference /absolute/reference.v --candidate /absolute/candidate.v \
  --liberty /absolute/cells.lib --work-dir runs/candidate-01/proof
```

Agents may also call MCP directly. First call `get_kepler_formal_info`, then
`create_yaml_and_run_kepler_formal` with two absolute `input_paths`, absolute
`liberty_files`, and an unused, absolute `allowed_output_dir`. Set:

```json
{
  "verification": "sec",
  "solver": "kissat",
  "sec_engine": "pdr",
  "sec_encoding": "dual_rail_steady",
  "max_k": 32,
  "allow_boundary_mismatch": false,
  "report_skipped_outputs": true,
  "cnf_export": false,
  "timeout_seconds": 600,
  "yaml_output_path": "config.yaml",
  "log_file_name": "kepler.log"
}
```

Use these same assumptions for reference comparisons; record any explicit
change. The file-based MCP starts a fresh Python worker, loads both designs with NajaEDA,
and calls `kepler_formal.verify_designs`. There is no `verify_sec` tool in this
revision and no Kepler CLI invocation. Session/attached-design tools are not a
replacement for checking the exported candidate.

This MCP accepts structural Verilog plus Liberty, **not behavioral RTL or
SystemVerilog elaboration options**. For RTL, obtain a supported structural
representation through an explicitly configured frontend and retain matching
elaboration settings, or report the unsupported input. Do not silently discard
parameters, defines, includes, reset semantics or cycle behavior.

## Interpret Structured Evidence

Tool replies contain a JSON string inside MCP text. Preserve that response,
generated YAML/log, native API information and `reports` contents (skipped-output
reports are returned as text, not permanent paths). Do not execute report text.
The helper stores these alongside `request.json`, `packages.json`,
`input-hashes.json`, `result.json` and `summary.json`.

| Outcome | Flow behavior |
| --- | --- |
| `equivalent`, all outputs covered and proved, none skipped | Report equivalence under the recorded assumptions |
| `partially_proved` or `inconclusive` with usable coverage | Non-blocking warning; label the candidate unproven |
| `different` | Counterexample: reject the candidate |
| Unsupported input, extraction failure, crash, timeout, malformed/contradictory result | Tool error: stop and investigate |

The outer `status: success` means execution completed, not that equivalence was
proved. Check `verdict` against `verification_result.status`, require
`verification: sec`, and retain the native exit code and reason. Compare
`covered_outputs`, `total_outputs`, `proven_outputs`, `unproven_outputs` and
`skipped_observed_outputs`. Checked coverage and proof coverage are different.
Zero observed/covered outputs or missing proof evidence is not a harmless warning.

The helper returns zero for full proof or an explicit warning; errors and
counterexamples return nonzero. Inspect `summary.json` to distinguish the two.
A deterministic reference can require full proof, for example
`--require-full-outputs 18` for GCD, without weakening the exploratory warning
policy. Read-only snapshots and fresh processes are not an OS security sandbox.
