---
id: C005
kind: claim
status: holds
created: 2026-08-21
tags: t3-04,oracle,recompiler,first-initializer
depends: tools/recomp_boundary.py#render_slices, tools/recomp_boundary.py#compare_boundary, tests/recomp_boundary.cpp#main, tools/verify_startup.py#verify_startup
---

## Claim

Tekken 3 hybrid interpreter/generated execution agrees with independent Mednafen on all 35 CPU fields before game_main first initializer 0x80079D10.

## Evidence

C005/I005: provisioned USA executable SHA-256 fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c; verify_startup matches 18/18 structural facts. With verified psxport pin 692b9b20e3d4a6194452522060fd2657c2235f40, tools/recomp_boundary.py regenerates exact shipping-emitter slices and the hybrid port still agrees 35/35 with independent Mednafen before 0x80079D10 at oracle step 106159. The expanded permanent 6/6 selftest detects altered a0, altered generated source, missing boundary traces, and unmeasured runner targets.

## What would falsify it

The selected executable/hash, startup first-call bytes, psxport emitter/decoder, interpreter state at direct-main, oracle trace semantics, generated runner, or comparator changes; or a repeat ceases to agree 35/35 at the measured edge.
