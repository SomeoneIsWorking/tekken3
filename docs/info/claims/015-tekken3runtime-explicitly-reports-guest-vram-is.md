---
id: C015
kind: claim
status: holds
created: 2026-08-24
tags: runtime,widescreen,t3-04
depends: game/core/tekken3_runtime.cpp#guestVramIsPicture, tests/runtime_seam.cpp#main
---

## Claim

Tekken3Runtime explicitly reports guest VRAM is not picture content at its boundary-only seam; this is an ownership refusal, not evidence of a rendered frame.

## Evidence

On psxport bc8c8897, the Clang-built production game_guest_vram_is_picture query returned false in runtime_seam; the authoritative verify target, CTest 6/6, cpp-policy format 7/7 and clang-tidy 6/6, and the bounded CPU replay passed. The test and replay explicitly disclaim frames/gameplay.

## What would falsify it

Falsified if Tekken3Runtime returns true before a verified guest-VRAM picture owner exists, the production query no longer returns false, or a renderer path bypasses the runtime policy.
