---
id: 23
title: On the record path Tekken 3's 16:9 margins stay black — its draw area is letterboxed and its widening is shaped for the old GTE canvas
status: resolved
symptom: At 16:9 on RenderPath::Record the 62-column margins are black; the only reachable frame is the NAMCO PRESENTS card, so no 3D exists to fill them
state_items: S005,S007
tags: widescreen,record-path,render,canvas,draw-area
created: 2026-10-07
updated: 2026-10-10
---

## Reproduction

`build/bin/tekken3_port` headless, `config/aspect_16x9.ini`, sink 512x720, present shots at fields
30..1200 (`scratch/record/rec_16x9/`). The card is pixel-identical to the GTE-path baseline
(`scratch/record/base_16x9/`) from field 60 on: 133x16 at the centre, both margins black. Field 30
(fade-in) differs on 374 pixels by one 5-bit step; record matches the device there
(`recordcheck` mismatched=0), the GTE rasterizer did not.

## Cause, measured at the card

RAM at field 1200 (`PSXPORT_RAMDUMP`, both aspects):

| word | value | meaning |
|---|---|---|
| `0x800ADDA0` x,y,w,h | 0, 20, 368, 448 | DrawEnv clip = preset 0's active rect (`0x800B0CC8` via `FUN_80080F38`, `FUN_80080EB8`) |
| display | 368x480 at 0,0 | the displayed buffer |
| `0x800ADEF4` | 384 at 4:3, 512 at 16:9 | view width handed to `FUN_80080A40` by `WidescreenProjection::publishDimensions` |
| `0x800ADFA0` | 6826 at 4:3, 5120 at 16:9 | `(height << 14) / width / 3`, derived from that width |
| `0x800A918C` centre, `0x800ADE7C` OFX | 0, 0 | `FUN_80081068(0,0)` cleared the centre after boot; boot OFX comes from the preset (192) directly |

1. Fixed in psxport 9a9f43b4: a draw area spanning the buffer's columns with rows inset inside it
   now reaches the margins, so Tekken's rows 20..467 qualify.
2. Tekken's widening was built for the GTE path, which presented a left-anchored 492-wide guest
   frame. The record canvas is the buffer plus 62 columns each side, so a widened guest picture has
   to land at buffer x -62..429. The two clippers (`clipStagePrimitives`, `clipEffectPrimitive`)
   still cull `x < 0` on the left and `x >= guestDrawWidth` on the right. psxport's Record plan keeps
   `guestDrawWidth` at the retail width, so on the shipping path they cull at 368 as retail does;
   `tekken3_widescreen_contract` and `tekken3_widescreen_stage_wedge_contract` still build a
   `RenderPath::Gte` plan, the shape this widening was written for.
3. If gameplay derives its centre through `FUN_80081148` (`width / 2`), the 512 view moves the 3D
   centre from 192 to 256 inside the buffer, 64 columns right of the 4:3 picture. Gameplay's centre
   owner lives in the runtime-loaded mode window (issue 0022) and is unmeasured.

## Proper fix

- psxport: decide whether a draw area whose x range is the buffer and whose rows lie inside it (a
  letterboxed 3D view) is a display draw. That is a framework rule for every title, not a Tekken
  branch.
- Tekken: on Record keep the retail centre, widen what it culls to the canvas extent
  `[-M, width + M)` (both clippers and the stage wedge from the one plan), and keep 4:3 on the
  original guest bodies.
- Both need a fight frame to prove (issues 0020, 0022); until then the 16:9 picture is the 4:3
  picture centred with black margins, never stretched.

## Update 2026-10-10

Not black any more. At 16:9 (sink 1280x720 and 640x360, `config/aspect_16x9.ini`) the intro scenes at fields 3,200 and
6,000 and an attract fight at 12,000 draw stage geometry into both margins, projected wider, not stretched, and
`recordcheck` reports mismatched=0 on 13,010 of 13,010 presents. The black margins' cause 1 is gone
(psxport's letterboxed-draw rule and its per-buffer canvases); which of the widened owners produces the margin
geometry on the record path (cause 2) is not re-measured. Still open from this issue: gameplay's 3D centre owner (issue 0022) and what a fight frame at the widened
edges needs; a guest 2D element drawn left of the buffer now shows in the left margin (a portrait at field 12,000).
The ranking and second attract fight at 16:9 draw garbage textures: issue 0025.
