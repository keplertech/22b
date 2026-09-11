# Install OpenROAD

Check `openroad -version` first. The [pinned Nixpkgs definition](https://github.com/NixOS/nixpkgs/blob/8ce4ef6cb6f871616146b9fe26d2a5ae594e94fe/pkgs/by-name/op/openroad/package.nix)
packages OpenROAD 26Q2. Use the same package for both baseline and candidate:

```sh
nix profile add --max-jobs 0 --builders '' \
  github:NixOS/nixpkgs/8ce4ef6cb6f871616146b9fe26d2a5ae594e94fe#openroad
openroad -version
```

Availability of a compatible cached binary must be checked on the target
platform. If unavailable, stop rather than compiling implicitly. OpenROAD does
not come from the `keplertech` Kepler cache merely because that cache is enabled.

The GCD historical measurements used a different, pinned prebuilt Docker image,
recorded in [toolchain.json](../../toolchain.json). New Nix-package measurements
need a fresh baseline; do not compare their candidate against the historical
numbers and attribute every difference to the edit.

The executable is not the PDK or a complete flow. Obtain matching Liberty, LEF,
RC/extraction data, constraints and Tcl scripts separately. The GCD guide pins
its small test fixture; no tool compilation or Git submodule is required.

See [official OpenROAD build/install documentation](https://openroad.readthedocs.io/en/latest/user/Build.html)
for platform-specific package alternatives. Check disk space before large downloads.
