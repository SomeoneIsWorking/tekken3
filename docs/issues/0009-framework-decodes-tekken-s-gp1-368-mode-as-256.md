---
id: 9
title: Framework decodes Tekken's GP1 368 mode as 256
status: resolved
symptom: Tekken 3 preset 0 presents or widens from 256 pixels instead of its measured 368-pixel active display
tags: rendering,display,gp1,framework,tekken3
state_items: S006,S007
created: 2026-08-22
updated: 2026-08-27
---

## Root cause

Tekken's preset-0 `PutDispEnv` emits GP1(08) horizontal-resolution bit 6 for the
368-pixel mode. The framework's `gpu_native.cpp` switch documents bit 6 but derives
`s_disp_w` only from bits 0-1, so the `0x40` mode falls through to 256. The same wrong
state would feed presentation and guest-widescreen extent resolution.

## What was tried / dead ends

Compensating in Tekken's projection policy is rejected. That would make one consumer
disagree with the framework's GPU/presenter state and leave every other 368-mode title
broken.

## Resolution

Framework commit `2e840231` gives the split GP1(08) field one pure decoder:
`HRES2` bit 6 selects 368 independently of the low two bits, otherwise the low bits select
256/320/512/640. `test_gpu_display_mode` covers all four bit-6 combinations and all four neighboring
modes. Tekken consumes that framework state through the shared guest-projection plan; there is no
title-side display-width exception.
