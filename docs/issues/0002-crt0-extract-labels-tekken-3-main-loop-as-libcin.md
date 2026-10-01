---
id: 2
title: crt0_extract labels Tekken 3's main loop as libcInit
status: resolved
symptom: crt0_extract reports 0x80028BA0 under the generic libcInit field, but Ghidra decompiles it as the non-returning game main loop
tags: reverse-engineering,binary-fact
created: 2026-08-20
updated: 2026-08-21
---

**The label is not semantic evidence.** `crt0_scan` stops at the first JAL opcode and stores its
target in a field named `libcInit`. Tekken 3 does its BSS/stack/heap setup inline and then calls its
non-returning main loop directly, so the field name describes the tool, not this executable.

The real structure, in bytes: entry `0x80079C70` jumps at `0x80079D04` to `0x80028BA0` (`game_main`,
naming the boundary `libcInit` obscures), a `break` guards against return at `0x80079D0C`, and
`0x80028E0C` returns to the frame-loop body at `0x80028BCC`. Recorded in
`titles/tekken3/executable.json` and `titles/tekken3/README.md`.