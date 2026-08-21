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

tools/verify_startup.py matched 18/18 machine-code structural facts on the provisioned hashed executable and passed 10/10 agreement/disagreement/refusal fixtures. This includes both `game_main` initializer calls and delay words plus the first initializer's exact `jr ra` return. Fresh Ghidra 12.0.4 decompilation of FUN_80079c70, FUN_80028ba0, and FUN_80079d10 confirms the entry/main relationship and first initializer semantics.

## What would falsify it

The selected executable changes; an earlier entry or `game_main` call appears; either call, delay slot, initializer return, return guard, or loop back-edge changes; or independent control-flow analysis shows 0x80028BA0 is not the game main loop.
