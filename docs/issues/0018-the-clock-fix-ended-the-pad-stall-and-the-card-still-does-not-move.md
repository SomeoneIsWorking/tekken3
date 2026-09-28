---
id: 18
title: The in-segment clock fix ended the pad stall — and the card still does not move, because the CD completion was never a clock question
status: open
symptom: the pad wait loop now returns, the product runs 25,030 fields and 1.44 G guest instructions, and 0x800A069F is still 1 in every sample
state_items: S003,S004,S007,S008
tags: re-first,cd,completion,interrupt,loader,clock,recovery
created: 2026-09-28
updated: 2026-09-28
---

## Answer

**The framework clock fix landed and it worked, and it was not this blocker's cause.** The pad
driver's second wait loop now returns in 6,526 cycles instead of exhausting a 564,492-cycle budget,
through the same single segment. The product then runs **25,030 presented fields and 1,442,602,195
executed guest instructions with 0 faults and 0 interpreter fallbacks** — 3.6x the depth issue 0016
recorded. And the card is still up.

**The reason is that the missing thing was never a clock. It is a CD completion that nobody
delivers.** The guest's own loader registers a completion callback, the callback sits in guest RAM
unread, and the port has no mechanism that would ever call it. This is now a **title defect in a
native override**, and it is the first one in this repository: issue 0017 and issue 0016 both
attributed the stall to the framework and both are wrong about the remaining half.

## 1. The clock fix is measured, and it is not the fix

`tools/verify_pad_wait_exit.py`, same tool, same image, same four arms, run against psxport
`5d4b3327`. The tool **refuses** rather than reporting a pass, which is the correct behaviour and
which is why this section quotes its transcript rather than its verdict:

| arm | at `b951d747` (issue 0017) | at `5d4b3327` |
|---|---|---|
| `retail` | `returned=0 exhausted_in_wait_loop=1`, **564,492 cycles**, 40,316 blocks, 282,244 instructions, 1 segment | `returned=1 exhausted_in_wait_loop=0`, **6,526 cycles**, 462 blocks, 3,261 instructions, 1 segment |
| `bit7` (control) | returns, 186 cycles | returns, 186 cycles — unchanged |
| `segmented` | leaves the loop, 9 segments | **identical to `retail`** |
| `clock` | 1 distinct value / 4,096 polls without accounting | unchanged |

Two things in that table matter more than the headline.

- **`bit7` is unchanged at 186 cycles.** That is the control for *reaching* the loop, and it is
  stable, so the `retail` arm's 86x drop is the loop and not the harness stopping measuring it.
- **`segmented` is now identical to `retail`.** That arm existed to identify the mechanism by
  varying only the segment length. It can no longer vary anything, because the mechanism is gone.
  **A mutant that can no longer fail is not a control any more, and the tool's refusal is the
  honest outcome**: "Either the loop now exits — which is the fix working, and is a real change to
  re-verify the rest of the port against — or the harness stopped measuring it."

`retail` exited by the **pad-status bit 7** arm (`0x800935F8`), not the countdown arm
(`returned_by_countdown=0`): with the clock moving, the SIO0 exchange completes inside the window
and sets the flag before the countdown expires. Both arms of issue 0017's reading were therefore
live; neither is the blocker.

## 2. The product measurement: 25,030 fields, and the same wait byte

One headless run, `build/ci` against psxport `5d4b3327`, 4:3 settings, no pacing, the loopback
endpoint driven by one client. `scratch/probe_logs/clockfix.probe.txt`, 24 samples from field 634
to field 23,665.

| word | value | over 24 samples |
|---|---|---|
| `0x800AE204` mode | `2` | constant |
| `0x800AE224` phase | `8` | constant |
| **`0x800A069F` the wait byte** | **`01`** | **constant, never cleared** |
| `0x8009B8E8` sector-callback-registered | `0` | constant, never set |
| `0x8009B8D0` the registered callback | `0` | constant |
| `0x8009B774` outstanding-command counter | cycles 1..28 | **cycling** |
| `0x8009B778` completion counter | 9 -> 0x324 (804) | **climbing monotonically** |

Guest execution at field 25,030: `calls=401006 translated_blocks=1917 executed_blocks=241373778
executed_instructions=1442602195 host_dispatches=126867 cache_hits=241371861 cache_misses=1920
invalidations=70169068 faults=0`, and `fallback: calls=0 instructions=0 refused_calls=0
compilation_failed=0 self_modifying_code=0 unsupported_block=0 load_delay_hazard=0
unsafe_instruction_fetch=0`. **The JIT is the gameplay default and it is not silently degrading.**

**So the answer to "does the class-2 CD completion arrive, and is `0x800A069F` cleared" is NO, and
it is measured rather than inferred**: 0 of 24 samples, over 3.6x the depth issue 0016 reached.

## 3. The root cause, named to the instruction

`FUN_8006C084` sets the wait byte and registers the completion callback in one breath:

```asm
8006C1A4  sb    v0,7(s1)      ; s1 = 0x800A0698  ->  0x800A069F = 1     THE WAIT BYTE
8006C1B0  addiu a0,zero,0xA0  ; CdGetID
8006C1BC  jal   0x8008F08C    ; submit to the CD chain
8006C1C0  addiu a3,s3,-15764  ; a3 = 0x8006C26C                          THE COMPLETION CALLBACK
```

and `FUN_8006C26C` is what would install the sector callback that clears the byte:

```c
// 0x8006C26C — the chain's completion callback. $a0 is the CD event CLASS.
void LoaderClassCallback(u8 eventClass) {
  if (eventClass == 2) {                    // 0x8006C278: bne a0, 2
    FUN_80091F38(0x8007C2A0, -1);           // 0x8006C288: install the SECTOR callback
  }
}
// 0x8007C2A0 — the sector callback. Class 1 means one sector arrived; it consumes it and
// 0x8006C2EC clears 0x800A069F, which is the ONLY writer of that byte to zero on this path.
```

**Measured, from the live capture, not inferred:** the callback is in RAM and nobody has called it.

| fact | measurement |
|---|---|
| `FUN_8008F08C` stores `$a3` into its record at `+12` | `0x8008F184: sw s3,12(v0)` |
| where that landed | the value `0x8006C26C` appears in the whole 2 MB capture at **exactly one** address, `0x800A3DD0`, in **both** captures taken (field 25,030 and field ~1,200) |
| the sector callback it would install | the value `0x8007C2A0` appears at **0 of 524,288** words |
| the CD interrupt the callback rides in on | 4,458 interrupt deliveries in a 1,200-field traced run, and **every one** logged `I_STAT&I_MASK=0x001` — VBlank. **0 of 4,458** carried bit 2. |
| `I_MASK` bit 2 | **set** — so a raised CD edge would reach the guest |

**And the framework says outright that it does not model this.** `psxport/runtime/psx/cd_override.cpp`
line 3: *"No emulation" — we do NOT model the CD controller or deliver CD IRQs.*

### The title's own CD owner is what removed the delivery

`game/core/cd_sync.cpp` installs six overrides. The two that matter:

```cpp
// kCdQueueStart = 0x80090F78, retail's CdReady-chain start
std::uint32_t queueRead(CdMachine &machine, std::uint32_t location,
                        std::uint32_t sectors, std::uint32_t destination) {
  ...
  machine.write32(kQueueBusy, 1);
  // "Retail turns that request into Pause/Setmode/Setloc/ReadN, then spins on callbacks that
  //  decrement the remaining-sector word. Native ownership must be synchronous all the way down"
  const bool succeeded = machine.readSectors(location, sectors, destination);
  machine.write32(kQueueSecondArgument, succeeded ? 0u : static_cast<std::uint32_t>(-1));
  machine.write32(kQueueBusy, 0);        // <-- busy CLEARED on the way out
  return succeeded ? 1u : 0u;
}
```

and `kCdControl = 0x80083E4C`, retail's `CdControl` wrapper, which `control()` drives to
completion inline and returns 0. **Both complete the operation inside the override and neither
invokes the callback the caller registered.** Retail's bodies issue the command to the controller
and return; the completion arrives later, on the controller's interrupt, and *that* is the only
thing that ever calls `FUN_8006C26C`.

The comment is the design decision, and the design decision is the defect. "Native ownership must be
synchronous all the way down" is true of the *data* and false of the *lifecycle*: the guest's CD
driver in this title is a per-sector **callback loop** whose termination signal is its own callback
being invoked. Completing synchronously deletes the loop and leaves the guest waiting for an event
that the port has by construction stopped being able to produce.

### The framework's own mechanism would have done it, and cannot reach this title

`cd_override.cpp`'s `cd_drive_stock_read` is precisely the right shape — its own comment: *"A
stock-libcd read is a per-sector CALLBACK LOOP ... the port does not need an interrupt controller, a
CD IRQ, or the guest's ISR chain to finish a read. **It needs to call the callback the game already
registered.**"* It re-reads the slot every iteration and dispatches until the guest's own Pause.

It returns immediately here, for a measurable reason and not by accident:

```cpp
std::uint32_t cd_ready_callback_pointer(const Core &core) {
  if (core.cfg && core.cfg->cdReadyCbPtr) return core.cfg->cdReadyCbPtr;      // nullptr: direct runtime
  const GameRuntime *runtime = core.game ? core.game->runtime : nullptr;
  const GuestCdStreamCallbackLayout *layout = runtime ? runtime->guestCdStreamCallbackLayout() : nullptr;
  return layout && layout->valid() ? layout->readyCallbackPointer : 0u;       // base returns nullptr
}
```

Tekken 3 is a **direct runtime** — `CLAUDE.md` forbids it instantiating `GameConfig`, so `core.cfg`
is null — and it does not override `guestCdStreamCallbackLayout()`. `grep` over the title's whole
`game/` tree finds no mention of either. So the pointer is 0, `cd_drive_stock_read` returns at its
first line, and **0 sector callbacks are ever dispatched**.

**This is not only a missing declaration, and the next step has to know that.** Even with the slot
declared, the FIRST hop is still missing: `0x8009B8D0` is 0 because nothing has run
`FUN_8006C26C` to install it. So the fix has two hops, and only the second one is the framework's
existing mechanism.

| hop | what it is | whose it is | state |
|---|---|---|---|
| 1 | the CD chain's completion callback `FUN_8006C26C`, sitting in the record at `0x800A3DD0` | the title's own CD driver, and the title's own `jal` passed it in | **undelivered** |
| 2 | the sector callback `FUN_8007C2A0`, installed into `0x8009B8D0` by hop 1 | the framework's `cd_drive_stock_read`, pointed at a slot the title must declare | **never armed, because hop 1 never ran** |

## 4. The mode-3 recovery: the method is built and gated, and the subject is not there yet

`tools/recover_runtime_handlers.py`. Three independent routes to the same bytes, four arms, 13
selftest checks. Run against the field-25,030 capture:

| arm | result |
|---|---|
| `indisc` — **the control that can fail** | **9 of 9** in-disc handlers byte-identical to the authenticated image over 1,024 bytes each. Route B is a faithful read, so the zeros below mean something. |
| `window` | **0 of 11** window handlers hold a code marker on the disc, and **0 of 11** after 25,030 fields. `ram diff words` is **0 of 256** at all 11. |
| `negative` | a capture holding the disc and nothing else scores 9/9 on the control and 0/115,712 in the window — so a later non-zero would be a real change, not tool noise |
| `payload` | **127 of 127** mode-0 payloads decode offline from the disc, **0 refused**, and **0 of 127** contain a code marker |
| `loaders` | **7** placement sites in the text, 7/7 paired with a `placement-next`; mode 0's loader is **1 of 7** |

The window is reported as a **measured absence, not a scan that found nothing**, and it is reported
next to a reference corpus with a known answer:

```
reference, the in-disc text 0x80010000-0x800B0000 : 163,840 words, 1,663 prologues (1.02%), 1,499 `jr $ra` (0.915%), opcode entropy 4.599 of 6.000
the disc's own window 0x800C0000-0x80131000      : 115,712 words,     0 prologues (0.00%),     0 `jr $ra` (0.000%), opcode entropy 5.390
```

0x800C0000-0x80131000 is 96.91% non-zero and it is **data**. The 16-bit-stride structure is
visible in the raw words — `0x800DB1B8` reads `143ECD42 43CF0002 D6640D15 BDCF3BFE`, each word a
high half and a small low half, which is a vertex/CLUT table and not instructions.

**So the premise of issue 0016 is wrong on both halves, and this is a correction rather than a
refinement:** the mode handlers are *not* in the mode-0 resource set, and the mode-0 loader *did*
run to completion (the log records `entry 0x800B0708 ... returned ... after 6 suspended field(s)`)
without writing a single word to any handler address. What the loader did write is **5,821 words of
PSX1 vertex data** at `0x8012867C`+, and the placement cursor `*(0x800A3B88)` stands 0x218 bytes
into it.

The recovery of mode 3 is therefore **not blocked on method, and it is blocked on the CD
completion**: the code images are not in the disc text, not in mode 0's 127 payloads, and not in
RAM at the frontier this port reaches. `arm=loaders` says where to look next.

## Falsifier

Each of these would make this issue wrong, and each is a measurement rather than an opinion:

1. **The card claim.** A run in which `0x800A069F` is observed 0 while `0x8009B8E8` is nonzero.
   Today: 0 of 24 samples, with `0x8009B8E8` = 0 in all of them.
2. **The hop-1 claim.** The value `0x8006C26C` absent from a capture, or present at an address other
   than `0x800A3DD0`. Today: exactly one word, at that address, in both captures.
3. **The framework-mechanism claim.** `cd_ready_callback_pointer()` returning nonzero for this
   title, which would make `cd_drive_stock_read` run. Today: 0, by two independent nulls
   (`core.cfg` is null and `guestCdStreamCallbackLayout()` is not overridden).
4. **The window claim.** Any of the 11 window handlers holding a `jr $ra` or a `0x27BD` prologue in
   a capture taken after a run that reaches past the card. Today: 0 of 11, with 0 of 256 words
   differing from the disc at each.
5. **The loader-count claim.** Fewer or more than 7 `FUN_8007EFC8` call sites in the authenticated
   text. The selftest pins the census by requiring it to FIND mode 0's own call at `0x800B0744`
   first.

## Not established

- **Which of the 7 loaders places the code images, and whether any of them runs before the card.**
  Named, not guessed. `0x80035784`, `0x8004C734`, `0x8004C82C`, `0x8004C984`, `0x8006E3A4` and
  `0x800762A4` are the six sites other than mode 0's.
- **Whether fixing the CD completion is sufficient.** The window's contents at the frontier are
  consistent with "the code images are placed after the card" and equally consistent with "they are
  placed by one of the 6 other loaders and something else is also wrong". A run past the card
  settles it; nothing shorter does.
- **The `FUN_80093478` SIO0 spin.** `tools/probe_cd_completion.py` sampled `0x1F801044` as `0x0101`
  in one 1,200-field run, so bit 1 read clear. **That is a sample at a different instant than the
  guest's poll and is not evidence about the loop** — issue 0017's `retail` arm, which *is* the
  loop, now returns. Recorded so the next reader does not mistake the probe's live sample for a
  measurement of the loop.
- **Nothing about the widescreen picture changed.** The 4:3 leg still logs
  `native_width=368 render_width=368` as its last `[wide]` line, and the 133x16 card is still the
  only content. S007 is untouched by this issue.

## Ruled out

- **"The clock fix did not land."** It landed: the same binary, same image, same four arms, 564,492
  -> 6,526 cycles, with the `bit7` control unmoved at 186.
- **"`0x800A069F` needs a host write."** Writing it skips the lifecycle under investigation, which
  issue 0016 already rules out. The byte's only clearing writer on this path is
  `0x8006C2EC`, inside the guest's own sector callback, and getting *that* to run is the fix.
- **"The mode handlers are mode 0's resources."** 0 of 127 decompressed images contain a code
  marker, decoded offline from the disc with the decompressor this repository already verified
  against the guest. A loader census that stops at `FUN_8004CA40`'s two call sites would have
  concluded "unreachable" from a table that is 1 of 7.

## Next

1. **Own the CD completion, in the title, at the point retail's controller interrupt ran.** The
   contract the framework already states is "call the callback the game already registered"; for this
   title the registered callback is the chain's `$a3`, and the sector callback lands in `0x8009B8D0`
   afterwards. Both hops are named above, and hop 2 is the framework's loop pointed at a slot this
   title must declare.
2. **Re-run `tools/verify_pad_wait_exit.py` after it.** The `segmented` arm is now a duplicate of
   `retail`; it is a spent mutant and the tool's `judge()` needs widening for the post-fix world.
3. **Re-run this issue's §2 probe**, in this order: `0x800A069F` with `0x8009B8E8`; then
   `0x800AE204` leaving 2. **Mode 3 reached is success; mode 2 phase 9 is not.**
4. **Then `arm=window` against the new capture.** That is the moment the 11 handlers stop being data,
   and it is the measurement this issue's §4 is built to receive.
5. **Then the six other loaders**, in the order `arm=loaders` lists them, reading each one's resource
   table the way §4 reads `0x800B8D58` — a stride-8 `{size, offset}` array of LZ payloads inside the
   executable. One of them holds the code images, and it is readable from the disc with no run at all.

## Evidence discipline

`tools/recover_runtime_handlers.py`'s selftest is 13 checks and each can fail: the in-disc control is
**defeated** (a one-word edit to the capture drops it from 9/9 to 8/9, so a clobbered capture is
detectable rather than reported as an absence); a truncated capture is **refused**, not scored 0 of 0;
two wrong table bases are **refused** instead of producing 20 confident wrong addresses; the LZ
decoder is cross-checked byte-for-byte against `tools/verify_decompressor_lightrec.py`'s independent
`reference_decode`; a 4-byte payload is **refused** rather than decoded short; the code census is
shown to score 1 KiB of mode 2's real handler high and 1 KiB of zeros zero; and the call-site census
must **find** mode 0's own `jal` before it is allowed to report anything about the other six.

**Two of my own instruments were wrong before they were right, and both are recorded because the
shape recurs.** The first `opcode_histogram` took the opcode from the low six bits, which is the
SPECIAL funct field, and reported 0 `jal` call sites and 0 `lui 0x800B` for a text holding 2,470 of
the latter — a uniform zero indistinguishable from a result. The MIPS opcode is the **top** six
bits. The run harness's product-slot guard had the same shape: `ps -eo args | grep _port` matched the
guard's own shell command line and refused forever; `ps -eo comm` cannot. Both are now pinned by a
selftest that requires a find before it permits a report.

**No product run overlapped another.** `coord/claims/product-slot` was held by megamanx4 when this
work started, on a claim whose own stated falsifier — "no `megamanx4_port` process is alive" — was
satisfied; that holder was running `clang-tidy`, a gate. The prior claim is archived verbatim beside
mine and the takeover is released, with the note that megamanx4 may reclaim at any time.
