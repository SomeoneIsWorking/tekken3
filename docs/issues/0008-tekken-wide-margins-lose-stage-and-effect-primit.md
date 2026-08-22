---
id: 8
title: Tekken wide margins lose stage and effect primitives at retail culling bounds
status: investigating
symptom: Tekken 3 widescreen shows missing stage tiles or effects in the added horizontal margins
tags: rendering,widescreen,culling,tekken3
created: 2026-08-22
updated: 2026-08-22
---

## Root cause

`FUN_8006D014` feeds authored 600/780 horizontal visibility wedges to `FUN_8006D95C`'s
6x6 stage-tile selector. That is a second horizontal-culling owner which must be checked
against the resolved wide frustum, but static evidence alone does not prove the correct
wide-angle policy. `FUN_8006CC28` unambiguously drops stage triangle, quad, and sprite
primitives wholly past x=368 at eleven signed `-368` comparisons, and `FUN_8006E44C`
applies the twelfth rendering-path comparison to effects. Wider projection alone cannot
recover work these title functions discard at the retail edge.

## What was tried / dead ends

The separate `-368` use in `FUN_80054B48` was inspected and ruled out: it is a
player-select text-slide distance, not a rendering clip bound, and belongs to retail 2D
layout.

`tools/verify_projection.py` now proves the complete eleven-plus-one rendering census and
the distinct 2D use against the real executable. This resolves the ownership uncertainty,
not the missing wide implementation or its pixel A/B.

## Resolution

Pending. Title-owned overrides must consume one shared resolved guest-wide draw/clip
extent. A real A/B must determine whether the tile wedge needs widening; if so, the
replacement derives from the authored angle and resolved projection. The 4:3 generated
bodies remain the differential control.
