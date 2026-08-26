---
id: C009
kind: claim
status: holds
created: 2026-08-22
tags: enhancement,widescreen,scope,architecture
depends: game/core/tekken3_runtime.cpp#Tekken3Runtime::renderCapabilities
reconfirmed: 2026-08-27
verified_at: 2026-08-27 00:18:00
---

## Claim

Tekken 3 (`SLUS_004.02`) already runs at 60 fps, so its rendering-enhancement target is widescreen only. The title
must not gain an fps60 mode, interpolation/lerp, temporal state that exists solely to support
interpolation, or a title-owned native renderer. The wide path binds RE-proven guest
camera/projection/culling owners through the shared non-temporal guest-widescreen contract.

## Evidence

The user set this title policy explicitly on 2026-08-22. A repository-wide source and documentation
audit found no operational fps60 or interpolation path: `Tekken3Runtime` owns only the measured
resident-program image and deliberately stops at the partial T3-04 boot frontier. The only
contrary material was the unimplemented `T3-07` planning step and matching prose, which this change
removed. The current milestone advances boot fidelity only and introduces no rendering-time state.

## What would falsify it

The user changes Tekken 3's target scope, the original executable is shown not to run at 60 fps, or
shipping Tekken code introduces an fps60/interpolation mode, lerp-only temporal state, or a
title-owned native renderer.

## Re-confirmed 2026-08-22 15:26:34

Repository audit found 0 operational Tekken fps60/interpolation paths; runtime seam passed, and the
production generated-boundary harness still agreed 35/35 at all four measured edges through
post-store 0x80085D98 with SELFTEST 7/7. Policy-only documentation changes do not alter runtime
behavior or T3-04.

## Re-confirmed 2026-08-22

Repository audit remains free of Tekken fps60/interpolation paths. Clang policy passed 6/6 format/size and 5/5 clang-tidy TUs; CTest passed 4/4. The boundary suite advanced only boot fidelity, agreeing 35/35 at post-store 0x80085D98 and 3/3 device observations at 0x80085DA4 with SELFTEST 9/9; no interpolation state was introduced.

## Re-confirmed 2026-08-22

After direct GameRuntime migration, source audit and the 6-token contract found no Tekken fps60/interpolation/lerp state and no legacy adapter/config/hooks path. CTest passed 5/5, Clang policy 7/7 format/size and 6/6 tidy; the real boundary remained 35/35 CPU and 3/3 IRQ with SELFTEST 9/9.

## Re-confirmed 2026-08-22

2026-08-22 runtime contract and source audit retain zero FPS60, interpolation, lerp, temporal, or native-depth dependencies; Tekken target remains widescreen-only and CTest 6/6 passed.

## Re-confirmed 2026-08-24

On pinned psxport bc8c8897, repository audit still found no operational Tekken fps60/interpolation/lerp state. The direct boundary runtime added only explicit guest-VRAM picture ownership=false; authoritative verify, CTest 6/6, and Clang policy passed. No rendered frame is claimed.

## Re-confirmed 2026-08-24

Post-landing verify and runtime seam retain direct widescreen-only boundary ownership; no temporal/interpolation/lerp path added

## Re-confirmed 2026-08-26

User scope remains widescreen-only with no native renderer or interpolation/lerp; touched runtime and repository policy audit retain that boundary, and focused Clang checks pass.

## Re-confirmed 2026-08-27

Against recorded psxport `99a42aa3`, CTest 11/11 and full Clang `verify` pass; the runtime seam proves
13/13 capability facts. A bounded product run rejected a persisted Native request and resolved it to
GTE. The product did not reach a first present or X11 window, so actual Native/60fps menu-row absence
remains static-only rather than visually verified.
