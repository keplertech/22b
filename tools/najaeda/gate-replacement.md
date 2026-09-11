# Replace Gates While Preserving Connections

Purpose: local structural replacement. This is not a constant-propagation helper.

1. Resolve each target with `top.get_child_instance(name)` and check its model.
   For hierarchical/shared models, establish the intended occurrence and supported
   uniquification procedure before editing; a model-level edit can affect siblings.
2. Capture boundary **net objects**, not guessed names, from
   `instance.get_term(pin).get_upper_net()`. Capture all output nets, including
   intermediate outputs with consumers outside the replacement group.
3. Check every expected chain connection and make new net/instance names unique.
   Validate the complete replacement specification before deleting anything.
4. Create internal nets with `top.create_net(name)` and gates with
   `top.create_child_instance(model=model_name, name=instance_name)`.
5. Connect inputs and outputs with `gate.get_term(pin).connect_upper_net(net)`.
   Connect outputs to the captured original nets so existing consumers remain
   attached. Use upper connections for child-instance pins and lower connections
   for top/model terminals; those are different sides of the hierarchy.
6. Delete the old instances only after every replacement is connected. If any
   operation fails, discard the in-memory candidate; never export a half-edit.
   Temporary overlapping drivers must not survive into an exported design.
7. Export, reload and run SEC. Preserve the input file and record the script.

For a majority carry stage, `x = majority(a,b,c)` equals
`g | (p & c)`, where `g = a & b` and `p = a | b`. Combining group generate and
propagate signals in a prefix network reduces serial carry dependence. Every
original stage output with side consumers must still be reproduced, not only
the final carry. See the complete [GCD example](../../examples/backend/gcd/README.md).
