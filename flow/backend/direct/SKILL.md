---
name: backend-direct
description: Run backend optimization through NajaEDA Python, Naja-Scope MCP, Kepler Formal MCP and OpenROAD directly, with agent-managed revision files and no 22b flow helper.
---

# Direct Backend

Follow the [backend objectives](../SKILL.md),
[shared session policy](../../session-policy.md) and
[direct revision recipe](../../direct-revisions.md). Do not instantiate a 22b
session helper or use its checkpoint, undo or Scope adapter. The agent performs
the documented steps; no Python flow controller is installed by this skill.

1. Preserve baseline design, libraries and constraints. Run baseline OpenROAD
   and keep the reports before proposing an edit.
2. Select the numbered design file, load it in the separate
   [Scope MCP](../../../tools/naja-scope/SKILL.md) server, and inspect connectivity.
3. Review and syntax-check the proposed script. Use the
   [NajaEDA Python API](../../../tools/najaeda/SKILL.md) in a fresh candidate
   process to load the selected file, edit it and export to a new staging path.
   NajaEDA is a Python library here, not a separately configured editing MCP.
4. Call the agent's [Kepler MCP tools](../../../tools/kepler-formal/SKILL.md)
   directly on golden versus the exported file, explicitly selecting SEC.
   Preserve the structured result, reports, hashes and actual coverage.
5. Publish the revision only after interpreting the proof. Measure it with
   [OpenROAD](../../../tools/openroad/SKILL.md) under unchanged settings; record
   the revision and hashes with every report. Promote best only on comparable
   measured improvement under the recorded objective and proof policy.
6. Restore and reverify the previous retained file when undo is requested.
   Refresh Scope and external inputs before discarding the undone checkpoint.

Use the agent's registered MCP connections, not a hidden notebook flow client.
The [setup guide](../../../setup/README.md) registers Kepler; Scope has its own
installation/client instructions. Direct mode has no automatic edit validator,
mandatory-SEC gate, retention scheduler or crash recovery. The skill requires
those actions but cannot guarantee the agent performed them: retain evidence.
