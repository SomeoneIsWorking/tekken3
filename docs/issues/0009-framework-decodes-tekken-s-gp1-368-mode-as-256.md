---
id: 9
title: Framework decodes Tekken's GP1 368 mode as 256
status: investigating
symptom: Tekken 3 preset 0 presents or widens from 256 pixels instead of its measured 368-pixel active display
tags: rendering,display,gp1,framework,tekken3
created: 2026-08-22
updated: 2026-08-22
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

Pending a generic GP1 display-mode decoder fix with a 368 positive case and a
neighboring-mode opposite-answer test in psxport.
