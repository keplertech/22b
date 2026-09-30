# Direct Revision Recipe

This is an agent-executed procedure, not another Python flow helper. Use normal
file operations, reviewed NajaEDA scripts and direct MCP calls. Apply the
[session policy](session-policy.md); do not import the session, history or Scope
adapter modules from 22b to carry out these steps.

## Start And Record

Create a private, unused `runs/session_<UTC-date>/` directory; include finer time
precision or a unique suffix if needed. Keep immutable `inputs/`, numbered
`versions/revision-0000/` directories, a separate `attempts/` log, and independent
`best/` when a measured winner exists. Initialize a session manifest with mode,
flow, retention (default ten), current revision zero, next attempt number,
objective if supplied, and hashes of original inputs and settings.

Each published revision records its parent, file hashes, edit script, verification
options, proof result and actual coverage. Include measurement context/report
paths when available. For RTL, include the entire source bundle and frontend
configuration, plus hashes linking generated structural files to those sources.
No particular manifest schema is consumed by the flow helper in direct mode;
choose a clear JSON format and keep it consistent within the session.

## Edit And Publish

1. Read the current manifest and verify input hashes. Serialize mutations: do
   not edit, switch Scope, undo or prune while another operation uses the design.
2. Reserve a never-reused attempt number and create a fresh staging directory.
   Copy the current candidate's inputs, not a stale physical-tool output. Review
   and syntax-check the script before executing it.
3. In a fresh candidate-only Python process, load libraries and the selected
   structural file with [NajaEDA](../tools/najaeda/SKILL.md), edit and dump to the
   staging directory. Golden remains a read-only file, not a mutable peer in
   this process. A crash or partial edit leaves current unchanged.
4. Call [Kepler MCP](../tools/kepler-formal/SKILL.md#file-based-verification)
   directly on original golden and the dumped candidate, explicitly selecting
   SEC. Save the full response, report text and input hashes. Interpret the
   actual verdict and coverage; transport success alone is not proof.
5. Only a supported full proof or explicitly labelled non-blocking warning may
   publish a structural checkpoint. Keep errors/counterexamples in attempts,
   not selectable versions. Write its manifest and rename staging to the final
   revision directory, then atomically replace the session's current manifest.
   If interrupted, reconcile incomplete publication rather than guessing current.
6. Run external tools on the exact published file and record their hashes with
   results. Scope reload and physical measurement are explicit agent actions.
   For source-only RTL, retain tests and an explicit SEC-unavailable state, not
   a structural checkpoint falsely labelled verified or eligible for proved best.

## Inspect And Undo

Resolve current through the manifest, or use the requested retained revision.
In the separate [Scope MCP](../tools/naja-scope/SKILL.md) server, reset only its
own copy, load libraries and the selected Verilog, and confirm top/loaded paths.
Record revision and file hashes with query results. Reuse that loaded copy only
while it still corresponds to the selected immutable files. After a switch or
undo, invalidate the old loaded-revision claim and reload before answering.

To undo, identify the previous retained checkpoint from the manifest lineage.
After a failed unpublished attempt, keep/restore the existing current checkpoint
instead of discarding it. Check target hashes and reverify its saved design
against original golden in a fresh proof directory. For RTL restore the matching
source bundle too and rerun the applicable checks. In this file-based flavor,
restoration means making this verified file bundle the next tool input; the next
NajaEDA process loads it, and Scope must be refreshed. There is no hidden live
candidate that is magically rolled back.

After successful validation, update current and refresh Scope; only then remove
the discarded checkpoint. Failed restore leaves current and history unchanged.
Keep failure/proof diagnostics outside the deleted bundle, preserve best, and
never decrement the attempt counter. If a separate live session exists, do not
reuse its old IDs/proofs: an explicit handoff is needed, not a silent mode switch.

## Retention And Best

After publishing, prune only this session's superseded edited checkpoints beyond
the configured limit. Baseline, current, in-use files and best must survive. Undo
may skip pruned revisions; make the selected retained parent explicit.

For best, compare actual reports under identical constraints, libraries, corner,
tool versions, frontend/physical flow and relevant seed/thread settings. Apply
the recorded objective and bounds. Reject absent/nonfinite metrics and missing
evidence. Copy the winning bundle independently to a temporary best directory,
validate its hashes, then replace best and its metadata; do not use a symlink
to a prunable checkpoint. Failed replacement must leave the previous best usable.

The regression exercises this recipe on a small structural fixture using real
NajaEDA, Scope MCP and Kepler MCP. It is not an agent-reasoning evaluation or
evidence of behavioral RTL synthesis support.
