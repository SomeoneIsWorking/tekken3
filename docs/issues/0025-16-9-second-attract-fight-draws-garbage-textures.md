---
id: 25
title: At 16:9 the second attract fight draws garbage textures where 4:3 shows a clean fight
status: open
symptom: after the first attract fight (field 12,000, clean at 16:9) the next scene at about field 12,500 and 13,000 is noise textures on the stage and both characters; 4:3 at the same fields is clean
state_items: S005,S007
tags: tekken3,widescreen,record-path,textures
created: 2026-10-10
updated: 2026-10-10
---

## Observed

`build/bin/tekken3_port` headless, `PSXPORT_DEBUG=recordcheck`, shots at 7,000 to 12,500 and 13,000 to 13,001.
At 16:9 the scenes through field 12,000 are clean (time record, first attract fight). At 12,500 and 13,000 the
fight scene is garbage textures. At 4:3 the attract timeline differs (another matchup at 12,500, Hwoarang) and is clean.
`recordcheck` is mismatched=0 on every present at both aspects, so the record path agrees with the device and the
garbage is in the device's VRAM: a guest or title state difference, not the presenter.

## Not established

Whether the 16:9 view width handed to the guest (`WidescreenProjection::publishDimensions`, 512) changes what the
guest uploads or clears in the texture area right of the 368-wide buffer, or the CD-loaded texture set differs because
the attract timeline diverged. Next: dump VRAM at field 12,500 for both aspects and find the first texture upload that
differs.
