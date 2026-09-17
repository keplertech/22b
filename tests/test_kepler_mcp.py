"""Offline MCP contract tests; native SEC is tested separately."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from test_gcd_reference_regression import REPLAY, proof_result


SEC = REPLAY.SEC


class KeplerMcpTests(unittest.TestCase):
    def test_full_proof_uses_structured_fields_not_log_strings(self):
        value = proof_result()
        value["log_tail"] = "A different version may change all logging."
        self.assertEqual(SEC.summarize(value)["status"], "proved")
        with self.assertRaises(ValueError):
            SEC.summarize({"status": "success", "exit_code": 0, "log_tail": "SEC proved equivalence"})

    def test_incomplete_is_warning_and_coverage_is_not_proof(self):
        for status, proven in (("partially_proved", 8), ("inconclusive", 0)):
            value = proof_result(status, proven=proven)
            value["verification_result"]["unproven_outputs"] = ["output[0]"]
            summary = SEC.summarize(value)
            self.assertEqual(summary["status"], "warning")
            self.assertEqual(summary["coverage_percent"], 100)
            self.assertAlmostEqual(summary["proof_coverage_percent"], 100 * proven / 18)
            with self.assertRaises(ValueError):
                SEC.require_full(summary, 18)

    def test_tool_errors_unsupported_and_counterexamples_fail(self):
        for status in ("different", "error", "unsupported", "no_result", "exported", None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                SEC.summarize(proof_result(status))
        with self.assertRaises(ValueError):
            SEC.summarize(dict(proof_result(), status="error"))

    def test_bad_counts_lec_skips_and_contradictions_fail(self):
        changes = [
            {"verification": "lec"}, {"covered_outputs": 0}, {"covered_outputs": True},
            {"covered_outputs": 19}, {"proven_outputs": 17}, {"proven_outputs": -1},
            {"total_outputs": 0}, {"coverage_percent": float("nan")},
            {"coverage_percent": 99}, {"coverage_percent": True}, {"exit_code": 2},
            {"equivalent": False}, {"conclusive": False},
            {"unproven_outputs": ["Z"]}, {"skipped_observed_outputs": ["Z"]},
            {"unproven_outputs": None}]
        for change in changes:
            value = proof_result()
            value["verification_result"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                SEC.summarize(value)
        for change in ({"verdict": "different"}, {"reports": {}},
                       {"reports": {name: "skipped" for name in SEC.REPORTS}},
                       {"exit_code": False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                SEC.summarize(dict(proof_result(), **change))

    def test_json_text_tool_response(self):
        response = SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text=json.dumps(proof_result()))])
        self.assertEqual(SEC.payload(response), proof_result())
        for text in ("not json", "[]", "true"):
            response.content[0].text = text
            with self.assertRaises(ValueError):
                SEC.payload(response)
        response.isError = True
        with self.assertRaises(ValueError):
            SEC.payload(response)
        response.isError = False
        response.content = []
        with self.assertRaises(ValueError):
            SEC.payload(response)

    def test_run_records_sec_request_snapshots_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            sources = [root / name for name in ("reference.v", "candidate.v", "fixture.lib")]
            for source in sources:
                source.write_text("original " + source.name)
            directory = root / "proof"

            async def fake_call(path, arguments):
                self.assertEqual(arguments["verification"], "sec")
                self.assertEqual(arguments["sec_engine"], "pdr")
                self.assertEqual(arguments["sec_encoding"], "dual_rail_steady")
                self.assertTrue(arguments["report_skipped_outputs"])
                self.assertFalse(arguments["allow_boundary_mismatch"])
                self.assertEqual(arguments["timeout_seconds"], 5)
                self.assertEqual(arguments["allowed_output_dir"], str(directory))
                for snapshot in arguments["input_paths"] + arguments["liberty_files"]:
                    self.assertTrue(Path(snapshot).is_relative_to(directory))
                    self.assertFalse(Path(snapshot).stat().st_mode & 0o222)
                SEC.save(path / "result.json", proof_result())
                return proof_result()

            with patch.object(SEC, "package_identity", return_value={}), \
                 patch.object(SEC, "call_server", side_effect=fake_call):
                self.assertEqual(SEC.run_sec(directory, *sources[:2], sources[2:], timeout=5)["status"], "proved")
                with self.assertRaises(FileExistsError):
                    SEC.run_sec(directory, *sources[:2], sources[2:])
            self.assertEqual(json.loads((directory / "request.json").read_text())["tool"], SEC.VERIFY_TOOL)
            self.assertTrue((directory / "result.json").exists())
            self.assertTrue(all((directory / name).is_file() for name in SEC.REPORTS))
            for source in sources:
                self.assertEqual(source.read_text(), "original " + source.name)

    def test_transport_timeout_is_not_equivalence_and_inputs_are_guarded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input.v"
            source.write_text("original")
            with patch.object(SEC, "package_identity", return_value={}), \
                 patch.object(SEC, "call_server", new=AsyncMock(side_effect=TimeoutError("transport"))):
                with self.assertRaises(TimeoutError):
                    SEC.run_sec(root / "timeout", source, source, [])
            self.assertIn("transport", (root / "timeout/error.json").read_text())

            async def mutate(*args):
                source.write_text("changed")
                return proof_result()

            with patch.object(SEC, "package_identity", return_value={}), \
                 patch.object(SEC, "call_server", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "inputs changed"):
                    SEC.run_sec(root / "mutation", source, source, [])

    def test_package_pin_checks_commit_not_only_same_version_label(self):
        pins = json.loads((SEC.ROOT / "toolchain.json").read_text())
        pin = pins["kepler_formal_mcp"]
        origin = {"url": pin["repository"], "vcs_info": {"commit_id": pin["revision"]}}
        dist = SimpleNamespace(version=pin["version"], read_text=lambda name: json.dumps(origin))
        with patch.object(SEC.importlib.metadata, "version", side_effect=pins["python_packages"].get), \
             patch.object(SEC.importlib.metadata, "distribution", return_value=dist):
            SEC.package_identity()
            origin["vcs_info"]["commit_id"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "Git package"):
                SEC.package_identity()

    def test_session_structured_report_retains_real_skipped_details(self):
        value = proof_result("partially_proved", covered=17, proven=8)
        value["verification_result"]["skipped_observed_outputs"] = ["y: no driver"]
        value["verification_result"]["unproven_outputs"] = ["z: inconclusive"]
        value["report_format"] = "structured-v1"
        value["reports"] = {"verification-result.json": json.dumps(value["verification_result"])}
        result = SEC.summarize(value)
        self.assertEqual(result["skipped_observed_outputs"], ["y: no driver"])
        self.assertEqual(result["unproven_outputs"], ["z: inconclusive"])
        self.assertEqual(result["status"], "warning")
        for reports in ({}, {"verification-result.json": "{}"},
                        dict(value["reports"], unexpected="")):
            with self.assertRaises(ValueError):
                SEC.summarize(dict(value, reports=reports))

    def test_development_override_matches_exact_installed_source(self):
        pins = json.loads((SEC.ROOT / "toolchain.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            checkout, installed = root / "checkout", root / "installed"
            for directory in (checkout, installed):
                (directory / "kepler_formal_mcp").mkdir(parents=True)
                (directory / "kepler_formal_mcp/__init__.py").write_text("# reviewed wrapper\n")
            origin = {"url": checkout.as_uri(), "dir_info": {}}
            dist = SimpleNamespace(version="0.1.0", read_text=lambda name: json.dumps(origin),
                                   locate_file=lambda path: installed / path)
            with patch.object(SEC.importlib.metadata, "version", side_effect=pins["python_packages"].get), \
                 patch.object(SEC.importlib.metadata, "distribution", return_value=dist):
                result = SEC.package_identity(checkout)
                self.assertTrue(result["development_override"])
                self.assertIn("kepler_formal_mcp/__init__.py", result["source_hashes"])
                with self.assertRaises(ValueError):
                    SEC.package_identity()
                (checkout / "kepler_formal_mcp/__init__.py").write_text("# changed after install\n")
                with self.assertRaisesRegex(ValueError, "reinstall"):
                    SEC.package_identity(checkout)
                origin["url"] = installed.as_uri()
                with self.assertRaisesRegex(ValueError, "selected local checkout"):
                    SEC.package_identity(checkout)


if __name__ == "__main__":
    unittest.main()
