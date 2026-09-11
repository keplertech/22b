"""Fetch only the pinned OpenROAD GCD test data, never a tool source checkout."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[3]
REVISION = json.loads((ROOT / "toolchain.json").read_text())["gcd"]["fixture_revision"]
BASE = f"https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD/{REVISION}/"
FILES = (
    "LICENSE", "test/helpers.tcl", "test/flow_helpers.tcl", "test/flow.tcl",
    "test/sky130hd/sky130hd.vars", "test/sky130hd/sky130hd.tlef",
    "test/sky130hd/sky130hd_std_cell.lef", "test/sky130hd/sky130hd_tt.lib",
    "test/sky130hd/sky130_fd_sc_hd__ff_n40C_1v95.lib",
    "test/sky130hd/sky130_fd_sc_hd__ss_n40C_1v40.lib",
    "test/sky130hd/sky130hd.pdn.tcl", "test/sky130hd/sky130hd.tracks",
    "test/sky130hd/sky130hd.rc", "test/sky130hd/sky130hd.rcx_rules",
)
# GitHub raw serves symlink text rather than the referenced file's contents.
SOURCES = {
    name: {
        "test/sky130hd/sky130hd_tt.lib": "test/sky130hd/sky130_fd_sc_hd__tt_025C_1v80.lib",
        "test/sky130hd/sky130hd_std_cell.lef": "test/sky130hd/sky130_fd_sc_hd_merged.lef",
    }.get(name, name)
    for name in FILES
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest["revision"] != REVISION or set(manifest["files"]) != set(FILES)
            or manifest.get("sources") != SOURCES):
        raise ValueError("Fixture revision or file inventory does not match")
    for name in FILES:
        if digest(directory / name) != manifest["files"][name]:
            raise ValueError(f"Modified fixture file: {name}")


def fetch(directory):
    if directory.exists():
        verify(directory)
        print(f"Verified existing fixture: {directory}")
        return
    directory.mkdir(parents=True)
    hashes = {}
    for name in FILES:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {name}", flush=True)
        with urllib.request.urlopen(BASE + SOURCES[name], timeout=30) as response:
            data = response.read()
        if not data or data.startswith(b"version https://git-lfs.github.com/spec/"):
            raise ValueError(f"Missing fixture content: {name}")
        path.write_bytes(data)
        hashes[name] = digest(path)
    (directory / "manifest.json").write_text(
        json.dumps({"revision": REVISION, "sources": SOURCES, "files": hashes}, indent=2) + "\n"
    )
    verify(directory)
    print(f"Fixture ready: {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        fetch(args.directory.resolve())
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Fixture unavailable: {error}\nUse a fresh path for an incomplete cache.\n")
