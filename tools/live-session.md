# Persistent Python/Jupyter Sessions

Use this mode for cumulative NajaEDA edits with automatic SEC after each edit.
One dedicated kernel holds two designs: immutable golden and mutable candidate.
The candidate is never replaced by a reload between iterations. Both designs
have their own database and loaded Liberty definitions; library sharing and
Naja-Scope attachment are deferred. No design dump is needed for verification.

## Setup

Use the [packaged native tools](README.md) in one environment, then add the
optional kernel packages:

```sh
python -m pip install --only-binary=:all: -r tools/session-requirements.txt
```

The pinned Kepler Formal MCP includes native-ID selection and attached-session
reports. Upgrade the wrapper in both the kernel and the MCP server together;
the older named-design protocol is not compatible. Install the **pure-Python
wrapper** without rebuilding or replacing native wheels:

```sh
python -m pip install --no-deps --force-reinstall -r tools/kepler-formal/mcp-requirements.txt
python -m pip check
```

The helper checks the installed Git commit, not only the package version label.
When upgrading an existing MCP installation, the wrapper-only force reinstall
is needed because different Git revisions can share the same version label.
Reuse the installation if its commit already matches the pin.
For explicit wrapper development only, you may instead install a reviewed local
checkout with `python -m pip install --no-deps /absolute/kepler-formal-mcp` and
pass that path as `development_mcp_checkout`. This override requires installation
from that exact path and matches installed wrapper source to the checkout,
recording hashes in `packages.json`. It fails if sources change after installation.
Normal sessions and regressions do not need the override.

## Use Across Cells

Start one fresh Jupyter/Python kernel using that environment and the 22b root
as its working directory. Use a local, private connection file; do not expose
the kernel or its credentials to a network or include them in artifacts.
Keep the same kernel and `session` object across calls.

First cell:

```python
from tools.live_session import LiveDesignSession

session = LiveDesignSession(
    reference="/absolute/original.v",
    liberty_files=["/absolute/cells.lib"],
    work_dir="runs/my-live-session",  # Must not already exist.
)
initial_proof = session.verify()
```

The model supplies a reviewed script containing `def edit(top):` and optionally
pure helpers. The only design object supplied is the candidate. Its restricted
API contract is defined in [edit_validation.py](edit_validation.py); unsupported
operations are rejected, not silently rewritten. The script cannot import,
reset/load/export designs, invoke files/processes or reach private attributes.
This is validation for trusted editing code, **not an OS security sandbox**.
The notebook owner must not mutate either native design outside this API.

For every subsequent edit, in another cell of the same kernel:

```python
from pathlib import Path

script = Path("runs/proposed-edit.py").read_text()
result = session.apply_edit(script)
print(result["status"], result["proved_outputs"], result["existing_outputs"])
```

`apply_edit` validates before mutation, invalidates the previous proof, edits
the current candidate, and automatically runs SEC against original golden.
It does not ask a model to select the verification mode. The MCP attaches to
this interpreter and calls the native Python library using explicit native
references: session ID, database ID, library ID, and design ID. It resolves
those coordinates directly in the owning Naja universe; there is no
golden/candidate name registry in MCP. These are 22b's local design roles only.
All edits and verification share a native lock; concurrent work is rejected.
New cells resolve against the candidate database, not golden's library.

`session.status()` records `golden_reference` and `candidate_reference`.
Each verification request and response must identify that exact pair,
including the database and session IDs. Identical top-module names or local
design IDs in the two databases cannot redirect verification. A mismatched
pair in either the proof response or retrieved report is rejected.
These native IDs are valid only for this live universe; they are not restart
or reload handles. Do not destroy/reload designs or databases behind the
session. Close it and obtain fresh references in a new session instead.

Inspect `session.status()` for current revision, state and proof. Closing with
`session.close()` detaches the MCP and destroys only this session's universe.
Opening refuses an already-loaded universe rather than resetting user data.

## Outcomes And Recovery

| State | Meaning |
| --- | --- |
| `proved` | Full SEC proof for the current cumulative revision |
| `unproven` | Partial/inconclusive proof with actual coverage; warning, not equivalence |
| `rejected` | Counterexample or verification error; no valid proof |
| `edit_error` | Script raised; partial candidate changes remain, no valid proof |
| `verification_pending` | Timed-out verification may still be running; no edits allowed |
| `invalid` | Golden/untracked candidate/universe changed; stop this session |

A rejected script that never executes leaves the existing revision and proof
intact. An execution error or counterexample does not roll back the candidate:
inspect the error and repair that same cumulative candidate through `apply_edit`.
After a verification timeout, wait until the native call is idle and explicitly
call `session.verify()` before editing again. Never treat a timeout as a warning
proof. Do not forcibly destroy designs while native verification is running.

The session hashes native connectivity, model identities and revisions before
and after operations to detect untracked changes. Direct hostile Python can
bypass such safeguards; use trusted dedicated kernels. A script or native
crash loses the in-memory session; automatic checkpoints/recovery are not
implemented in this first version.

## Evidence And Validation

Every revision records its exact editing script. Every proof records SEC
options, native result, checked/proved counts, skipped and unproven outputs,
log and unique report identity. `get_session_reports` retrieves that completed
proof without rerunning verification. Attached reports use `structured-v1`
JSON from the actual native result, not fabricated empty text reports, and
never change the notebook's working directory. Saved old reports are historical
evidence, not proof of a later revision.

Run the real packaged integration separately from offline tests:

```sh
python scripts/live_session_regression.py --work-dir runs/live-session-check
```

It uses separate cells in one actual Jupyter kernel and the actual MCP/native
SEC: two cumulative equivalent edits, a rejected counterexample, repair,
invalid-script rejection, and stale-proof detection. No design export occurs.
`python -m unittest discover -s tests -v` checks policy offline, not native proof.

Physical-design tools still require exported input files. An in-memory proof
alone does not certify the eventually exported file; use the existing
[file-based verifier](kepler-formal/SKILL.md) for that separate handoff.
