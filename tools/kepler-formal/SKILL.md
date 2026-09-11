---
name: kepler-formal
description: Run Kepler Formal SEC on reference and candidate hardware designs and interpret proof outcomes, checked-output coverage, skipped outputs, counterexamples and execution errors without conflating them.
---

# Verify An Exported Candidate

Use the [Nix package guide](install.md) if needed. Always request SEC, including
for purely combinational edits. Keep the exact reference and candidate files,
libraries, elaboration settings, command, exit code and complete logs.

For mapped Verilog, run from a fresh proof directory:

```sh
kepler-formal -verilog --verification sec --report-skipped-pos \
  /absolute/reference.v /absolute/candidate.v /absolute/cells.lib \
  > kepler.log 2>&1
```

Capture the exit code even when nonzero. For RTL use `-sv` and explicit
`--sv_design1_flist`, `--sv_design1_top`, `--sv_design2_flist` and
`--sv_design2_top`. Check the installed CLI's help for elaboration options.
The package's [flag reference](https://github.com/keplertech/kepler-formal/blob/0e0abf2aa6979e337aead8996983952dc1742530/docs/sec-flags-spec.md)
defines the SEC assumptions and engines.

## Interpret Evidence

| Outcome | Flow behavior |
| --- | --- |
| Explicit full proof, consistent coverage | Report equivalence under the reported assumptions |
| Explicit partial or inconclusive proof | Non-blocking warning; keep unproved/skipped counts visible |
| Counterexample | Reject candidate; investigate the difference |
| Parse/extraction failure, crash, timeout, missing/contradictory outcome | Tool error; stop and investigate |

Do not use exit status alone: tool errors can overlap proof outcome codes.
Inspect the actual SEC summary, checked/existing output counts, partial-proof
counts and skipped-output reports. Covered outputs and proved outputs are not
the same statistic. Zero unmatched outputs alone does not establish coverage.

If no observed outputs remain and SEC cannot run, report a tool/extraction error,
not a harmless partial-proof warning. Always specify the proof abstraction,
depth/engine when reported, and assumptions that constrain an equivalence claim.

After a gate edit, verify the exported file as reloaded by Kepler. An in-memory
truth check cannot detect exporter naming/alias errors in the final Verilog.
