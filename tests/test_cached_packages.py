"""Offline installer control-flow tests using a fake Nix executable."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools/install-cached-package.sh"
FAKE_NIX = r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$CALLS"
case "$1" in
  --version) echo 'nix (Nix) test' ;;
  eval)
    if [[ "$CASE" == eval-failure ]]; then echo 'evaluation failed' >&2; exit 7; fi
    echo /nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-openroad-test ;;
  path-info)
    if [[ "$CASE" == json-null && "$*" == *'--json'* ]]; then
      echo '{"/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-openroad-test":null}'; exit 0
    fi
    if [[ "$*" == *'--store'* ]]; then
      if [[ "$CASE" == cache-miss || "$CASE" == json-null ]]; then
        echo 'path is not valid' >&2; exit 1
      fi
    elif [[ "$CASE" != local && ! -f "$BUILT" ]]; then
      exit 1
    fi
    echo '{}' ;;
  build)
    if [[ "$CASE" == install-failure ]]; then echo 'substitution failed' >&2; exit 42; fi
    touch "$BUILT" ;;
  *) exit 99 ;;
esac
'''


class CachedPackageTests(unittest.TestCase):
    def run_case(self, case):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        binary = root / "nix"
        binary.write_text(FAKE_NIX)
        binary.chmod(0o755)
        calls = root / "calls.txt"
        artifacts = root / "artifacts"
        env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                   CASE=case, CALLS=str(calls), BUILT=str(root / "built"))
        result = subprocess.run(
            ["bash", str(INSTALLER), "openroad", "github:owner/repo/pinned#openroad",
             "https://cache.example", str(artifacts)],
            env=env, text=True, capture_output=True, timeout=10)
        return result, calls.read_text(), artifacts

    def test_cached_output_is_checked_before_installation(self):
        result, calls, artifacts = self.run_case("cached")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(calls.index("path-info --store"), calls.index("build "))
        self.assertIn("build --max-jobs 0 --builders  --out-link", calls)
        self.assertEqual((artifacts / "openroad-exit-code.txt").read_text(), "0\n")
        self.assertTrue((artifacts / "openroad-installed.json").is_file())

    def test_existing_package_does_not_require_a_cache_query(self):
        result, calls, _ = self.run_case("local")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--store", calls)
        self.assertIn("Reusing existing output", result.stdout)

    def test_missing_binary_fails_before_dependency_download(self):
        result, calls, artifacts = self.run_case("cache-miss")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("build ", calls)
        self.assertIn("source builds remain disabled", (artifacts / "openroad-install.log").read_text())
        self.assertIn("path is not valid", (artifacts / "openroad-cache.log").read_text())

    def test_json_null_with_success_exit_is_not_used_as_existence_check(self):
        result, calls, _ = self.run_case("json-null")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("--json", calls)
        self.assertNotIn("build ", calls)

    def test_install_failure_keeps_original_exit_code_and_logs(self):
        result, _, artifacts = self.run_case("install-failure")
        self.assertEqual(result.returncode, 42)
        self.assertEqual((artifacts / "openroad-exit-code.txt").read_text(), "42\n")
        self.assertIn("substitution failed", (artifacts / "openroad-install.log").read_text())

    def test_evaluation_failure_keeps_diagnostics(self):
        result, calls, artifacts = self.run_case("eval-failure")
        self.assertEqual(result.returncode, 7)
        self.assertNotIn("build ", calls)
        self.assertIn("evaluation failed", (artifacts / "openroad-install.log").read_text())
        self.assertTrue((artifacts / "openroad-installable.txt").is_file())

    def test_workflow_preserves_installation_logs_even_before_design_runs(self):
        workflow = (ROOT / ".github/workflows/gcd-reference-verify.yml").read_text()
        self.assertIn("if: always()", workflow)
        self.assertIn(".cache/gcd-tools/*.log", workflow)
        self.assertIn("bash tools/install-cached-package.sh", workflow)
        self.assertNotIn('p["nixpkgs"]+"#"+p["openroad"]', workflow)

    def test_openroad_has_its_own_pinned_cached_package(self):
        package = json.loads((ROOT / "toolchain.json").read_text())["openroad"]
        self.assertRegex(package["installable"], r"^github:NixOS/nixpkgs/[0-9a-f]{40}#openroad$")
        self.assertEqual(package["cache"], "https://cache.nixos.org")
        self.assertIn(package["installable"], (ROOT / "tools/openroad/install.md").read_text())


if __name__ == "__main__":
    unittest.main()
