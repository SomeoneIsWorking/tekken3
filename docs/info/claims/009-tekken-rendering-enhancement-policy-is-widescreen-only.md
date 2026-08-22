---
id: C009
kind: claim
status: holds
created: 2026-08-22
tags: enhancement,widescreen,scope,architecture
depends: game/core/tekken3_runtime.cpp#Tekken3Runtime::bootInit
reconfirmed: 2026-08-22 15:26:34
verified_at: 2026-08-22 15:26:34
---

## Claim

Tekken 3 (`SLUS_004.02`) already runs at 60 fps, so its rendering-enhancement target is widescreen only. The title
must not gain an fps60 mode, interpolation/lerp, or temporal state that exists solely to support
interpolation. Native camera/projection or graphics ownership is added only when RE of the true wide
path proves it necessary, not as an interpolation prerequisite.

## Evidence

The user set this title policy explicitly on 2026-08-22. A repository-wide source and documentation
audit found no operational fps60 or interpolation path: `Tekken3Runtime` owns only the measured
resident-program compatibility range and deliberately stops at the pre-I_MASK frontier. The only
contrary material was the unimplemented `T3-07` planning step and matching prose, which this change
removes without changing executable behavior or advancing T3-04.

## What would falsify it

The user changes Tekken 3's target scope, the original executable is shown not to run at 60 fps, or
shipping Tekken code introduces an fps60/interpolation mode or temporal state used only by lerp.

## Re-confirmed 2026-08-22 15:26:34

Repository audit found 0 operational Tekken fps60/interpolation paths; runtime seam passed, and the
production generated-boundary harness still agreed 35/35 at all four measured edges through
pre-I_MASK 0x80085D98 with SELFTEST 7/7. Policy-only documentation changes do not alter runtime
behavior or T3-04.
