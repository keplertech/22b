"""Offline storage/selection guards, not physical or formal verification."""

from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest

from tools.session_history import RevisionHistory
from tools.scope_checkpoints import ScopeCheckpoints
from scripts.gcd_undo_regression import require_restored


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = RevisionHistory(self.root)

    def publish(self, revision, status="proved"):
        directory = Path(tempfile.mkdtemp(dir=self.root))
        (directory / "design.v").write_text(f"// revision {revision}\nmodule top(); endmodule\n")
        return self.history.publish(directory, revision, {"top": "top", "export_proof": {"status": status}})

    def test_default_ten_recent_edits_plus_preserved_baseline(self):
        for i in range(13):
            self.publish(i)
        self.assertEqual(sorted(self.history.records), [0, *range(3, 13)])
        self.assertEqual(self.history.active, 12)
        self.assertEqual(json.loads((self.root / "config.json").read_text())["retention"], 10)

    def test_configurable_retention_and_invalid_values(self):
        for i in range(4):
            self.publish(i)
        for bad in (0, -1, True, 1.5, "10"):
            with self.assertRaises(ValueError):
                self.history.configure(bad)
        self.history.configure(1)
        self.assertEqual(sorted(self.history.records), [0, 3])

    def test_undo_deletes_latest_and_does_not_reuse_numbers(self):
        self.publish(0)
        latest = self.publish(1)
        target = self.history.undo_target()
        self.history.finish_undo(target["revision"])
        self.assertEqual(self.history.active, 0)
        self.assertFalse(Path(latest["directory"]).exists())
        with self.assertRaises(ValueError):
            self.publish(1)
        self.publish(2)
        self.assertEqual(sorted(self.history.records), [0, 2])
        self.assertEqual(self.history.get()["parent"], 0)

    def test_empty_history_or_baseline_cannot_undo(self):
        self.publish(0)
        with self.assertRaises(ValueError):
            self.history.undo_target()
        with self.assertRaises(ValueError):
            self.history.get(99)

    def test_inflight_inputs_survive_pruning_and_block_deletion(self):
        self.publish(0)
        self.publish(1)
        self.history.configure(1)
        with self.history.acquire(1):
            with self.assertRaises(RuntimeError):
                self.history.undo_target()
            self.publish(2)
            self.assertIn(1, self.history.records)
        self.assertNotIn(1, self.history.records)

    def test_modified_export_or_manifest_rejected(self):
        record = self.publish(0)
        path = Path(record["verilog_file"])
        original = path.read_text()
        path.write_text("corrupt")
        with self.assertRaises(ValueError):
            self.history.get()
        path.write_text(original)
        (Path(record["directory"]) / "manifest.json").write_text("{}")
        with self.assertRaises(ValueError):
            self.history.get()

    def test_bad_or_empty_snapshot_not_published(self):
        directory = Path(tempfile.mkdtemp(dir=self.root))
        with self.assertRaises(ValueError):
            self.history.publish(directory, 0, {})
        self.assertFalse(self.history.records)
        self.assertIsNone(self.history.active)

    def test_best_survives_undo_and_retention_and_requires_comparable_evidence(self):
        self.history.objective = {"weights": {"slack": -1}, "bounds": {"area": {"max": 20}}}
        proof = self.root / "report.txt"
        proof.write_text("synthetic unit-test evidence, not a real timing result")
        context = {"constraints": "fixture"}
        self.publish(0)
        self.publish(1)
        result = self.history.measure(1, {"slack": 1, "area": 10}, context, [proof])
        self.assertTrue(result["promoted"])
        best = (self.root / "best/design.v").read_bytes()
        self.history.finish_undo(0)
        self.publish(2)
        self.assertFalse(self.history.measure(2, {"slack": 0, "area": 10}, context, [proof])["promoted"])
        self.publish(3)
        self.assertFalse(self.history.measure(3, {"slack": 2, "area": 30}, context, [proof])["promoted"])
        self.history.configure(1)
        self.assertEqual((self.root / "best/design.v").read_bytes(), best)
        self.publish(4)
        with self.assertRaises(ValueError):
            self.history.measure(4, {"slack": 2, "area": 10}, {"constraints": "changed"}, [proof])

    def test_warning_preserved_not_promoted_as_full_proof(self):
        self.history.objective = {"weights": {"slack": -1}}
        self.publish(0, "warning")
        source = self.root / "report.txt"
        source.write_text("fixture")
        result = self.history.measure(0, {"slack": 3}, {"setup": "fixture"}, [source])
        self.assertFalse(result["promoted"])
        self.assertEqual(self.history.get()["export_proof"]["status"], "warning")

    def test_missing_nan_metrics_or_evidence_rejected(self):
        self.publish(0)
        for metrics, context, evidence in (({"slack": float("nan")}, {"setup": 1}, [__file__]),
                                            ({"slack": 1}, {}, [__file__]),
                                            ({"slack": 1}, {"setup": 1}, [])):
            with self.assertRaises(ValueError):
                self.history.measure(0, metrics, context, evidence)


class ScopeSelectionTests(unittest.TestCase):
    def test_current_historical_undo_and_reuse(self):
        current = [0]
        calls, loaded = [], []

        class Session:
            libraries = []

            @contextmanager
            def use_checkpoint(self, revision=None):
                key = current[0] if revision is None else revision
                yield {"revision": key, "verilog_file": f"{key}.v", "top": "top",
                       "files": {"design.v": str(key)}, "export_proof": {"status": "proved"}}

        def call(tool, arguments):
            calls.append(tool)
            if tool == "load_verilog":
                loaded[:] = arguments["files"]
            if tool == "reset_universe":
                loaded.clear()
            return {"loaded": bool(loaded), "top": {"name": "top"}, "loaded_files": loaded[:], "answer": loaded[:]}

        scope = ScopeCheckpoints(Session(), call)
        self.assertEqual(scope.query("get_stats")["revision"], 0)
        scope.query("get_stats")
        self.assertEqual(calls.count("load_verilog"), 1)
        current[0] = 1
        self.assertEqual(scope.query("get_stats")["revision"], 1)
        self.assertEqual(scope.query("get_stats", revision=0)["revision"], 0)
        self.assertEqual(scope.query("get_stats")["revision"], 1)
        current[0] = 0
        self.assertEqual(scope.query("get_stats")["result"]["answer"], ["0.v"])
        with self.assertRaises(ValueError):
            scope.query("query_python")

    def test_restored_physical_metrics_must_match_all_fields(self):
        baseline = {k: 1 for k in ("setup_ns", "hold_ns", "tns_ns", "area_um2", "routing_drc", "power_report")}
        require_restored(baseline, dict(baseline))
        for key in baseline:
            with self.assertRaises(ValueError):
                require_restored(baseline, dict(baseline, **{key: 2}))

    def test_new_workflow_is_distinct_and_exercises_undo(self):
        root = Path(__file__).resolve().parents[1]
        old = (root / ".github/workflows/gcd-reference-verify.yml").read_text()
        new = (root / ".github/workflows/gcd-undo-verify.yml").read_text()
        self.assertNotIn("gcd_undo_regression.py", old)
        self.assertIn("gcd_undo_regression.py", new)
        self.assertIn("versioned_session_regression.py", new)
        self.assertIn("if: always()", new)
