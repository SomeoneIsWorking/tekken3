---
id: 19
title: The card's spin is on the CONTROLLER port, not on the CD completion
status: open
symptom: The NAMCO PRESENTS card never leaves; the wait loop does not exit at any field
state_items: S003
tags: tekken3,pad,sio,cd-completion,blocker
created: 2026-09-29
updated: 2026-09-29
---

## WHAT THIS ISSUE GOT WRONG ON FIRST WRITE, AND WHAT SURVIVED

The first version of this issue named **SIO0 status bit 1** as the bit the card waits on, and named
`0x800A069F` as the card's wait byte. **Both were quoted from `tools/probe_cd_completion.py`'s
disassembly comment, and decoding the authenticated image says both are wrong.** The corrections are
below and the surviving claim is at the end; the corrections are kept rather than edited away,
because the reason the wrong answer looked right is the useful part.

Three separate errors, in a comment that had never been checked against the bytes:

| quoted | actual, from the image |
|---|---|
| the spin is at `0x800934D8..0x800934E4` | `0x800934D8` is `sw $ra,0x10($sp)` — a function **prologue** |
| it loads a **halfword** (`lhu`) | `0x800934DC` is `lw $v0,0x4($v1)` — a **word** |
| it masks bit **`0x0002`** | `0x800934E4` is `andi $v0,$v0,0x0001` — bit **0**, not bit 1 |

And the word that probe called the wait byte, `0x800A069F`, has **0 materialised readers** in the
whole text. So the byte several earlier notes call "mode 2, phase 8"'s wait target is not read by any
instruction that materialises its address.

The reason a wrong disassembly survives review is that it is a plausible, specific, quoted string.
**A claim about an instruction is a measurement, and this one had none behind it.**

## The tool that settles it

`tools/tekken3_sio_poll_census.py` decodes the authenticated text itself rather than trusting any
comment, and is built to be wrong loudly:

- **It re-derives eight control decodings** from a separate hand reading of the same image and fails
  if it disagrees with any. It earned that immediately: the expected branch offset was first written
  as `+0x3C` and the control caught it — `0x1040000E` carries immediate `0x000E`, and a MIPS branch
  offset is the immediate **times four**, so the branch goes to `+0x38`. The slip was in the
  hand-written expectation, not in the image. A control that has never caught anything is a control
  nobody should trust.
- **It refuses** a missing or short image rather than reporting `0 matches`.
- **It reports two routes separately** and says so: an instruction-only census and a data-word
  census answer different questions, and a zero from one is not a zero for the other.

## Measured

    route A (direct `lui 0x1F80` + displacement) — 0 site(s) in 163,840 word(s)
    route B (a word in the image that IS an SIO0 address) — 4 site(s) in 296,448 word(s)
      pointer 0x8009935C, 0x8009C164, 0x8009C17C, 0x8009C198   all hold 0x1F801040 (SIO0 data)

**Route A is zero for reads and writes alike, so the guest never materialises an SIO0 address in an
instruction.** It reaches the port through a pointer. All four static pointers name the **data**
register; the status and control registers are reached as `+4` and `+0xA` off that pointer, which is
why the older comment's "`0x1F801044` = `*0x8009B964` + 4" was right about the address and wrong
about everything else.

The pointer global this driver uses is **`0x8009B964`**, with **18 materialised readers** in the text
(against **0** for `0x800A069F`, which is the control that proves the sweep works). Through it the
driver polls SIO0 status twice, and the two masks are:

    0x800934DC  lw    $v0,0x4($v1)      ; v1 = *(0x8009B964) = 0x1F801040
    0x800934E4  andi  $v0,$v0,0x0001    ; status bit 0  — data available
    0x8009392C  lhu   $v0,0x4($v1)
    0x80093934  andi  $v0,$v0,0x0200    ; status bit 9  — the ACK bit

Live values, from one disc-backed run at fields 10,242 / 10,345 / 10,448:

    0x1F801040  SIO0 data   = 0x00FF
    0x1F801044  SIO0 status = 0x0001
    0x1F80104A  SIO0 ctrl   = 0x0000

**So bit 0 is SET and the first poll is satisfied; bit 9 (`0x0200`) is CLEAR and the second is not.**
That is the unsatisfied one, and it is an **ACK** — the controller's acknowledgement of the command
that was just shifted out. `0x00FF` in the data register is also the pad-error code: the framework's
own pad notes (`psxport/runtime/psx/pad_input.cpp:16`) record `0x00` for "present/ok" and `0xFF` for
"no pad / error", and the same file's header (`:25`) records the identical SIO0 status poll spinning
for Tomba! 2, which has a timeout that marks "no pad" and carries on. **This one has no exit observed
in 10,448 fields.**

## What survives, and what is now open

**Survives:** the blocker is not the disc. The CD completion is delivered and measured delivered — the
guest consumed every record it queued, the ring drained to empty and stayed drained while the CD
completion count kept climbing `0x62` → `0xF7`. The card's remaining wait is on the **controller**,
and specifically on the port's **ACK bit**.

**Now open, and a smaller question than this issue first claimed:** the framework's pad owner answers
Tomba! 2's equivalent poll by writing the pad packet straight into the guest's registered slot buffer
instead of emulating SIO (`psxport/runtime/psx/pad_input.cpp`, and its header's account of
`FUN_80003a4c`). Tekken 3 drives the port itself through `0x8009B964` and therefore expects a real ACK
cycle. The next step is to decide whether the framework's SIO0 model can raise bit 9 for a port the
guest has itself commanded, or whether the title needs the same native-buffer bypass its sibling has.
**That is not decided here.**

## Falsifier

Each of these would make this issue wrong, and each is a measurement rather than an opinion:

- If the framework's SIO0 status is not the register the guest means — i.e. if `*(0x8009B964)` does
  not hold `0x1F801040` in a run that reaches the wait — the whole address chain is an artifact of
  when it was sampled.
- If a run **with a pad attached** shows status bit 9 set, then `0x0001` is what a real no-pad port
  looks like and the fix is input, not the port model.
- If the guest writes `0x1F801044` itself through the pointer — which route A cannot see, and which
  the run does not exclude — the framework's model is not the owner of the bit.
