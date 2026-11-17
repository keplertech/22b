"""A narrow editing contract, not a security sandbox for hostile Python."""

import ast
import builtins


BUILTINS = {name: getattr(builtins, name) for name in (
    "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list",
    "max", "min", "range", "reversed", "set", "sorted", "str", "sum", "tuple",
    "zip", "Exception", "RuntimeError", "ValueError", "AssertionError")}
METHODS = frozenset({
    "get_child_instance", "get_child_instances", "get_leaf_children", "get_term",
    "get_terms", "get_net", "get_nets", "get_upper_net", "get_lower_net",
    "get_bits", "get_bit", "get_name", "get_model_name", "get_direction",
    "is_input", "is_output", "is_inout", "is_leaf", "is_sequential",
    "create_net", "create_child_instance", "connect_upper_net", "disconnect",
    "delete", "rename", "set_name", "get", "items", "keys", "values", "append", "extend",
    "add", "update", "pop", "copy", "index", "count",
})


def validate_script(source):
    """Permit pure helper definitions and calls on the provided candidate only."""
    if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
        raise ValueError("Edit script must be text no larger than 1 MiB")
    tree = ast.parse(source, filename="candidate-edit.py")
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    edits = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "edit"]
    if (len(edits) != 1 or len(edits[0].args.args) != 1 or edits[0].args.posonlyargs
            or edits[0].args.kwonlyargs or edits[0].args.vararg or edits[0].args.kwarg):
        raise ValueError("Define exactly one edit(top) function")
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if not isinstance(node, ast.FunctionDef):
            raise ValueError("Only function definitions are allowed at module level; no imports/load/reset/export")
    forbidden = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.ClassDef,
                 ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom, ast.With, ast.AsyncWith)
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise ValueError(f"Unsupported editing construct: {type(node).__name__}")
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list or node.args.defaults or node.args.kw_defaults or node.returns:
                raise ValueError("Edit helpers cannot have decorators, defaults or return annotations")
        if isinstance(node, ast.arg) and (node.annotation or (node.arg.startswith("_") and node.arg != "_")):
            raise ValueError("Private names and annotations are not allowed")
        if isinstance(node, ast.Name) and node.id.startswith("_") and node.id != "_":
            raise ValueError("Private names are not allowed")
        if isinstance(node, ast.Attribute) and node.attr not in METHODS:
            raise ValueError(f"Unsupported editing attribute: {node.attr}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in functions | BUILTINS.keys():
                raise ValueError(f"Unsupported editing call: {node.func.id}")
            if not isinstance(node.func, (ast.Name, ast.Attribute)):
                raise ValueError("Indirect editing calls are not allowed")
    return compile(tree, "candidate-edit.py", "exec", optimize=0)


def editing_function(source):
    code = validate_script(source)
    namespace = {"__builtins__": dict(BUILTINS)}
    exec(code, namespace)
    return namespace["edit"]


def shared_names(top):
    """(module, name) for each instance named like a net or port of its module.

    Verilog keeps a module's instances, nets and ports in one name space.
    NajaEDA keeps them apart: it creates such a pair and exports it, and its
    own reader, Kepler Formal and OpenROAD accept the file, so neither SEC nor
    the physical flow fails. Strict readers such as Verilator and Yosys reject
    it, and OpenROAD loses the extracted parasitics of those nets.
    """
    found, seen, pending = set(), set(), [top]
    while pending:
        design = pending.pop()
        module = design.get_model_name()
        if module in seen:
            continue
        seen.add(module)
        children = list(design.get_child_instances())
        taken = {item.get_name() for item in (*design.get_nets(), *design.get_terms())} - {""}
        found.update((module, name) for name in (child.get_name() for child in children) if name in taken)
        pending.extend(child for child in children if not child.is_leaf())
    return found


def explain_shared_names(names):
    listed = sorted(names)
    text = ", ".join(f"{name} (module {module})" for module, name in listed[:8])
    if len(listed) > 8:
        text += f" and {len(listed) - 8} more"
    return ("An instance has the name of a net or port of its module, which Verilog "
            f"does not allow: {text}. Rename one of each pair with set_name")


def main():
    """Check an exported netlist, reloaded from the file as the flow's tools read it."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fail if an instance of the netlist has the name of a net or port of its module.")
    parser.add_argument("--liberty", required=True, nargs="+")
    parser.add_argument("--verilog", required=True)
    args = parser.parse_args()
    from najaeda import netlist

    netlist.reset()
    netlist.load_liberty(args.liberty)
    top = netlist.load_verilog([args.verilog])
    if top is None:
        parser.exit(1, "Name check failed: no top loaded\n")
    found = shared_names(top)
    if found:
        parser.exit(1, f"Name check failed: {explain_shared_names(found)}\n")
    print("NAMES_OK: no instance has the name of a net or port")


if __name__ == "__main__":
    main()
