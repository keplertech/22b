# Numbered Netlist History And Undo

Use `VersionedDesignSession` when exploration needs saved netlists, rollback,
Scope inspection and physical measurements. It extends the existing
[live session](live-session.md); the original no-export mode is unchanged.
All implementation is in 22b, using the existing packaged tools.

```python
from tools.versioned_session import VersionedDesignSession

session = VersionedDesignSession(
    reference="original.v", liberty_files=["cells.lib"],
    sessions_root="runs", retention=10,
    objective={
        "weights": {"setup_ns": -1},  # Minimize score: maximize slack.
        "bounds": {"hold_ns": {"min": 0}, "routing_drc": {"max": 0}},
    },
)
```

The default directory is `runs/session_<UTC-date-and-time>/`. An explicit,
unused `work_dir` is also supported. The date identifies the session, not the
netlist revision. Numbered `versions/revision-0000/`, `revision-0001/`, etc.
contain `design.v`, a manifest, edit script where applicable, and export proof.
`inputs/` preserves original Verilog and Liberty files. Keep constraints and
physical setup immutable too; record their hashes in measurement context.

Initialization proves the baseline and saves revision zero. Every validated
`apply_edit(script)` runs mandatory live SEC, exports the result, and runs
separate file-based SEC before publishing its checkpoint. Counterexamples and
tool errors are hard failures; partial proof remains explicitly unproven.
Incomplete checkpoint writes are never selected as current. Failed attempts
retain diagnostics, not accepted versions. If live editing succeeds but
checkpointing fails, current inspection is blocked until repair or undo.

## Select And Inspect

```python
current = session.checkpoint()         # Latest retained, active netlist.
baseline = session.checkpoint(0)       # Explicit historical selection.
session.configure_history(retention=20)
```

Retain ten recent edited checkpoints by default, plus the permanent baseline.
Numbers use the existing edit-attempt counter: failures can leave gaps, and undo
never reuses a number. `session.status()["revision"]` is the attempt counter;
`session.status()["netlist_revision"]` is the active saved netlist. Manifests
and file hashes are checked before reuse.

Naja-Scope runs in a separate process. With an agent's direct MCP tools, resolve
`session.checkpoint()` (or an explicit revision), then load its Verilog and
`session.libraries` through Scope's reset/load tools if the selected copy changed.
Never reset the editing kernel. Confirm Scope's status and record the revision
with answers; current-design questions must not reuse historical data.

For an existing synchronous MCP client, `ScopeCheckpoints(session, call)` in
[scope_checkpoints.py](scope_checkpoints.py) automates selection and refresh.
`call(tool, arguments)` returns the parsed payload and must raise on MCP errors.
`query(tool, arguments, revision=None)` defaults to current, supports historical
versions and reuses an unchanged loaded copy. It does not register an MCP with
the agent or replace the agent's own client configuration. Do not let another
writer share that Scope server during queries.

Use `with session.use_checkpoint() as checkpoint:` around external runs. This
pins their input, prevents mid-run undo/pruning, and checks hashes afterward.
The API is for trusted local callers, not a filesystem security sandbox.

## Undo

```python
result = session.undo()
attachment = session.mcp_attachment()  # External Kepler clients reattach here.
```

Undo validates the previous saved file, restores only the candidate in the same
Python kernel, and reruns SEC against unchanged golden. Only after success does
it delete the discarded latest checkpoint. Undo after an unsaved failed edit
restores the latest good checkpoint without deleting it. If intermediate versions
were pruned, undo selects the preceding retained version; baseline is permanent.

Naja can reuse native IDs on reload. Undo expires the old Kepler attachment and
creates a new binding identity; external MCP clients must reattach and obtain
fresh references. The Python session remains alive, and golden is not reloaded.
Old proof reports remain historical. The attempt counter never decreases.
If native restoration fails, the session is marked invalid and no checkpoint is
deleted; retain the files and start a new session rather than using that candidate.

## Measurements And Best

```python
session.record_measurement(
    {"setup_ns": 0.04, "hold_ns": 0.02, "routing_drc": 0},
    context={"constraints_sha256": "recorded-hash", "tool_version": "recorded-version"},
    evidence=["physical-run/summary.json", "physical-run/power.rpt"],
)
```

These values illustrate the API, not actual measurements. Supply parsed tool
results and evidence, never model estimates. The helper checks numeric validity,
required metrics, consistent context, proof policy and objective bounds; it does
not establish that arbitrary caller-provided metrics are true. Include libraries,
corners, flow, seed/thread settings and constraints in context. Each external run
needs a fresh output directory and an identified checkpoint.

The objective minimizes the weighted sum subject to bounds. Choose units,
normalization and weights explicitly for combined goals. No objective means no
automatic best selection. Equal/worse or infeasible results do not replace best.
Promotion requires full exported SEC proof by default; `allow_unproven: True`
explicitly permits warning-labelled results without claiming full equivalence.
The general non-blocking warning policy is unchanged.

`best/` holds an independent copy of the netlist, proof and measurements, not a
symlink into rolling history. Undo and pruning cannot delete it. Changing the
objective or physical setup requires a new comparison/session. Baseline and best
are protected independently of the rolling retention limit.

## Validation

The new [GCD packaged undo workflow](../.github/workflows/gcd-undo-verify.yml)
uses the same packaged tools and reference rewrite as the existing GCD workflow,
which is unchanged. It checks original/edited/restored Scope connectivity, full
SEC coverage, timing improvement, discarded-netlist deletion and best preservation.
It runs OpenROAD three times and requires restored setup, hold, TNS, area, power
report and DRC results to match this run's baseline exactly.

```sh
python -m unittest discover -s tests -v
python scripts/versioned_session_regression.py --jupyter --work-dir runs/history-check
python scripts/gcd_undo_regression.py --work-dir runs/gcd-undo-check
```

Offline tests do not prove equivalence or physical results. The real history
regression also tests failed-edit recovery, Scope refresh, continued editing,
retention and rejection of stale native references after undo.
