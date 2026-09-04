---
id: C011
kind: claim
status: holds
created: 2026-08-22
tags: runtime,inheritance,architecture,guest-program-image
depends: game/core/tekken3_runtime.h, game/core/tekken3_runtime.cpp#Tekken3Runtime::guestProgramImage, tests/runtime_seam.cpp#main, tests/runtime_contract.cpp#main
reconfirmed: 2026-08-24
verified_at: 2026-08-24 20:05:28
---

## Claim

Tekken3Runtime derives directly from GameRuntime and owns its measured resident text only through immutable GuestProgramImage; Tekken exposes no legacy config, hooks, or context view.

## Evidence

Clang-built runtime_seam proved 2/2 resident-range fields reach Core::guestProgramImage, 3/3 cfg/hooks/context views are null, an unbound runtime invents no image, and 1/1 invalid range is refused. runtime_contract proves direct GameRuntime inheritance, rejects LegacyGameRuntimeAdapter inheritance, and checks 6/6 forbidden adapter/config/hooks tokens absent from both runtime sources. CTest passed 5/5 and Clang policy passed 7/7 format/size plus 6/6 tidy. Retained boundary evidence records 35/35 CPU fields through 0x80085D98 and 3/3 IRQ observations through 0x80085DA4.

## What would falsify it

Falsified if Tekken3Runtime derives from or names the legacy adapter, GameConfig, or GameHooks; a Core created from it exposes non-null cfg/hooks/context; residentText differs from the executable-provided range; or the real boundary comparison regresses.

## Re-confirmed 2026-08-22

2026-08-22: direct GameRuntime contract 6/6, runtime seam 2/2 resident fields and 3/3 null legacy views, Clang format 7/7, structure 7/7, clang-tidy 6/6, CTest 5/5, and real boundary SELFTEST 9/9 passed on the combined tree.

## Re-confirmed 2026-08-22

2026-08-22 final gate: default Clang build verify passed against recorded psxport ad5cf802; runtime contract 6/6, seam resident 2/2 and null legacy views 3/3, cpp policy format 7/7 structure 7/7 tidy 6/6, real boundary SELFTEST 9/9, CTest 5/5.

## Re-confirmed 2026-08-22

2026-08-22 full Clang verify passed direct GameRuntime contract 6/6, resident seam 2/2, null legacy views 3/3, Clang format 7/7, structure 7/7, tidy 6/6, and CTest 6/6.

## Re-confirmed 2026-08-24

On pinned psxport bc8c8897, authoritative verify and CTest 6/6 passed: direct GameRuntime contract rejects all 6 legacy adapter/config/hooks tokens; runtime_seam proved 2/2 resident fields, 3/3 null legacy views, invalid-range refusal, and the production guest-VRAM policy query returned false; Clang format 7/7, size 7/7, tidy 6/6.

## Re-confirmed 2026-08-24

Post-landing runtime_seam and runtime_contract passed direct GameRuntime ownership, 2/2 program facts, 3/3 null legacy views, invalid-range refusal, and explicit false picture policy
