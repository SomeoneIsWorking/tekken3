---
id: 3
title: Boot probe crashes before the direct-main boundary
status: resolved
symptom: The first psxport leg exits with SIGSEGV after loading the PS-X EXE, before the observer reaches game_main
tags: harness,psxport,core,lifecycle
created: 2026-08-21
updated: 2026-08-21
---

## Root cause

The probe first placed the roughly 12 MB `Core` object on the process stack, overflowing it. Moving
`Core` to the heap exposed a second lifecycle violation: constructing `Core` alone leaves `core.game`
null, while the interpreter consults `game->platform_hle` at every JAL target. The shipping machine
owner is `Game`, whose constructor wires that invariant.

## Resolution

The probe heap-allocates `Game`, uses its `Core` member, and captures the direct-main boundary through
the normal `PcObserver` seam. The permanent two-engine selftest passes its agreement,
forced-disagreement, and too-short-window refusal cases. No framework change or null bypass was added.
