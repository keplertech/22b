# Install Kepler Formal With Nix

The upstream package exposes `#kepler-formal` on `x86_64-linux` and
`aarch64-darwin`. See the [pinned upstream Nix instructions](https://github.com/keplertech/kepler-formal/blob/0e0abf2aa6979e337aead8996983952dc1742530/README.md#nix--nixos).

First check an existing `kepler-formal --help`. If installation is needed,
configure the public cache once, with permission to modify Nix configuration:

```sh
nix run --max-jobs 0 --builders '' \
  github:NixOS/nixpkgs/8ce4ef6cb6f871616146b9fe26d2a5ae594e94fe#cachix -- use keplertech
```

`cachix use` obtains the cache's actual signing key; do not invent a key or
disable signature checks. On NixOS, review and apply the generated configuration
with `sudo nixos-rebuild switch`. No Cachix account or download token is needed.

Install the pinned CLI into the current user's profile:

```sh
nix profile add --max-jobs 0 --builders '' \
  'git+https://github.com/keplertech/kepler-formal?rev=0e0abf2aa6979e337aead8996983952dc1742530&submodules=1#kepler-formal'
kepler-formal --help
```

The `submodules=1` query is part of upstream Nix source acquisition, not a Git
submodule in 22b. Nix resolves the package and obtains published binaries from
`https://keplertech.cachix.org` and dependencies from the configured Nix caches.

**Cache availability for this pinned revision has not yet been verified here.**
If a required binary is absent, this command fails rather than compiling. Ask
the package maintainer to publish that revision or agree on another cached pin;
do not silently remove the no-build flags. Never request a cache write token for
ordinary installation.

Kepler includes its own runtime for primitives. Do not inject an unrelated Naja
build with `PYTHONPATH`; install the separate [NajaEDA package](../najaeda/install.md)
for editing. Test the installed CLI with a small equivalent and inequivalent
pair before relying on it for a new platform or package revision.
