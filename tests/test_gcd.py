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

    def get_child_instance(self, name):
        return self.gates.get(name)

    def get_net(self, name):
        return self.nets.get(name)

    def create_net(self, name):
        if name in self.nets:
            raise ValueError(name)
        self.nets[name] = object()
        return self.nets[name]

    def create_child_instance(self, *, model, name):
        pins = ("A1", "A2", "B1", "X") if "__a21o_" in model else ("A", "B", "X")
        self.gates[name] = Gate(model, {pin: Pin() for pin in pins})
        return self.gates[name]


class GcdTests(unittest.TestCase):
    def test_truth_table_all_2048_inputs_and_five_outputs(self):
        self.assertEqual(len(ROWS), 31)
        for bits in itertools.product((0, 1), repeat=11):
            values = dict(zip([f"a{i}" for i in range(5)] + [f"b{i}" for i in range(5)] + ["c0"], bits))
            expected = []
            carry = values["c0"]
            for i in range(5):
                carry = int(values[f"a{i}"] + values[f"b{i}"] + carry >= 2)
                expected.append(carry)
            for model, output, *inputs in ROWS:
                args = [values[key] for key in inputs if key != "-"]
                if "__and2_" in model:
                    result = args[0] & args[1]
                elif "__or2_" in model:
                    result = args[0] | args[1]
                elif "__a21o_" in model:
                    result = (args[0] & args[1]) | args[2]
                else:
                    self.fail(f"Unknown Boolean model: {model}")
                self.assertNotIn(output, values)
                values[output] = result
            self.assertEqual([values[f"x{i}"] for i in range(5)], expected, bits)

    def test_actual_edit_keeps_boundary_objects_and_wires_every_pin(self):
        top = Top()
        originals = list(top.gates.values())
        outputs = [pin.net for pin in top.side_loads]
        EDIT["edit"](top)
        self.assertTrue(all(gate.deleted for gate in originals))
        live = [gate for gate in top.gates.values() if not gate.deleted]
        self.assertEqual(len(live), 31)
        self.assertTrue(all(pin.net is not None for gate in live for pin in gate.pins.values()))
        for i, output in enumerate(outputs):
            self.assertIs(top.side_loads[i].net, output)
            drivers = [gate for gate in live if gate.get_term("X").net is output]
            self.assertEqual(len(drivers), 1)

    def test_broken_chain_is_rejected_before_mutation(self):
        top = Top()
        top.gates["_217_"].pins["C"].net = object()
        with self.assertRaises(AssertionError):
            EDIT["edit"](top)
        self.assertEqual(len(top.gates), 5)
        self.assertFalse(any(gate.deleted for gate in top.gates.values()))

    def test_name_collision_is_rejected_before_mutation(self):
        top = Top()
        top.nets["ppa_cla_g44"] = object()
        with self.assertRaises(AssertionError):
            EDIT["edit"](top)
        self.assertEqual(len(top.gates), 5)

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
        self.assertTrue(url.startswith(self.fetcher.BASE))
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
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=AssertionError("Unexpected download")):
            self.fetcher.fetch(self.destination)

    def test_modified_cache_rejected(self):
        with patch.object(self.fetcher.urllib.request, "urlopen", side_effect=self.fake_download):
            self.fetcher.fetch(self.destination)
        (self.destination / "test/flow.tcl").write_text("modified")
        with self.assertRaisesRegex(ValueError, "Modified fixture"):
            self.fetcher.fetch(self.destination)

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
