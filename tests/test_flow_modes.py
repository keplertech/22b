"""Mode discovery, dependency boundaries and direct-replay evidence guards."""

import ast
import copy
from pathlib import Path
import re
import unittest

from scripts.direct_tools_regression import EDIT, require_proof
from test_gcd_reference_regression import proof_result


ROOT = Path(__file__).resolve().parents[1]


def links(path):
    return {(path.parent / target.split("#", 1)[0]).resolve()
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text())
            if "://" not in target and not target.startswith("#")}


class ModeTests(unittest.TestCase):
    def test_both_applications_route_to_both_local_flavors(self):
        shared = ROOT / "flow/session-policy.md"
        for flow in ("backend", "rtl"):
            entry = ROOT / f"flow/{flow}/SKILL.md"
            for mode in ("managed", "direct"):
                skill = ROOT / f"flow/{flow}/{mode}/SKILL.md"
                with self.subTest(flow=flow, mode=mode):
                    self.assertTrue(skill.is_file())
                    self.assertIn(skill, links(entry))
                    self.assertIn(entry, links(skill))
                    self.assertIn(shared, links(skill))

    def test_direct_guides_share_recipe_not_managed_startup(self):
        for flow in ("backend", "rtl"):
            skill = ROOT / f"flow/{flow}/direct/SKILL.md"
            direct_links = links(skill)
            self.assertIn(ROOT / "flow/direct-revisions.md", direct_links)
            self.assertNotIn(ROOT / "tools/live-session.md", direct_links)
            self.assertNotIn(ROOT / "tools/session-history.md", direct_links)
            for tool in ("najaeda", "naja-scope", "kepler-formal"):
                self.assertIn(ROOT / f"tools/{tool}/SKILL.md", direct_links)

    def test_managed_guides_select_tested_owner(self):
        for flow in ("backend", "rtl"):
            skill = ROOT / f"flow/{flow}/managed/SKILL.md"
            self.assertIn(ROOT / "tools/live-session.md", links(skill))
            self.assertIn(ROOT / "tools/session-history.md", links(skill))

    def test_direct_runner_has_no_flow_helper_dependencies(self):
        path = ROOT / "scripts/direct_tools_regression.py"
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                self.assertNotIn(module.split(".")[0], {"tools", "scripts", "flow"})
        candidate = ast.parse(EDIT)
        imports = [n.module for n in ast.walk(candidate) if isinstance(n, ast.ImportFrom)]
        self.assertEqual(imports, ["najaeda"])

    def test_direct_fixture_requires_real_full_proof(self):
        result = proof_result(total=1, covered=1, proven=1)
        require_proof(result)
        for key, value in (("verification", "lec"), ("proven_outputs", 0),
                           ("covered_outputs", 0), ("total_outputs", 0),
                           ("conclusive", False), ("skipped_observed_outputs", ["y"])):
            bad = copy.deepcopy(result)
            bad["verification_result"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_proof(bad)
        for status in ("partially_proved", "inconclusive", "different"):
            with self.assertRaises(ValueError):
                require_proof(proof_result(status, total=1, covered=1, proven=0))

    def test_counterexample_is_distinguished_from_execution_error(self):
        different = proof_result("different", total=1, covered=1, proven=0)
        require_proof(different, different=True)
        for bad in ({"status": "error"}, {"status": "success"},
                    proof_result(total=1, covered=1, proven=1)):
            with self.assertRaises(ValueError):
                require_proof(bad, different=True)

    def test_new_workflow_runs_both_real_modes_without_changing_gcd_replay(self):
        workflow = (ROOT / ".github/workflows/flow-modes-verify.yml").read_text()
        for runner in ("direct_tools_regression.py", "versioned_session_regression.py"):
            self.assertIn(runner, workflow)
        original = (ROOT / ".github/workflows/gcd-reference-verify.yml").read_text()
        self.assertNotIn("direct_tools_regression.py", original)
        self.assertIn("if: always()", workflow)


if __name__ == "__main__":
    unittest.main()
