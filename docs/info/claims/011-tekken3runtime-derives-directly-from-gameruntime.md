---
id: C011
kind: claim
status: holds
created: 2026-08-22
tags: runtime,inheritance,architecture,guest-program-image
depends: game/core/tekken3_runtime.h, game/core/tekken3_runtime.cpp#Tekken3Runtime::guestProgramImage, tests/runtime_seam.cpp#main, tests/runtime_contract.cpp#main, tests/recomp_boundary.cpp#main
reconfirmed: 2026-08-22
verified_at: 2026-08-22 18:11:46
---

## Claim

Tekken3Runtime derives directly from GameRuntime and owns its measured resident text only through immutable GuestProgramImage; Tekken exposes no legacy config, hooks, or context view.

## Evidence

Clang-built runtime_seam proved 2/2 resident-range fields reach Core::guestProgramImage, 3/3 cfg/hooks/context views are null, the interpreter-only runtime invents no image, and 1/1 invalid range is refused. runtime_contract statically proves direct GameRuntime inheritance, rejects LegacyGameRuntimeAdapter inheritance, and checks 6/6 forbidden adapter/config/hooks tokens absent from both runtime sources. CTest passed 5/5 and Clang policy passed 7/7 format/size plus 6/6 tidy. The real boundary stayed 35/35 CPU fields through 0x80085D98 and 3/3 IRQ observations through 0x80085DA4 with SELFTEST 9/9.

## What would falsify it

Falsified if Tekken3Runtime derives from or names the legacy adapter, GameConfig, or GameHooks; a Core created from it exposes non-null cfg/hooks/context; residentText differs from the executable-provided range; or the real boundary comparison regresses.

## Re-confirmed 2026-08-22

2026-08-22: direct GameRuntime contract 6/6, runtime seam 2/2 resident fields and 3/3 null legacy views, Clang format 7/7, structure 7/7, clang-tidy 6/6, CTest 5/5, and real boundary SELFTEST 9/9 passed on the combined tree.

## Re-confirmed 2026-08-22

2026-08-22 final gate: default Clang build verify passed against recorded psxport ad5cf802; runtime contract 6/6, seam resident 2/2 and null legacy views 3/3, cpp policy format 7/7 structure 7/7 tidy 6/6, real boundary SELFTEST 9/9, CTest 5/5.
