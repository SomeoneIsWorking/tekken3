---
id: 24
title: The 3D intro scenes and the ranking screen show line artifacts on the record path
status: open
symptom: stage and character scenes in the intro show alternating-line combing, and the GREATEST SURVIVORS ranking screen draws portrait strips and doubled text
state_items: S005,S008
tags: tekken3,rendering,record-path
created: 2026-10-09
updated: 2026-10-09
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
