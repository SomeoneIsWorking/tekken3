---
id: 13
title: Shared F1 menu exposes excluded fps60 interpolation to Tekken
status: investigating
symptom: Tekken's F1 overlay presents and accepts a 60fps Interpolation toggle although the title target explicitly excludes fps60 and lerp
tags: rendering,interpolation,configuration,framework,scope
state_items: S005
created: 2026-08-26
updated: 2026-08-27
---

## Root cause

The original shared menu always declared the `fps60` row, bound it to `Mods::fps60`, and accepted
`cv_fps60`; `GameRuntime` had no typed capability declaring that Tekken is a non-temporal title.
Tekken received the neutral current-frame presenter, so the toggle changed no title-owned
interpolation behavior but remained a misleading accepted option.

The proper fix is a shared typed title capability consumed by configuration resolution, Mods, and menu row availability. A Tekken-only environment reset, ignored toggle, or local copy of the shared menu is rejected.

## What was tried / dead ends

Repository audit confirms Tekken owns no fps60 producer, interpolation/lerp, or temporal history. That absence does not remove the shared player-facing toggle.

## Resolution

The consumer now declares `temporalInterpolation=false` through the shared
`widescreenOnly()` profile. Shared configuration and menu-row owners consult that same capability,
while legacy interpolation consumers retain their explicit support.

The exact Clang build against recorded psxport `99a42aa3` passes CTest 11/11, full `verify`, and the
13/13 capability seam, including `temporalInterpolation=false` and a one-entry player render-path
cycle.

Pending: issue 0012's bounded real-window inspection produced no X11 window or first present before
the product reached its current IRQ/CD-init frontier. Therefore the absence of the 60fps
Interpolation row remains static-only and is not visually verified in the actual menu. The exact
product PID was terminated and confirmed gone.
