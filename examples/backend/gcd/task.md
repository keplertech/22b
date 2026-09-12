# Improve GCD Setup Timing

Use 22b's [orchestration skill](../../../SKILL.md) and
[backend skill](../../../flow/backend/SKILL.md) to improve setup timing of the
supplied GCD design through behavior-preserving logic restructuring. Identify
the opportunity yourself from fresh tool results; no particular rewrite is prescribed.

The design is [input.v](input.v), top `gcd`. Use the original
[constraints.sdc](constraints.sdc) and [SKY130HD platform](platform/README.md).
Target nonnegative setup slack; if you cannot reach it, report the measured
improvement or lack of improvement honestly.

## Constraints

- Preserve the original design and constraints. Keep registers, clock/reset
  behavior, interfaces, pipeline boundaries, and cycle latency unchanged.
- Compare against a fresh baseline with the same tool versions, physical
  setup, timing corner, activity assumptions, and clock/I/O constraints.
- Explain the proposed change before editing. Validate the exported candidate
  with Kepler Formal SEC and report the actual proof outcome and coverage.
- Do not trade an apparent setup win for hidden hold or routing violations.
  Report area and estimated-power tradeoffs, not only timing.
- Do not use `reference/`, its replay scripts, historical results, or demo as
  solution input. The shared skills and platform files are allowed context.

## Deliverable

A separate candidate and a concise explanation supported by current reports:
the timing bottleneck, chosen edit, reviewed NajaEDA script, SEC outcome with
coverage and skipped outputs, and before/after timing, area, estimated power,
hold, and routing checks. Preserve commands, versions, input hashes, logs, and
reports with the attempt. Label partial or inconclusive proof as unproven;
counterexamples and tool errors are not successful results.
