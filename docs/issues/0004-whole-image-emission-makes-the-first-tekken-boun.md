---
id: 4
title: Whole-image emission makes the first Tekken boundary unnecessarily huge
status: resolved
symptom: T3-04 compiles 1,884 generated functions and floods Clang warnings to test six game_main instructions
tags: harness,recompiler,build,reverse-engineering
created: 2026-08-21
updated: 2026-08-21
---

## Evidence

Binary-wide emission measured 593 executable roots and 1,884 discovered functions. Because Tekken game_main is a non-returning dispatcher, that compiles downstream mode bodies that cannot execute before its first call at 0x80028BB0. Eight shards still produced hundreds of thousands of generated lines and more than 1,000 tautological warnings in individual shards. This does not prove the pointer roots are false; treating that denominator as false-positive evidence is ruled out.

## Resolution

T3-04 preserves the verified interpreter entry-to-main state and invokes psxport tools/recomp/emit.py emit_func only for measured executable slices. The substrate has since grown to exact 6 + 28 + 2 instruction ranges through the first initializer return and next call; independently traced Mednafen agrees on 35/35 CPU fields at all three edges. Generated-source integrity recomputes every slice through the shipping emitter, so this remains a scoped boundary substrate, not a handwritten game_main clone or guessed whole-image seed set.

## Dead end

Do not use emit.py --limit as a boundary slice: it truncates address-sorted output while retaining the full funcset and can leave emitted calls to missing bodies. Do not label the 593 pointer-derived roots false without separate provenance evidence.
