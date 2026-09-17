"""One caller-owned Python/Jupyter session, immutable golden, evolving candidate."""

import asyncio
from concurrent.futures import Future
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import sys
import threading

from tools.edit_validation import editing_function


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("live_sec", ROOT / "tools/kepler-formal/verify.py")
SEC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEC)


def _fingerprint(design):
    """Hash in-memory connectivity and model revisions without exporting a design."""
    digest = hashlib.sha256()
    visited = set()
    pending = [design]

    def add(value):
        digest.update(json.dumps(value, sort_keys=True, default=str).encode() + b"\n")

    def identity(value):
        return list(value.getNLID().toTuple()) if value is not None else None

    while pending:
        current = pending.pop()
        key = current.getNLID().toTuple()
        if key in visited:
            continue
        visited.add(key)
        add(("design", key, current.getName(), current.getRevisionCount()))
        for term in current.getBitTerms():
            add(("term", identity(term), str(term.getDirection()), str(term.getRole()),
                 identity(term.getNet())))
        for net in current.getBitNets():
            add(("net", identity(net), net.getName(), net.getTypeAsString()))
        for instance in current.getInstances():
            model = instance.getModel()
            add(("instance", identity(instance), instance.getName(), identity(model)))
            for term in instance.getInstTerms():
                add(("connection", identity(term), identity(term.getNet())))
            pending.append(model)
    return digest.hexdigest()


class _McpClient:
    """Keep MCP async contexts in one task, even across separate notebook cells."""

    def __init__(self, directory, timeout):
        self.directory = directory
        self.timeout = timeout
        self.requests = queue.Queue()
        self.ready = Future()
        self.pending = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="22b-kepler-client")
        self.thread.start()
        self.tools = self.ready.result(timeout=30)

    def _run(self):
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(error)
            if self.pending is not None and not self.pending.done():
                self.pending.set_exception(error)

    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "NAJAEDA_SRC", "EQUIVALENCE_CHECK"):
            env.pop(name, None)
        params = StdioServerParameters(command=sys.executable, args=["-m", "kepler_formal_mcp"],
                                      env=env, cwd=str(self.directory))
        with (self.directory / "mcp-server.log").open("w") as log:
            async with stdio_client(params, errlog=log) as streams:
                async with ClientSession(*streams) as session:
                    await asyncio.wait_for(session.initialize(), timeout=10)
                    schemas = await asyncio.wait_for(session.list_tools(), timeout=10)
                    SEC.save(self.directory / "mcp-tools.json", schemas.model_dump(mode="json"))
                    self.ready.set_result({tool.name for tool in schemas.tools})
                    while True:
                        request = await asyncio.to_thread(self.requests.get)
                        if request is None:
                            return
                        name, arguments, future = request
                        try:
                            response = await session.call_tool(name, arguments)
                            future.set_result(SEC.payload(response))
                        except Exception as error:
                            future.set_exception(error)

    def call(self, name, arguments):
        if not self.thread.is_alive() or self.busy():
            raise RuntimeError("MCP transport is unavailable or still processing a request")
        self.pending = Future()
        self.requests.put((name, arguments, self.pending))
        return self.pending.result(timeout=self.timeout + 45)

    def busy(self):
        return self.pending is not None and not self.pending.done()

    def close(self):
        if self.busy():
            raise RuntimeError("MCP request is still running; do not discard the live session")
        self.requests.put(None)
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise RuntimeError("MCP transport did not stop")


class LiveDesignSession:
    """Validate each incremental edit and automatically SEC it against golden.

    Use only in a dedicated trusted Python/Jupyter kernel. The editing contract
    is deliberately restricted; neither Python nor the Naja native API is an OS
    sandbox. No design is exported, reloaded or reset between iterations.
    """

    def __init__(self, reference, liberty_files, work_dir, *, timeout=600,
                 development_mcp_checkout=None):
        from najaeda import naja, netlist
        from kepler_formal_mcp.session_bridge import SessionBridge

        if type(timeout) is not int or timeout <= 0:
            raise ValueError("Timeout must be a positive integer")
        if naja.NLUniverse.get() is not None:
            raise RuntimeError("Start a dedicated kernel: an existing Naja universe must not be reset")
        self.directory = Path(work_dir).resolve()
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.timeout = timeout
        self.revision = 0
        self.proof = None
        self.state = "unverified"
        self._pending = False
        self._closed = False
        self._operation = threading.Lock()
        self._naja, self._netlist = naja, netlist
        self._bridge = self._client = self._universe = None
        self._databases = []
        self._attempt = 0
        try:
            identity = SEC.package_identity(development_mcp_checkout)
            SEC.save(self.directory / "packages.json", identity)
            paths = [Path(reference).resolve(strict=True), *[Path(p).resolve(strict=True) for p in liberty_files]]
            SEC.save(self.directory / "source-hashes.json", {
                str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
            self._universe = naja.NLUniverse.create()
            designs = []
            for _ in range(2):
                db = naja.NLDB.create(self._universe)
                self._databases.append(db)
                if liberty_files:
                    db.loadLibertyPrimitives([str(path) for path in paths[1:]])
                db.loadVerilog([str(paths[0])])
                designs.append(db.getTopDesign())
            # NajaEDA resolves new cell models by searching user DBs in order.
            # Load candidate first so edits never borrow golden's cell models.
            self._candidate, self._golden = designs
            if self._golden is None or self._candidate is None or self._golden is self._candidate:
                raise RuntimeError("Two independent loaded designs are required")
            self._universe.setTopDesign(self._candidate)
            self._golden_hash = _fingerprint(self._golden)
            self._candidate_hash = _fingerprint(self._candidate)
            self._bridge = SessionBridge(output_dir=self.directory / "formal").start()
            self._golden_ref = self._bridge.design_reference(self._golden)
            self._candidate_ref = self._bridge.design_reference(self._candidate)
            self._client = _McpClient(self.directory, timeout)
            if not {"attach_session", "verify_session", "get_session_reports"} <= self._client.tools:
                raise RuntimeError("Install Kepler MCP with the attached-session reports API")
            attached = self._client.call("attach_session", {"connection_file": str(self._bridge.connection_file)})
            if attached.get("status") != "success" or attached.get("pid") != os.getpid():
                raise RuntimeError("Kepler MCP did not attach to this kernel's designs")
            self._session_id = attached["session_id"]
            if (attached.get("design_addressing") != "native-id-v1"
                    or self._golden_ref["session_id"] != self._session_id
                    or self._candidate_ref["session_id"] != self._session_id):
                raise RuntimeError("Install matching Kepler MCP native-ID session support")
            info = self._client.call("get_kepler_formal_info", {})
            if info.get("status") != "success":
                raise RuntimeError("Attached native API capability check failed")
            SEC.save(self.directory / "native-info.json", info)
            self._record()
        except BaseException:
            if self._client is not None:
                self._client.close()
            if self._bridge is not None:
                self._bridge.close()
            if self._universe is not None:
                self._universe.destroy()
            raise

    def _record(self):
        result = {"kernel_pid": os.getpid(), "revision": self.revision, "state": self.state,
                  "golden_sha256": self._golden_hash, "proof": self.proof,
                  "candidate_sha256": self._candidate_hash,
                  "golden_reference": self._golden_ref, "candidate_reference": self._candidate_ref,
                  "verification_pending": self._pending, "closed": self._closed}
        SEC.save(self.directory / "status.json", result)
        return json.loads(json.dumps(result))

    def _check(self):
        if self._closed or self.state == "invalid":
            raise RuntimeError("Session is closed or invalid; its proof cannot be reused")
        if self._naja.NLUniverse.get() is not self._universe:
            self.state = "invalid"
            self.proof = None
            self._record()
            raise RuntimeError("Session universe changed outside the editing API")
        if self._client.busy() or not self._bridge.lock.acquire(blocking=False):
            raise RuntimeError("Verification is still running; editing is blocked")
        try:
            try:
                golden = _fingerprint(self._golden)
                candidate = _fingerprint(self._candidate)
            except Exception as error:
                self.state, self.proof = "invalid", None
                self._record()
                raise RuntimeError("Native design handles are no longer valid; stop this session") from error
            if golden != self._golden_hash:
                self.state, self.proof = "invalid", None
                self._record()
                raise RuntimeError("Golden design was modified; stop this session")
            if candidate != self._candidate_hash:
                self.state, self.proof = "invalid", None
                self._record()
                raise RuntimeError("Candidate changed outside the editing API; previous proof is invalid")
        finally:
            self._bridge.lock.release()

    def status(self):
        with self._operation:
            if not self._closed:
                self._check()
            return self._record()

    def apply_edit(self, script):
        function = editing_function(script)
        if not self._operation.acquire(blocking=False):
            raise RuntimeError("Another session operation is running")
        try:
            self._check()
            if self._pending:
                raise RuntimeError("A timed-out proof is unresolved; verify again when idle before editing")
            self.revision += 1
            self.proof, self.state = None, "editing"
            directory = self.directory / f"revision-{self.revision:04}"
            directory.mkdir()
            (directory / "edit.py").write_text(script)
            self._record()
            try:
                with self._bridge.lock:
                    self._universe.setTopDesign(self._candidate)
                    try:
                        function(self._netlist.get_top())
                    finally:
                        self._candidate_hash = _fingerprint(self._candidate)
                        self._check()
            except BaseException as error:
                self.proof = None
                if self.state != "invalid":
                    self.state = "edit_error"
                SEC.save(directory / "error.json", {"error": str(error)})
                self._record()
                raise
            return self._verify()
        finally:
            self._operation.release()

    def verify(self):
        if not self._operation.acquire(blocking=False):
            raise RuntimeError("Another session operation is running")
        try:
            self._check()
            return self._verify()
        finally:
            self._operation.release()

    def _verify(self):
        self.proof, self.state = None, "verifying"
        self._pending = True
        self._attempt += 1
        directory = self.directory / f"proof-{self._attempt:04}"
        directory.mkdir()
        arguments = {"session_id": self._session_id,
                     "design1": dict(self._golden_ref), "design2": dict(self._candidate_ref),
                     "verification": "sec", "solver": "kissat", "max_k": 32,
                     "sec_engine": "pdr", "sec_encoding": "dual_rail_steady",
                     "allow_boundary_mismatch": False, "report_skipped_outputs": True,
                     "timeout_seconds": self.timeout, "log_file_name": f"proof-{self._attempt:04}.log"}
        SEC.save(directory / "request.json", {"revision": self.revision, "arguments": arguments})
        self._record()
        try:
            result = self._client.call("verify_session", arguments)
            SEC.save(directory / "result.json", result)
            if result.get("may_still_be_running"):
                raise TimeoutError("SEC timed out and may still be running; edits remain blocked")
            self._pending = False
            self._check()
            if result.get("pid") != os.getpid() or result.get("session_id") != self._session_id:
                raise ValueError("Verification came from a different session")
            if result.get("design1") != self._golden_ref or result.get("design2") != self._candidate_ref:
                raise ValueError("Verification came from different native designs")
            # Retrieve the report through the new API and require this exact proof.
            if result.get("report_id"):
                reports = self._client.call("get_session_reports", {
                    "session_id": self._session_id, "report_id": result["report_id"]})
                SEC.save(directory / "reports.json", reports)
                if (reports.get("report_id") != result["report_id"]
                        or reports.get("session_id") != self._session_id
                        or reports.get("pid") != os.getpid()
                        or reports.get("design1") != self._golden_ref
                        or reports.get("design2") != self._candidate_ref
                        or reports.get("verification_result") != result.get("verification_result")):
                    raise ValueError("Session report does not match the completed verification")
                SEC.summarize(reports)
            else:
                raise ValueError("Attached verification omitted its report identity")
            summary = SEC.summarize(result)
            summary.update(revision=self.revision, report_id=result.get("report_id"),
                           log=result.get("generated_log_file"))
            self.proof = summary
            self.state = "proved" if summary["status"] == "proved" else "unproven"
            SEC.save(directory / "summary.json", summary)
            self._record()
            return json.loads(json.dumps(summary))
        except BaseException as error:
            self.proof = None
            if self.state != "invalid":
                self.state = "verification_pending" if self._pending else "rejected"
            SEC.save(directory / "error.json", {"error": str(error)})
            self._record()
            raise

    def close(self):
        with self._operation:
            if self._closed:
                return
            if self._client.busy() or not self._bridge.lock.acquire(blocking=False):
                raise RuntimeError("Native work is still running; wait before closing this session")
            self._bridge.lock.release()
            self._client.call("close_session", {"session_id": self._session_id})
            self._client.close()
            self._bridge.close()
            if self._naja.NLUniverse.get() is self._universe:
                self._universe.destroy()
            self._closed, self.state, self.proof = True, "closed", None
            self._record()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
