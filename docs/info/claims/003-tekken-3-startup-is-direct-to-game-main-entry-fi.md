---
id: C003
kind: claim
status: holds
created: 2026-08-21
tags: crt0,direct-main,t3-03a
depends: tools/verify_startup.py#verify_startup
reconfirmed: 2026-08-21
verified_at: 2026-08-21 11:21:50
---

## Claim

Tekken 3 startup is direct-to-game_main: entry first-calls 0x80028BA0, traps if it returns, and that target owns the non-returning frame loop.

## Evidence

tools/verify_startup.py matched 12/12 machine-code structural facts on the provisioned hashed executable and passed 7/7 agreement/disagreement/refusal fixtures. This includes `game_main`'s first call at 0x80028BB0, its 0x80079D10 target, and exact 0xAFB00010 delay word. A fresh Ghidra 12.0.4 decompile of FUN_80079c70 and FUN_80028ba0 shows the entry call then trap and the target initialization followed by an infinite mode/frame loop.

## What would falsify it

The selected executable changes; an earlier entry or `game_main` call appears; either call, delay slot, return guard, or loop back-edge changes; or independent control-flow analysis shows 0x80028BA0 is not the game main loop.

## Re-confirmed 2026-08-21

Post-landing Clang verify passed startup 12/12, startup selftest 7/7, direct-main oracle 3/3, and T3-04 generated boundary 35/35 at step 106159 against psxport 9f1bb927.
