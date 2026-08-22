---
id: C009
kind: claim
status: holds
created: 2026-08-22
tags: enhancement,widescreen,scope,architecture
depends: game/core/tekken3_runtime.cpp#Tekken3Runtime::bootInit
reconfirmed: 2026-08-22
verified_at: 2026-08-22 18:05:01
---

## Claim

Tekken 3 (`SLUS_004.02`) already runs at 60 fps, so its rendering-enhancement target is widescreen only. The title
must not gain an fps60 mode, interpolation/lerp, or temporal state that exists solely to support
interpolation. Native camera/projection or graphics ownership is added only when RE of the true wide
path proves it necessary, not as an interpolation prerequisite.

## Evidence

The user set this title policy explicitly on 2026-08-22. A repository-wide source and documentation
audit found no operational fps60 or interpolation path: `Tekken3Runtime` owns only the measured
resident-program image and deliberately stops at the partial T3-04 boot frontier. The only
contrary material was the unimplemented `T3-07` planning step and matching prose, which this change
removed. The current milestone advances boot fidelity only and introduces no rendering-time state.

## What would falsify it

The user changes Tekken 3's target scope, the original executable is shown not to run at 60 fps, or
shipping Tekken code introduces an fps60/interpolation mode or temporal state used only by lerp.

## Re-confirmed 2026-08-22 15:26:34

Repository audit found 0 operational Tekken fps60/interpolation paths; runtime seam passed, and the
production generated-boundary harness still agreed 35/35 at all four measured edges through
post-store 0x80085D98 with SELFTEST 7/7. Policy-only documentation changes do not alter runtime
behavior or T3-04.

## Re-confirmed 2026-08-22

Repository audit remains free of Tekken fps60/interpolation paths. Clang policy passed 6/6 format/size and 5/5 clang-tidy TUs; CTest passed 4/4. The boundary suite advanced only boot fidelity, agreeing 35/35 at post-store 0x80085D98 and 3/3 device observations at 0x80085DA4 with SELFTEST 9/9; no interpolation state was introduced.

## Re-confirmed 2026-08-22

After direct GameRuntime migration, source audit and the 6-token contract found no Tekken fps60/interpolation/lerp state and no legacy adapter/config/hooks path. CTest passed 5/5, Clang policy 7/7 format/size and 6/6 tidy; the real boundary remained 35/35 CPU and 3/3 IRQ with SELFTEST 9/9.
