---
id: 2
title: crt0_extract labels Tekken 3 main loop as libcInit
status: resolved
symptom: crt0_extract reports 0x80028BA0 under the generic libcInit field, but Ghidra decompiles it as the non-returning game main loop
tags: tool,crt0,reverse-engineering
created: 2026-08-20
updated: 2026-08-21
---

## Root cause

`crt0_scan` stops at the first JAL opcode and stores its target in the field named `libcInit`. Tekken 3 performs its BSS/stack/heap setup inline and then calls its non-returning game main loop directly, so the field name does not describe this executable's control flow.

## What was tried / dead ends

Treating `COMPLETE (8 of 8)` or the derived heap plan as proof that the target is InitHeap is ruled out: the tool itself reports that `0x80028BA0` is not the A(39h) thunk and that the JAL delay slot is not `addi a0,a0,4`. Ghidra decompiles the target as the game loop. `crossvalidate_crt0.py` also cannot validate this shape: a 400,000-instruction oracle window never reached its assumed out-of-image BIOS boundary, so it refused after comparing zero fields.

## Resolution

Tekken now owns a direct-main startup manifest and verifier: real bytes prove the first entry call,
return trap, and main-loop back-edge, while fresh Ghidra output proves the target semantics. No Tekken
code consumes `crt0_extract`'s generic `libcInit` label. Generalizing the shared reporter remains
separate framework work; no game-side semantic alias or guessed InitHeap call is permitted.
