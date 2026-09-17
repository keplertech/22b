"""Offline session-policy tests; real kernel/SEC checks are a separate runner."""

import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import live_session as live
from tools.edit_validation import editing_function, validate_script
from test_gcd_reference_regression import proof_result

GOLDEN_REF = dict(session_id="fixture-session", db_id=2, library_id=1, design_id=0)
CANDIDATE_REF = dict(session_id="fixture-session", db_id=1, library_id=1, design_id=0)


def attached_result(status="equivalent", proven=18):
    result = proof_result(status, proven=proven)
    result.update(report_format="structured-v1", report_id="proof-identity",
                  session_id="fixture-session", pid=os.getpid(),
                  design1=dict(GOLDEN_REF), design2=dict(CANDIDATE_REF))
    result["reports"] = {"verification-result.json": json.dumps(result["verification_result"])}
    return result


class EditContractTests(unittest.TestCase):
    def test_candidate_operations_and_pure_helpers(self):
        top = Mock()
        top.get_child_instances.return_value = []
        editing_function('''def helper(top):
    for child in list(top.get_child_instances()):
        assert child is not None
def edit(top):
    helper(top)
    top.create_net("new")
''')(top)
        top.create_net.assert_called_once_with("new")

    def test_no_load_reset_export_import_or_python_escape(self):
        scripts = ["from najaeda import netlist\nnetlist.reset()",
                   "top = None", "def edit(top):\n top.dump_verilog('x.v')",
                   "def edit(top):\n top.__class__",
                   "def edit(top):\n open('original.v', 'w')",
                   "def edit(top):\n import os", "def edit(top):\n eval('1')",
                   "def edit(top, extra):\n pass", "def edit(top=None):\n pass",
                   "def edit(top):\n yield top", "@run\ndef edit(top):\n pass",
                   "def edit(top):\n global external", "def edit(top):\n (lambda: 1)()"]
        for source in scripts:
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_script(source)

    def test_bad_syntax_and_oversized_script(self):
        with self.assertRaises(SyntaxError):
            validate_script("def edit(top):\n  x = '")
        with self.assertRaises(ValueError):
            validate_script(" " * (1024 * 1024 + 1))


class SessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        session = live.LiveDesignSession.__new__(live.LiveDesignSession)
        session.directory = Path(temp.name)
        session.timeout, session.revision, session._attempt = 5, 0, 0
        session._pending = session._closed = False
        session.state, session.proof = "unverified", None
        session._operation = threading.Lock()
        session._universe = Mock()
        session._naja = SimpleNamespace(NLUniverse=SimpleNamespace(get=lambda: session._universe))
        session._golden = SimpleNamespace(signature="golden")
        session._candidate = SimpleNamespace(signature="candidate")
        session._golden_hash, session._candidate_hash = "golden", "candidate"
        session._golden_ref, session._candidate_ref = dict(GOLDEN_REF), dict(CANDIDATE_REF)
        session._netlist = SimpleNamespace(get_top=lambda: session._candidate)
        session._bridge = SimpleNamespace(lock=threading.RLock(), close=Mock())
        session._session_id = "fixture-session"
        session._client = Mock()
        session._client.busy.return_value = False
        session._client.call.return_value = attached_result()
        self.session = session
        fingerprint = patch.object(live, "_fingerprint", side_effect=lambda design: design.signature)
        fingerprint.start()
        self.addCleanup(fingerprint.stop)

    def test_edits_accumulate_and_sec_is_automatic(self):
        def edit(top):
            top.signature += "-edit"
        with patch.object(live, "editing_function", return_value=edit):
            for revision in (1, 2):
                result = self.session.apply_edit("candidate-only script")
                self.assertEqual(result["revision"], revision)
                self.assertEqual(self.session.status()["golden_sha256"], "golden")
        self.assertEqual(self.session._candidate.signature, "candidate-edit-edit")
        calls = self.session._client.call.call_args_list
        self.assertEqual([call.args[0] for call in calls],
                         ["verify_session", "get_session_reports"] * 2)
        for call in calls[::2]:
            self.assertEqual(call.args[1]["verification"], "sec")
            self.assertEqual(call.args[1]["design1"], GOLDEN_REF)
            self.assertEqual(call.args[1]["design2"], CANDIDATE_REF)
            self.assertTrue(call.args[1]["report_skipped_outputs"])

    def test_counterexample_and_tool_error_clear_previous_proof(self):
        for result in (attached_result("different", 0), {"status": "error"}):
            self.session.proof = {"status": "proved"}
            self.session._client.call.return_value = result
            with self.assertRaises(ValueError):
                self.session.verify()
            self.assertIsNone(self.session.proof)
            self.assertEqual(self.session.state, "rejected")

    def test_partial_proof_is_warning_not_equivalence(self):
        self.session._client.call.return_value = attached_result("partially_proved", 8)
        result = self.session.verify()
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["proved_outputs"], 8)
        self.assertEqual(self.session.state, "unproven")

    def test_script_exception_keeps_partial_candidate_and_invalidates_proof(self):
        self.session.proof = {"status": "proved"}
        def edit(top):
            top.signature = "partial-edit"
            raise ValueError("bad pin")
        with patch.object(live, "editing_function", return_value=edit), self.assertRaisesRegex(ValueError, "bad pin"):
            self.session.apply_edit("partially executed script")
        self.assertEqual(self.session._candidate_hash, "partial-edit")
        self.assertIsNone(self.session.proof)
        self.assertEqual(self.session.status()["state"], "edit_error")
        self.session._client.call.assert_not_called()

    def test_invalid_script_never_mutates_or_discards_valid_proof(self):
        self.session.proof = {"status": "proved"}
        with self.assertRaises(ValueError):
            self.session.apply_edit("import os")
        self.assertEqual(self.session.revision, 0)
        self.assertEqual(self.session.proof, {"status": "proved"})
        self.session._client.call.assert_not_called()

    def test_golden_and_untracked_candidate_mutations_invalidate(self):
        for design in (self.session._golden, self.session._candidate):
            old = design.signature
            self.session.state, self.session.proof = "proved", {"status": "proved"}
            design.signature = "untracked"
            with self.assertRaises(RuntimeError):
                self.session.status()
            self.assertEqual(self.session.state, "invalid")
            self.assertIsNone(self.session.proof)
            design.signature = old

    def test_native_timeout_blocks_edit_until_fresh_proof(self):
        self.session._client.call.return_value = {"status": "error", "may_still_be_running": True}
        with self.assertRaises(TimeoutError):
            self.session.verify()
        self.assertEqual(self.session.state, "verification_pending")
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.session.apply_edit("def edit(top):\n pass")
        self.assertEqual(self.session.revision, 0)
        self.session._client.call.return_value = attached_result()
        self.assertEqual(self.session.verify()["status"], "proved")
        self.assertFalse(self.session._pending)

    def test_transport_timeout_is_not_proof(self):
        self.session._client.call.side_effect = TimeoutError("transport")
        with self.assertRaises(TimeoutError):
            self.session.verify()
        self.assertTrue(self.session._pending)
        self.assertIsNone(self.session.proof)

    def test_busy_transport_native_lock_and_operation_block_edits(self):
        self.session._client.busy.return_value = True
        with self.assertRaisesRegex(RuntimeError, "still running"):
            self.session.apply_edit("def edit(top):\n pass")
        with self.assertRaises(RuntimeError):
            self.session.close()
        self.session._client.busy.return_value = False
        self.session._bridge.lock = Mock()
        self.session._bridge.lock.acquire.return_value = False
        with self.assertRaises(RuntimeError):
            self.session.verify()
        self.session._operation.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, "Another session"):
                self.session.apply_edit("def edit(top):\n pass")
        finally:
            self.session._operation.release()
        self.assertEqual(self.session.revision, 0)

    def test_stale_report_and_wrong_session_rejected(self):
        good = attached_result()
        for bad in (dict(good, report_id="stale"), dict(good, session_id="other"),
                    dict(good, pid=-1), dict(good, reports={}),
                    dict(good, design1=CANDIDATE_REF), dict(good, design2=GOLDEN_REF)):
            self.session._client.call.side_effect = [good, bad]
            with self.assertRaises(ValueError):
                self.session.verify()
            self.assertIsNone(self.session.proof)

    def test_wrong_native_database_or_missing_identity_rejects_proof(self):
        for field, reference in (("design1", CANDIDATE_REF), ("design2", GOLDEN_REF),
                                 ("design1", None)):
            self.session._client.call.return_value = dict(attached_result(), **{field: reference})
            with self.assertRaisesRegex(ValueError, "different native designs"):
                self.session.verify()
            self.assertIsNone(self.session.proof)

    def test_missing_report_identity_rejected(self):
        result = attached_result()
        del result["report_id"]
        self.session._client.call.return_value = result
        with self.assertRaisesRegex(ValueError, "report identity"):
            self.session.verify()

    def test_closed_session_drops_proof_and_cannot_edit(self):
        self.session.close()
        self.assertEqual(self.session.status()["state"], "closed")
        self.assertIsNone(self.session.proof)
        self.session._universe.destroy.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.session.apply_edit("def edit(top):\n pass")

    def test_returned_results_cannot_mutate_the_retained_proof(self):
        result = self.session.verify()
        result["proved_outputs"] = 999
        self.session.status()["proof"]["proved_outputs"] = 888
        self.assertEqual(self.session.status()["proof"]["proved_outputs"], 18)

    def test_invalid_native_handle_clears_previous_proof(self):
        self.session.proof = {"status": "proved"}
        with patch.object(live, "_fingerprint", side_effect=ReferenceError("destroyed")):
            with self.assertRaisesRegex(RuntimeError, "no longer valid"):
                self.session.status()
        self.assertEqual(self.session.state, "invalid")
        self.assertIsNone(self.session.proof)


if __name__ == "__main__":
    unittest.main()
