"""Opt-in live editing with numbered Verilog checkpoints and checked undo."""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import threading

from tools.live_session import LiveDesignSession, SEC, _fingerprint
from tools.session_history import RevisionHistory, digest, write_json


class VersionedDesignSession(LiveDesignSession):
    def _record(self):
        record = super()._record()
        if hasattr(self, "history"):
            current = getattr(self, "_checkpoint_live_hash", None) == self._candidate_hash
            record.update(netlist_revision=self.history.active if current else None,
                          last_saved_revision=self.history.active, retention=self.history.retention,
                          best_revision=self.history.best["revision"] if self.history.best else None)
            write_json(self.directory / "status.json", record)
        return record

    def __init__(self, reference, liberty_files, work_dir=None, *, retention=10,
                 objective=None, sessions_root="runs", timeout=600):
        self._history_lock = threading.RLock()
        if work_dir is None:
            root = Path(sessions_root)
            root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            work_dir = root / ("session_" + stamp)
        super().__init__(reference, liberty_files, work_dir, timeout=timeout)
        try:
            self.history = RevisionHistory(self.directory, retention, objective)
            self.inputs = self.directory / "inputs"
            self.inputs.mkdir()
            self.reference_file = self.inputs / "golden.v"
            shutil.copyfile(reference, self.reference_file)
            self.reference_file.chmod(0o400)
            self.libraries = []
            for i, source in enumerate(self._liberty_paths):
                destination = self.inputs / f"cells-{i:03}.lib"
                shutil.copyfile(source, destination)
                destination.chmod(0o400)
                self.libraries.append(destination)
            self._input_hashes = {str(p): digest(p) for p in [self.reference_file, *self.libraries]}
            if digest(self.reference_file) != self._source_hashes[str(Path(reference).resolve())]:
                raise ValueError("Reference changed while starting the session")
            if any(digest(dst) != self._source_hashes[str(src)]
                   for src, dst in zip(self._liberty_paths, self.libraries)):
                raise ValueError("Library changed while starting the session")
            self._undo_count = 0
            self._checkpoint_live_hash = None
            self._checkpoint_epoch = 0
            super().verify()
            self._checkpoint(initial=True)
        except BaseException:
            super().close()
            raise

    def _check_inputs(self):
        if any(digest(path) != sha for path, sha in self._input_hashes.items()):
            raise ValueError("Session baseline or libraries were modified")

    def _file_sec(self, directory, candidate):
        # Notebook cells already have an event loop. The file-based MCP client
        # owns another loop; keep it off the kernel's thread, like the live client.
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(SEC.run_sec, directory, self.reference_file, candidate,
                                   self.libraries, timeout=self.timeout).result()

    def _checkpoint(self, initial=False):
        self._check_inputs()
        staging = Path(tempfile.mkdtemp(prefix=".checkpoint-", dir=self.directory))
        try:
            with self._inspection_access():
                before = self._candidate_hash
                if initial:
                    shutil.copyfile(self.reference_file, staging / "design.v")
                else:
                    self._candidate.dumpVerilog(str(staging), "design.v")
                    shutil.copyfile(self.directory / f"revision-{self.revision:04d}/edit.py", staging / "edit.py")
                live_proof = json.loads(json.dumps(self.proof))
            proof = self._file_sec(staging / "export-proof", staging / "design.v")
            self._check_inputs()
            with self._inspection_access():
                if before != self._candidate_hash:
                    raise RuntimeError("Candidate changed during checkpoint verification")
                record = self.history.publish(staging, self.revision, {
                    "top": self._candidate.getName(), "live_proof": live_proof,
                    "export_proof": proof, "candidate_reference": dict(self._candidate_ref),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                self._checkpoint_live_hash = before
                self._checkpoint_epoch += 1
                self._record()
                return record
        except BaseException as error:
            if staging.exists():
                # Do not publish a failed/partial export as a selectable revision.
                write_json(staging / "error.json", {"error": str(error)})
            raise

    def apply_edit(self, script):
        with self._history_lock:
            self._check_inputs()
            result = super().apply_edit(script)
            self._checkpoint()
            return result

    def checkpoint(self, revision=None):
        """Return an explicit historical version or the current saved design."""
        with self._history_lock:
            with self._inspection_access():
                self._check_inputs()
                if revision is None and self._checkpoint_live_hash != self._candidate_hash:
                    raise RuntimeError("Live candidate has unsaved changes; undo or repair it before current inspection")
                return self.history.get(revision)

    @contextmanager
    def use_checkpoint(self, revision=None):
        """Pin the exact tool input for the duration of an external run/query."""
        with self._history_lock:
            record = self.checkpoint(revision)
            with self.history.acquire(record["revision"]) as leased:
                yield leased

    def configure_history(self, *, retention):
        with self._history_lock:
            self.history.configure(retention)

    def record_measurement(self, metrics, *, context, evidence, revision=None):
        with self._history_lock:
            record = self.checkpoint(revision)
            return self.history.measure(record["revision"], metrics, context, evidence)

    def undo(self):
        """Restore first; only then delete the discarded netlist checkpoint."""
        from kepler_formal_mcp.session_bridge import SessionBridge

        with self._history_lock:
            self._check_inputs()
            self._undo_count += 1
            output = self.directory / f"undo-{self._undo_count:04d}"
            output.mkdir()
            with self._inspection_access():
                target = self.history.undo_target(
                    discard=self._checkpoint_live_hash == self._candidate_hash)
            # Revalidate the actual persisted file before replacing any live objects.
            file_proof = self._file_sec(output / "file-proof", target["verilog_file"])
            with self._operation:
                self._check()
                old_bridge = self._bridge
                if self._pending or not old_bridge.lock.acquire(blocking=False):
                    raise RuntimeError("Native work is running; undo is blocked")
                try:
                    self.history.get(target["revision"])
                    self._check_inputs()
                    self.state, self.proof = "restoring", None
                    self._record()
                    # Naja can reuse native IDs on reload. Expire the old binding
                    # BEFORE destroying objects; old agent references must fail.
                    detached = self._client.call("close_session", {"session_id": self._session_id})
                    if detached.get("status") != "success":
                        raise RuntimeError("Kepler could not detach before undo")
                    old_bridge.close()
                    db = self._candidate.getDB()
                    for library in list(db.getLibraries()):
                        if not library.isPrimitives():
                            for design in list(library.getSNLDesigns()):
                                design.destroy()
                    db.loadVerilog([target["verilog_file"]])
                    self._candidate = db.getTopDesign()
                    if self._candidate is None:
                        raise RuntimeError("Restored file did not produce a top design")
                    self._universe.setTopDesign(self._candidate)
                    self._candidate_hash = _fingerprint(self._candidate)
                    self._bridge = SessionBridge(output_dir=output / "formal").start()
                    self._golden_ref = self._bridge.design_reference(self._golden)
                    self._candidate_ref = self._bridge.design_reference(self._candidate)
                    self._check()
                except BaseException:
                    self.state, self.proof = "invalid", None
                    self._record()
                    raise
                finally:
                    old_bridge.lock.release()
                attached = self._client.call("attach_session", {
                    "connection_file": str(self._bridge.connection_file)})
                write_json(output / "attachment-result.json", attached)
                if attached.get("status") != "success" or attached.get("session_id") != self._bridge.session_id:
                    self.state, self.proof = "invalid", None
                    self._record()
                    raise RuntimeError("Kepler could not reattach after undo")
                self._session_id = attached["session_id"]
                proof = self._verify()
                self.history.finish_undo(target["revision"])
                self._checkpoint_live_hash = self._candidate_hash
                self._checkpoint_epoch += 1
                self._record()
                result = {"restored_revision": target["revision"], "proof": proof,
                          "export_proof": file_proof, "attempt_counter": self.revision,
                          "reattach_required": True}
                write_json(output / "result.json", result)
                return result

    def close(self):
        with self._history_lock:
            super().close()
