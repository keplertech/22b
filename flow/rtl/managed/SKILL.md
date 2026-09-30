---
name: rtl-managed
description: Coordinate RTL development with a helper-managed structural-edit stage, retaining original RTL and elaboration context while using checked checkpoints and undo where the installed tools support the representation.
---

# Managed RTL

Follow [RTL design guidance](../SKILL.md) and
[shared session policy](../../session-policy.md). This mode does not make the
session helper a behavioral RTL editor or supply an implicit synthesis tool.

1. Preserve the reference RTL, file list, parameters, includes, defines, top,
   clocks/resets and the selected frontend configuration. Run the chosen RTL
   lint/simulation checks for source edits; retain source revision hashes.
2. When an explicitly configured frontend produces a supported structural
   reference, follow [session startup](../../../tools/live-session.md) and
   create `VersionedDesignSession`. Associate its baseline with the source and
   frontend hashes. If no supported structural representation exists, report
   the blocked helper/SEC stage; do not invent an RTL proof or switch modes.
3. Review a NajaEDA `edit(top)` script and call `session.apply_edit(script)`.
   Keep live and checkpoint SEC outcomes, coverage and the correspondence to
   the RTL source. The helper operates on structural objects, not source text.
4. Inspect selected checkpoints with Scope. Use `session.undo()` to restore a
   structural revision, then refresh Scope and external Kepler attachments.
   This does not undo RTL files, rerun elaboration or recover source code.
5. A later source-level RTL change needs matching frontend settings and a new
   traceable structural candidate; do not reload it behind the helper or use a
   proof of an earlier structural edit as proof of the new RTL. Preserve the
   original reference and verify each candidate against it.

Use [session history](../../../tools/session-history.md) for retention and best
measurements. Delegate physical measurements to the backend flow with the same
managed choice. A design with no reference needs functional tests; it cannot
gain a specification-equivalence claim through self-comparison.
