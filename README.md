# 22b

Skills for AI-assisted hardware design using open-source tools.

Start with the [orchestration skill](SKILL.md). It selects a flow, loads only
the relevant tool guidance, and connects analysis, editing, verification and
measurement. There is no chatbot runtime or model dependency in this repository.

```text
SKILL.md                   Parent orchestration skill
flow/backend/              Physical-design analysis and improvement
flow/rtl/                  RTL authoring and design changes
examples/backend/gcd/      GCD carry-chain restructuring example
examples/rtl/              RTL example conventions
tools/                     Shared tool skills and package installation guides
toolchain.json             Pinned package and fixture references
tests/                     Fast, offline repository and example checks
```

## Demo

Watch the GCD timing-improvement flow: OpenROAD, AI report analysis,
Naja-Scope inspection, NajaEDA editing, Kepler Formal SEC, and a second
OpenROAD run to compare the results.

https://github.com/user-attachments/assets/deadc1db-22f3-4c32-8f59-9bbca4aa1ccd

46 seconds, no audio.

## Start

1. Read the [package setup](tools/README.md). Kepler Formal uses Nix and the
   public `keplertech` Cachix cache; no source submodules are required in 22b.
2. Choose the [backend](flow/backend/SKILL.md) or [RTL](flow/rtl/SKILL.md) flow.
3. For a concrete backend example, follow [GCD](examples/backend/gcd/README.md).

An agent can read these files directly. [AGENTS.md](AGENTS.md) points agents to
the same entry point; human users can follow the same procedures. Skills are
instructions, not a security sandbox or an API that enforces verification.

## Verification And Evidence

Run Kepler Formal **SEC** after an edit. Report full proof, partial proof,
inconclusive proof, counterexample and tool error distinctly. Partial or
inconclusive proof is a non-blocking warning, never a claim of full equivalence.
Counterexamples and tool errors stop the candidate flow.

Keep originals unchanged and save each candidate, commands, tool versions,
input hashes, proof coverage and physical reports in a separate `runs/` directory.
Never claim a PPA improvement from gate counts alone.

## Checks

```sh
python3 -m unittest discover -s tests -v
```

CI runs these offline checks; it does not install a model or silently launch
an expensive physical-design run. The GCD guide describes the separate tool run.
