---
id: C016
kind: claim
status: holds
created: 2026-08-26
tags: cd,interrupt,recompiler,t3-04
depends: tools/cd_response_boundary.py#check, tests/cd_response_boundary.cpp#main
reconfirmed: 2026-08-26
verified_at: 2026-08-26 22:40:14
---

## Claim

On selected Tekken 3 SLUS_004.02, whole-product execution reaches and accepts the first directory-read group, but no queued command issues because libcd is not in ready state 1. A controlled INT3/Getstat response publishes 0x02 correctly in both the interpreter and shipping-recompiler C; the live IRQ-context state remains the discriminator.

## Evidence

2026-08-26: scratch/logs/tekken3-discriminate.log watchdog stack is FUN_80091858 -> FUN_80091E5C -> FUN_80091328 after FUN_80090F78; the same 90-second provisioned trace contains 49 Getstat, one Reset, one Demute, and no Pause/Setmode/Setloc/ReadN. Ghidra proves FUN_8008F08C enqueues four entries but kicks only at DAT_8009B750==1. The saved CD-register trace proves each Getstat reaches FUN_800833A8 as INT3 and reads response byte 0x02. The focused boundary emits 668 measured instructions and agrees 34/34 CPU, 38/38 unique RAM bytes, and 4/4 CDC fields between interpreter and recompiler; both publish status 0x02 and advance init step 0x16 to 0x17, while the 0x00 negative control retains status/motor-off and init step 0x16 in both engines. Issue #11 records the exact chain and corrects the earlier unobserved state-3 inference.

## What would falsify it

Falsified if a provisioned run observes DAT_8009B750==1 when FUN_80090F78 returns, any queued 0x09/0x0E/0x02/0x06 command before the wait, interpreter/recompiler disagreement at the controlled boundary, or a different selected executable identity.

## Re-confirmed 2026-08-26

Controlled INT3/Getstat boundary verifies 2/2 emitted artifacts, agrees 34/34 CPU, 38/38 unique RAM bytes, and 4/4 CDC fields, and produces the opposite answer for response 0x00.
