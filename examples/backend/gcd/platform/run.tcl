# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2019-2026, The OpenROAD Authors
# Adapted from the OpenROAD GCD test configuration and reporting recipe.
foreach key {GCD_RUN_DIR GCD_TEST_DIR GCD_INPUT GCD_SDC} {
  if {![info exists ::env($key)]} { error "Missing environment variable $key" }
}
set run_dir [file normalize $::env(GCD_RUN_DIR)]
set fixture [file normalize $::env(GCD_TEST_DIR)]
set synth_verilog [file normalize $::env(GCD_INPUT)]
set sdc_file [file normalize $::env(GCD_SDC)]
foreach path [list $synth_verilog $sdc_file] {
  if {![file isfile $path]} { error "Missing input $path" }
}
if {[file exists [file join $run_dir results]]} {
  error "Refusing to overwrite existing results in $run_dir"
}
file mkdir [file join $run_dir results]
set reports [file join $run_dir reports]
file mkdir $reports
set ::env(RESULTS_DIR) [file join $run_dir results]
# This example uses Kepler separately, not the fixture's optional EQY harness.
unset -nocomplain ::env(EQUIVALENCE_CHECK)
cd $fixture
source helpers.tcl
source flow_helpers.tcl
source sky130hd/sky130hd.vars
# The matching upstream flow determines threads with getconf; use the same host
# for baseline and candidate.
set design gcd
set top_module gcd
set die_area {0 0 299.96 300.128}
set core_area {9.996 10.08 289.964 290.048}
source flow.tcl

report_checks -path_delay max -group_path_count 20 -format full_clock_expanded \
  -fields {input_pin slew capacitance} -digits 6 > [file join $reports setup.rpt]
report_checks -path_delay min -group_path_count 20 -format full_clock_expanded \
  -fields {input_pin slew capacitance} -digits 6 > [file join $reports hold.rpt]
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 \
  > [file join $reports electrical.rpt]
report_power -corner $power_corner > [file join $reports power.rpt]
report_worst_slack -max -digits 6 > [file join $reports worst_setup.rpt]
report_worst_slack -min -digits 6 > [file join $reports worst_hold.rpt]
report_tns -digits 6 > [file join $reports tns.rpt]
report_design_area > [file join $reports area.rpt]
write_db [file join $run_dir results gcd_final.odb]
write_def [file join $run_dir results gcd_final.def]
write_verilog -remove_cells $filler_cells [file join $run_dir results gcd_final.v]
write_sdc [file join $run_dir results gcd_final.sdc]
puts "GCD_FINAL_DRC=[detailed_route_num_drvs]"
puts "GCD_ROUTED=[design_is_routed]"
puts "GCD_COMPLETE=1"
