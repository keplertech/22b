# Agent MCP Setup

Install the pinned Kepler Formal MCP and register its tools **directly with
the agent app**. This is separate from the internal MCP client used by the
live-edit helper. Setup targets Codex and Claude Code, not model names. An
Ollama-backed agent needs its own MCP-capable host; Ollama alone is not configured
by this command. No model, account credentials or global agent settings change.

## Install And Register

From the 22b root, using Python 3.13, preview first:

```sh
python3.13 setup/mcp.py configure --client codex
python3.13 setup/mcp.py configure --client codex --apply
# Or, for Claude Code:
python3.13 setup/mcp.py configure --client claude-code --apply
```

The same installer checks and reuses `.venv`, installs only missing/mismatched
pins, tests real MCP initialization, lists tools and calls Kepler's native
information tool, then writes the selected client's **project-local** config:

| Client | Generated file | Activation |
| --- | --- | --- |
| Codex | `.codex/config.toml` | Trust the project, reload the client, check `/mcp` |
| Claude Code | `.mcp.json` | Approve the project MCP server, reload, check `/mcp` |

Use `--venv /absolute/existing-venv` to reuse the kernel's environment, and
`--project /absolute/project` to configure a different project. An existing venv
is modified only with `--apply`; use a dedicated one if its other packages must
remain unchanged. Config entries use absolute paths to that interpreter and
this checkout's launcher, so keep both at those paths. Regenerate after moving.

Existing unrelated configuration is preserved and backed up before changes.
An identical entry is reused; a conflicting entry stops setup before install.
Review it manually or use `--name another-name`; setup never silently replaces
an existing server. Local paths and config backups should not be committed.
The standard generated files are ignored by this repository.

The installer uses [pinned native wheels](../tools/python-requirements.txt),
[kernel packages](../tools/session-requirements.txt) and the
[pinned pure-Python wrapper](../tools/kepler-formal/mcp-requirements.txt).
No Nix, native build or source submodule is needed for this MCP. Missing native
wheels are an error, not permission to compile. The launcher checks the package
pins on every startup. Transitive dependencies are not fully locked.

Check an existing installation without installing or changing configuration:

```sh
python3.13 setup/mcp.py check --venv .venv
```

This checks transport/tool discovery and native loading, **not** whether your
agent has approved or displayed the tools, and not circuit equivalence. In the
agent's tool list confirm `get_kepler_formal_info`, `attach_session`,
`verify_session` and `get_session_reports`. Existing user/admin settings can
override or block project settings; resolve that in the host rather than
overwriting them. Keep normal host approval controls enabled. Codex's generated
tool timeout allows a 600-second proof plus transport overhead; for other hosts
ensure their MCP call timeout also accommodates the requested proof duration.

## Attach To The Live Designs

Start the [persistent session](../tools/live-session.md) in a dedicated kernel
using this same environment. In that kernel:

```python
attachment = session.mcp_attachment()
```

Then the **agent's registered Kepler tools**, not a new notebook MCP client, do:

1. Call `attach_session` with `attachment["connection_file"]`.
2. Require its returned session ID to match `attachment["session_id"]`.
3. Call `verify_session` with that session ID and the returned `design1` and
   `design2` native references. Set `verification="sec"`, `solver="kissat"`,
   `max_k=32`, `sec_engine="pdr"`, `sec_encoding="dual_rail_steady"`,
   `report_skipped_outputs=true`, `allow_boundary_mismatch=false`, and an
   appropriate `timeout_seconds` (600 by default).
4. Call `get_session_reports` with the result's `report_id` and session ID.
   Require the exact design pair and report identity to match. Apply the
   [SEC evidence rules](../tools/kepler-formal/SKILL.md), including proof coverage.

Use the native references as returned; golden/candidate are local roles, not
MCP aliases. Keep edits and direct proofs sequential. Recheck
`session.mcp_attachment()` after a direct proof: its revision and references
must still match the ones observed before it. A proof for an older revision
does not certify the current candidate.

Do not read, print or upload the connection file's token. Only its path is
returned. Attachment requires the same machine/user and permission to reach
the loopback bridge; a remote or sandboxed agent may need approved access.
Do not load/reset designs through another server or bypass `session.apply_edit`.
That method still enforces script validation and automatic SEC independently
of the model. Direct tools provide additional explicit agent verification;
they do not replace that mandatory check or overwrite its recorded proof.
Detach with `close_session`; this leaves the caller's designs alive. Closing
the owner session invalidates the attachment.

## Validation

```sh
python -m unittest discover -s tests -v
.venv/bin/python scripts/agent_mcp_regression.py --work-dir runs/agent-mcp-check
```

The real regression launches the generated server entries as independent MCP
clients, attaches to the live owner, proves both cumulative edits, rejects a
counterexample and checks that detaching preserves the designs. It does not
claim to test an interactive Codex or Claude model session.

Client formats: [Codex MCP documentation](https://developers.openai.com/codex/mcp)
and [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).
