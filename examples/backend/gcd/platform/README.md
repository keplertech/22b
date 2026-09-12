# GCD Platform Inputs

This directory describes the physical test environment, not an optimization.
Use the [packaged tools](../../../../tools/README.md).

- Technology: SKY130HD, with the Liberty/LEF/RC files selected by the pinned
  OpenROAD fixture in [toolchain.json](../../../../toolchain.json).
- Top: `gcd`; input and SDC are in the parent example directory.
- Die: `{0 0 299.96 300.128}`; core: `{9.996 10.08 289.964 290.048}`.
- [fetch_fixture.py](fetch_fixture.py) downloads only the pinned fixture data.
  Its argument is a destination directory. Existing complete caches are
  checksum-verified; incomplete or modified caches require a fresh path.
  The three upstream flow scripts (`helpers.tcl`, `flow_helpers.tcl`, `flow.tcl`)
  come from `openroad.source_revision`, matching the packaged binary's API.
  The PDK, platform variables and remaining data keep `gcd.fixture_revision`.
  Both revisions are recorded and checked in the download manifest. Use the
  new `.cache/gcd-fixture-v2` cache; do not overwrite a previous experiment's data.
- [run.tcl](run.tcl) is the same physical setup for any baseline or candidate.
  It takes absolute `GCD_RUN_DIR`, `GCD_TEST_DIR`, `GCD_INPUT`, and `GCD_SDC`
  environment paths. `GCD_TEST_DIR` is the downloaded fixture's `test/` directory.
  Invoke it with `openroad -no_init -exit -metrics <new-stage>/metrics.json`.

The original SDC uses a fixture helper named `set_all_input_output_delays`;
the Tcl wrapper loads that helper before reading the SDC. A standalone SDC
load without the helper is not equivalent to this setup.

The wrapper writes setup/hold/electrical/power reports, metrics, final physical
files, and completion/routing/DRC markers. Use a fresh stage directory and the
same package for both designs. Never reuse the historical demonstration as
the baseline of a run with a different package.

The matching upstream flow selects its thread count with
`getconf _NPROCESSORS_ONLN`. Run both designs on the same host. The regression
checks `openroad -version` against the pinned source revision before running.
