# GCD Reference Solution And Replay

**Contains the answer.** This is a worked reference for comparison and tool
regression, not initial context for the independent [model task](../task.md).
The scripts below replay a reviewed edit; they do not generate a new solution.

The [dedicated workflow](../../../../.github/workflows/gcd-reference-verify.yml)
installs packaged tools and runs the baseline, read-only Naja-Scope inspection,
saved NajaEDA edit, SEC, and candidate physical flow. It preserves fresh evidence
and compares the new measurements, not the historical values below. It requires
full SEC proof for this known small reference case; this stronger test assertion
does not change the shared policy for exploratory partial/inconclusive proofs.
Verification uses the Python-backed Kepler Formal MCP, not the legacy Nix CLI.

Small mapped SKY130HD GCD design: 249 original leaf cells, 4.36 ns clock period.
Five serial majority gates (`_215_` through `_219_`) are replaced with a 31-gate
generate/propagate prefix network. All five original output nets are reused,
including their side consumers. Registers and cycle boundaries stay unchanged.

The arithmetic identity is `majority(a,b,c) = (a & b) | ((a | b) & c)`.
Computing group generate/propagate terms in parallel reduces carry dependence.
Fewer logic levels, not fewer initial gates, is the timing hypothesis. The
edited design has 275 leaf cells before physical optimization.

## Contents

- [input.v](../input.v): original mapped design, never edited in place.
- [constraints.sdc](../constraints.sdc): original clock and I/O constraints.
- [edit.py](edit.py): reviewed standalone NajaEDA rewrite from the recorded demo,
  with additional input/name/output guards. Not a fresh model generation.
- [request.md](request.md): saved, solution-specific request for this reference.
- [fetch_fixture.py](../platform/fetch_fixture.py): downloads pinned flow/technology data only.
- [run.tcl](../platform/run.tcl): separate baseline or candidate OpenROAD run and final reports.
- [historical-results.json](historical-results.json): prior demo measurements.
- [LICENSE.OpenROAD](../LICENSE.OpenROAD): upstream notice for copied design/SDC data.

## Package Setup

For automated replay after package setup, from the repository root:

```sh
python scripts/gcd_reference_regression.py --work-dir runs/gcd-reference
```

The run directory must not already exist. Installation belongs to the workflow
and [package guides](../../../../tools/README.md), not the model task.

Follow [tool installation](../../../../tools/README.md). Use the same OpenROAD
package for both runs. The prior demo used the Docker image recorded in
`toolchain.json`; do not substitute those historical measurements for a new run.
The shared Python environment pins Kepler Formal, NajaEDA and both MCP servers.

From the repository root, in the Python environment with NajaEDA installed:

```sh
export ROOT="$PWD"
export EXAMPLE="$ROOT/examples/backend/gcd"
export FIXTURE="$ROOT/.cache/gcd-fixture-v2"
python "$EXAMPLE/platform/fetch_fixture.py" "$FIXTURE"
export LIBERTY="$FIXTURE/test/sky130hd/sky130hd_tt.lib"
export RUN="$ROOT/runs/gcd-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN"
openroad -version > "$RUN/openroad-version.txt"
nix profile list --json > "$RUN/nix-profile.json"
python -m pip freeze > "$RUN/python-packages.txt"
```

The fixture combines data from immutable OpenROAD revisions, not a tool source
checkout. The downloader verifies checksums before reusing a complete cache.
The flow scripts match the packaged OpenROAD source revision; technology data
retains the original fixture revision. Both are recorded in the manifest.
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
  "$EXAMPLE/platform/run.tcl" 2>&1 | tee "$RUN/baseline/openroad.log"
```

Require `GCD_COMPLETE=1`, `GCD_ROUTED=1` and `GCD_FINAL_DRC=0` in the log.
Reports and final physical files are under the stage directory. The SDC's
`set_all_input_output_delays` is a fixture helper, not a standalone SDC command;
the Tcl wrapper loads that helper before reading the constraints.

## 2. Inspect And Explain

Read `baseline/reports/setup.rpt`, then use [Naja-Scope](../../../../tools/naja-scope/SKILL.md)
to inspect the five-gate cone, drivers and loads. Show the full layout and the
critical path from the actual OpenROAD database if images are needed. Save the
model's actual request/response and proposed change in `analysis.md`.

The saved [request.md](request.md) documents this known rewrite. For deterministic
replay, inspect the reports and reviewed script without claiming a model produced
new analysis. For an independent agent attempt use [task.md](../task.md) instead,
without this directory in its initial context.

## 3. Apply The NajaEDA Edit

```sh
python -m py_compile "$EXAMPLE/reference/edit.py"
python "$EXAMPLE/reference/edit.py" --liberty "$LIBERTY" \
  --input "$EXAMPLE/input.v" --output "$RUN/candidate.v" | tee "$RUN/edit.log"
```

The script refuses an existing output file and checks the original carry chain
before editing. Run without Python's `-O` flag, which disables its assertions.
Input hashes and the 2,048-case Boolean truth table are checked by the offline
tests; those checks do not replace SEC of the exported candidate.

## 4. Prove With Kepler SEC

```sh
python tools/kepler-formal/verify.py \
  --reference "$EXAMPLE/input.v" --candidate "$RUN/candidate.v" \
  --liberty "$LIBERTY" --work-dir "$RUN/proof" --require-full-outputs 18
cat "$RUN/proof/summary.json"
cat "$RUN/proof/kepler.log"
```

**Stop and interpret the proof before running the next stage.** Follow the
[SEC outcome policy](../../../../tools/kepler-formal/SKILL.md): counterexamples and
tool errors stop the flow. Exploratory partial/inconclusive proof is a warning,
but this known reference requires all 18 outputs to be proved. The command
returns nonzero otherwise; do not run the next stage on failure. The automated
replay enforces that ordering. Proof evidence includes the MCP response, checked
and proved counts, skipped-output reports, native log and explicit SEC settings.

## 5. Candidate Physical Design

```sh
mkdir "$RUN/candidate"
GCD_RUN_DIR="$RUN/candidate" GCD_TEST_DIR="$FIXTURE/test" \
GCD_INPUT="$RUN/candidate.v" GCD_SDC="$EXAMPLE/constraints.sdc" \
  openroad -no_init -exit -metrics "$RUN/candidate/metrics.json" \
  "$EXAMPLE/platform/run.tcl" 2>&1 | tee "$RUN/candidate/openroad.log"
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
