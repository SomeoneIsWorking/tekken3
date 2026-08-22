---
id: C006
kind: claim
status: holds
created: 2026-08-21
tags: t3-04,oracle,initializer-return
depends: tools/recomp_boundary.py#render_slices, tools/recomp_boundary.py#compare_boundary, tests/recomp_boundary.cpp#main, tools/verify_startup.py#verify_startup
reconfirmed: 2026-08-22
verified_at: 2026-08-22 19:08:18
---

## Claim

Tekken 3 generated execution matches independent Mednafen after the first initializer returns and at the next initializer entry.

## Evidence

On the real hashed USA SLUS_004.02 with psxport 3418a79b624765614f3f198dc1e89632e1e650f0, shipping-emitter slices [0x80028BA0,0x80028BB8), [0x80079D10,0x80079D80), and [0x80028BB8,0x80028BC0) agree with independent Mednafen on all 35 CPU fields after the first initializer returns at 0x80028BB8 (oracle step 106181) and at the next initializer entry 0x800B0548 (step 106183). The 6/6 selftest detects altered CPU state/source and refuses missing or unmeasured boundaries.

## What would falsify it

The executable/hash, verified slice ranges or bytes, psxport emitter/interpreter, oracle trace semantics, generated runner, or comparator changes; or a repeat ceases to agree 35/35 at either measured edge.

## Re-confirmed 2026-08-22

2026-08-22 Clang verify against psxport 7f5d3f13 matched Mednafen 35/35 at the first-initializer return and next-initializer entry, with SELFTEST 7/7 opposite-answer/refusal coverage.

## Re-confirmed 2026-08-22

2026-08-22 full Clang verify passed 35/35 CPU-field agreement at first-initializer return 0x80028BB8 and next-initializer entry 0x800B0548; CTest 6/6 passed.
