---
id: C003
kind: claim
status: holds
created: 2026-08-21
tags: crt0,direct-main,t3-03a
depends: tools/verify_startup.py#verify_startup
reconfirmed: 2026-08-21
verified_at: 2026-08-21 03:33:06
---

## Claim

Tekken 3 startup is direct-to-game_main: entry first-calls 0x80028BA0, traps if it returns, and that target owns the non-returning frame loop.

## Evidence

tools/verify_startup.py matched 8/8 machine-code structural facts on the provisioned hashed executable and passed 5/5 agreement/disagreement/refusal fixtures. A fresh Ghidra 12.0.4 decompile of FUN_80079c70 and FUN_80028ba0 shows the call then trap and the target initialization followed by an infinite mode/frame loop.

## What would falsify it

The selected executable changes; an earlier entry call appears; the call, delay slot, return guard, or loop back-edge changes; or independent control-flow analysis shows 0x80028BA0 is not the game main loop.

## Re-confirmed 2026-08-21

The startup verifier passed 5/5 fixtures and matched 8/8 structural facts on the real hashed executable;
the downstream two-engine harness reached its recorded direct-main target.

## Re-confirmed 2026-08-21

Post-landing real USA verify_startup passed 8/8; the two-engine boundary selftest passed 3/3 and reached direct-main 0x80028BA0.
