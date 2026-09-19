# Inspect A Live Candidate Without Binding

Use this file-based handoff with the pinned Naja-Scope MCP server. Golden,
candidate and automatic SEC remain in their existing Python/Jupyter kernel.
Do not import Scope or call its load/reset tools inside that kernel.

## Decide Whether To Refresh

- For original-design questions, use the baseline files and retain baseline-labelled evidence.
- For current drivers, fanout, replacement boundaries or a newly reported timing
  path, check whether Scope's loaded copy matches the live candidate revision.
- Reuse the same loaded copy for multiple queries while current. An edit makes
  it historical, but does not require a refresh until current inspection is needed.
- Inspection is also useful for diagnosing a rejected or partially executed
  edit. It does not turn that candidate into an accepted or proven design.

## Export And Load

In the existing editing kernel, outside the generated `edit(top)` script:

```python
inspection = session.export_inspection()
manifest = inspection["manifest"]
assert session.inspection_status(manifest)["current"]
```

This creates a fresh private directory under the session's `inspections/`, with
read-only `candidate.v`, copies of the original Liberty files and a manifest.
It records the native candidate reference, revision, top and file hashes.
It holds the shared native lock, checks the live designs before/after export,
and does not reset/reload a design or advance the edit revision. A changed
Liberty source or failed dump is an error, not a usable checkpoint.

In the **separate Naja-Scope MCP server**, using its discovered schemas:

1. For a refresh, call `reset_universe` there only. This clears that server's
   old copy, never the editing kernel. A new empty server needs no reset.
2. Call `load_liberty` with `files=inspection["liberty_files"]` (skip if empty).
3. Call `load_verilog` with `files=[inspection["verilog_file"]]`, retaining
   strict unresolved-cell checking.
4. Confirm the returned top and `status` loaded files match the manifest, then
   record that manifest as the copy loaded by this Scope server. If any loading
   step fails, do not reuse the previous loaded-copy claim.
5. Use the typed inspection tools. Save query arguments and responses together
   with the manifest path and revision.

The paths must be accessible to the Scope server on the same host/filesystem.
The helper does not launch Scope, call its tools or monitor what another client
loads. Track the loaded manifest per server; use separate servers for concurrent
baseline/candidate inspection, or explicitly reset and switch one server.

## Check Freshness

In the editing kernel, before using Scope evidence for the current candidate:

```python
freshness = session.inspection_status(manifest)
if not freshness["current"]:
    print(freshness["reasons"])
    # Export and load a fresh copy only if current-candidate inspection is needed.
```

This checks the retained export record, current revision and artifact hashes.
It rejects manifests from other live sessions. It never silently refreshes.
Check again after a group of queries if editing could have occurred in between;
historical results remain historical even after loading a newer copy.
Do not edit read-only inspection files; make a new export instead. Read-only
permissions and hashes detect accidents, not hostile same-user Python code.

Freshness means the copy came from the current revision and its files are
unchanged, **not** that export preserved connectivity. Every manifest says
`export_equivalence: not_checked`. In-memory SEC is not a proof of dumped
Verilog; if an inspection answer will drive a subsequent edit, confirm its
target objects and connections in the live candidate before editing. Exported
Verilog used for physical measurements or equivalence claims must pass the
separate [file-based SEC](../kepler-formal/SKILL.md) handoff. Inspection never
replaces automatic SEC after a live edit.

## Validate The Handoff

With the pinned packages installed, run:

```sh
python scripts/live_inspection_regression.py --work-dir runs/inspection-check
```

This uses real NajaEDA, Kepler SEC and a separate Naja-Scope MCP server. It checks
two cumulative edits, stale-copy detection, explicit refresh, repeated queries
without reloading, and unchanged golden/proof state across export. Run
`scripts/live_session_regression.py` separately for the Jupyter no-export flow.
