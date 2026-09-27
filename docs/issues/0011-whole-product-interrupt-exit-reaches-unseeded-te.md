---
id: 11
title: Native/Lightrec first-frame budget and loader frontier
status: investigating
symptom: the first-frame mode call spans bounded guest turns; later loader and gameplay remain unverified
state_items: S003,S004,S008
tags: runtime,cd,title-loader,t3-04,sio
created: 2026-08-25
updated: 2026-09-27
---

## Measured correction: the CD command path is not the missing owner

The earlier text of this issue said "the current title CD overrides do not own that `FUN_8008F08C`
command path", and the working hypothesis was therefore a missing CD-command override. **Both are now
measured false**, and the real cause is on the SIO controller port, not the CD.

Measured on the shipping product (headless, silent, unpaced, live control endpoint, `tools/probe_loader_state.py`
and `tools/probe_cd_completion.py`, log `scratch/probe_logs/cdcomp4.log` and `loader_b.probe.txt`):

| guest word | value across fields 98..6865 | what it establishes |
|---|---|---|
| `0x800A05D8` loader state | `8` | `FUN_8006C084` writes 8 **after** its `do { FUN_8008F08C(...) } while (iVar1 == 0)` loop, so the submit **returned nonzero**. The loader is not spinning and not stalled in submission. |
| `0x800A3E40` raw queue count | `4` | exactly the four records `FUN_8008F08C` enqueues, and they are **never drained**. |
| `0x8009B730` CD initialised | `1` | the CD gate `FUN_8008FB08` requires is open. |
| `0x8009B774` outstanding command | `0x13`,`0x19`,`0x0E`,`0x10`,... cycling | `FUN_8008FCC0` armed its completion deadline, so a command **was really issued**. |
| `0x8009B778` completion count | `0x13` -> `0xEF`, climbing | the CD state machine is **retrying forever**. |
| `0x8009B734` live command | `1` = `CdSetloc` | the retrying command. |
| `0x800A05D8` | never `9` | the class-5 loader-failure branch **never ran**. This is not a loader error. |
| `0x8009B8D0` / `0x8009B8E8` | `0` / `0` | `FUN_8006C26C` never saw class 2, so `FUN_80091F38` never registered the sector callback. |

The command path is therefore **owned**: `FUN_8008F08C` only enqueues into the eight-slot ring at
`0x800A3D78`, and the record is executed by `FUN_8008E8B8` -> `FUN_8008FB08` -> `FUN_8008FCC0`, whose
only hardware call is `FUN_80083E4C(DAT_8009b734, DAT_8009b73c, 0, 1)` — and `FUN_80083E4C` is
`kCdControl`, one of the six title overrides `installCdOverrides` already installs through
`tekken3::guest::install`. `param_3` (the "request-mode argument 6" of the old text) is a **selector
into a 25-entry command-chain template jump table at `0x800387B0`** indexed by `param_3 - 3`, not a
libcd async mode. Command `0xA0` is not a PlayStation CD command: it is the first payload byte of the
chain's `CdGetID` record.

## The real cause: a SIO0 status poll with no timeout, inside the VBlank ISR

`scratch/probe_logs/cdcomp4.log` is 684,212 lines with `PSXPORT_DEBUG=irq,cd,cdc`:

- `3,815` interrupt deliveries, **every one** `elem 0x800A62E8 handler 0x80092D34 (I_STAT&I_MASK=0x001)`
  — VBlank (bit 0) only. Bit 2 (CD) is never delivered.
- `I_MASK = 0x6D` = bits 0,2,3,5,6, so **the guest enables the CD interrupt**. The absence of a
  delivery is not a guest masking decision.
- `CD raised IRQ2` occurs **0 times**. `Core::irqStatLatch()` is the only place the CD edge becomes
  `I_STAT` bit 2, and it is called *after* `irqPoll`'s `if (in_irq || !irq_enabled) return;`.
- `delivery declined 1,200,000 times: critical-section=0 nested=1,200,000 transient=0` — `in_irq`
  is stuck at 1, so every poll returns early and the CD edge is never even latched.

The last interrupt delivered is the VBlank element handler `FUN_80092D34`
(`[0x80092D34,0x80092E9F]`, returns 0), which calls `FUN_800931D8` and reaches `FUN_80093478`. That
function's **first** act is an unconditional poll:

```asm
0x800934CC  lui   v1,0x800A
0x800934D0  lw    v1,-0x469C(v1)     ; v1 = *(0x8009B964)   -- read live: 0x1F801040
0x800934D8  lhu   v0,0x4(v1)         ; SIO0 STAT (0x1F801044) -- read live: 0x0101
0x800934E0  andi  v0,v0,0x0002       ; "receive data available"
0x800934E4  beq   v0,zero,0x800934D8  ; loop until it is set
```

`0x1F801040`/`0x1F801044` are **SIO0 DATA/STAT** (`runtime/psx/io_peripherals.cpp:12`,
`kSio0Lo = 0x1F801040`), so `FUN_80093478` is the title's per-VBlank controller-port read. The
framework's `Sio0::status()` answers `0x0101` — bit 1 is never set, so the loop never exits.
`runtime/psx/pad_input.cpp` already documents this exact poll and states that the runtime "never
satisfies" it; the difference for this title is that its guest body has **no timeout escape** (the
loop is unconditional), so it does not bail.

Because the spin is inside the interrupt, it pins `Hle::in_irq` for the rest of the run. That is the
single mechanism behind every symptom above: no further interrupt is delivered, and the CD edge is
never latched, so a CD command that *is* issued can never complete.

## Ownership: a title pad-port override, not a CD command

`FUN_80093478` is a function **entry** in the authenticated resident text (`0x80010000..0x80131000`),
reached by `jal` from four sites (`0x800941C8`, `0x800941E0`, `0x800942A0`, `0x8009432C`), so it is a
legitimate image-scoped override target for this title — unlike the port `pad_input.cpp` documents,
where `FUN_80003A4C` lives in a low-text image that is never loaded and so cannot be overridden.
`Pad::overridesInit()` here only calls `init()`; it installs no override.

The proper fix is a title-owned native override of `FUN_80093478` that performs the exchange natively
— write the standard digital pad packet into the slot buffer the caller passes instead of bit-banging
SIO0 — installed through the same `tekken3::guest::install` path as the six CD overrides, with a
contract test that installs it with no HLE plan in existence. It is NOT implemented in this session:
a pad override that produces a wrong packet would silently feed wrong input, which is worse than the
visible stall, and there was no room left to build and verify it against the product.

## DMA: this title does not chain its CDROM transfer

Measured from the executable, not inferred. `FUN_80084838` is the sector fetch and programs DMA3
directly: `*(0x1F8010F0) |= 0x8000` (DPCR3 enable), `*(0x1F8010B0) = dest` (MADR3),
`*(0x1F8010B4) = count | 0x10000` (BCR3), `*(0x1F801014) = 0x11000000` (CHCR3 start). BCR bits 0-1
are the sync mode, and `0x10000` sets bit 16, **not** bits 0-1. The caller is `FUN_8006C2A0` ->
`FUN_80090AA8(dest, 0x800 >> 2)`, so the count is `0x200` and `BCR3 = 0x10200`, giving
`0x10200 & 3 == 0` — **manual/block mode**. Tekken 3 chains no DMA transfer, so the psxport
`492adace` fix changed nothing for this title. `tools/probe_dma_sync_mode.py` reports the 12 DMA
register literals it found and says plainly that they are descriptor-table addresses, not BCR values;
the value itself had to be read from the instruction that writes it.

## Instrument note: two wrong answers, and what caught them

`tools/probe_global_writers.py` is a constant-propagation sweep over the authenticated text. It was
wrong twice before it was right, and both times it answered confidently, so both are recorded:

1. It omitted the PS-X EXE's 0x800-byte header from the file offset. Every decoded instruction and
   every reported address was shifted, and it reported 0x8009B750 as having **18 stores** when the
   truth is 3. It now refuses to report anything unless it first reproduces two known instructions
   (`GROUND_TRUTH`), and the selftest asserts it does.
2. It could not see the `lui`/`addiu`/`sw` form, so it reported 0 for 0x8009B750 — and that zero was
   *believable*, because Ghidra's reference model independently reported zero references to the same
   address. Two instruments agreeing was not two facts: both missed the same form. `FUN_8008FBB4`
   reaches that address as `sll a0,a0,2` / `lui v0,0x800A` / `addu` / `lw v0,-18608(v0)`, so the
   byte-scaled-index form is now modelled.
3. Its first draft used 0x8009B750 as a **negative** control ("must find no store"). The
   disassembly disproved that — the three writers are real — so the control was false and the selftest
   correctly failed. A control that is simply false is worse than no control.

The confirmed writer census for the CD chain state word, each hand-checked in the disassembly:

| site | instruction | effect |
|---|---|---|
| `0x80090338` | `sw v1,0(v0)`, `v0 = 0x800A0000-0xB750`, `v1 = 1` | `0x8009B750 = 1` (ready) |
| `0x800908D8` | `sw v1,0(v0)`, `v0 = 0x800A0000-0xB750`, `v1 = 1` | `0x8009B750 = 1` (ready) |
| `0x8008FA54` | `sw v0,8(s0)`, `s0 = 0x800A0000-0x46B8`, `v0 = 2` | `0x8009B750 = 2` (in flight) |

which is exactly the 1 -> 2 transition `FUN_8008FB08` performs when it issues. No sweep-level
"wrong offset must disagree" control is claimed: one was tried and it produced identical counts,
because wrong bytes are mostly rejected by the decoder rather than producing different answers. The
guard that works is the pre-flight `GROUND_TRUTH` refusal, and that is what caught the real bug.

## The live control endpoint did not exist for this title

`PSXPORT_DEBUG_SERVER` was inert: `runPort` composes its own finite loop and never entered
`psxport_boot()`, which is the only caller of `dbg_server.start()` and `service()`. No listener, no
`guest` denominator, no way to read a guest word from a running product. `DbgServer::attach` is
documented as "the one call a title-owned spine needs before its loop" and is now called from
`game/core/tekken3_port.cpp`, with the per-frame `honourPause`/`service` pair in the same order the
framework's own spine uses. This is a title composition defect, not a framework one; it is also what
made every measurement in this section possible.

## Current boundary

The native/Lightrec product now completes its first title frame after resuming the mode call across
host fields; it has not reached the Namco or gameplay discriminator. An earlier bounded headless run of the
already linked Clang-built `build/ci/bin/tekken3_port` (SHA-256
`3e2259031b97f72208148a379450b4b4a952b6dae746f8ec55ed68b672ed0719`, build receipt
`psxport=8b2103294b68e082eef8fe64bb3e972da21bec09`) opened the authentic CHD, completed the
finite main prefix, initialized the 960x720 Vulkan sink, then aborted in the first
`FrameLoop::step` guest call: `budget-exhausted` at `0x80031C78` after 564,482 cycles. The cap was
1,200 frames, but zero frame ends completed; no `NAMCO PRESENTS` or loader-wait observation was
possible. The linked binary was not rebuilt while the shared framework was being edited.

Ghidra places `0x80031C78` in `FUN_80031BFC`, the title's LZ-style decompressor. The disassembly
at `0x80031C78..0x80031C90` copies a bounded back-reference run (`lbu` source, `sb` destination,
`slt` length, branch back). Five direct call sites use this decompressor: one static-resource
initializer (`FUN_800484F4`) and four image-loading wrappers (`FUN_8004C6FC`, `FUN_8004C7E4`,
`FUN_8004C91C`, `FUN_8004CA40`). That earlier error record did not identify which call site,
compressed input, or output position was active. The framework's `ExecutionBudget::currentTurn`
allows 33,868,800/60 cycles for each guest call while the title's `guest::call` requires a completed
return. Thus the current evidence cannot distinguish a legitimately long decompression from a
wrong input/loop state; raising the budget or treating the exit as a completed call would assume
the answer.

One new bounded shipping-product run used Clang-built `build/ci/bin/tekken3_port` (SHA-256
`66eecab8c9cff36c4c2c8cf96c5780489300dcd05038ce9a7aaa32822594ef02`, linked against
psxport `13806e8156376e8e1dd86c43b70a89b44c61598d`) with the authenticated executable and
CHD, one requested frame, headless Vulkan, no audio device, and no pacing. PID `85388` exited and
was confirmed absent. At the actual `guest::call` failure boundary, the title-local shipping
diagnostic reported the outer guest call `0x800B0708`, outer return `0x80028C9C`, and an exit inside
the decompressor at `0x80031C78` after 564,482 cycles. Its live `ra=0x8004CA9C` identifies the
`FUN_8004CA40` image-loading wrapper. Live `a0/source=0x800BC2D0`, `a1/destination=0x8012B223`,
`a3/back-reference=0x8012B21D`, and `t1/output-start=0x8012867C` all mapped to main RAM. The
output pointer was 11,175 bytes beyond its preserved start, with 883,076 mapped bytes remaining;
the active back-reference copy had completed `1/11` bytes and read six bytes behind its destination
within the format's 2,048-byte bound. The probe classified one of one sampled exits inside the
decompressor; its synthetic controls separately produced one reached, one unreached, one valid,
and one invalid-bound result through the same formatter. It cannot measure compressed-source
consumption because Lightrec exposes no decompressor-entry sample at this title-local boundary.

This proves mapped, bounded copy state at that instant, not the function's eventual return or a
correct compressed payload. The direct binary run omitted `PSXPORT_ASSET_DIR`, so the overlay
reported missing UI assets before this CPU stop; no presentation conclusion follows. The process
returned status `139`; the log shows the budget error followed by a watchdog signal-06 backtrace,
but no saved core for PID `85388` was found, so the cause of status `139` remains unproven. Zero
title frames completed.

The operator repeated the bounded retail run after pinning psxport `1d7701cc` and passing the
combined Clang gate. This run supplied the framework UI assets and kept normal pacing; it loaded
all four Rml assets, entered the first native-owned frame, and reported the same `0x80031C78`
budget exit after 564,482 cycles. The live output was again 11,175 bytes from its start, with a
`1/11` back-reference copy at distance six and mapped source/destination pointers. The process
again returned status `139` after the watchdog's signal-06 backtrace. No title frame completed;
the new run confirms the decompressor boundary under the current framework, not its eventual
progress or output correctness.

The authenticated `SLUS_004.02` text was re-imported at `0x80010000` from the provisioner-verified
SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` and queried
through Ghidra. This narrows one concrete loader wait but does **not** establish that the current
Lightrec product reached it. `FUN_80052A70` returns byte `0x800A069F`; its caller
`FUN_80052CC4` waits while the return is nonzero. `FUN_800529CC` starts the underlying loader:
`FUN_8006BF20` queues its asset extent, and `FUN_8006C084` sets the wait byte to `1` before
submitting command `0xA0` through `FUN_8008F08C` with request-mode argument `6` and callback
`FUN_8006C26C`. The current title CD overrides do not own that `FUN_8008F08C` command path.

> **SUPERSEDED — see "Measured correction" above.** "request-mode argument 6" is a jump-table index
> into the 25-entry chain template at `0x800387B0`, and the command path **is** owned: `FUN_8008F08C`
> only enqueues, and the record is executed by `FUN_8008E8B8` -> `FUN_8008FB08` -> `FUN_8008FCC0` ->
> `FUN_80083E4C`, which is the installed `kCdControl` override. The submission succeeds and the command
> is issued; it cannot complete because an SIO0 status poll inside the VBlank ISR never exits.

The callback chain distinguishes completion from error. `FUN_8006C26C` registers
`FUN_8006C2A0` with `FUN_80091F38` only on class `2`. `FUN_8006C2A0` consumes one 0x800-byte
sector on class `1`, decrements the outstanding byte count, advances the destination, and clears
`0x800A069F` after the last queued extent. Its class-`5` error branch records loader failure state
`9` and leaves the wait byte set. Ghidra's narrow disassembly confirms the byte set at
`0x8006C1A4` and the clear at `0x8006C410`. The code makes either a missing sector callback or a
class-`5` error a possible permanent wait; only live callback/result evidence can choose between
them and a different stalled title state.

The retired generated-source runner's last bounded real-CHD run completed 1,200 native fields and
emitted a 960x720 sink image. Field 1 was black while display state initialized; fields 119 and
1,199 showed the centered Namco card. The run reported no fatal, watchdog, guest VSync, or dropped
layer. This is historical presentation evidence, not evidence that the current native/Lightrec
product reached the card.

## Grounded preceding owners

- The retail entry reaches CD initialization. Getstat responses return `0x02`; retained boundary
  evidence records agreement on 34 CPU values, 38 distinct RAM bytes, and four CDC fields for the
  normal response path, including init step `0x16 -> 0x17`. That retired measurement is evidence,
  not a current product gate.
- Tekken's linked `CdSync` (`FUN_80083904`) and controller wrapper (`FUN_80083E4C`) preserve title
  validation, command/status globals, mirrors, and return ABI while delegating the hardware operation
  to psxport's synchronous stock-libcd owner.
- `FUN_80090F78` and `FUN_80091328` have one direct caller, `FUN_80091E5C`; the synchronous queue
  owner transfers the requested sectors before publishing success and never manufactures a clock or
  completion.
- `FUN_80090D88` routes blocking GetTN/GetTD through the synchronous controller and derives result
  bytes from the opened CHD's measured track metadata.
- GPU timeout armer `FUN_8007E8F0` and poller `FUN_8007E924` use `Game::timing.vblank` rather than
  guest VSync. A complete Ghidra xref census covers five armer callers and ten paired checks across
  GPU DMA, image transfer, command queue, and DrawSync.

Isolated PID `3216829` opened the real CHD, passed the synchronous directory and TOC paths, reached
ResetGraph, and exposed the GPU timeout clock at return PC `0x8007E900`. Its measured chain was:

```text
FUN_8007E8F0 <- FUN_8007E154 <- FUN_8007C528 <- FUN_800B07C8
  <- FUN_800B07A8 <- FUN_800B07A0 <- FUN_800B0794 <- FUN_800B0788 <- FUN_800B0548
```

The native timeout owner and the subsequent 1,200-field run crossed that boundary without weakening
the protected VSync trap. PID `3216829` exited and was confirmed absent.

## Ruled-out shortcuts

- Advancing a synthetic clock, raising the watchdog, or increasing the field cap would conceal the
  stalled state rather than complete the missing title transition.
- Publishing fabricated success before requested sectors are in guest RAM violates the synchronous
  read contract.
- Forcing CD state, kicking a queue manually, or bypassing callbacks would skip the lifecycle whose
  ownership is under investigation.
- The earlier inference that CD-system state had failed was too strong: a trace excluded ready state
  `1` at one sample but did not distinguish initializing state `2` from failed state `3`.

## Next discriminator

The first sampled image resource made 11,175 bytes of bounded output progress before the call's
single-turn budget expired. Ghidra decompiled both `FUN_8004CA40` and `FUN_80031BFC` (2/2 requested
functions) and disassembled 16/16 instructions in `0x8004CA70..0x8004CAB0`: the wrapper's current
eight-byte table entry is `s1`, its table base is `s3`, `lw a0,4(s1)` executes at `0x8004CA8C`,
and the `jal FUN_80031BFC` delay slot adds `s3` to form the compressed-source entry. `s5` supplies
the output start. At return address `0x8004CA9C`, the wrapper checks whether the returned output
length exceeds `0x8240` (33,344 bytes). This is a maximum, not an exact resource length. The
decompressor stops at a zero control byte, so exact encoded output length depends on the live
source bytes. No saved log contains `s3`/`s1`, and no numerical source entry or encoded extent can
be claimed from the previous runs.

The title-local shipping exit probe now checks the live reached-wrapper register/table invariants,
reconstructs the source entry, and scans only mapped RAM through the zero control byte, bounded by
the wrapper's output limit read from its actual guest instruction. It reports a source-consumed
denominator and encoded output extent only if the scan terminates, cursor/output progress fits, and
source/output spans do not overlap. Missing reach, invalid table/instruction, truncated input, and
unterminated input report their negative result and scanned count; focused synthetic controls pass.
An authenticated headless, silent retail run after the 11/11 Clang gate reached the wrapper at
`0x8004CA9C`: table base `0x800B8D58`, entry index 2/127, encoded source
`0x800BAFCC`, and destination `0x8012867C`. The bounded scan found the zero terminator after
7,772 source bytes and described 21,524 output bytes under the wrapper's 33,344-byte cap.
At the typed `BudgetExhausted` exit at `0x80031C78` (564,482 cycles), the guest had consumed
4,868/7,772 source bytes and produced 11,175/21,524 output bytes. The scan reported
`complete consistent=1`; no frame had completed. The watchdog's signal backtrace follows the
intentional failed-call abort, so the product still does not boot. This is evidence of remaining
finite encoded input, not proof that Lightrec's output or guest state agrees with an independent
CPU oracle.

A test-only call mapped the same authenticated SHA-256-matched EXE into the shipping Lightrec
executor and entered original `FUN_80031BFC` directly, with source `0x800BAFCC`, destination
`0x8012867C`, return `0x8004CA9C`, and the unchanged `564,480`-cycle current-turn budget. The call
returned to that wrapper address after 442,550 cycles, with `v0=21,524`, source cursor at the
7,772-byte terminator, 31,688 executed Lightrec blocks, and zero interpreter fallbacks. All 21,524
output bytes matched a separately implemented bounded LZ decoder of the authenticated stream
(SHA-256 `7da9ab4738ec5455d66856f6f4ae549b122fdaddc0d7b3f627ce56a436d09766`). A one-cycle
negative arm reached one translated block and exited `budget-exhausted` after 12 guest cycles with
zero output and zero fallback, demonstrating that the test distinguishes return from budget stop.
The child process exited 0; its transcript is gitignored under
`scratch/diagnostics/decompressor-lightrec.stdout`. This proves isolated decompression fits a fresh
turn and produces the decoded bytes; it does not prove the outer first-frame call or complete guest
state matches an independent CPU oracle. That earlier first-frame call exhausted its cumulative
turn budget inside this decompressor.

Ghidra's authenticated `FUN_800B0708` mode-0 body calls `FUN_8004CA40`, whose table count at the
reached wrapper was 127. The wrapper synchronously decompresses each eight-byte resource entry and
processes its image before advancing to the next. The independently checked third resource uses 442,550
cycles when called fresh; the cumulative outer call therefore cannot be required to return within
one 564,480-cycle field allowance. The title's previous `guest::call` treated a typed
`BudgetExhausted` as failure. The frame-mode call now retains its original outer return boundary and
the guest register/memory state, resumes Lightrec at the exact stopped PC with the same per-field
budget, and presents/services audio and pad once on each held field. It does not repeat the guest
barrier, increment the guest frame counter, or run the frame tail until `GuestReturn`.

The Clang-built shipping binary (SHA-256
`8ffdd62e1538c4cfacc8baa5366a5825138af29ae90f86ac9f0fa5cc68846645`, psxport
`ff3709e74b24d21de4f3dcdcd402de8c33d57df7`) ran the authenticated executable and CHD headless,
silent, and unpaced with a seven-field cap. Exact PID `751763` exited 0. Its first mode call
`0x800B0708` stopped at `0x80031C78` after 564,482 cycles with live nested
`ra=0x8004CA9C`, while the saved outer return stayed `0x80028C9C`. It returned to the saved
outer boundary after six suspended fields, and the product reported seven completed host fields
and 360,083 executed Lightrec blocks / 2,235,207 instructions with zero fallback blocks or
instructions. The headless run establishes a completed first frame and bounded guest-call return;
it does not establish a visually correct card, loader callback, independent whole-frame CPU parity,
or gameplay. A focused synthetic nested-call test distinguished suspended and single-field returns
from a deliberately wrong outer boundary (`v0=107` versus early `v0=100`), with zero fallback.

After the native/Lightrec product reaches the Namco-to-menu boundary, the next title-loader check is
the measured loader state below. Its binary ownership is established, but its live reachability is
still unknown:

Capture `0x800AE204` (mode), `0x800AE224` (phase), loader wait `0x800A069F`, outstanding bytes
`0x800A06A4`, destination `0x800A06A8`, raw-command queue count `0x800A3E40`, callback pointer
`0x8009B8D0`, callback class, and final loader state `0x800A05D8` across the card-to-menu boundary
in an independent retail run and the native/Lightrec product. Report both reached and not-reached
answers for `FUN_8006C26C` and `FUN_8006C2A0`, including request and callback denominators.
Implement only the first measured missing owner, then rerun the same bounded boundary; do not add a
delay, phase write, or scene-pointer shortcut.
