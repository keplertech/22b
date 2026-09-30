"""Execute the documented startup contract without claiming native proof."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from tools import live_session, versioned_session


ROOT = Path(__file__).resolve().parents[1]


class SessionStartupTests(unittest.TestCase):
    def setUp(self):
        document = (ROOT / "tools/live-session.md").read_text()
        self.cells = re.findall(r"```python\n(.*?)\n```", document, re.DOTALL)
        self.assertGreaterEqual(len(self.cells), 3)

    def test_standard_startup_selects_versioned_helper_and_edits_same_owner(self):
        with patch.object(versioned_session, "VersionedDesignSession", autospec=True) as factory, \
                patch.object(live_session, "LiveDesignSession", autospec=True) as legacy:
            owner = factory.return_value
            proof = {"status": "proved", "proved_outputs": 1, "existing_outputs": 1}
            owner.status.return_value = {"proof": proof, "netlist_revision": 0}
            owner.apply_edit.return_value = proof
            namespace = {}
            exec(compile(self.cells[0], "tools/live-session.md:startup", "exec"), namespace)
            factory.assert_called_once_with(reference="/absolute/original.v",
                                            liberty_files=["/absolute/cells.lib"],
                                            sessions_root="runs", retention=10)
            legacy.assert_not_called()
            self.assertIs(namespace["session"], owner)
            self.assertIs(namespace["initial_proof"], proof)
            owner.verify.assert_not_called()  # Initialization already checks baseline.
            script = "def edit(top):\n    pass\n"
            with patch.object(Path, "read_text", return_value=script), redirect_stdout(io.StringIO()):
                exec(compile(self.cells[1], "tools/live-session.md:edit", "exec"), namespace)
            owner.apply_edit.assert_called_once_with(script)
            self.assertIs(namespace["session"], owner)
            self.assertIs(namespace["result"], proof)
            factory.assert_called_once()

    def test_explicit_no_export_startup_keeps_legacy_api(self):
        with patch.object(live_session, "LiveDesignSession", autospec=True) as legacy, \
                patch.object(versioned_session, "VersionedDesignSession", autospec=True) as versioned:
            namespace = {}
            exec(compile(self.cells[2], "tools/live-session.md:no-export", "exec"), namespace)
            legacy.assert_called_once_with(reference="/absolute/original.v",
                                           liberty_files=["/absolute/cells.lib"],
                                           work_dir="runs/my-no-export-session")
            versioned.assert_not_called()
            legacy.return_value.verify.assert_called_once_with()
            self.assertIs(namespace["session"], legacy.return_value)


if __name__ == "__main__":
    unittest.main()
