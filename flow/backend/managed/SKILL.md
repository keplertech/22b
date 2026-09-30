---
name: backend-managed
description: Run backend optimization with the 22b Python session helper for cumulative structural edits, checked checkpoints, undo and measured best results. Use for the managed execution flavor, not direct tool orchestration.
---

# Managed Backend

Follow the [backend objectives](../SKILL.md) and
[shared session policy](../../session-policy.md). Use this mode's instructions
only; do not load the direct-mode recipe unless the caller switches modes.

1. Follow [session startup](../../../tools/live-session.md) to create one
   `VersionedDesignSession` in a dedicated Python/Jupyter kernel. Keep golden
   unchanged. Configure retention (ten edited checkpoints by default) and the
   measurement objective using [session history](../../../tools/session-history.md).
2. Review the NajaEDA script, then call `session.apply_edit(script)`. The helper
   validates it, runs live SEC, exports a numbered candidate and runs file SEC.
   Keep both proof outcomes and actual coverage; a warning is not full proof.
3. Resolve `session.checkpoint()` for current or an explicit revision for
   history. Load that file and `session.libraries` into the separate Scope MCP
   server. Use `session.use_checkpoint()` to pin inputs during external runs.
4. Run OpenROAD under the same physical setup. Record actual measurements and
   reports with `session.record_measurement(...)`; let the configured objective
   select best, never substitute estimated improvements.
5. For undo, use `session.undo()`, not manual database reset or file deletion.
   After successful restoration, get `session.mcp_attachment()` again and
   reattach external Kepler clients. Refresh Scope to the restored checkpoint.

A failed edit may leave an unsaved live candidate; repair it or undo to the last
saved checkpoint. Do not treat that checkpoint as the current live state while
the helper reports unsaved changes. Rejected proofs and tool errors stop progress.
The older no-export helper is an explicit compatibility option, not an automatic
fallback when checkpointing fails.
