---
id: 2
title: crt0_extract labels Tekken 3 main loop as libcInit
status: investigating
symptom: crt0_extract reports 0x80028BA0 under the generic libcInit field, but Ghidra decompiles it as the non-returning game main loop
tags: tool,crt0,reverse-engineering
created: 2026-08-20
updated: 2026-08-20
---

## Root cause

`crt0_scan` stops at the first JAL opcode and stores its target in the field named `libcInit`. Tekken 3 performs its BSS/stack/heap setup inline and then calls its non-returning game main loop directly, so the field name does not describe this executable's control flow.

## What was tried / dead ends

Treating `COMPLETE (8 of 8)` or the derived heap plan as proof that the target is InitHeap is ruled out: the tool itself reports that `0x80028BA0` is not the A(39h) thunk and that the JAL delay slot is not `addi a0,a0,4`. Ghidra decompiles the target as the game loop. `crossvalidate_crt0.py` also cannot validate this shape: a 400,000-instruction oracle window never reached its assumed out-of-image BIOS boundary, so it refused after comparing zero fields.

## Resolution

Unresolved in the shared framework. Tekken 3 documentation treats `0x80028BA0` as the measured first startup target and T3-03 explicitly requires a direct-to-main boot model. The proper framework change is to generalize the field/report vocabulary and extend the independent cross-validator for startup shapes that call main directly; no game-side semantic alias or guessed InitHeap call is permitted.
