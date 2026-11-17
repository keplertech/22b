import ast
import hashlib
import importlib.util
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/backend/gcd"
TREE = ast.parse((EXAMPLE / "reference/edit.py").read_text())
ROWS = next(ast.literal_eval(node.value) for node in ast.walk(TREE)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "rows" for t in node.targets))
# Exercise the actual edit function without importing a native package in offline CI.
FUNCTIONS = ast.Module(body=[n for n in TREE.body if isinstance(n, ast.FunctionDef)], type_ignores=[])
EDIT = {}
exec(compile(FUNCTIONS, "edit.py", "exec"), EDIT)


class Pin:
    def __init__(self, net=None):
        self.net = net

    def get_upper_net(self):
        return self.net

    def connect_upper_net(self, net):
        self.net = net


class Gate:
    def __init__(self, model, pins):
        self.model = model
        self.pins = pins
        self.deleted = False

    def get_model_name(self):
        return self.model

    def get_term(self, name):
        return self.pins.get(name)

    def delete(self):
        self.deleted = True


class Top:
    def __init__(self):
        self.nets = {f"{prefix}{i}": object() for prefix in "abx" for i in range(5)}
        self.nets["c0"] = object()
        self.gates = {}
        for i in range(5):
            pins = {pin: Pin(self.nets[f"{prefix}{i}"]) for pin, prefix in (("A", "a"), ("B", "b"), ("X", "x"))}
            pins["C"] = Pin(self.nets["c0" if i == 0 else f"x{i-1}"])
            self.gates[f"_{215+i}_"] = Gate("sky130_fd_sc_hd__maj3_2", pins)
        self.side_loads = [Pin(self.nets[f"x{i}"]) for i in range(5)]
        self.ports = {}

    def get_child_instance(self, name):
        return self.gates.get(name)

    def get_net(self, name):
        return self.nets.get(name)

    def get_term(self, name):
        return self.ports.get(name)

    def create_net(self, name):
        if name in self.nets:
            raise ValueError(name)
        self.nets[name] = object()
        return self.nets[name]

    def create_child_instance(self, *, model, name):
        _, output_pin, function = CELLS[model]
        pins = (*function.__code__.co_varnames[:function.__code__.co_argcount], output_pin)
        self.gates[name] = Gate(model, {pin: Pin() for pin in pins})
        return self.gates[name]


# The cells the rewrite uses: output pin and Boolean function of the Liberty cell.
CELLS = {f"sky130_fd_sc_hd__{name}_1": (name, pin, function) for name, pin, function in (
    ("and2", "X", lambda A, B: A & B),
    ("or2", "X", lambda A, B: A | B),
    ("nand2", "Y", lambda A, B: 1 - (A & B)),
    ("nor2", "Y", lambda A, B: 1 - (A | B)),
    ("inv", "Y", lambda A: 1 - A),
    ("a21oi", "Y", lambda A1, A2, B1: 1 - ((A1 & A2) | B1)),
    ("o21ai", "Y", lambda A1, A2, B1: 1 - ((A1 | A2) & B1)),
)}


class GcdTests(unittest.TestCase):
    def test_truth_table_all_2048_inputs_and_five_outputs(self):
        self.assertEqual(len(ROWS), 23)
        for bits in itertools.product((0, 1), repeat=11):
            values = dict(zip([f"a{i}" for i in range(5)] + [f"b{i}" for i in range(5)] + ["c0"], bits))
            expected = []
            carry = values["c0"]
            for i in range(5):
                carry = int(values[f"a{i}"] + values[f"b{i}"] + carry >= 2)
                expected.append(carry)
            for model, output, output_pin, inputs in ROWS:
                self.assertIn(model, CELLS, f"Unknown Boolean model: {model}")
                _, pin, function = CELLS[model]
                self.assertEqual(output_pin, pin)
                self.assertNotIn(output, values)
                values[output] = function(**{name: values[key] for name, key in inputs.items()})
            self.assertEqual([values[f"x{i}"] for i in range(5)], expected, bits)

    def test_actual_edit_keeps_boundary_objects_and_wires_every_pin(self):
        top = Top()
        originals = list(top.gates.values())
        outputs = [pin.net for pin in top.side_loads]
        EDIT["edit"](top)
        self.assertTrue(all(gate.deleted for gate in originals))
        live = [gate for gate in top.gates.values() if not gate.deleted]
        self.assertEqual(len(live), 23)
        self.assertTrue(all(pin.net is not None for gate in live for pin in gate.pins.values()))
        for i, output in enumerate(outputs):
            self.assertIs(top.side_loads[i].net, output)
            drivers = [gate for gate in live if gate.get_term(CELLS[gate.model][1]).net is output]
            self.assertEqual(len(drivers), 1)

    def test_a_row_cannot_read_a_term_before_it_is_driven(self):
        # x0 is an original net: it exists from the start, but its new driver comes with its row.
        source = ast.unparse(FUNCTIONS).replace("{'A1': 'p0', 'A2': 'c0', 'B1': 'g0'}", "{'A1': 'p0', 'A2': 'x0', 'B1': 'g0'}")
        broken = {}
        exec(compile(source, "edit.py", "exec"), broken)
        top = Top()
        with self.assertRaisesRegex(AssertionError, "read before it is driven"):
            broken["edit"](top)
        self.assertEqual(len(top.gates), 5)

    def test_broken_chain_is_rejected_before_mutation(self):
        top = Top()
        top.gates["_217_"].pins["C"].net = object()
        with self.assertRaises(AssertionError):
            EDIT["edit"](top)
        self.assertEqual(len(top.gates), 5)
        self.assertFalse(any(gate.deleted for gate in top.gates.values()))

    def test_new_gates_and_nets_never_share_a_name(self):
        top = Top()
        before = set(top.nets)
        EDIT["edit"](top)
        created = set(top.nets) - before
        # 23 gates drive the 5 original boundary nets and 18 new ones.
        self.assertEqual(len(created), 18)
        self.assertFalse(created & set(top.gates))

    def test_name_collision_is_rejected_before_mutation(self):
        # One Verilog name space: a new name must be unused by nets, instances and ports alike.
        for kind in ("nets", "gates", "ports"):
            for name in ("ppa_cla_nG41", "ppa_cla_nG41_net", "ppa_cla_x4"):
                top = Top()
                getattr(top, kind)[name] = object()
                with self.subTest(kind=kind, name=name):
                    with self.assertRaises(AssertionError):
                        EDIT["edit"](top)
                    self.assertEqual(len(top.gates), 5 + (kind == "gates"))
                    self.assertEqual(len(top.nets), 16 + (kind == "nets"))

    def test_missing_target_rejected(self):
        top = Top()
        del top.gates["_218_"]
        with self.assertRaises(AssertionError):
            EDIT["edit"](top)

    def test_original_input_hashes(self):
        history = json.loads((EXAMPLE / "reference/historical-results.json").read_text())
        for name, key in [("input.v", "input_sha256"), ("constraints.sdc", "sdc_sha256")]:
            self.assertEqual(hashlib.sha256((EXAMPLE / name).read_bytes()).hexdigest(), history[key])

    def test_historical_provenance_consistent(self):
        history = json.loads((EXAMPLE / "reference/historical-results.json").read_text())
        toolchain = json.loads((ROOT / "toolchain.json").read_text())
        self.assertEqual(history["kind"], "historical_demo_not_current_validation")
        self.assertEqual(history["fixture_revision"], toolchain["gcd"]["fixture_revision"])
        self.assertEqual(history["openroad_image"], toolchain["gcd"]["historical_openroad_image"])


class FixtureTests(unittest.TestCase):
    def setUp(self):
        quiet = patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)
        spec = importlib.util.spec_from_file_location("fetch_fixture", EXAMPLE / "platform/fetch_fixture.py")
        self.fetcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.fetcher)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "fixture"

    def fake_download(self, url, timeout):
        self.assertIn(url, self.fetcher.URLS.values())
        self.assertEqual(timeout, 30)
        return io.BytesIO(b"fixture data\n")

    def test_fetch_and_reuse_without_network(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=self.fake_download) as request:
            self.fetcher.fetch(self.destination)
            self.assertEqual(request.call_count, len(self.fetcher.FILES))
            urls = [call.args[0] for call in request.call_args_list]
            self.assertIn(self.fetcher.BASE + "test/sky130hd/sky130_fd_sc_hd__tt_025C_1v80.lib", urls)
            self.assertIn(self.fetcher.BASE + "test/sky130hd/sky130_fd_sc_hd_merged.lef", urls)
            self.assertNotIn(self.fetcher.BASE + "test/sky130hd/sky130hd_tt.lib", urls)
            for name in self.fetcher.FLOW_FILES:
                self.assertIn(self.fetcher.FLOW_BASE + name, urls)
                self.assertNotIn(self.fetcher.BASE + name, urls)
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=AssertionError("Unexpected download")):
            self.fetcher.fetch(self.destination)

    def test_modified_cache_rejected(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=self.fake_download):
            self.fetcher.fetch(self.destination)
        (self.destination / "test/flow.tcl").write_text("modified")
        with self.assertRaisesRegex(ValueError, "Modified fixture"):
            self.fetcher.fetch(self.destination)

    def test_old_or_mismatched_flow_revision_cache_is_rejected(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=self.fake_download):
            self.fetcher.fetch(self.destination)
        path = self.destination / "manifest.json"
        original = json.loads(path.read_text())
        for revision in (None, self.fetcher.REVISION):
            manifest = dict(original)
            if revision is None:
                del manifest["flow_revision"]
            else:
                manifest["flow_revision"] = revision
            path.write_text(json.dumps(manifest))
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.fetcher.verify(self.destination)

    def test_only_flow_scripts_move_to_binary_revision(self):
        pins = json.loads((ROOT / "toolchain.json").read_text())
        self.assertEqual(self.fetcher.FLOW_REVISION, pins["openroad"]["source_revision"])
        self.assertEqual(set(self.fetcher.FLOW_FILES),
                         {"test/helpers.tcl", "test/flow_helpers.tcl", "test/flow.tcl"})
        for name, url in self.fetcher.URLS.items():
            base = self.fetcher.FLOW_BASE if name in self.fetcher.FLOW_FILES else self.fetcher.BASE
            self.assertEqual(url, base + self.fetcher.SOURCES[name])

    def test_partial_cache_is_not_reused(self):
        self.destination.mkdir()
        with self.assertRaises(FileNotFoundError):
            self.fetcher.fetch(self.destination)

    def test_cache_from_old_alias_mapping_rejected(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=self.fake_download):
            self.fetcher.fetch(self.destination)
        path = self.destination / "manifest.json"
        manifest = json.loads(path.read_text())
        del manifest["sources"]
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.fetcher.verify(self.destination)

    def test_failed_download_never_marks_cache_complete(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                self.fetcher.fetch(self.destination)
        self.assertFalse((self.destination / "manifest.json").exists())

    def test_lfs_pointer_rejected(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", return_value=io.BytesIO(b"version https://git-lfs.github.com/spec/v1")):
            with self.assertRaisesRegex(ValueError, "Missing fixture content"):
                self.fetcher.fetch(self.destination)


if __name__ == "__main__":
    unittest.main()
