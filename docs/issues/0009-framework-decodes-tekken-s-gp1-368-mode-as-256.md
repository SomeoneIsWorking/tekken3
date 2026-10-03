---
id: 9
title: The framework decoded Tekken's GP1 368 mode as 256
status: resolved
symptom: Tekken 3 preset 0 presents or widens from 256 pixels instead of its measured 368-pixel active display
tags: rendering,display,gp1,framework,binary-fact
created: 2026-08-22
updated: 2026-08-27
---

**Binary fact:** Tekken's preset-0 `PutDispEnv` emits GP1(08) horizontal-resolution bit 6 for the
368-pixel mode. The framework's `runtime/psx/gpu/gpu_native.cpp` documented bit 6 but derived `s_disp_w` only from
bits 0-1, so the `0x40` mode fell through to 256 and fed presentation and guest-widescreen extent
resolution with wrong state. Fixed generically at framework commit `2e840231`: `HRES2` bit 6 selects
368 independently of the low two bits.

**Dead end, do not repeat:** compensating in Tekken's own projection policy. It would make one
consumer disagree with the framework's GPU/presenter state and leave every other 368-mode title
broken. There is no title-side display-width exception.