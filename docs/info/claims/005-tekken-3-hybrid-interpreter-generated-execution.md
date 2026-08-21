---
id: C005
kind: claim
status: holds
created: 2026-08-21
tags: t3-04,oracle,recompiler,first-initializer
depends: tools/recomp_boundary.py#render_prefix, tools/recomp_boundary.py#compare_boundary, tests/recomp_boundary.cpp#main, tools/verify_startup.py#verify_startup
---

## Claim

Tekken 3 hybrid interpreter/generated execution agrees with independent Mednafen on all 35 CPU fields before game_main first initializer 0x80079D10.

## Evidence

C005/I005: provisioned USA executable SHA-256 fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c; verify_startup matches 12/12 structural facts including 0x80028BB0 -> 0x80079D10 and delay word 0xAFB00010. With verified psxport pin 9f1bb9279e8607de3fd4315dd52410726bd7ff7b, tools/recomp_boundary.py renders six instructions [0x80028BA0,0x80028BB8) with psxport emit_func; the hybrid port and independent Mednafen agree 35/35 before 0x80079D10 at oracle step 106159. Permanent 5/5 selftest detects altered a0, altered generated source, and missing boundary trace.

## What would falsify it

The selected executable/hash, startup first-call bytes, psxport emitter/decoder, interpreter state at direct-main, oracle trace semantics, generated runner, or comparator changes; or a repeat ceases to agree 35/35 at the measured edge.
