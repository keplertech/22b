# GCD Backend Task

An example for a model to solve using the [backend skill](../../../flow/backend/SKILL.md),
not a prescribed optimization recipe. Give the model [task.md](task.md), the
original design, and its platform inputs. Let it choose and justify the change.

## Inputs

- [task.md](task.md): objective, constraints, and expected evidence.
- [input.v](input.v): original mapped GCD, top `gcd`, 249 leaf cells.
- [constraints.sdc](constraints.sdc): original timing constraints, 4.36 ns clock.
- [Platform](platform/README.md): pinned SKY130HD technology data and physical setup.
- [License](LICENSE.OpenROAD): upstream notice for the design and constraints.

Tool installation and orchestration belong to the shared skills, not this task.
Write attempts to a fresh `runs/` directory; do not modify these inputs.

## Reference (Contains The Answer)

[reference/](reference/README.md) preserves the worked solution, replay steps,
historical measurements, and demo. Do not read or supply it as initial context
for a fresh model attempt. Consult it afterward for comparison, or explicitly
choose the deterministic reference regression rather than an independent attempt.

The [reference workflow](../../../.github/workflows/gcd-reference-verify.yml)
tests package installation and the real tool stages using that saved solution.
It does not evaluate a model's ability to discover an optimization.
