#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 4 ]]; then
  echo "Usage: $0 NAME PINNED_INSTALLABLE CACHE_URL ARTIFACT_DIR" >&2
  exit 2
fi
name=$1
installable=$2
cache=$3
artifacts=$4
if [[ ! "$name" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "Invalid package name: $name" >&2
  exit 2
fi
mkdir -p "$artifacts"
artifacts=$(cd "$artifacts" && pwd)
(
  trap 'code=$?; printf "%s\n" "$code" > "$artifacts/$name-exit-code.txt"' EXIT
  printf 'Package: %s\nInstallable: %s\nCache: %s\n' "$name" "$installable" "$cache"
  printf '%s\n' "$installable" > "$artifacts/$name-installable.txt"
  nix --version
  nix eval --raw "$installable.outPath" > "$artifacts/$name-store-path.txt"
  store_path=$(cat "$artifacts/$name-store-path.txt")
  if [[ ! "$store_path" =~ ^/nix/store/[a-z0-9]{32}-[^/]+$ ]]; then
    echo "Invalid package output path: $store_path" >&2
    exit 1
  fi

  # Query the output before Nix downloads dependencies for an uncached derivation.
  # Do not use --json for existence: Nix can return null with exit code zero.
  if nix path-info --offline "$store_path" > "$artifacts/$name-local.txt" 2> "$artifacts/$name-local.log"; then
    echo "Reusing existing output: $store_path"
  elif nix path-info --store "$cache" "$store_path" > "$artifacts/$name-cache.txt" 2> "$artifacts/$name-cache.log"; then
    echo "Cached output found: $store_path"
  else
    cat "$artifacts/$name-cache.log" >&2
    echo "No usable cached $name output at $cache; source builds remain disabled." >&2
    exit 1
  fi

  # Signature verification remains enabled; neither local nor remote builds are allowed.
  nix build --max-jobs 0 --builders '' --out-link "$artifacts/$name" "$installable"
  nix path-info --json --json-format 1 "$artifacts/$name" > "$artifacts/$name-installed.json"
) 2>&1 | tee "$artifacts/$name-install.log"
