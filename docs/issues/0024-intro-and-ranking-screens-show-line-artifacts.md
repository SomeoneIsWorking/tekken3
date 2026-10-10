---
id: 24
title: The 3D intro scenes and the ranking screen show line artifacts on the record path
status: resolved
symptom: stage and character scenes in the intro show alternating-line combing, and the GREATEST SURVIVORS ranking screen draws portrait strips and doubled text
state_items: S005,S008
tags: tekken3,rendering,record-path
created: 2026-10-09
updated: 2026-10-10
---

## Observed

At 4:3 (`aspect=0`), `recordcheck` reports mismatched=0 on every present, so the record path matches the
device; the shots still show, in the intro scene at about field 3,200 and 6,000, horizontal line combing on
the character and the ground, and on the ranking screen (mode 17, about field 13,000) portrait strips one
column wide and doubled rank text. The title menu, character select, stage intro and fight shots are clean.

## Not established

Whether the guest draws these interlaced on purpose (a 368x480 display with alternating field offsets) or the
product loses a field's GP0 state. The owner has not been traced; reproduce from a `shot` at those fields and
read the display-area registers (`disp`) first.

## Cause

The guest draws these screens at 368x480 interlaced with E1 bit 10 clear, so the device rasterizes one field per
frame: the rows of the displayed field are skipped (`GpuDevice::probe`, `skipRowParity`) and the VRAM holds this
frame's rows beside the previous frame's. `recordcheck` shows the undrawn parity alternating 0, 1 on every field of the
3D scenes. A display shows one field at a time; the presenter showed the woven 480 rows, two moments 1/60 s apart
(`RecordRasterizer::present` before `selectField`), which combs every moving edge. The ranking screen's background is
the same 3D stage scrolling, and its strips are the same weave. Not a Tekken defect and not a lost GP0 state.

## Fix

psxport `RecordRasterizer::selectField` presents the field the shown record drew (`FrameRecord::undrawnRowParity`), each
undrawn row repeating the drawn row of its pair; the VRAM image stays woven and `recordcheck` compares it
(`RecordRasterizer::woven`). Unit test `an_interlaced_one_field_frame_presents_that_field` in psxport
`tests/test_record_raster.cpp` fails before and passes after. Shots at fields 3,200, 6,000 and 13,001 (4:3) are clean;
`recordcheck` mismatched=0 on 13,010 of 13,010 presents.

## Still true

A static scene drawn one field per frame loses the second field's vertical detail. Weaving only where the two
fields agree is the way to keep it, and is not done.
