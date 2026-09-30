"""Real packaged-tool history guards, independent of the physical GCD run."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.live_session_regression import LIBERTY, FIRST, SECOND, DIFFERENT
from scripts.gcd_undo_regression import ScopeClient
from tools.scope_checkpoints import ScopeCheckpoints
from tools.versioned_session import VersionedDesignSession
from tools.live_session import SEC


def run(work):
    work.mkdir(parents=True, exist_ok=False)
    source, library = work / "input.v", work / "cells.lib"
    source.write_text("module top(input a, output y); BUF g(.A(a), .Y(y)); endmodule\n")
    library.write_text(LIBERTY)
    with VersionedDesignSession(source, [library], sessions_root=work, retention=2) as session:
        client = ScopeClient(work, 120)
        scope = ScopeCheckpoints(session, client.call)
        try:
            def gates():
                response = scope.query("find", {"pattern": "*", "kind": "instance", "limit": 200})
                return sorted(item["path"] for item in response["result"]["matches"])

            initial = gates()
            original = session.mcp_attachment()
            for script in (FIRST, SECOND):
                assert session.apply_edit(script)["proved_outputs"] == 1
            assert gates() == ["top.g", "top.h1", "top.h2"]
            checkpoint_before_error = session.checkpoint()
            with patch.object(SEC, "run_sec", side_effect=RuntimeError("simulated export check failure")):
                try:
                    session.apply_edit('def edit(top):\n    top.create_net("unsaved")\n')
                except RuntimeError as error:
                    assert "simulated export" in str(error)
                else:
                    raise AssertionError("Failed checkpoint was published")
            assert session.status()["netlist_revision"] is None
            assert session.history.active == checkpoint_before_error["revision"]
            assert session.undo()["restored_revision"] == 2
            try:
                session.apply_edit(DIFFERENT)
            except ValueError as error:
                assert "counterexample" in str(error)
            else:
                raise AssertionError("Counterexample accepted")
            try:
                session.checkpoint()
            except RuntimeError:
                pass
            else:
                raise AssertionError("Stale checkpoint claimed as current")
            # A failed edit restores the last saved version, without discarding it.
            assert session.undo()["restored_revision"] == 2
            assert gates() == ["top.g", "top.h1", "top.h2"]
            before_failed_undo = session.status()
            with patch.object(SEC, "run_sec", side_effect=RuntimeError("simulated restore proof failure")):
                try:
                    session.undo()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Undo ignored its failed file check")
            assert session.status() == before_failed_undo
            assert Path(session.checkpoint()["verilog_file"]).exists()
            assert session.undo()["restored_revision"] == 1
            assert gates() == ["top.g", "top.h"]
            assert session.undo()["restored_revision"] == 0
            assert gates() == initial
            assert session.mcp_attachment()["session_id"] != original["session_id"]
            stale = session._client.call("verify_session", {
                "session_id": session.mcp_attachment()["session_id"],
                "design1": original["design1"], "design2": original["design2"], "verification": "sec"})
            assert stale["status"] == "error"  # Native IDs may match; binding identity cannot.
            assert session.apply_edit(FIRST)["revision"] == 5  # Never reuse discarded IDs.
            assert gates() == ["top.g", "top.h"]
            for number in range(3):
                session.apply_edit(f'def edit(top):\n    top.create_net("unused{number}")\n')
            assert sorted(session.history.records) == [0, 7, 8]
            session.configure_history(retention=1)
            assert sorted(session.history.records) == [0, 8]
            artifact = session.checkpoint()
            Path(artifact["verilog_file"]).write_text("corrupt export")
            before = session.status()
            try:
                session.checkpoint()
            except ValueError:
                pass
            else:
                raise AssertionError("Modified checkpoint accepted")
            assert session.status() == before  # Disk tampering never mutates live golden/candidate.
            (work / "result.json").write_text(json.dumps({"status": "passed", "retention": True,
                "undo": True, "scope_refresh": True, "counterexample_rejected": True,
                "failed_edit_recovered": True, "stale_native_reference_rejected": True,
                "failed_checkpoint_unpublished": True, "failed_undo_nondestructive": True,
                "post_undo_edit": True, "modified_checkpoint_rejected": True}, indent=2) + "\n")
            print("PASS: real SEC, Scope, undo, retention, continued edits and stale-ID rejection", flush=True)
        finally:
            client.close()


def run_notebook(work):
    from jupyter_client import KernelManager
    from scripts.gcd_reference_regression import clean_env

    work.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="22b-history-kernel-", dir="/tmp") as private:
        manager = KernelManager(transport="ipc", connection_file=str(Path(private) / "connection.json"))
        manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        manager.start_kernel(cwd=str(ROOT), env=clean_env())
        client = manager.blocking_client()
        client.start_channels()
        try:
            client.wait_for_ready(timeout=30)
            code = ("from pathlib import Path\nfrom scripts.versioned_session_regression import run\n"
                    f"run(Path({str(work / 'native')!r}))\n")
            (work / "cell.py").write_text(code)
            request = client.execute(code, store_history=False, allow_stdin=False)
            deadline = time.monotonic() + 600
            error = None
            with (work / "kernel.log").open("w") as log:
                while True:
                    message = client.get_iopub_msg(timeout=max(0.1, deadline - time.monotonic()))
                    if message.get("parent_header", {}).get("msg_id") != request:
                        continue
                    kind, content = message["msg_type"], message["content"]
                    if kind == "stream":
                        log.write(content["text"])
                    elif kind == "error":
                        error = content["ename"] + ": " + content["evalue"]
                        log.write(error + "\n")
                    elif kind == "status" and content["execution_state"] == "idle":
                        break
            if error:
                raise RuntimeError(error)
            if json.loads((work / "native/result.json").read_text())["status"] != "passed":
                raise RuntimeError("Missing successful notebook history result")
            print("PASS: versioned history, Scope and SEC inside a real Jupyter kernel", flush=True)
        finally:
            client.stop_channels()
            manager.shutdown_kernel(now=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--jupyter", action="store_true")
    args = parser.parse_args()
    (run_notebook if args.jupyter else run)(args.work_dir.resolve())
