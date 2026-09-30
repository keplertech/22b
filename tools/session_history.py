"""Numbered, integrity-checked checkpoints; no native tools required here."""

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    data = json.dumps(value, indent=2, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class RevisionHistory:
    def __init__(self, directory, retention=10, objective=None):
        self.directory = Path(directory)
        self.versions = self.directory / "versions"
        self.versions.mkdir()
        self.records = {}
        self.active = None
        self.high_water = -1
        self.leases = {}
        self.best = None
        self.context = None
        self.objective = json.loads(json.dumps(objective)) if objective is not None else None
        if self.objective is not None:
            weights = self.objective.get("weights", {})
            if not weights or not all(self._number(x) for x in weights.values()):
                raise ValueError("Objective requires finite numeric weights (lower score wins)")
            for bounds in self.objective.get("bounds", {}).values():
                if not set(bounds) <= {"min", "max"} or not all(self._number(x) for x in bounds.values()):
                    raise ValueError("Objective bounds must be finite min/max values")
        self.configure(retention)

    @staticmethod
    def _number(value):
        return type(value) in (int, float) and math.isfinite(value)

    def configure(self, retention):
        if type(retention) is not int or retention < 1:
            raise ValueError("Retention must be a positive integer")
        self.retention = retention
        write_json(self.directory / "config.json", {"retention": retention, "objective": self.objective})
        self.prune()

    def _pointer(self):
        write_json(self.directory / "current.json", {"revision": self.active,
                                                     "high_water": self.high_water})

    def publish(self, staging, revision, metadata):
        if type(revision) is not int or revision <= self.high_water:
            raise ValueError("Revision numbers must increase and cannot be reused")
        staging = Path(staging)
        if not (staging / "design.v").is_file() or not (staging / "design.v").stat().st_size:
            raise ValueError("Missing checkpoint netlist")
        record = dict(metadata, revision=revision, parent=self.active)
        record["files"] = {str(p.relative_to(staging)): digest(p)
                           for p in staging.rglob("*") if p.is_file()}
        write_json(staging / "manifest.json", record)
        destination = self.versions / f"revision-{revision:04d}"
        staging.rename(destination)
        self.records[revision] = {"directory": destination,
                                  "manifest_hash": digest(destination / "manifest.json")}
        self.active = self.high_water = revision
        self._pointer()
        self.prune()
        return self.get(revision)

    def get(self, revision=None):
        revision = self.active if revision is None else revision
        if type(revision) is not int or revision not in self.records:
            raise ValueError("Revision is not retained in this session")
        entry = self.records[revision]
        directory = entry["directory"]
        if digest(directory / "manifest.json") != entry["manifest_hash"]:
            raise ValueError("Checkpoint manifest was modified")
        record = json.loads((directory / "manifest.json").read_text())
        for name, expected in record["files"].items():
            path = directory / name
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or digest(path) != expected:
                raise ValueError("Checkpoint file was modified: " + name)
        return dict(record, directory=str(directory), verilog_file=str(directory / "design.v"))

    @contextmanager
    def acquire(self, revision=None):
        record = self.get(revision)
        key = record["revision"]
        self.leases[key] = self.leases.get(key, 0) + 1
        try:
            yield record
            self.get(key)
        finally:
            self.leases[key] -= 1
            self.prune()

    def prune(self):
        # Baseline is permanent; active tool inputs are never deleted mid-run.
        recent = sorted(key for key in self.records if key != 0)
        keep = set(recent[-self.retention:]) | {0, self.active}
        for key in list(self.records):
            if key not in keep and not self.leases.get(key):
                shutil.rmtree(self.records.pop(key)["directory"])

    def undo_target(self, discard=True):
        if discard:
            candidates = [key for key in self.records if key < self.active]
            if not candidates:
                raise ValueError("No previous checkpoint to restore")
            if self.leases.get(self.active):
                raise RuntimeError("Current revision is in use by another tool")
            return self.get(max(candidates))
        return self.get()

    def finish_undo(self, target):
        self.get(target)
        discarded = [key for key in self.records if key > target]
        if any(self.leases.get(key) for key in discarded):
            raise RuntimeError("A discarded revision is still in use")
        self.active = target
        self._pointer()
        for key in discarded:
            shutil.rmtree(self.records.pop(key)["directory"])
        # high_water deliberately does not decrease after undo.

    def measure(self, revision, metrics, context, evidence):
        record = self.get(revision)
        if not metrics or not all(self._number(x) for x in metrics.values()):
            raise ValueError("Measurements must be finite numeric values")
        if not context or not evidence:
            raise ValueError("Measurements require setup identity and evidence files")
        if self.context is not None and context != self.context:
            raise ValueError("Measurement setup differs from earlier results")
        objective = self.objective
        if objective:
            required = set(objective["weights"]) | set(objective.get("bounds", {}))
            if not required <= metrics.keys():
                raise ValueError("Missing objective metrics")
        directory = Path(record["directory"]) / "measurements"
        directory.mkdir(exist_ok=False)
        for index, source in enumerate(evidence):
            source = Path(source)
            shutil.copyfile(source, directory / f"{index:03d}-{source.name}")
        result = {"revision": revision, "design_sha256": record["files"]["design.v"],
                  "metrics": metrics, "context": context, "promoted": False}
        self.context = json.loads(json.dumps(context))
        if objective:
            score = sum(metrics[key] * weight for key, weight in objective["weights"].items())
            if not math.isfinite(score):
                raise ValueError("Objective score is not finite")
            eligible = record["export_proof"]["status"] == "proved" or (
                objective.get("allow_unproven", False) and record["export_proof"]["status"] == "warning")
            for key, bounds in objective.get("bounds", {}).items():
                eligible &= (metrics[key] >= bounds.get("min", -math.inf)
                             and metrics[key] <= bounds.get("max", math.inf))
            result.update(score=score, eligible=bool(eligible))
            result["promoted"] = bool(eligible and (self.best is None or score < self.best["score"]))
        write_json(directory / "result.json", result)
        if result["promoted"]:
            # A real copy, not a link into the rolling history.
            temporary = Path(tempfile.mkdtemp(prefix=".best-", dir=self.directory))
            shutil.copytree(record["directory"], temporary, dirs_exist_ok=True)
            best = self.directory / "best"
            previous = self.directory / ".previous-best"
            if best.exists():
                best.rename(previous)
            try:
                temporary.rename(best)
            except BaseException:
                if previous.exists():
                    previous.rename(best)
                raise
            if previous.exists():
                shutil.rmtree(previous)
            self.best = dict(result)
        return result
