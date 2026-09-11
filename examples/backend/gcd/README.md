# GCD: One Timing-Improvement Iteration

Small mapped SKY130HD GCD design: 249 original leaf cells, 4.36 ns clock period.
Five serial majority gates (`_215_` through `_219_`) are replaced with a 31-gate
generate/propagate prefix network. All five original output nets are reused,
including their side consumers. Registers and cycle boundaries stay unchanged.

The arithmetic identity is `majority(a,b,c) = (a & b) | ((a | b) & c)`.
Computing group generate/propagate terms in parallel reduces carry dependence.
Fewer logic levels, not fewer initial gates, is the timing hypothesis. The
edited design has 275 leaf cells before physical optimization.

## Contents

- [input.v](input.v): original mapped design, never edited in place.
- [constraints.sdc](constraints.sdc): original clock and I/O constraints.
- [edit.py](edit.py): reviewed standalone NajaEDA rewrite from the recorded demo,
  with additional input/name/output guards. Not a fresh model generation.
- [request.md](request.md): task for an agent to inspect and explain the change.
- [fetch_fixture.py](fetch_fixture.py): downloads pinned flow/technology data only.
- [run.tcl](run.tcl): separate baseline or candidate OpenROAD run and final reports.
- [historical-results.json](historical-results.json): prior demo measurements.
- [LICENSE.OpenROAD](LICENSE.OpenROAD): upstream notice for copied design/SDC data.

## Package Setup

Follow [tool installation](../../../tools/README.md). Use the same OpenROAD package
for both runs. This fresh Nix-packaged flow has not yet been validated end to end;
the prior demo used the Docker image recorded in `toolchain.json`.

The published NajaEDA 0.7.20 wheel has been checked on Apple Silicon: this script
executes, exports and reloads a 275-cell candidate. Naja-Scope 0.1.11 also loads
the reference and queries its fanout through MCP. These package smoke checks
are not a new SEC proof or an OpenROAD timing measurement.

From the repository root, in the Python environment with NajaEDA installed:

```sh
export ROOT="$PWD"
export EXAMPLE="$ROOT/examples/backend/gcd"
export FIXTURE="$ROOT/.cache/gcd-fixture-v1"
python "$EXAMPLE/fetch_fixture.py" "$FIXTURE"
export LIBERTY="$FIXTURE/test/sky130hd/sky130hd_tt.lib"
export RUN="$ROOT/runs/gcd-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN"
openroad -version > "$RUN/openroad-version.txt"
nix profile list --json > "$RUN/nix-profile.json"
python -m pip freeze > "$RUN/python-packages.txt"
```

The fixture is data from an immutable OpenROAD revision, not a tool source
checkout. The downloader verifies checksums before reusing a complete cache.
It will not repair or overwrite an incomplete/modified cache automatically.
Use a fresh cache path if a download is interrupted. Keep `manifest.json` with
the experiment. No source submodule or model installation is involved.

## 1. Baseline Physical Design

Run in Bash with `set -o pipefail` so logging does not hide command failures:

```sh
set -o pipefail
mkdir "$RUN/baseline"
GCD_RUN_DIR="$RUN/baseline" GCD_TEST_DIR="$FIXTURE/test" \
GCD_INPUT="$EXAMPLE/input.v" GCD_SDC="$EXAMPLE/constraints.sdc" \
  openroad -no_init -exit -metrics "$RUN/baseline/metrics.json" \
  "$EXAMPLE/run.tcl" 2>&1 | tee "$RUN/baseline/openroad.log"
```

Require `GCD_COMPLETE=1`, `GCD_ROUTED=1` and `GCD_FINAL_DRC=0` in the log.
Reports and final physical files are under the stage directory. The SDC's
`set_all_input_output_delays` is a fixture helper, not a standalone SDC command;
the Tcl wrapper loads that helper before reading the constraints.

## 2. Inspect And Explain

Read `baseline/reports/setup.rpt`, then use [Naja-Scope](../../../tools/naja-scope/SKILL.md)
to inspect the five-gate cone, drivers and loads. Show the full layout and the
critical path from the actual OpenROAD database if images are needed. Save the
model's actual request/response and proposed change in `analysis.md`.

Use [request.md](request.md) for the analysis task. For a deterministic replay,
review the supplied script instead of claiming a model generated it anew. For a
fresh agent experiment, save and review its new script separately and validate
all boundary connections before execution.

## 3. Apply The NajaEDA Edit

```sh
python -m py_compile "$EXAMPLE/edit.py"
python "$EXAMPLE/edit.py" --liberty "$LIBERTY" \
  --input "$EXAMPLE/input.v" --output "$RUN/candidate.v" | tee "$RUN/edit.log"
```

The script refuses an existing output file and checks the original carry chain
before editing. Run without Python's `-O` flag, which disables its assertions.
Input hashes and the 2,048-case Boolean truth table are checked by the offline
tests; those checks do not replace SEC of the exported candidate.

## 4. Prove With Kepler SEC

```sh
mkdir "$RUN/proof"
(
  cd "$RUN/proof"
  # Capture nonzero proof outcomes without losing their logs.
  set +e
  kepler-formal -verilog --verification sec --report-skipped-pos \
    "$EXAMPLE/input.v" "$RUN/candidate.v" "$LIBERTY" > kepler.log 2>&1
  rc=$?
  printf '%s\n' "$rc" > exit-code.txt
)
cat "$RUN/proof/kepler.log"
```

**Stop and interpret the proof before running the next stage.** Follow the
[SEC outcome policy](../../../tools/kepler-formal/SKILL.md): counterexamples and
tool errors stop the flow; partial/inconclusive proof is a visible, non-blocking
warning. These manual commands do not implement an automatic proof gate.

## 5. Candidate Physical Design

```sh
mkdir "$RUN/candidate"
GCD_RUN_DIR="$RUN/candidate" GCD_TEST_DIR="$FIXTURE/test" \
GCD_INPUT="$RUN/candidate.v" GCD_SDC="$EXAMPLE/constraints.sdc" \
  openroad -no_init -exit -metrics "$RUN/candidate/metrics.json" \
  "$EXAMPLE/run.tcl" 2>&1 | tee "$RUN/candidate/openroad.log"
```

Compare `DRT::worst_slack_max`, `DRT::worst_slack_min`, `DRT::tns_max`,
`DPL::design_area` and power reports. Require completed routing and zero routing
DRCs in both logs; check hold and electrical violations as well as setup.
Record units from each tool's reports. View the candidate's new critical path,
which need not be the original path. Do not adjust constraints between stages.

## Historical Result, Not A New Nix Validation

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| Setup slack (ns) | -0.599800449 | +0.000132339 |
| Hold slack (ns) | +0.480459686 | +0.488284926 |
| Cell area (um^2) | 3931 | 3636 |
| Estimated power (mW) | 1.49 | 1.34 |
| Routing DRCs | 0 | 0 |

That recorded run proved all 18/18 observed outputs at k=5 under Kepler's
dual-rail steady-state abstraction. Setup improved by about 600 ps, but the
positive margin was only 0.132 ps. Power used the same default activity
assumptions and this is a typical-corner demonstration, not multi-corner signoff.

The full source revision and image are recorded in
[historical-results.json](historical-results.json). A new tool package requires
new baseline and candidate measurements; no particular improvement is guaranteed.
