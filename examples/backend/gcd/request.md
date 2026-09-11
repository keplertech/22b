# Inspect The GCD Carry Chain

Read the baseline's final setup and hold reports. Explain the actual critical
path and its dominant delay using reported numbers, not assumptions.

Load the original GCD through Naja-Scope with the matching SKY130HD Liberty.
Inspect the majority gates `_215_`, `_216_`, `_217_`, `_218_`, `_219_`, their
input drivers and every output consumer. Preserve exact instance/pin names.
Determine whether a parallel generate/propagate rewrite is appropriate and
explain its timing hypothesis, gate-count tradeoff and hold risk.

Before any edit, explain the proposed change. Preserve all registers, resets,
cycle boundaries and all five boundary output connections. If approved,
generate a NajaEDA script that captures the original nets, connects the full
replacement, then deletes the five original gates. Use the relevant
gate-replacement skill rather than unrelated constant-source helpers.

Run SEC on the exported candidate and report proof coverage, skipped outputs
and any limitations. Rerun OpenROAD with the original constraints and settings;
compare actual reports and new critical paths. Do not claim improvement from
the Boolean identity or the old demonstration's results alone.
