---
id: 16
title: The NAMCO PRESENTS card is mode 2 phase 8's CD-read wait, and it is left by copying one byte — not by input
status: open
symptom: the product presents the card indefinitely; the natural reading is a menu waiting for a press
state_items: S003,S007,S008
tags: re-first,cd,loader,mode,card,input
created: 2026-09-28
updated: 2026-09-28
---

## Answer

**The card is not a screen the player dismisses. It is the CD-read wait of mode 2, phase 8, and the
product is *inside* it.** Leaving it copies one guest byte into the mode word and reads no input
anywhere on the path. So the missing thing is not a pad edge, and a route that pressed buttons would
be compensating for nothing.

Everything below is measured out of the authenticated `SLUS_004.02` by
`tools/verify_title_flow.py`, which refuses to report until it reproduces the file-offset formula
against two known instructions, and whose recorded facts are diffed against
`titles/tekken3/executable.json` (`title_flow`) on every run. The same run is the product's
regression: 24/24, including **eight one-word negative cases and two controls**.

## The two dispatch tables, read out of the image

The frame loop's mode dispatch, at `0x80028C64`:

```asm
80028C64  lh    $v1, -0x1DFC($v0)   ; $v0 = 0x800B0000  ->  the mode halfword at 0x800AE204
80028C6C  sltiu $v0, $v1, 0x14        ; unsigned, 20 entries
80028C74  lui   $v0, 0x8001
80028C78  addiu $v0, $v0, 0
80028C7C  sll   $v1, $v1, 2
80028C80  addu  $v1, $v1, $v0
80028C84  lw    $v0, ($v1)
80028C8C  jr    $v0
```

The table is at **`0x80010000`**, 20 entries, and entry *i* is the stub at
`0x80028C94 + i*0x10`, which is a `jal` into the handler. Mode 2 is `0x8004FA60`. The twenty targets
are recorded verbatim in `title_flow.mode_dispatch.targets`, so the whole table is diffable.

Mode 2's phase dispatch has the same shape at `0x8004FAE0` over the phase halfword at `0x800AE224`,
bounded by `sltiu 0x0D`, with its table at **`0x8002242C`** — immediately after the card's own
string.

## Mode 0 gets the card on screen, and cannot get past it

```asm
800B0714  lh    $v1, -0x1DDC($s0)   ; the phase halfword, $s0 = 0x800B0000
800B071C  beqz  $v1, 0x800B0738     ; phase 0: load the resources
800B0728  beq   $v1, $v0(=1), 0x800B0758  ; phase 1: switch away
800B0738  lui   $a0, 0x8013
800B073C  addiu $a0, $a0, -0x7984   ; $a0 = 0x8012867C, the staging base
800B0740  lui   $a1, 0x800C
800B0744  jal   0x8004CA40          ; the resource loader
800B0748  addiu $a1, $a1, -0x72A8   ; $a1 = 0x800B8D58, a 127-entry table (count read from the image)
800B0754  sh    $v0, -0x1DDC($s0)   ; phase = 1
800B0758  jal   0x8007C30C          ; display mask 1
800B0768  sb    $v0, -0x561($v1)    ; 0x800AFA9F = 0xFF
800B076C  jal   0x8004F8F8          ; the mode switch
800B0770  addiu $a0, $zero, 3       ; "3"
```

and the switch itself, at `0x8004FA28`:

```asm
8004FA28  sb    $s0, ($s1)          ; $s1 = 0x80097F38: the RETURN-mode byte = 3
8004FA30  lbu   $a0, -0x1DFC($v1)   ; the current mode
8004FA34  addiu $v0, $zero, 2
8004FA38  sh    $v0, -0x1DFC($v1)   ; 0x800AE204 = 2   <- the card
8004FA40  sh    $zero, -0x1DDC($v0) ; 0x800AE224 = 0
```

The **return-mode byte is what the card exits to**, and mode 0 wrote `3` into it.

## Phase 0 issues a CD read, and phases 5..11 are the fade around it

```asm
; phase 0, 0x8004FB7C
8004FB7C  sh    $v0(=5), -0x1DDC($a0)   ; phase = 5
8004FB80  lbu   $v1, ($s0)              ; the return-mode byte
8004FB88  beq   $v1, $v0(=6), 0x8004fef4   ; 6 -> straight to the tail, no CD read
8004FB90  bne   $v1, $v0(=3), 0x8004fba8   ; not 3 -> phase 1
8004FB98  lbu   $v0, 6($s0)             ; 0x80097F3E
8004FBA0  bne   $v0, $v1, 0x8004fef4    ; != 3 -> straight to the tail
8004FBAC  sh    $v0(=1), -0x1DDC($a0)   ; phase = 1
```

So the CD read happens only on `return-mode == 3 AND 0x80097F3E == 3`; otherwise the guest draws
nothing and sits in phase 5. The product **did** issue the read, so on this run that condition held.

Phases 5 and 1 both call the same pair:

```asm
8004FBD4  jal   0x80052B7C          ; the extent descriptor
8004FBE0  jal   0x800529CC          ; ISSUE THE READ
8004FBE4  move  $a1, $s1            ; $a1 = 5 or 7
```

`FUN_800529CC` calls `FUN_8006BF20` to queue the extent and then `FUN_8006C084`, whose `0x8006C1A4`
is the store that arms the wait:

```asm
8006C1A0  addiu $v0, $zero, 1
8006C1A4  sb    $v0, 7($s1)         ; $s1 = 0x800A0698  ->  0x800A069F = 1
8006C1B0  addiu $a0, $zero, 0xA0     ; CdGetID
```

## Phase 8 is the wait, and it is what is on screen

```asm
; phase 8, 0x8004FD9C
8004FDAC  jal   0x80052A70          ; "still loading?"
8004FDB4  bnez  $v0, 0x8004FDF0     ; nonzero -> straight to the tail, PHASE UNCHANGED
8004FDFC  addiu $v0, $zero, 9
8004FE00  sh    $v0, -0x1DDC($v1)   ; otherwise phase = 9
; the shared tail, 0x8004FEF4
8004FEF4  move  $a0, $s2            ; $s2 = 1 in phase 8
8004FEF8  jal   0x8004F750          ; draw
```

and the predicate, to the single byte:

```asm
80052A78  jal   0x8006C23C
80052A80  bnez  $v0, 0x80052ABC     ; nonzero -> "busy"
8006C240  addiu $v0, $v0, 0x698     ; $v0 = 0x800A0698
8006C244  lbu   $v0, 7($v0)         ; the byte at 0x800A069F
```

**So phase 8 holds itself exactly while `*(0x800A069F) != 0`, and it redraws the card on every
frame of the wait.** The card is the wait, not a screen in front of it.

The card itself, at `0x8004F804`:

```asm
8004F804  lui   $a0, 0x8002
8004F808  addiu $a0, $a0, 0x240C    ; "%c%f%H%VNAMCO %cPRESENTS."
8004F80C  addiu $a1, $zero, 2
8004F814  addiu $a3, $zero, 0x75    ; x = 117
8004F81C  sw    $v0, 0x10($sp)      ; y = 240
8004F824  jal   0x8004CE74          ; the text engine
8004F828  sw    $v0, 0x14($sp)      ; scale = 6
```

`x = 117`, `y = 240` is the (117, 240) origin issue 0015 measured for the 133x16 band, from the same
two numbers. The renderer draws the text for `$a0` in **{0, 1, 2}** — established by a constant-folded
CFG walk, because the dispatch tests `$a0` *and* `$a1` against `0x100`; phase 8 passes 1.

## Phase 12 leaves, and reads no input

```asm
; phase 12, 0x8004FED0
8004FED0  jal   0x8004C470          ; the auto-save-error check
8004FED8  bnez  $v0, 0x8004FF00     ; nonzero -> stay, showing the error
8004FEE4  sh    $zero, -0x1DDC($v0) ; 0x800AE224 = 0
8004FEE8  lbu   $v1, ($s0)          ; $s0 = 0x80097F38, the return-mode byte = 3
8004FEF0  sh    $v1, -0x1DFC($v0)   ; 0x800AE204 = 3   <- THE MODE SWITCH
```

`tools/verify_title_flow.py` scans the **294 instructions** between this block and the card call for
a dereference of a controller-port pointer and reports **none**. That scan is not vacuous: the
selftest injects the guest's own two-instruction form of that read (`lui $a1, 0x800A` /
`lw $a1, -0x469C($a1)`, exactly as `FUN_80093478` writes it) into this window and requires it to be
found.

**Therefore no pad edge takes this card anywhere.** The only gate is the sector callback that clears
`0x800A069F`.

## What the product is not sending: a CD completion

The shipping product's own live state, `scratch/probe_logs/loader_b.probe.txt`, twelve samples from
field 98 to field 6865:

| word | value | what it establishes |
|---|---|---|
| `0x800AE204` | `2` | mode 2, the whole run |
| `0x800AE224` | `8` | phase 8, the whole run — the wait above |
| `0x800A069F` | `0x01` | the wait byte, never cleared |
| `0x800A3E40` | `4` | the raw command queue, never drained |
| `0x8009B8D0` / `0x8009B8E8` | `0` / `0` | the sector callback was never registered |
| `0x8009B774` / `0x8009B778` | cycling / climbing | `CdSetloc` issued, retried, retried |

So the missing thing is a **CD completion**: the class-2 event that makes `FUN_8006C26C` register
`FUN_8006C2A0` (whose class-1 branch clears the wait byte) never arrives. That is issue 0011's
mechanism, and this issue narrows *where the product is* while leaving *why the callback never
arrives* to 0011 — with one correction, below.

## Correction to issue 0011: the guest gets PAST the SIO0 spin

Issue 0011 attributes the stall to the first spin in the guest's per-VBlank controller-port read,
`FUN_80093478`:

```asm
800934CC  lui   $v1, 0x800A
800934D0  lw    $v1, -0x469C($v1)   ; $v1 = *(0x8009B964) = 0x1F801040
800934D8  lhu   $v0, 4($v1)         ; SIO0 STAT
800934E0  andi  $v0, $v0, 0x0002
800934E4  beq   $v0, $zero, 0x800934D8
```

**That spin is not where the product is.** `FUN_80093478`'s next act is
`jal 0x800951B8` with `$a0 = 0x190`, and `FUN_800951B8`'s only effect is
`DAT_800AE228 = $a0` plus a snapshot of RCnt2. A constant-propagation sweep of the authenticated
text (`tools/probe_global_writers.py`, 227,175 instructions scanned) finds **exactly two** stores to
`0x800AE228`: the constant `0x1AE` at `0x80093398`, and `FUN_800951B8`'s own store. Decoding every
`jal` to `0x800951B8` gives seven sites, and the delay-slot immediates are `0x91`, `0x50`, **`0x190`**,
`0x3C`, `0x3C`, `0x3C`, `0x3C` — so `0x190` names one site and one only, `0x800934EC`.

The product's live probe reads `0x800AE228 = 0x190` in **every** one of its twelve samples. So the
guest executed `FUN_800951B8(0x190)` at `0x800934EC` and therefore **exited the SIO0 spin**, and is
somewhere after it. `scratch/probe_logs/cdcomp4.log` agrees: of 324,845 `I_STAT` reads, 322,576 carry
`ra=800934F4`, and `0x800934F4` is the instruction immediately after that `jal` — a link register is
only written by `jal`/`jalr`, so that value places the guest in `FUN_80093478`'s **second** loop, past
the spin.

`FUN_80093478`'s second loop has two exits: SIO0 status bit 7, or an RCnt2 countdown. The countdown
needs RCnt2's MODE bit `0x200`, and a sweep of the whole text finds **zero stores to `0x1F801124`**,
so the guest never sets it and that arm can never be taken. Whether the other arm
(`DAT_800AE228 <= elapsed >> 3`, i.e. 3200 counts) fires depends on the framework's root counter 2
advancing past the snapshot. **That is the open question, and it is a runtime one.**

**This does not change the recommended fix.** Issue 0011's proposal — a title-owned native override
of `FUN_80093478` that performs the exchange instead of bit-banging SIO0 — replaces the whole
function, so it settles the question either way. What changes is the diagnosis: the override is
needed because the function has **two** unbounded loops, not because the first one is stuck, and a
fix aimed only at the first would leave the second in place.

## What mode 3 is: NOT derivable from the disc executable, and why that is a real limit

`title_flow.resident_code` measures the density of `jr $ra` and `addiu $sp, $sp, -N` in three windows
of the resident text:

| window | words | `jr $ra` | `addiu $sp` |
|---|---|---|---|
| `0x80010000-0x800B0000` | 163,840 | 1,499 (0.91%) | 1,663 |
| `0x800B0000-0x800C0000` | 16,384 | 9 (0.05%) | 18 |
| `0x800C0000-0x80131000` | 115,712 | **0 (0.00%)** | **0** |

**11 of the 20 mode targets are at or above `0x800C0000`, a window with no code at all.** Mode 3's
handler at `0x800DB1B8` is one of them: Capstone decodes its first word as
`bne $at, $fp, 0x800CE6C4` and the next twelve as nonsense. Those handlers are written at run time by
the mode-0 loader from disc-compressed resources, and `FUN_8004CA40` decompresses every entry into
ONE staging buffer at `0x8012867C` and hands it to `FUN_8007EFC8`, so the destination of each
processed image is in the compressed payload, not in the executable.

**So the menu, the inputs it accepts, and the branch toward a fight are not statically derivable
here, and this issue does not guess them.** The concrete next measurement is one `r` read of
`0x800DB1B8` from a run that has completed mode 0 — the product already gets that far, in seven
fields — after which those words can be decompiled. `tools/probe_loader_state.py` now watches that
address for exactly that.

## Ruled-out shortcuts

- **Pressing buttons to leave the card.** Phase 12 reads no controller port over 294 instructions,
  and the mode it installs is a byte mode 0 wrote before the card was ever drawn. A route that
  pressed Start would be compensating for nothing, and would look like progress.
- **Clearing `0x800A069F` from the host.** That byte is the guest's own "a CD read is in flight"
  flag. Writing it skips the lifecycle under investigation, which is the shortcut issue 0011 already
  rules out.
- **Treating the card as the mode-2 *entry* rather than its *phase 8*.** Modes 0 and 2 have been read
  as whole screens before; the phase halfword is a separate dispatch with its own 13-entry table, and
  conflating them is what makes "the card waits for input" look plausible.
- **Naming mode 3 from the 20-entry table.** A table of addresses is not the contents of the
  functions it points at, and 11 of those functions are not in the disc executable.

## What a run would settle, and what it would not

**No product run was performed.** The machine's single product slot was held by another agent for a
Spyro capture until 2026-09-29T12:00 (`coord/claims/product-slot/claim.md`), and two instances are
never run at once here. Every claim above is static or is quoted from a run another agent already
made and whose log is retained. A run would settle, in order:

1. **Does `FUN_80093478`'s second loop exit?** Read `0x800AE228` and `0x800A8680` together with the
   framework's root counter 2. If the countdown never advances past the snapshot, that is the loop.
2. **Does the sector callback then fire?** `0x800A069F` falling to 0 with `0x8009B8E8` nonzero is
   the answer, and it is the same probe.
3. **What is mode 3?** Read `0x800DB1B8` and decompile.

It would **not** settle the menu, its accepted inputs, or the branch toward a fight — those need
(3) first, and then a further run.

## Next

Implement the `FUN_80093478` override issue 0011 already names, reproducing the whole function
rather than only the first loop, and install it through the same `tekken3::guest::install` path as
the six CD overrides. Then re-run `tools/probe_loader_state.py` and take the answer to (1) and (2)
from the live words. Only after mode 2 exits does the fight scene exist to widen, and
`tools/probe_tekken3_widescreen_pair.py` has a frame worth shooting at.
