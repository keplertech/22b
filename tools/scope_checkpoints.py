"""Select numbered checkpoints for a separate, file-based Naja-Scope MCP."""


READ_ONLY = frozenset({"status", "resolve", "find", "get_hierarchy", "get_drivers",
                       "get_loads", "trace_cone", "get_stats", "get_module_card"})


class ScopeCheckpoints:
    """call(tool, arguments) is supplied by the caller's existing MCP client."""

    def __init__(self, session, call):
        self.session = session
        self.call = call
        self.loaded = None

    def query(self, tool, arguments=None, *, revision=None):
        if tool not in READ_ONLY:
            raise ValueError("Checkpoint queries must use typed read-only Scope tools")
        with self.session.use_checkpoint(revision) as checkpoint:
            path = checkpoint["verilog_file"]
            identity = (path, checkpoint["files"]["design.v"])
            status = self.call("status", {})
            if (self.loaded != identity or not status.get("loaded")
                    or path not in status.get("loaded_files", [])):
                self.loaded = None
                self.call("reset_universe", {})  # The Scope process only.
                if self.session.libraries:
                    self.call("load_liberty", {"files": [str(p) for p in self.session.libraries]})
                self.call("load_verilog", {"files": [path]})
                status = self.call("status", {})
                if (not status.get("loaded") or status.get("top", {}).get("name") != checkpoint["top"]
                        or path not in status.get("loaded_files", [])):
                    raise RuntimeError("Scope did not load the selected checkpoint")
                self.loaded = identity
            result = self.call(tool, arguments or {})
            return {"revision": checkpoint["revision"], "design_sha256": identity[1],
                    "result": result, "export_proof": checkpoint["export_proof"]}
