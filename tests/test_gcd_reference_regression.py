"""Offline gate tests; no model, native package, SEC or OpenROAD is run here."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gcd_replay", ROOT / "scripts/gcd_reference_regression.py")
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)
COVERAGE = "SEC checked-output coverage: 100.00% (18/18 covered/existing outputs).\n"
PROVED = COVERAGE + "SEC proved equivalence under the dual-rail steady-state abstraction at k = 5.\n"


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def physical_fixture(self):
        (self.work / "reports").mkdir()
        (self.work / "results").mkdir()
        for name in REPLAY.REPORTS:
            (self.work / "reports" / (name + ".rpt")).write_text("report data\n")
        for ext in ("odb", "def", "v", "sdc"):
            (self.work / "results" / ("gcd_final." + ext)).write_text("physical data\n")
        (self.work / "tool.log").write_text("GCD_COMPLETE=1\nGCD_ROUTED=1\nGCD_FINAL_DRC=0\n")
        self.metrics = {"DRT::worst_slack_max": -0.6, "DRT::worst_slack_min": 0.48,
                        "DRT::tns_max": -1.2, "DPL::design_area": 3931}
        (self.work / "metrics.json").write_text(json.dumps(self.metrics))

    def test_explicit_full_proof(self):
        self.assertEqual(REPLAY.require_full_sec(PROVED, 0)["proved_outputs"], 18)

    def test_partial_proof_is_not_a_reference_pass(self):
        with self.assertRaisesRegex(ValueError, "partial proof is not a mismatch"):
            REPLAY.require_full_sec(COVERAGE + "SEC partially proved equivalence: 8/18", 0)

    def test_counterexample_missing_coverage_and_tool_errors_fail(self):
        cases = [(PROVED, 2), ("No difference was found", 0), (COVERAGE + "counterexample", 0),
                 (PROVED.replace("18/18", "0/0"), 0), (PROVED.replace("18/18", "17/18"), 0),
                 (PROVED.replace("18/18", "1/1"), 0), (PROVED.replace("100.00%", "99.00%"), 0),
                 (COVERAGE + PROVED, 0), (COVERAGE, 0)]
        for log, code in cases:
            with self.subTest(log=log, code=code), self.assertRaises(ValueError):
                REPLAY.require_full_sec(log, code)

    def test_fresh_physical_reports_required(self):
        self.physical_fixture()
        self.assertEqual(REPLAY.physical_summary(self.work)["setup_ns"], -0.6)
        (self.work / "reports/power.rpt").unlink()
        with self.assertRaisesRegex(ValueError, "Missing/empty report"):
            REPLAY.physical_summary(self.work)

    def test_incomplete_routing_and_drc_errors_fail(self):
        self.physical_fixture()
        for log in ("GCD_COMPLETE=1\n", "GCD_COMPLETE=1\nGCD_ROUTED=1\nGCD_FINAL_DRC=01\n"):
            (self.work / "tool.log").write_text(log)
            with self.assertRaises(ValueError):
                REPLAY.physical_summary(self.work)

    def test_clean_electrical_report_may_be_empty_but_must_exist(self):
        self.physical_fixture()
        path = self.work / "reports/electrical.rpt"
        path.write_text("")
        REPLAY.physical_summary(self.work)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing/empty report"):
            REPLAY.physical_summary(self.work)

    def test_missing_or_invalid_metrics_fail(self):
        self.physical_fixture()
        for value in (None, float("nan"), float("inf"), "-0.6", True):
            self.metrics["DRT::worst_slack_max"] = value
            (self.work / "metrics.json").write_text(json.dumps(self.metrics))
            with self.subTest(value=value), self.assertRaises(ValueError):
                REPLAY.physical_summary(self.work)

    def test_fresh_timing_gain_and_hold(self):
        baseline = {"setup_ns": -0.6, "hold_ns": 0.48, "routing_drc": 0}
        candidate = dict(baseline, setup_ns=0.01)
        self.assertAlmostEqual(REPLAY.compare(baseline, candidate)["setup_gain_ns"], 0.61)
        self.assertFalse(REPLAY.compare(baseline, dict(candidate, setup_ns=-0.1))["setup_met"])
        for changed in ({"setup_ns": -0.7}, {"setup_ns": -0.6}, {"hold_ns": -0.1},
                        {"routing_drc": 1}, {"setup_ns": float("nan")}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                REPLAY.compare(baseline, dict(candidate, **changed))

    def test_process_error_and_timeout_are_not_passes(self):
        with self.assertRaises(RuntimeError):
            REPLAY.run_command(self.work / "failed", [sys.executable, "-c", "raise SystemExit(7)"], timeout=10)
        execution = json.loads((self.work / "failed/execution.json").read_text())
        self.assertEqual(execution["exit_code"], 7)
        with patch.object(REPLAY.subprocess, "run", side_effect=subprocess.TimeoutExpired("tool", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                REPLAY.run_command(self.work / "timeout", ["tool"], timeout=1)
        self.assertIsNone(json.loads((self.work / "timeout/execution.json").read_text())["exit_code"])

    def test_existing_work_dir_is_never_reused_by_prepare(self):
        marker = self.work / "keep.txt"
        marker.write_text("untouched")
        with self.assertRaises(FileExistsError):
            REPLAY.prepare(self.work, self.work / "fixture")
        self.assertEqual(marker.read_text(), "untouched")

    def test_stage_cannot_skip_formal_proof(self):
        (self.work / "metadata.json").write_text(json.dumps({"completed": ["prepare", "baseline", "inspect", "edit"]}))
        with self.assertRaisesRegex(ValueError, "successful earlier stages"), patch.object(REPLAY, "run_command") as run:
            REPLAY.stage("candidate", self.work, self.work / "fixture", 10)
        run.assert_not_called()

    def test_changed_candidate_after_proof_is_rejected(self):
        inputs = self.work / "inputs"
        inputs.mkdir()
        for name in ("input.v", "constraints.sdc"):
            (inputs / name).write_bytes((REPLAY.EXAMPLE / name).read_bytes())
        fixture = self.work / "fixture"
        fixture.mkdir()
        (fixture / "manifest.json").write_text('{"files": {}}')
        candidate = self.work / "candidate.v"
        candidate.write_text("original candidate")
        metadata = {"source_hashes": REPLAY.input_hashes(), "fixture": str(fixture),
                    "fixture_manifest_sha256": REPLAY.digest(fixture / "manifest.json"),
                    "completed": ["prepare", "baseline", "inspect", "edit", "proof"],
                    "candidate_sha256": REPLAY.digest(candidate)}
        REPLAY.validate_inputs(self.work, metadata)
        candidate.write_text("different candidate")
        with self.assertRaisesRegex(ValueError, "Candidate changed"):
            REPLAY.validate_inputs(self.work, metadata)

    def test_scope_errors_rejected_even_in_successful_mcp_envelopes(self):
        for error, value in ((True, {}), (False, {"error": "not found"})):
            with self.assertRaises(ValueError):
                REPLAY.scope_payload(SimpleNamespace(isError=error, structuredContent=value))

    def test_scope_requires_correct_top_and_complete_boundary_results(self):
        REPLAY.validate_scope_query("status", {"loaded": True, "top": {"name": "gcd"}})
        REPLAY.validate_scope_query("get_loads", {"leaf_loads": [{"path": "gcd.consumer"}]})
        REPLAY.validate_scope_query("get_drivers", {"top_drivers": [{"path": "gcd.input"}]})
        for name, value in (("status", {}), ("status", {"loaded": True, "top": {"name": "other"}}),
                            ("get_loads", {}), ("get_drivers", {"leaf_drivers": [], "top_drivers": []}),
                            ("get_loads", {"leaf_loads": ["load"], "truncated": True})):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                REPLAY.validate_scope_query(name, value)

    def test_model_context_excludes_reference_answer(self):
        example = REPLAY.EXAMPLE
        self.assertFalse((example / "edit.py").exists())
        self.assertFalse((example / "historical-results.json").exists())
        self.assertTrue((example / "reference/edit.py").is_file())
        self.assertTrue((example / "reference/historical-results.json").is_file())
        task = (example / "task.md").read_text()
        self.assertIn("flow/backend/SKILL.md", task)
        for leaked in ("_215_", "_219_", "generate/propagate", "prefix", "31-gate", "0.5998"):
            self.assertNotIn(leaked, task)


if __name__ == "__main__":
    unittest.main()
