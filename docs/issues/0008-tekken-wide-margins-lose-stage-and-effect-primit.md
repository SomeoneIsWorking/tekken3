---
id: 8
title: Tekken wide margins lose stage and effect primitives at retail culling bounds
status: investigating
symptom: Tekken 3 widescreen shows missing stage tiles or effects in the added horizontal margins
tags: rendering,widescreen,culling,tekken3
state_items: S006,S007
created: 2026-08-22
updated: 2026-08-27
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

`Tekken3Widescreen` now latches one shared projection plan at measured dimension owner
`FUN_80080A40`. Wide-only readable ports of `FUN_8006CC28` and `FUN_8006E44C` consume that plan's
guest draw width instead of their twelve retail x=368 comparisons; 4:3 routes to the authenticated
original guest bodies. The hermetic contract proves stage/effect primitives at x=400/450 survive the
492-pixel 16:9 draw span while projection widens 384->512 with height 480 unchanged.

This is implemented, not visually verified. A real 4:3/wide product A/B must still verify packet
fidelity and determine whether the separate authored 600/780 stage-tile visibility wedge needs a
derived wide-frustum adjustment.
