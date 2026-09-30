# Session Policy For Both Modes

These are shared rules, not executable enforcement. Managed mode implements
structural checkpoint operations in its helper; direct mode follows the
[file-based recipe](direct-revisions.md) through agent tool calls.

- Keep original golden, constraints, libraries and tool/frontend settings
  immutable and hashed. Candidate history is never a replacement for golden.
- Use a unique dated session directory and numbered revisions. Reserve a fresh
  increasing number for each edit attempt; failures and undo never reuse it.
  Keep an explicit current revision, not a newest-timestamp guess.
- Save baseline revision zero permanently. Default retention is ten recent
  edited checkpoints, configurable per session. Keep inputs being used by an
  external tool, baseline and an independent best copy out of pruning.
- Review and syntax-check edits before execution. Record real SEC outcome and
  coverage for each supported edited design. Exported files need their own
  verification; a live proof does not certify Verilog serialization.
- Partial or inconclusive proofs with usable coverage remain explicitly
  unproven warnings. Counterexamples, zero usable coverage, tool errors and
  timeouts stop the candidate flow. Never publish missing evidence as success.
- Undo restores the preceding retained version (or the last saved version
  after an unsaved failed attempt). Verify restoration before deleting the
  discarded checkpoint. Invalidate obsolete Scope observations, proofs and
  live design references. Never reset a universe holding golden to undo candidate.
- Keep each measurement tied to the exact revision, input hashes and physical
  context. Select best by a recorded objective and bounds, not by intuition.
  Full exported proof is required for promotion by default; any explicit
  allowance for unproven results must remain visible in best's metadata.
- Best is an independent bundle of design, proof, measurements and provenance;
  it survives undo and rolling retention. Without an objective, do not invent
  one or automatically select best. A changed objective/setup starts a new
  comparison rather than mixing incomparable results.

For RTL, also preserve source files and their correspondence to elaborated
structural artifacts. Helper undo covers only the structural candidate; direct
bundle restoration must include source/configuration. Report unavailable
frontend/SEC stages explicitly rather than claiming an unsupported RTL proof.
