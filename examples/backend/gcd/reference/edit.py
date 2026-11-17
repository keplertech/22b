"""Replay the reviewed GCD prefix rewrite; always export a new candidate file."""

from najaeda import netlist

def get_instance(top, name): return top.get_child_instance(name)

def create_net(top, name): return top.create_net(name)

def connect_term(term, net): term.connect_upper_net(net)

def edit(top):
    instances = [get_instance(top, name) for name in ['_215_', '_216_', '_217_', '_218_', '_219_']]
    assert all(inst is not None and inst.get_model_name() == 'sky130_fd_sc_hd__maj3_2' for inst in instances)

    wires = {}
    for i, inst in enumerate(instances):
        for prefix, pin_name in [('a', 'A'), ('b', 'B'), ('x', 'X')]:
            term = inst.get_term(pin_name)
            assert term is not None
            key = prefix + str(i)
            wires[key] = term.get_upper_net()
            assert wires[key] is not None
    term = instances[0].get_term('C')
    assert term is not None
    wires['c0'] = term.get_upper_net()
    assert wires['c0'] is not None
    assert set(wires) == {'a0', 'a1', 'a2', 'a3', 'a4', 'b0', 'b1', 'b2', 'b3', 'b4', 'x0', 'x1', 'x2', 'x3', 'x4', 'c0'}
    for i in range(1, len(instances)):
        assert instances[i].get_term('C').get_upper_net() == wires[f'x{i-1}']

    # Carry out of bit i: x_i = g_i | p_i & x_(i-1), with g = a & b, p = a | b and x_(-1) = c0.
    # All inputs arrive together, so the carry-in is folded into bit 0 and the terms form a
    # balanced tree. A name starting with n is an inverted term: gates alternate polarity,
    # so every level is a single-stage cell. Rows: cell, output, output pin, inputs.
    rows = [
        # Bit 0 takes the carry-in: nx0 = !(g0 | p0 & c0).
        ('sky130_fd_sc_hd__and2_1', 'g0', 'X', {'A': 'a0', 'B': 'b0'}),
        ('sky130_fd_sc_hd__or2_1', 'p0', 'X', {'A': 'a0', 'B': 'b0'}),
        ('sky130_fd_sc_hd__a21oi_1', 'nx0', 'Y', {'A1': 'p0', 'A2': 'c0', 'B1': 'g0'}),
        ('sky130_fd_sc_hd__inv_1', 'x0', 'Y', {'A': 'nx0'}),
        # Inverted generate and propagate of bits 1 to 4.
        ('sky130_fd_sc_hd__nand2_1', 'ng1', 'Y', {'A': 'a1', 'B': 'b1'}),
        ('sky130_fd_sc_hd__nor2_1', 'np1', 'Y', {'A': 'a1', 'B': 'b1'}),
        ('sky130_fd_sc_hd__nand2_1', 'ng2', 'Y', {'A': 'a2', 'B': 'b2'}),
        ('sky130_fd_sc_hd__nor2_1', 'np2', 'Y', {'A': 'a2', 'B': 'b2'}),
        ('sky130_fd_sc_hd__nand2_1', 'ng3', 'Y', {'A': 'a3', 'B': 'b3'}),
        ('sky130_fd_sc_hd__nor2_1', 'np3', 'Y', {'A': 'a3', 'B': 'b3'}),
        ('sky130_fd_sc_hd__nand2_1', 'ng4', 'Y', {'A': 'a4', 'B': 'b4'}),
        ('sky130_fd_sc_hd__nor2_1', 'np4', 'Y', {'A': 'a4', 'B': 'b4'}),
        # Pairs of bits: G = g_hi | p_hi & g_lo and P = p_hi & p_lo.
        ('sky130_fd_sc_hd__o21ai_1', 'G21', 'Y', {'A1': 'np2', 'A2': 'ng1', 'B1': 'ng2'}),
        ('sky130_fd_sc_hd__nor2_1', 'P21', 'Y', {'A': 'np2', 'B': 'np1'}),
        ('sky130_fd_sc_hd__o21ai_1', 'G43', 'Y', {'A1': 'np4', 'A2': 'ng3', 'B1': 'ng4'}),
        ('sky130_fd_sc_hd__nor2_1', 'P43', 'Y', {'A': 'np4', 'B': 'np3'}),
        # Bits 1 to 4 as one group, inverted.
        ('sky130_fd_sc_hd__a21oi_1', 'nG41', 'Y', {'A1': 'P43', 'A2': 'G21', 'B1': 'G43'}),
        ('sky130_fd_sc_hd__nand2_1', 'nP41', 'Y', {'A': 'P43', 'B': 'P21'}),
        # The carries, on the original nets.
        ('sky130_fd_sc_hd__o21ai_1', 'x1', 'Y', {'A1': 'np1', 'A2': 'nx0', 'B1': 'ng1'}),
        ('sky130_fd_sc_hd__a21oi_1', 'nx2', 'Y', {'A1': 'P21', 'A2': 'x0', 'B1': 'G21'}),
        ('sky130_fd_sc_hd__inv_1', 'x2', 'Y', {'A': 'nx2'}),
        ('sky130_fd_sc_hd__o21ai_1', 'x3', 'Y', {'A1': 'np3', 'A2': 'nx2', 'B1': 'ng3'}),
        ('sky130_fd_sc_hd__o21ai_1', 'x4', 'Y', {'A1': 'nP41', 'A2': 'nx0', 'B1': 'nG41'}),
    ]

    # Validate every new name before mutating the candidate. Verilog keeps a
    # module's instances, nets and ports in one name space, which NajaEDA does
    # not enforce: a new gate and the net it drives get different names, and
    # each must be unused by all three kinds. A row reads earlier rows only.
    driven = set(key for key in wires if key[0] != 'x')
    for _, output_key, _, inputs in rows:
        assert all(key in driven for key in inputs.values()), f'Term read before it is driven: {output_key}'
        driven.add(output_key)
        instance_name = f'ppa_cla_{output_key}'
        new_names = [instance_name] if output_key in wires else [instance_name, f'{instance_name}_net']
        for name in new_names:
            assert top.get_child_instance(name) is None, f'Instance already exists: {name}'
            assert top.get_net(name) is None, f'Net already exists: {name}'
            assert top.get_term(name) is None, f'Port already exists: {name}'

    for model, output_key, output_pin, inputs in rows:
        instance_name = f'ppa_cla_{output_key}'
        if output_key not in wires:
            wires[output_key] = create_net(top, f'{instance_name}_net')
        new_inst = top.create_child_instance(model=model, name=instance_name)
        for pin_name, input_key in inputs.items():
            connect_term(new_inst.get_term(pin_name), wires[input_key])
        connect_term(new_inst.get_term(output_pin), wires[output_key])

    for inst in instances:
        inst.delete()

    return top

if __name__ == '__main__':
    import argparse
    from pathlib import Path
    p = argparse.ArgumentParser(description='Standalone combinational prefix rewrite')
    p.add_argument('--liberty', required=True)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    output = Path(a.output).resolve()
    if output in (Path(a.input).resolve(), Path(a.liberty).resolve()) or output.exists():
        p.error('--output must be a new file, distinct from all inputs')
    output.parent.mkdir(parents=True, exist_ok=True)
    netlist.reset()
    netlist.load_liberty([a.liberty])
    top = netlist.load_verilog([a.input])
    assert top is not None
    before = len(list(top.get_leaf_children()))
    edit(top)
    after = len(list(top.get_leaf_children()))
    top.dump_verilog(a.output)
    print(f'NAJA_EDIT: replaced 5 majority gates with 23 prefix-network gates; {before} -> {after} leaf instances')
    print('NAJA_EDIT: existing boundary nets reused; registers unchanged')
    print(f'OUTPUT={a.output}')
