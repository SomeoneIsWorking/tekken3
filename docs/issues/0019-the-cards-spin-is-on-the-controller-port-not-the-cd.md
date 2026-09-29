---
id: 19
title: The card's spin is on the CONTROLLER port, not on the CD completion
status: open
symptom: The NAMCO PRESENTS card never leaves; the wait loop does not exit at any field
state_items: S003
tags: tekken3,pad,sio,cd-completion,blocker,sector-callback-dispatch
created: 2026-09-29
updated: 2026-09-29
---

## SUPERSEDED 2026-09-29 — BOTH REFUTATIONS BELOW ARE DEAD TAPS. SEE ISSUE 0020.

**The two claims this issue rests on are both wrong, and both are zeros from a census that could not
report anything else.** `docs/issues/0020` re-measures with `tools/census_word.py`, which is pinned
in both directions:

| this issue said | measured, of 295,936 walked words |
|---|---|
| `0x800A069F` has **0 materialised readers** | **4 readers, 5 writers** — including `0x8006BEBC`, inside `FUN_8006BEA8`, the function mode 2 is sitting in |
| **no instruction reads** `0x8009B8D0` | **6 readers, 1 writer** — and `0x8009213C  jalr $a3` calls the value loaded from it at `0x80092110  lw $a3,8($s1)` |

The sweep that produced the zeros propagated `lui`/`addiu` **in the same register only**, and this
image builds every global the way a MIPS compiler does — `lui $v0` then `addiu $s0,$v0,imm`, i.e.
built in one register and consumed in another. It also reset its register file at every branch
target, discarding cross-block constants, and the handler that dispatches the sector callback holds
`$s1 = 0x8009B8C8` live across ~40 instructions and four branches.

**So "the card's spin is on the controller port" is refuted, and the CD chain is the blocker after
all** — which is what issue 0018 said before this issue. The hop-2 dispatch is real, it is
`0x8009213C`, and it is exactly where issue 0018 left it.

**What survives from this issue unchanged:** the SIO measurements below. They answer a different
question, nothing in issue 0020 touches them, and whether the pad is *also* wrong is still open. The
CD chain being the blocker does not make the controller port correct.

## A PARKING NOTE: the sector-callback dispatch, found on 2026-09-29 and parked here — THE PARKING
## IS WRONG, see issue 0020

The note below is kept rather than deleted, because the error's shape is the useful part: it is a
confident negative about a callback slot, resting on a census, and it parked the real fix.

`FUN_80091F38` (`0x80091F38`) stores the sector callback at **`0x8009B8D0`**
(`0x80091F78  sw v1, -24(s0)` over the `s0 = 0x8009B8E8` base). **No instruction in the
authenticated text reads that word** — a `lui`+`addiu`/displacement propagation census over all
295,936 text words, pinned by requiring the same sweep to find the writers and the readers of
`0x8009B8C8`..`0x8009B8E8` first (0x80092058, 0x80092158, 0x80091F50, 0x80091FD0, 0x80092494).

The per-sector handler the same routine arms — `0x80091F7C  jal 0x8009268C` with
`0x8009B8DC`-relative `0x80092034` going into slot `0x800BE034` — instead calls the pointer at
**`0x8009B8CC`**:

    800920E8  lw    v1, 4(s1)      ; s1 = 0x8009B8C8, so v1 = *(0x8009B8CC)
    800920F0  slt   v0, v0, s0
    800920F4  beq   v0, zero, ...
    800920F8  addiu a0, zero, 1
    80092100  jalr  ra, v1

and `FUN_80091F38` **zeroes that very word** at `0x80091F70  sw zero, -28(s0)`. So the sector
callback is installed into a slot nothing dispatches, while the slot that IS dispatched is cleared
by the same routine. At the frontier, post-hop-1, `0x8009B8D0` = `0x8006C2A0` and `0x8009B8E8` = 1,
so the install did happen and the dispatch still cannot reach it.

**CORRECTION (issue 0020).** The listing above is read correctly but **concluded wrongly**, and the
error is one instruction of bookkeeping. `0x800920E8  lw $v1,4($s1)` loads `0x8009B8CC` into `$v1`
— but `$v1` is then used only for the `slt` comparison, and the `jalr $a1`-shaped call at
`0x80092100` goes through a register loaded **at `0x800920D8  lw $v1,8($s1)`**, which is
`0x8009B8C8 + 8` = **`0x8009B8D0`** — the sector-callback slot after all. The same handler's second
arm is the one the test pins: `0x80092110  lw $a3,8($s1)` then `0x8009213C  jalr $a3`.

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

**CORRECTION (issue 0020): the sentence above is false and so is the one it justifies.**
`0x800A069F` has **4 readers and 5 writers** in the authenticated text. The sweep that reported 0
propagated a global's address only when the `lui` and the `addiu` wrote the **same** register, and
this image writes the base in `$v0` and consumes it in `$s0`. `0x8006BEBC` — inside `FUN_8006BEA8`,
the very function mode 2 is sitting in — reads it. The 18 readers of `0x8009B964` quoted below came
out of the same sweep, so they are not independently trustworthy either; the direction of the error
is a **under**count, so a genuine 18 can only be larger, but the figure should not be quoted.

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

**CORRECTED 2026-09-29. The figures below were produced by a scan that read the wrong bytes, and the
correction is kept because the error's shape is the useful part.**

    text walked            295,936 word(s), loaded from FILE OFFSET 0x800 to t_addr
                           (was wrongly reported as 163,840, from file offset 0 with a guessed size)
    route A candidate(s)   1, and it is NOT CODE (was wrongly reported as 0)
    route B                4 image words that ARE an SIO0 address
                           0x8009935C, 0x8009C164, 0x8009C17C, 0x8009C198 — all SIO0 DATA

**Two mistakes, and the first hid the second.**

1. **A PS-X EXE is 2048-byte sector padded.** Its text is loaded from **file offset `0x800`** to
   `t_addr`; mapping the file from its start lands every address `0xF800` bytes high. The first scan
   did exactly that, and read 163,840 words instead of 295,936.
2. **That truncated scan then reported "route A: 0 sites", and the conclusion "the guest never
   materialises an SIO0 address" was written on top of it.** With the correct text the same scan
   finds **one** candidate: `0x800C2B18`, `ori` with immediate `+0x1040` off a `lui`'d register, which
   builds `0x1F801040` — SIO0 data.

**The one candidate is not a real access, and saying so required asking something that decodes
properly.** The framework's own disassembler **refuses** the window around `0x800C2B18` — 4 of 8
words undecodable, and the rest sitting inside an ASCII string (`3a35203c` reads `"<5 :"`,
`013d4d42` reads `"=M"`). A linear pass that tracks `lui` values cannot know a register was
reassigned, so it manufactures hits inside data regions. The census now **verifies every candidate
against the framework's disassembler and demotes any window it refuses**, rather than asserting a
number.

So the verdict survives, and is now better founded: **the guest reaches SIO0 by pointer, not by
building the address in an instruction it can be shown to execute.** All four static pointers name
the **data** register; the status and control registers are reached as `+4` and `+0xA` off that
pointer, which is why the older comment's "`0x1F801044` = `*0x8009B964` + 4" was right about the
address and wrong about everything else.

The pointer global this driver uses is **`0x8009B964`**, with **18 materialised readers** in the text
(against **0** for `0x800A069F`, which is the control that proves the sweep works). Through it the
driver polls SIO0 status twice, and the two masks are:

    0x80093924  lw    $v1,-0x469C($v1)   ; v1 = *(0x8009B964) = 0x1F801040
    0x8009392C  lhu   $v0,0x4($v1)
    0x80093934  andi  $v0,$v0,0x0200      ; status bit 9 — the ACK bit

and, at a **neighbouring global**, the first poll:

    0x800934D0  lw    $v1,-0x46A0($v1)   ; v1 = *(0x8009B960) — NOT 0x8009B964
    0x800934DC  lw    $v0,0x4($v1)
    0x800934E4  andi  $v0,$v0,0x0001      ; status bit 0 — data available

**The two globals are four bytes apart and were once written as one.** `0xB960` is a displacement of
`-0x46A0` and `0xB964` is `-0x469C`; a four slipped between them and merged `0x8009B960` with
`0x8009B964`. The census's control now checks both landings explicitly, because that four reached a
written record during this session.

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

## Measured at run time, in the same run

Read again over the control channel on a second disc-backed run, fields 2,117 to 2,392:

    0x8009B964  port pointer  = 0x1F801040   <- the chain IS real; this refutes the first falsifier
    0x1F801044  SIO0 status   = 0x0001       constant
    0x1F801040  SIO0 data     = 0x000000FF   constant
    0x8009B940  a guest word  = 0x00000002   constant
    0x8009B920  a code pointer= 0x80094E40   constant

**`0x8009B964` really does hold `0x1F801040`**, so the port chain in this issue is not an artifact of
sampling, and the first falsifier above is refuted by measurement. `0x8009B940` sits at exactly 2
and does not move across 275 fields.

## NOT ESTABLISHED: which loop is actually stuck

The obvious candidate was the back edge at `0x800938C4` (`bgtz $v0,+0x-68`, i.e. branching back to
`0x80093860`) over the counter at `0x8009B940`. **That is now decoded, and it is not the stuck
loop** — see the next section. The loop is real code, and the counter is not moving, which is what
rules it out.

## The candidate window, re-read with the extended decoder

The decoder was then extended to cover the `SPECIAL` opcodes and the full load/store table, and the
selftest was rebuilt to be **construction-based rather than arithmetic-based**: the mnemonic must
equal the name Lightrec's own `enum special_opcodes` gives that `funct`, and the load/store
classification must follow from the top six bits alone. That rewrite was forced by a failure worth
recording — the first version of this selftest asserted text an agent had re-derived by hand from
hex, and it was wrong three times in a row on words it had not actually checked. **A control built
from the same unreliable step it is meant to check is not a control.** Checking against an enum
already in the tree is a control that can be wrong.

The extension also fixed a real opcode-table bug: `0x2A` was mapped to `slti` when it is `SWL` and
`slti` is `0x0A`. That silently ate every unaligned load, and the symptom was a region that looked
like data instead of an opcode table with a hole in it. Modelled coverage went from **120,783 to
154,260** of 163,840 words, and **both census conclusions are unchanged under the better decoder** —
route A is still 0 sites and route B still 4 — so the SIO0 findings do not rest on the gap.

With the window decoded, `0x80093860..0x800938C8` reads as a **bounded retry countdown around a call
through a function pointer**:

    0x80093864  lw   $v1,-18112($v1)   ; v1 = *(0x8009B940), an array base
    0x8009386C  sll  $v1,$v1,2         ; index by a slot, stride 4
    0x80093870  addu $v1,$v1,$s1
    0x8009387C  addiu $v0,$v0,-1       ; n--
    0x80093880  sll  $a0,$v0,4 / subu / sll   ; a0 = 240 * n
    0x8009388C  sw   $v0,0($v1)        ; store the decremented value
    0x80093898  lw   $v1,-18144($v1)   ; v1 = *(0x8009B920) = 0x80094E40
    0x800938A0  jalr $ra,$v1           ; call it
    0x800938A4  addu $a0,$v0,$a0       ; delay slot: a0 = 241 * n
    0x800938C4  bgtz $v0,0x80093860    ; loop while n > 0

**And this loop is not where the guest is stuck.** Its counter `0x8009B940` reads **2** and does not
move across 275 fields; a countdown starting at 2 would reach 0 in two passes and leave. A counter
that is pinned while a countdown sits in the code means the countdown is not executing. So this
window is real code and a dead end for the card, and the stuck site is still elsewhere.

## The pad hypothesis is REFUTED by the framework's own channel

The obvious reading of "the card polls SIO0 status bit 9 and it never sets" is that the guest is
waiting for a pad **ACK** the model withholds. **That is wrong, and the framework's own `sio`
diagnostic says so.** One run with `PSXPORT_DEBUG=sio`, 3,000 fields, 78,669 `[sio]` lines:

    /ACK lines that raised the bit :  the log prints "/ACK -> JOY_STAT#9 + I_STAT#7" whenever
                                     CTRL bit 12 is set, and it is set for the whole pad sequence
    tx 01 -> rx 41 ACK              3,279   the digital pad's ID — the handshake WORKS
    tx 00 -> rx 5A ACK              3,276   the pressure/analog payload
    tx .. -> rx FF                  13,110  the floating bus: the RX FIFO was empty
    no-ack                          6,558   of 19,665 byte exchanges, all with `pos -1`

So the pad is initialised and read **3,276 times successfully**. The guest gets its `0x41` pad ID
and its `0x5A` data. A guest waiting for an ACK it never receives is not what this is.

**And the guest sets CTRL bit 12.** The trace's own `w CTRL 1003` lines mean the `/ACK` interrupt
enable IS on for the whole pad sequence, so `Sio0::service` does raise `irq` and JOY_STAT bit 9 does
get set — repeatedly, thousands of times. **The bit the poll waits for is therefore not the bit that
is stuck**, and the run's steady state is not a pad that cannot answer.

What the run *ends* on is this, repeated:

    w CTRL 0000 (raw 0040)  ra=80094934      reset
    w CTRL 0000 (raw 0000)  ra=80094934
    w CTRL 3003 (raw 3003)  ra=80093018      bit 13 set
    tx 01 -> rx FF no-ack (pos -1, ctrl 3003)  no device addressed
    w CTRL 3003 (raw 3013)  ra=8009323C
    w CTRL 0000 (raw 0000)  ra=800948E4

`pos -1` means the framework has no device addressed, and `Sio0::ctrlWrite` cancels the exchange
whenever CTRL bits `0x2002` change — bit 13 is inside that mask, and the mask is documented as
"DTR or selecting the other physical port ends this device's exchange". So the guest's final move
each cycle is a CTRL write that, under this model, tears down the very device it is about to talk to,
and the `0x01` that follows is answered by a floating bus.

**What is still open, precisely:** whether SIO CTRL bit 13 should end the exchange. That is a
hardware-semantics question, and this tree cannot answer it — and the absence is **total**, not
confined to the one file. `psxport/vendor/beetle-psx/mednafen/psx/sio.c` is, in its own words, a
"Dummy implementation" with no status semantics, and the string `0x1F801044` appears **nowhere** in
the whole vendored Beetle tree — so the emulator psxport is built alongside models the controller
somewhere else entirely, and cannot be consulted. **No fix is attempted here**, because both
available moves — raising bit 9 on ACK regardless of CTRL, or keeping the device across a bit-13
write — would be asserting hardware behaviour this repository has no evidence for, and one of them
would be fabricating the guest's controller state.

## What survives, and what is now open

**Survives:** the blocker is not the disc. The CD completion is delivered and measured delivered — the
guest consumed every record it queued, the ring drained to empty and stayed drained while the CD
completion count kept climbing `0x62` → `0xF7`. The card's remaining wait is on the **controller**.

**Refuted along the way, and kept here because a refuted hypothesis that is not written down gets
re-derived:** the pad is NOT failing to answer. The framework's own `sio` channel shows the digital
pad ID `0x41` read 3,279 times and its `0x5A` payload 3,276 times, with `/ACK -> JOY_STAT#9` raised
every time because the guest *does* set CTRL bit 12. So "the card waits for an ACK that never comes"
is false. What the run ends on, repeatedly, is a `CTRL = 0x3003` write followed by a `0x01` byte that
comes back `no-ack` with `pos -1` — no device addressed — and `Sio0::ctrlWrite` cancels the exchange
whenever CTRL bits `0x2002` change, with bit 13 inside that mask. Whether bit 13 *should* end the
exchange is a hardware-semantics question this tree cannot answer: Beetle's vendored `sio.c` is a
self-described dummy with no status model. **No fix is attempted**, because either move available
would be asserting hardware behaviour with no evidence behind it.

**Now open, and a smaller question than this issue first claimed:** the framework's pad owner answers
Tomba! 2's equivalent poll by writing the pad packet straight into the guest's registered slot buffer
instead of emulating SIO (`psxport/runtime/psx/pad_input.cpp`, and its header's account of
`FUN_80003a4c`). Whether Tekken 3 needs the same bypass, or whether the port model needs a real ACK
cycle, depends on the bit-13 question above. **That is not decided here.**

## Falsifier

Each of these would make this issue wrong, and each is a measurement rather than an opinion:

- If the framework's SIO0 status is not the register the guest means — i.e. if `*(0x8009B964)` does
  not hold `0x1F801040` in a run that reaches the wait — the whole address chain is an artifact of
  when it was sampled.
- If a run **with a pad attached** shows status bit 9 set, then `0x0001` is what a real no-pad port
  looks like and the fix is input, not the port model.
- If the guest writes `0x1F801044` itself through the pointer — which route A cannot see, and which
  the run does not exclude — the framework's model is not the owner of the bit.
