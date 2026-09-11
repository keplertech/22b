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

    rows = [
        ('sky130_fd_sc_hd__and2_1', 'g0', 'a0', 'b0', '-', '-', '-'),
        ('sky130_fd_sc_hd__or2_1', 'p0', 'a0', 'b0', '-', '-', '-'),
        ('sky130_fd_sc_hd__and2_1', 'g1', 'a1', 'b1', '-', '-', '-'),
        ('sky130_fd_sc_hd__or2_1', 'p1', 'a1', 'b1', '-', '-', '-'),
        ('sky130_fd_sc_hd__and2_1', 'g2', 'a2', 'b2', '-', '-', '-'),
        ('sky130_fd_sc_hd__or2_1', 'p2', 'a2', 'b2', '-', '-', '-'),
        ('sky130_fd_sc_hd__and2_1', 'g3', 'a3', 'b3', '-', '-', '-'),
        ('sky130_fd_sc_hd__or2_1', 'p3', 'a3', 'b3', '-', '-', '-'),
        ('sky130_fd_sc_hd__and2_1', 'g4', 'a4', 'b4', '-', '-', '-'),
        ('sky130_fd_sc_hd__or2_1', 'p4', 'a4', 'b4', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g11', '-', '-', 'p1', 'g0', 'g1'),
        ('sky130_fd_sc_hd__and2_1', 'p11', 'p1', 'p0', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g21', '-', '-', 'p2', 'g1', 'g2'),
        ('sky130_fd_sc_hd__and2_1', 'p21', 'p2', 'p1', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g31', '-', '-', 'p3', 'g2', 'g3'),
        ('sky130_fd_sc_hd__and2_1', 'p31', 'p3', 'p2', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g41', '-', '-', 'p4', 'g3', 'g4'),
        ('sky130_fd_sc_hd__and2_1', 'p41', 'p4', 'p3', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g22', '-', '-', 'p21', 'g0', 'g21'),
        ('sky130_fd_sc_hd__and2_1', 'p22', 'p21', 'p0', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g32', '-', '-', 'p31', 'g11', 'g31'),
        ('sky130_fd_sc_hd__and2_1', 'p32', 'p31', 'p11', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g42', '-', '-', 'p41', 'g21', 'g41'),
        ('sky130_fd_sc_hd__and2_1', 'p42', 'p41', 'p21', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'g44', '-', '-', 'p42', 'g0', 'g42'),
        ('sky130_fd_sc_hd__and2_1', 'p44', 'p42', 'p0', '-', '-', '-'),
        ('sky130_fd_sc_hd__a21o_1', 'x0', '-', '-', 'p0', 'c0', 'g0'),
        ('sky130_fd_sc_hd__a21o_1', 'x1', '-', '-', 'p11', 'c0', 'g11'),
        ('sky130_fd_sc_hd__a21o_1', 'x2', '-', '-', 'p22', 'c0', 'g22'),
        ('sky130_fd_sc_hd__a21o_1', 'x3', '-', '-', 'p32', 'c0', 'g32'),
        ('sky130_fd_sc_hd__a21o_1', 'x4', '-', '-', 'p44', 'c0', 'g44'),
    ]

    # Validate every new name before mutating the candidate.
    for _, output_key, *_ in rows:
        name = f'ppa_cla_{output_key}'
        assert top.get_child_instance(name) is None, f'Instance already exists: {name}'
        if output_key not in wires:
            assert top.get_net(name) is None, f'Net already exists: {name}'

    for model, output_key, *inputs in rows:
        instance_name = f'ppa_cla_{output_key}'
        if output_key not in wires:
            wires[output_key] = create_net(top, instance_name)
        new_inst = top.create_child_instance(model=model, name=instance_name)
        for pin_name, input_key in zip(['A', 'B', 'A1', 'A2', 'B1'], inputs):
            if input_key != '-':
                connect_term(new_inst.get_term(pin_name), wires[input_key])
        connect_term(new_inst.get_term('X'), wires[output_key])

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
    print(f'NAJA_EDIT: replaced 5 majority gates with 31 prefix-network gates; {before} -> {after} leaf instances')
    print('NAJA_EDIT: existing boundary nets reused; registers unchanged')
    print(f'OUTPUT={a.output}')
