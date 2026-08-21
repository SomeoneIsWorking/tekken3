---
id: C006
kind: claim
status: holds
created: 2026-08-21
tags: t3-04,oracle,initializer-return
depends: tools/recomp_boundary.py#render_slices, tools/recomp_boundary.py#compare_boundary, tests/recomp_boundary.cpp#main, tools/verify_startup.py#verify_startup
---

## Claim

Tekken 3 generated execution matches independent Mednafen after the first initializer returns and at the next initializer entry.

## Evidence

On the real hashed USA SLUS_004.02 with psxport 692b9b20e3d4a6194452522060fd2657c2235f40, shipping-emitter slices [0x80028BA0,0x80028BB8), [0x80079D10,0x80079D80), and [0x80028BB8,0x80028BC0) agree with independent Mednafen on all 35 CPU fields after the first initializer returns at 0x80028BB8 (oracle step 106181) and at the next initializer entry 0x800B0548 (step 106183). The 6/6 selftest detects altered CPU state/source and refuses missing or unmeasured boundaries.

## What would falsify it

The executable/hash, verified slice ranges or bytes, psxport emitter/interpreter, oracle trace semantics, generated runner, or comparator changes; or a repeat ceases to agree 35/35 at either measured edge.
