---
id: C001
kind: claim
status: holds
created: 2026-08-20
tags: target,executable,t3-01
depends: titles/tekken3/executable.json
reconfirmed: 2026-08-21
verified_at: 2026-08-21 12:06:07
---

## Claim

The selected Tekken 3 USA disc names TEKKEN3/SLUS_004.02 as its boot executable. The complete PS-X EXE has SHA-256 fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c, entry 0x80079C70, load 0x80010000, and text extent ending at 0x80131000. This is disc/executable identity evidence, not a claim that the PC port boots.

## Evidence

SYSTEM.CNF and discdump identify the nested executable at LBA 25 with 1,185,792 bytes; crt0_extract reports the header/load map; Ghidra plus a post-decompile disassembly spot-check independently confirm the entry startup body and its jal 0x80028BA0.

## What would falsify it

A fresh extraction from the selected USA disc changes SYSTEM.CNF, size, SHA-256, pc0, t_addr, or t_size, or proves this image is not the intended region.

## Re-confirmed 2026-08-21

Real-disc provisioning matched all 8/8 tracked identity/header facts, including the complete executable
SHA-256 and entry/text map; fresh Ghidra analysis of that image reproduced the entry and game-main target.

## Re-confirmed 2026-08-21

Post-landing provisioning and startup verification passed the selected USA executable identity and manifest, including the newly recorded first game_main edge.

## Re-confirmed 2026-08-21

Post-landing verify reprovisioned SLUS_004.02 with all 8/8 identity facts and the provisioning selftest passed 12/12 against psxport ce2c83adb0fce89c44eb764f2abf3e4f999d32a8.
