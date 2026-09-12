# Install OpenROAD

Check `openroad -version` first. The [pinned Nixpkgs definition](https://github.com/NixOS/nixpkgs/blob/b6018f87da91d19d0ab4cf979885689b469cdd41/pkgs/by-name/op/openroad/package.nix)
packages OpenROAD `2.0-unstable-2025-03-01`. Its Linux output and 194-entry runtime
closure were verified in `cache.nixos.org`, and cache-only installation was
tested; the output path is recorded in [toolchain.json](../../toolchain.json).
The previously selected 26Q2 output was not cached, so it could not be installed
with source builds disabled. OpenROAD now has its own package pin, independent
of the Python/tooling Nixpkgs pin. Use the same package for both designs:

```sh
nix profile add --max-jobs 0 --builders '' \
  github:NixOS/nixpkgs/b6018f87da91d19d0ab4cf979885689b469cdd41#openroad
openroad -version
```

Availability of a compatible cached binary must be checked on the target
platform; cache metadata does not establish physical-flow compatibility.
The complete reference run still requires validation with this older package.
The corresponding `aarch64-darwin` binary was not cached when checked, so this
pin is currently verified for Linux installation only, not macOS installation.
If unavailable, stop rather than compiling implicitly. OpenROAD does
not come from the `keplertech` Kepler cache merely because that cache is enabled.

The workflow uses [install-cached-package.sh](../install-cached-package.sh) to
check the exact output before downloading package dependencies. It reuses a
present output or requires cache availability, preserves installation logs and
exit codes even on failure, and keeps signature checks and no-build flags enabled.

The GCD historical measurements used a different, pinned prebuilt Docker image,
recorded in [toolchain.json](../../toolchain.json). New Nix-package measurements
need a fresh baseline; do not compare their candidate against the historical
numbers and attribute every difference to the edit.

The executable is not the PDK or a complete flow. Obtain matching Liberty, LEF,
RC/extraction data, constraints and Tcl scripts separately. The GCD guide pins
its small test fixture; no tool compilation or Git submodule is required.

See [official OpenROAD build/install documentation](https://openroad.readthedocs.io/en/latest/user/Build.html)
for platform-specific package alternatives. Check disk space before large downloads.
