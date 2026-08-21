---
id: C004
kind: claim
status: holds
created: 2026-08-21
tags: t3-03,oracle,direct-main
depends: tools/boot_oracle.py#run_harness
---

## Claim

Tekken 3 psxport and independent Mednafen execution are deterministic and agree on all 35 CPU fields immediately before the verified direct-main target 0x80028BA0.

## Evidence

On the real hashed USA SLUS_004.02 with verified psxport pin ce2c83adb0fce89c44eb764f2abf3e4f999d32a8, two psxport interpreter runs and two oracle_trace runs agreed 35/35 at oracle step 106153. The 3/3 permanent selftest uses both real engines, detects a forced a0 disagreement, and refuses a one-step window.

## What would falsify it

The selected executable, framework interpreter, oracle CPU/capture logic, entry-boundary probe, or comparison parser changes; either leg becomes nondeterministic; a forced field change is accepted; or independent evidence places the call boundary elsewhere.
