---
id: C018
kind: claim
status: holds
created: 2026-09-28
tags: re-first,cd,loader,mode,card,input
depends: tools/verify_title_flow.py, titles/tekken3/executable.json#title_flow
reconfirmed: 2026-09-28
verified_at: 2026-09-28
---

## Claim

In the authenticated Tekken 3 `SLUS_004.02` image, the `NAMCO PRESENTS` card is **mode 2, phase 8**,
and phase 8 is a wait on the byte at `0x800A069F` that redraws the card every frame it holds. The
guest leaves the card by copying the return-mode byte at `0x80097F38` into the mode halfword
`0x800AE204` (`0x8004FEF0`), and the 294 instructions between that block and the card's own draw read
no controller port. **The card is not dismissed by input, and a pad route to it is compensating for
nothing.**

## Evidence

`tools/verify_title_flow.py` derives the whole chain from the image and records it in
`titles/tekken3/executable.json` under `title_flow`, which the tool diffs on every run. The record
diff is clean; the selftest is 24/24, of which **eight are one-word negative cases** and **two are
controls** (an injected controller-port read on the exit path must be found, and a second `0x190`
timer-argument site must be counted).

| fact | where | value |
|---|---|---|
| mode dispatch | `0x80028C64` | `lh` of `0x800AE204`, `sltiu 0x14`, table `0x80010000`, 20 entries |
| the card's mode | table entry 2 | `0x8004FA60` |
| phase dispatch | `0x8004FAE0` | `lh` of `0x800AE224`, `sltiu 0x0D`, table `0x8002242C`, 13 entries |
| the wait | `0x8004FDAC` | `jal 0x80052A70` -> `0x8006C23C` -> `lbu 7(0x800A0698)` = `0x800A069F` |
| the hold | `0x8004FDF0` | `bne $v0, $zero` into the shared tail; the phase is left unchanged |
| the card | `0x8004F804` | `"%c%f%H%VNAMCO %cPRESENTS."` at x=117, y=240, scale 6 |
| the card's draw set | `0x8004F750` | drawn for `$a0` in {0, 1, 2}; phase 8 passes 1 |
| the exit | `0x8004FEF0` | `0x800AE204 = *(0x80097F38)`; **0 controller-port reads over 294 instructions** |
| who set the return mode | `0x800B076C` -> `0x8004FA28` | mode 0's last phase calls the switch with `3` |
| who arms the wait | `0x8006C1A4` | `sb $v0(=1), 7(0x800A0698)`, immediately before `addiu $a0, $zero, 0xA0` |

The live half is the product's own retained probe, `scratch/probe_logs/loader_b.probe.txt`, twelve
samples from field 98 to field 6865: `0x800AE204 = 2`, `0x800AE224 = 8`, `0x800A069F = 1`,
`0x800A3E40 = 4`, `0x8009B8D0 = 0`, `0x8009B8E8 = 0`, `0x8009B774` cycling and `0x8009B778` climbing.
**The product is measured to be sitting in the block the claim names.**

x=117 / y=240 is the same pair issue 0015 measured as the card band's origin, which is an
independent confirmation from the rendered picture rather than from the same tool.

## What would falsify it

- `tools/verify_title_flow.py` printing a `RECORD DIFF` disagreement against
  `titles/tekken3/executable.json` `title_flow`, or any of its 24 selftest cases failing.
- An independent disassembly of `0x80028C64`, `0x8004FD9C`, `0x8006C244` or `0x8004FEF0` disagreeing
  with the bytes quoted above.
- A controller-port dereference existing among the 294 instructions between `0x8004FED0` and
  `0x8004FEF8` that the scan misses — which its own control is there to make visible.
- A live run reading `0x800AE224 != 8` or `0x800A069F != 1` across the card, which would place the
  product somewhere other than the block this claim names.
- Executable identity differing from SHA-256
  `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c`.

## Limits of this claim, stated here rather than in a reader's inference

- **It does not name the menu, its accepted inputs, or the branch toward a fight.** 11 of the 20 mode
  targets are at or above `0x800C0000`, a 115,712-word window with **0** `jr $ra` and **0** `addiu
  $sp, $sp, -N` against 1,499 and 1,663 in the code window. Those handlers are written at run time by
  the mode-0 loader from disc-compressed resources, so their contents are not in the disc executable
  and this claim does not infer them.
- **It does not claim the product will reach mode 3 after the wait clears.** It claims only that
  phase 12 installs the return-mode byte, and that byte is 3.
- **No product run was made for this claim**; the machine's single product slot was held until
  2026-09-29T12:00. The live half is quoted from a retained probe another agent ran.
- It **corrects** issue 0011's mechanism, not its conclusion: the SIO0 spin at `0x800934D8` is not
  where the product is, because the live word `0x800AE228 = 0x190` is written by exactly one call site
  in the image (`0x800934EC`, past that spin) and is read in every sample. Issue 0011's proposed
  `FUN_80093478` override still stands, and now needs to replace the function's SECOND unbounded loop
  as well.
