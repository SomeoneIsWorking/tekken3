---
id: 12
title: Shared player menu can select Tekken's excluded native renderer
status: investigating
symptom: After Tekken validates GTE at startup, the shared F1 renderer row can still cycle GTE to Native
tags: rendering,configuration,framework,widescreen,scope
state_items: S005
created: 2026-08-26
updated: 2026-08-27
---

## Root cause

The original implementation split policy ownership: Tekken 3 rejected `RenderPath::Native` in a
title-local startup validator, while shared psxport `RenderPathControl::cycle()` independently used
the global Native/GTE cycle. The title had no typed way to declare GTE as its only player-selectable
path while retaining PSX as a diagnostic path.

The proper fix is a shared typed `GameRuntime` render-path capability used by both startup resolution and live menu cycling. A title-local UI special case or resetting the path after selection would duplicate policy and is rejected.

## What was tried / dead ends

Repository audit found no title-owned native renderer, fps60 mode, interpolation/lerp, or
interpolation-only temporal state. The retired `Tekken3Runtime::configureRenderPath()` accepted
GTE/PSX and refused Native at startup but could not govern the later shared UI cycle.

## Resolution

The consumer now returns `RenderCapabilities::widescreenOnly()` and removes the former
title-local render-path parser. Its seam test requires default GTE, supported GTE/PSX, unsupported
Native, and player-selectable GTE only.

The exact Clang build against recorded psxport `99a42aa3` passes CTest 11/11, full `verify`, and the
13/13 render-capability seam. A bounded product run rejected a persisted `native` request as
unsupported and resolved it to the declared GTE path, proving startup resolution consumes the title
contract.

Pending: actual menu-row inspection remains unverified. The same bounded run dispatched the retail
entry and reached IRQ/CD initialization but produced no first present or visible X11 window within
20 seconds, so there was no Display pane to capture. The exact launched PID was terminated with the
scoped safe-kill helper and confirmed gone. The absence of the Renderer row remains static-only until
the product reaches a window.
