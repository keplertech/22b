"""Offline setup safety and client-format checks; no host configuration writes."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mcp_setup", ROOT / "setup/mcp.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.python = self.project / "env with spaces/bin/python"

    def test_codex_preserves_existing_content_and_is_idempotent(self):
        original = b'# keep this comment\nmodel = "example"\n[mcp_servers.other]\ncommand = "other"\n'
        entry = setup.configuration("codex", self.python)
        data = setup.render_config(original, "codex", "kepler-formal", entry)
        self.assertTrue(data.startswith(original))
        parsed = tomllib.loads(data.decode())
        self.assertEqual(parsed["mcp_servers"]["other"]["command"], "other")
        self.assertEqual(parsed["mcp_servers"]["kepler-formal"], entry)
        self.assertEqual(setup.render_config(data, "codex", "kepler-formal", entry), data)
        self.assertGreater(entry["tool_timeout_sec"], 600)

    def test_claude_preserves_other_servers_and_fields(self):
        original = json.dumps({"mcpServers": {"other": {"command": "other"}}, "custom": 7}).encode()
        entry = setup.configuration("claude-code", self.python)
        data = setup.render_config(original, "claude-code", "kepler-formal", entry)
        parsed = json.loads(data)
        self.assertEqual(parsed["custom"], 7)
        self.assertEqual(parsed["mcpServers"]["other"], {"command": "other"})
        self.assertEqual(parsed["mcpServers"]["kepler-formal"], entry)
        self.assertEqual(entry["type"], "stdio")
        self.assertEqual(setup.render_config(data, "claude-code", "kepler-formal", entry), data)

    def test_existing_entry_conflict_never_overwritten(self):
        for client in ("codex", "claude-code"):
            old = setup.render_config(None, client, "kepler-formal", {"command": "other"})
            with self.assertRaisesRegex(ValueError, "different settings"):
                setup.render_config(old, client, "kepler-formal", setup.configuration(client, self.python))

    def test_malformed_configs_fail(self):
        for client, data in (("codex", b"broken ["), ("codex", b"mcp_servers = 1"),
                             ("claude-code", b"{"), ("claude-code", b"[]"),
                             ("claude-code", b'{"mcpServers": []}')):
            with self.subTest(client=client, data=data), self.assertRaises(ValueError):
                setup.render_config(data, client, "test", {})

    def test_config_preview_does_not_install_or_write(self):
        with patch.object(setup, "install") as install, patch.object(setup, "check") as check:
            setup.main(["configure", "--client", "codex", "--project", str(self.project)])
        install.assert_not_called()
        check.assert_not_called()
        self.assertEqual(list(self.project.iterdir()), [])

    def test_apply_checks_before_writing(self):
        with patch.object(setup, "install", return_value=self.python), \
             patch.object(setup, "check", side_effect=ValueError("discovery failed")):
            with self.assertRaisesRegex(ValueError, "discovery failed"):
                setup.main(["configure", "--client", "codex", "--project", str(self.project), "--apply"])
        self.assertFalse((self.project / ".codex").exists())

    def test_conflict_is_checked_before_installation(self):
        path = self.project / ".mcp.json"
        path.write_text('{"mcpServers":{"kepler-formal":{"command":"other"}}}')
        with patch.object(setup, "install") as install, self.assertRaises(ValueError):
            setup.main(["configure", "--client", "claude-code", "--project", str(self.project), "--apply"])
        install.assert_not_called()

    def test_write_backups_and_noop_does_not_rewrite(self):
        path = self.project / ".mcp.json"
        old, new = b"{}", b'{"mcpServers":{}}'
        path.write_bytes(old)
        setup.write_config(path, old, new)
        self.assertEqual(path.read_bytes(), new)
        backup = list(self.project.glob("*.22b-backup-*"))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_bytes(), old)
        before = path.stat().st_mtime_ns
        setup.write_config(path, new, new)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_concurrent_change_and_symlink_rejected(self):
        path = self.project / ".mcp.json"
        path.write_bytes(b"newer")
        with self.assertRaisesRegex(ValueError, "changed during"):
            setup.write_config(path, b"old", b"replace")
        with self.assertRaisesRegex(ValueError, "changed during"):
            setup.write_config(path, b"old", b"old")
        self.assertEqual(path.read_bytes(), b"newer")
        link = self.project / "linked.json"
        link.symlink_to(path)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            setup.read_config(link)

    def test_live_lock_is_not_removed(self):
        path = self.project / ".mcp.json"
        lock = path.with_name(path.name + ".22b-lock")
        lock.touch()
        with self.assertRaises(FileExistsError):
            setup.write_config(path, None, b"{}")
        self.assertTrue(lock.exists())

    def test_matching_environment_reused_without_pip_install(self):
        directory = self.project / "venv"
        (directory / "bin").mkdir(parents=True)
        (directory / "pyvenv.cfg").touch()
        (directory / "bin/python").touch()
        result = subprocess.CompletedProcess([], 0, '{"packages_match":true,"wrapper_match":true}')
        with patch.object(setup, "run", return_value=result) as run:
            setup.install(directory)
        self.assertEqual(len(run.call_args_list), 2)
        self.assertEqual(run.call_args_list[-1].args[0][-2:], ["pip", "check"])

    def test_mismatched_wrapper_reinstalls_only_wrapper(self):
        directory = self.project / "venv"
        (directory / "bin").mkdir(parents=True)
        (directory / "pyvenv.cfg").touch()
        (directory / "bin/python").touch()
        result = subprocess.CompletedProcess([], 0, '{"packages_match":true,"wrapper_match":false}')
        with patch.object(setup, "run", return_value=result) as run:
            setup.install(directory)
        command = run.call_args_list[1].args[0]
        self.assertIn("--no-deps", command)
        self.assertIn("--force-reinstall", command)
        self.assertTrue(str(command[-1]).endswith("mcp-requirements.txt"))

    def test_native_packages_never_fall_back_to_source_builds(self):
        directory = self.project / "venv"
        (directory / "bin").mkdir(parents=True)
        (directory / "pyvenv.cfg").touch()
        (directory / "bin/python").touch()
        result = subprocess.CompletedProcess([], 0, '{"packages_match":false,"wrapper_match":true}')
        with patch.object(setup, "run", return_value=result) as run:
            setup.install(directory)
        self.assertIn("--only-binary=:all:", run.call_args_list[1].args[0])

    def test_existing_non_venv_untouched(self):
        with self.assertRaisesRegex(ValueError, "not a usable venv"):
            setup.install(self.project)

    def test_launcher_uses_absolute_path_and_keeps_venv_symlink(self):
        entry = setup.configuration("codex", self.python)
        self.assertEqual(entry["command"], str(self.python))
        self.assertEqual(entry["args"], ["-I", str(ROOT / "setup/kepler_server.py")])


if __name__ == "__main__":
    unittest.main()
