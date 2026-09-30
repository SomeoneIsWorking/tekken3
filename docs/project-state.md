# Tekken 3 project state

This is the factual capability inventory. Epic intent lives in `docs/project-goals.md`, atomic work
in `docs/issues/`, ownership and placement in `docs/codemap.md`, and ordered reverse-engineering
dependencies in `docs/re-frontier.md`.

| ID | Capability / observable outcome | State | Dependencies | Goals |
|---|---|---|---|---|
| S001 | The selected USA disc executable is reproducibly identified and provisioned | verified | — | G001, G003 |
| S002 | Retail entry and direct-main startup execute deterministically to an independent boundary | verified | S001 | G001, G003 |
| S003 | The authenticated executable runs through the native/Lightrec gameplay product | partial | S001, S002 | G001, G003 |
| S004 | Boot and CD initialization are compared across independent or distinct execution engines | partial | S002 | G001, G003 |
| S005 | The title declares a non-temporal, guest-rendered widescreen capability contract | partial | S003 | G002 |
| S006 | Tekken-owned projection, display, visibility, and clipping state is identified for widescreen | partial | S001 | G002 |
| S007 | True widescreen renders additional correctly projected content | missing | S004, S005, S006 | G002 |
| S008 | Product frames, input, audio, and gameplay execute correctly | partial | S003, S004 | G001 |
| S009 | The default launcher delivers the playable widescreen product | missing | S007, S008 | G001, G002, G003 |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | S003 | G001, G003 |
| S011 | Tekken 3: load operations complete without loading-only waits or presentation; logos cancel through the recovered route | missing | S003 | G004 |

## Current focus

S003 is the current focus, and **its blocker is the CD completion lifecycle, not the controller
port** — issue 0019's refutation was wrong on both counts and is superseded by issue 0020.

**MEASURED 2026-09-29, live, over the loopback control channel, in one disc-backed process.**
Issue 0019 held that `0x800A069F` has 0 materialised readers and that nothing reads the
sector-callback slot `0x8009B8D0`. Decoded from the authenticated executable with
`tools/census_word.py`, over **295,936 walked words**: `0x800A069F` has **4 readers and 5 writers**,
and `0x8009B8D0` has **6 readers and 1 writer**. The dispatch is real: `0x80092110 lw $a3,8($s1)`
loads the slot into `$a3` and `0x8009213C jalr $a3` calls it. The sweep that produced the zeros
propagated `lui`/`addiu` only within a single register, and this image builds every global the way a
MIPS compiler does — `lui $v0` then `addiu $s0,$v0,imm`, built in one register and consumed in
another — so it reported 0 for essentially every global in the image. This is the **tenth dead tap**
in this workspace, and the first produced by a census rather than a counter.

**The full causal chain is recovered into readable C++** (`game/core/loader_lifecycle.h`, pinned by
`tests/loader_lifecycle_contract.cpp` at **15 of 15** recovered instructions matching the image
words, with a mutant-proven control in both directions): the guest sets `0x800A069F` and registers
`0x8006C26C` in the same breath at `0x8006C1A4`, the class-2 chain completion installs the sector
callback into the record at `0x8009B8D0` via `0x80091F38`, the per-sector handler dispatches it at
`0x8009213C`, and **the only writer that clears `0x800A069F` is `0x8006C2EC`, inside that callback.**

**What a live run now shows, and this is the new information.** In one disc-backed process over the
control channel, read at **1,054,867 presented frames** — 42x deeper than the 25,030 of any prior
run — mode **2**, phase **8**, `0x800A069F` = **1** (never cleared), `0x800A069E` =
**0**, `0x8009B8D0` = **`0x8006C2A0`** (the sector callback IS installed), `0x8009B8E8` = **1**
(registered), `0x8009B8C8` = `0xFFFFFFFF`, across 3 consecutive samples unchanged. Guest execution
at the same point: **4,167,259,337** executed instructions in 697,286,435 blocks from 1,956
translated, `faults=0`, `fallback: calls=0`, `budget_exit: exits=6`.

**So both hops are armed and the byte is still up — which is a genuinely new position.** Issue 0018
recorded hop 2 as "never armed"; it is armed. And because `0x800A069E` is **0** while `0x800A069F`
is **1**, the guest is **not** sitting in `FUN_8006BEA8`'s inner spin, because that loop exits on
`0x800A069E` and clears the byte on its way out (`0x8006BEFC`). **The blocker is therefore no longer
the CD chain and is not yet named**; identifying where the guest actually is, is the next step and is
recorded as the frontier in issue 0020. The sector callback being installed but never dispatched
remains one candidate, and the specific question is what invokes `0x80092034` at all.

**What has NOT changed:** no fight is reached, S003 stays `partial`, and S007 (widescreen showing
real scene content) is untouched — the only picture is still the authored 4:3 NAMCO PRESENTS card.

**The gate is 30 tests with 2 red, and BOTH reds are known and owned, not skipped.** `build` is a
configured tree and `ctest --test-dir build -N` reports **30**, so this is a real gate and not the
ninth dead tap this workspace has already hit on an unconfigured directory.

| test | state | why |
|---|---|---|
| `tekken3_psxport_pin_live` | red | **the pin is not bumped, and the required order is genuinely blocked — one level lower than before.** `psxport` itself is now **clean** at `c777c320`, so this is no longer "another agent's uncommitted files". The reconfigure fails in `psxport/cmake/lightrec_dependency.cmake:71`, which refuses because **`shared/lightrec` has worktree changes** — and the modified file is `blockcache.c`, which is exactly the file issue 0050 says must change to revoke a block on an interior-word write. **The psxport owner is mid-repair.** psxport pins `shared/lightrec` to `e1a6a09` and requires that exact clean revision, so `reconfigure -> build -> test -> bump` cannot complete until that commit lands. The guard is working; the pin stays at `7981f596` |
| `tekken3_mode_call_budget_resume` | **now green** | was red for **six** separate reasons, all in its own synthetic body — five field-level hand-assembly errors and a missing MIPS load delay slot. See issue 0021 |
| `tekken3_frame_loop_contract` | **now green** | asserted the old `boundedStarts == 0` contract; updated to the new one, and its own pass message already claimed "3-field bounded continuation" — it was written for this behaviour and only the count was stale |

**A caveat that has to be stated rather than hidden:** the blocked reconfigure left `build/` unable
to **regenerate** — `make` now fails at `cmake_check_build_system`, while `ctest` still runs and
reports **30 tests, 29 passing**. The binaries are from the last successful build against
`d74e7f63`. **That is a stale build tree, not a green one.** The next agent should reconfigure once
`shared/lightrec` is committed rather than trusting `ctest` alone, which is the
`ctest`-on-an-unconfigured-tree trap this workspace has already paid for once.

**The frame-loop change itself is correct and kept**: routing every mode body through `BoundedCall`
is required because mode 2's loader legitimately outlives a display field and the non-suspending
entry aborts on `budget-exhausted`. `tekken3_frame_loop_contract` and `tekken3_mode_call_budget_resume`'s
own `arm=control` both still show the two entries behaving differently, so they remain distinct.

**Every product depth figure in this file was last taken on a framework that is logging a guest fault it should not, and that bounds how far it can be trusted.** A post-hop-1 run logs ~25,000 `[executor:error] guest transferred control to 0x000000A0/0xB0/0xC0` lines where an earlier run on an older framework logged **0**. A one-variable discriminator settles the attribution: pre-fix `game/core/cd_sync.{h,cpp}` from `c93d0b1^` rebuilt against the **current** framework still logs 23,543 of the same errors, so it is a **framework** regression and not a consequence of the CD completion work; psxport's own newest commit `77c13f0c` ("Name the block behind a wild control transfer, and never go silent on the fatal one") is already on it. Recorded in issue 0018 so the number is not re-read as a `c93d0b1` regression.

**The framework clock fix landed, and it was not the blocker (issue 0018).** psxport `5d4b3327`
charges the guest clock inside a translated segment. Measured by `tools/verify_pad_wait_exit.py`
against the same image and the same four arms, the `retail` arm goes from **564,492 cycles exhausted
in the wait loop** to **`returned=1` in 6,526 cycles**, in the same single segment, with the `bit7`
control unmoved at 186 cycles. The product then reaches **25,030 presented fields and 1,442,602,195
executed guest instructions with 0 faults and 0 interpreter fallbacks** — 3.6x the depth issue 0016
recorded — and the card is still up. The `segmented` mutant is now byte-identical to `retail`,
which is the tool correctly reporting that a spent mutant is no longer a control, so it **refuses**
rather than passing.

**The card's wait is not a wait for a clock (issue 0016, 0017, 0018).** It is **mode 2, phase 8**, a
wait on the byte at `0x800A069F` that redraws the card every frame it holds, and the only writer of
that byte to zero on this path is `0x8006C2EC`, inside the guest's own sector callback
`FUN_8007C2A0`. That callback is installed by `FUN_8006C26C`'s class-2 branch, which is the
completion callback `FUN_8008F08C` was handed. **Measured from the live capture: that callback value
`0x8006C26C` is present at exactly one address in the whole 2 MB, `0x800A3DD0`, and the sector
callback `0x8007C2A0` is present at 0 of 524,288 words.** The callback is in guest RAM, unread.

**The owner is this repository's `game/core/cd_sync.cpp`.** Its `kCdControl` (`0x80083E4C`) and
`kCdQueueStart` (`0x80090F78`) overrides complete each CD operation inline and never invoke the
callback the caller registered. Retail's bodies issue the command and return; the completion arrives
on the controller's interrupt, and that is the only thing that ever calls `FUN_8006C26C`. The
framework states that it does not model this — `cd_override.cpp` line 3, "we do NOT model the CD
controller or deliver CD IRQs" — and its own mechanism for it, `cd_drive_stock_read` ("it needs to
call the callback the game already registered"), returns at its first line here because
`cd_ready_callback_pointer()` is 0: this is a direct runtime, so `core.cfg` is null, and
`guestCdStreamCallbackLayout()` is not overridden. In a 1,200-field run with the framework's own
CD/CDC/IRQ trace, **4,458 of 4,458** interrupt deliveries carried `I_STAT&I_MASK=0x001` — VBlank —
and **0** carried the CD bit, with `I_MASK` bit 2 set.

**The mode-3 recovery is built, gated, and waiting on that completion (issue 0018 §4).**

**The completion itself is now OWNED, gated, AND MEASURED IN THE PRODUCT — and the card is still up, for a different reason.** `CdProtocol::deliverCompletions` (`game/core/cd_sync.{h,cpp}`) enters the guest's own CD-event routine `0x8008E928` with `$a0 = 2` and the interrupted return address, after each completed `cdControl` / `cdCommand` / `cdQueueStart`. It is bounded twice by the GUEST's own words rather than a host constant — the pool depth the guest's initialiser publishes at `0x8008EC74` (`slti $v0,$s1,8`, eight records at stride 24) and the live-record count at `0x800A3E40`, bounded the same way at `0x8008EEA8` — and it stops the moment a delivery leaves the ring cursor `0x800A3E3C` unchanged, which is the guest's own "I consumed a record" signal. **`tests/cd_protocol_contract.cpp` covers it with four negatives** (an empty chain, a live count above the depth, a cursor outside the pool, and a guest that consumes nothing) and each refusal was shown to turn the test red by mutating the implementation, so the refusals are measured rather than asserted.

**In one disc-backed run of 10,448 fields the guest consumed all four records it ever queued** — the chain cursor reached 4 and the live count 0, and both held while the CD completion count kept climbing `0x62` → `0xF7` — so the owner fires and the ring drains. **The card does not leave anyway, and not because the pad is silent.** `PSXPORT_DEBUG=sio` over 3,000 fields gives 78,669 `[sio]` lines: the digital pad's ID `0x41` is read **3,279** times, its `0x5A` payload **3,276** times, and `/ACK -> JOY_STAT#9` is raised on every exchange because the guest does set CTRL bit 12 — so "the card waits for an ACK that never comes" is refuted by the framework's own channel. What each cycle ends on is `CTRL = 0x3003` then a `0x01` byte answered `no-ack` with `pos -1`; `Sio0::ctrlWrite` cancels the exchange whenever CTRL bits `0x2002` change, and bit 13 is inside that mask. `tools/tekken3_sio_poll_census.py` re-derives the instruction facts from the authenticated image and **corrected an earlier disassembly that named the wrong address, the wrong load width and the wrong bit**; issue 0019 keeps that correction, and keeps the refuted pad hypothesis, because a refuted hypothesis that is not written down gets re-derived.

`tools/recover_runtime_handlers.py` recovers the 11 window handlers through three independent routes
with a control that can fail: the in-disc control scores **9 of 9** byte-identical against the
capture, and at all 11 window handlers the capture differs from the authenticated image in **0 of
256** words each. `0x800C0000-0x80131000` is 96.91% non-zero and it is **data** — 0 prologues and 0
`jr $ra` in 115,712 words against 1,663 and 1,499 (1.02% / 0.915%) in the in-disc reference. All
**127 of 127** mode-0 payloads decode offline from the disc and **0 of 127** contain code. So the
mode-0 loader ran to completion and wrote 5,821 words of PSX1 vertex data to the staging buffer, and
the code images are in **1 of 7** placement sites in this text, not in the one mode 0 uses.

After the completion is owned, the first discriminator is the native/Lightrec product leaving mode 2
phase 8 — `0x800A069F` falling to 0 with `0x8009B8E8` nonzero, then `0x800AE204` leaving 2 — within
1,200 frames while executing nonzero Lightrec blocks and routing all 14 address-based original calls
through the shipping dispatcher. Product inspection must prove that Lightrec remains the default and
no interpreter gameplay selector exists; runtime evidence must report every bounded JIT-refusal
fallback and satisfy its release threshold. That checkpoint is followed by a representative
interactive gameplay run.

## Hosted verification and host gaps

Linux x86_64 is the only currently supported host product boundary. The tracked GitHub Actions job
uses full history, disables persisted credentials and caches, installs pinned Python tooling, builds
the actual asset-free `tekken3_port`, runs every asset-free title contract plus clang-format and
clang-tidy, and inspects the linked execution boundary. The consumer pins PSXPort
`eb5f23a8b3506f8853b3cfadcedc024cd90818a0`; CI checks out Lightrec
`b1457137c31cedff5f440d59da29401d021ba2da`. It contains no disc, executable, BIOS, or runtime
translation cache and therefore claims no gameplay evidence. The same canonical Python gate passes
locally and in the hosted run recorded in S010.

Windows x86_64 is an applicable future PC host but currently unsupported: psxport still exports GNU
linker `--wrap` options and has no MSVC/clang-cl product contract. macOS arm64 is likewise unsupported
while that GNU linker contract remains and no AppleClang package/runtime gate exists. Android arm64
is unsupported because this title has no Activity/JNI/package owner and does not yet consume the
shared Android build contract. Successful no-op jobs for those platforms would be false evidence, so
they remain explicit gaps rather than green matrix entries.

## Capability details

### S001 — selected executable identity and provisioning

Evidence: C001/C002 and I001/I002 record the USA `SLUS_004.02` path, full-file identity, PS-X EXE
header, disc extent, extraction route, controlled disagreement cases, and a verified real extraction.
`titles/tekken3/executable.json` is the measured authority and `tools/provision_executable.py` keeps
all extracted bytes under gitignored `scratch/`.

### S002 — deterministic retail startup boundary

Evidence: C003/C004 and I003/I004 establish the direct `entry -> game_main` structure from executable
bytes and Ghidra, then compare psxport and an independent Mednafen CPU at the call boundary. Both
engines are deterministic and agree on 35/35 CPU fields; forced disagreement and too-short execution
are refused.

### S003 — native/Lightrec gameplay product

Evidence: player composition installs `Tekken3Runtime`, loads the identity-checked executable as
runtime data, binds framework devices, installs image-and-address-keyed native overrides, and
dispatches the retail entry through psxport's per-Core Lightrec executor. The title resumes its
first synchronous 127-resource mode call over bounded host fields without changing the field budget.
An authenticated, headless seven-field run (issue 0011, PID `751763`, exit 0) reached the outer guest
return after six suspensions, completed the first frame, and reported 360,083 executed blocks,
2,235,207 executed instructions, and zero fallback. A synthetic nested-call control verifies the
original outer return address survives a changed live `r31`.

**Issue 0018 supersedes the depth figure and the blocker attribution.** Against psxport `5d4b3327`
the product now runs **25,030 presented fields** and reports `executed_blocks=241373778
executed_instructions=1442602195 translated_blocks=1917 host_dispatches=126867 cache_misses=1920
faults=0` with `fallback: calls=0 instructions=0 refused_calls=0 compilation_failed=0
self_modifying_code=0 unsupported_block=0 load_delay_hazard=0 unsafe_instruction_fetch=0` — the JIT is
the gameplay default and is not silently degrading, which is the release threshold issue 0011 asked
for. The pad wait loop that issue 0017 measured as budget-exhausted now returns in 6,526 cycles
through the same single segment, with its `bit7` control unmoved at 186.

Gap: the product still has not reached the menu, or representative gameplay, and **the blocker is
this title's own CD ownership rather than a framework gap.** Issue 0016 locates the product exactly:
inside mode 2 phase 8, the CD-read wait, which leaves only when the guest's own sector callback
`FUN_8007C2A0` clears `0x800A069F`, with no input on the path. Issue 0017 cleared the pad loop and
ruled out a `FUN_80093478` override. Issue 0018 then names the remaining cause to the instruction:
`FUN_8006C26C` is the completion callback `FUN_8008F08C` was handed, its value sits at exactly one
address in the whole 2 MB capture (`0x800A3DD0`) and has never been called, the sector callback it
would install is at 0 of 524,288 words, and the trace shows 0 of 4,458 interrupt deliveries carrying
the CD bit. `game/core/cd_sync.cpp`'s `kCdControl` and `kCdQueueStart` overrides complete each
operation inline and never invoke the registered callback, so the lifecycle the guest's driver is
built around is gone by construction. Historical product evidence remains useful only as the
measured native/device frontier because it predates this executor: the isolated `3c342ec3` product PID
`3216829` dispatched the retail entry, opened the real CHD, and passed the synchronous directory-read
and GetTN/GetTD owners. It then reached ResetGraph and trapped the next protected guest VSync query in
linked GPU timeout armer `FUN_8007E8F0`. Its exact PID exited and is confirmed gone. The resulting
native-ledger GPU arm/poll owner is combined-gate green but not yet product-verified. The next
product evidence must show `0x800A069F` falling with `0x8009B8E8` nonzero, then `0x800AE204`
leaving 2.

The title now also has a working live control channel. `runPort` composes its own finite loop and never
entered `psxport_boot()` — the only caller of `DbgServer::start`/`service` — so `PSXPORT_DEBUG_SERVER`
bound nothing and no guest word could be read from a running product. `game/core/tekken3_port.cpp` now
calls `DbgServer::attach` before choosing the cap and services the endpoint once per frame, in the
framework's own order. Measured: `[dbgsrv] listening on 127.0.0.1:5959`, and `r`/`rw`/`guest` all answer
against a live run (`scratch/probe_logs/cdcomp4.probe.txt`).

### S004 — differential boot and CD initialization

Historical psxport-interpreter and independent-Mednafen runs agreed on 35/35 CPU fields at the
entry-to-main boundary. Those observations remain useful measurements, but the interpreter probe and
retired execution harness are deleted and are not current verification paths.

Gap: The independent CPU now continues through DPCR and the measured context-save path, but cannot yet
execute B(19) HookEntryInt and return for another two-engine comparison. Whole-product execution now
passes CD/TOC initialization with no guest VSync call and reaches ResetGraph. Issue 0011 records the
exact GPU timeout-arm chain and the combined-gate-green native field/poll owner for
`FUN_8007E8F0/FUN_8007E924`. The newer Lightrec run covers one frame, but no gameplay.

### S005 — title render-capability contract

`Tekken3Runtime::renderCapabilities()` returns the shared `widescreenOnly()` policy. The runtime seam
checks GTE as the only player-selectable path, PSX as a supported diagnostic path, Native as
unsupported, and temporal interpolation as unsupported.

Evidence: The historical shared capability implementation was recorded at `psxport.pin` `fb08d30f`. The exact
Clang gate passes CTest 17/17, clang-tidy 19/19, and the 13/13 capability seam. A bounded product run
also rejected a persisted `native` selection as unsupported and resolved it to GTE.

Gap: The new headless product run completed a first present, but the absence of Native and 60fps
Interpolation rows is verified only at the source contract and not visually in the actual menu.

### S006 — measured widescreen owners

C012/I007 and `tools/verify_projection.py` identify the complete six-writer CR24/CR25/CR26 census,
the view-dimension and projection-centre chain, focal-length owner, both display presets, stage
visibility angles, and rendering-path right-edge comparisons on the hashed executable.

Framework commit `2e840231` now decodes Tekken's GP1 368-pixel mode generically. The title's
`Tekken3Widescreen` owner binds the measured 384x480-view/368-draw and 320x240/320 facts to the shared
projection plan, then uses the same resolved guest draw width for the stage/effect primitive
clippers while retaining their original 4:3 guest bodies. The hermetic contract proves the wide
384->512 projection and x=400/450 added-margin cases.

Gap: These owners have not been driven in a completed gameplay frame or A/B-tested against a faithful
4:3 image. A historical runner presented the title-loader card; the current Lightrec run completed
one frame without image inspection. The stage-tile visibility wedge is no longer
measurement-dependent: the derived `theta' = atan(k tan theta)` domain is verified 6912/6912
bit-identical against the real guest selector, 600 -> 762 at 16:9, with the horizontal culling set
closed at a denominator (295,936 instructions scanned, culling owners asserted as exactly 12 right-edge
comparisons plus the 2 authored wedge angles). What is missing is a **product** observation, not the
derivation: no real wide frame has yet exercised the seven widened cull owners or the wedge.

### S007 — true widescreen output

Missing capability: no completed Tekken frame has demonstrated wider guest geometry, stage/effect
coverage, and final presentation while preserving vertical framing and the faithful 4:3 control.

Blocked behind S003, and the blocker is now named down to the instruction and attributed to its
**owner, which changed**: the guest cannot leave the card because the card **is** mode 2 phase 8, a
wait on the byte at `0x800A069F` that the guest's own sector callback `FUN_8007C2A0` would clear, and
that callback is installed by the completion callback `FUN_8006C26C`, which nothing ever calls
(issues 0016, 0017 and **0018**). Issue 0017 attributed the stall one level down to the framework's
guest clock; issue 0018 measures that fix working and **clears it** — the pad loop returns in 6,526
cycles through one segment, and the product now reaches 25,030 fields — leaving the CD completion,
whose owner is **this title's** `game/core/cd_sync.cpp`, whose `kCdControl` and `kCdQueueStart`
overrides complete each operation inline and never invoke the callback the caller registered.
`tools/recover_runtime_handlers.py` adds the second half: the 11 window handlers are **not** code at
this frontier (0 of 11, 0 of 256 words differing from the disc at each, against 9 of 9 in-disc
handlers byte-identical), so the frame to widen does not exist yet for a third, independent reason.
Until the completion is owned there is no gameplay frame to widen, and the widened owners and the
stage wedge still have no product observation of any kind. `widescreen_pair.py` was therefore **not
run** on anything new: it would only have been handed two views of the same `NAMCO PRESENTS` card,
whose glyphs sit on a flat black field, and the tool correctly refuses that pair (its own `seams()`
docstring records that refusal on this title's card). Re-shooting until it passes would be
manufacturing evidence.

### S008 — frames, input, audio, and gameplay

Evidence: the bounded headless product run completed seven host fields and one title frame, including
per-field presentation/audio/pad service during the suspended guest call (issue 0011). Issue 0018 adds
depth rather than capability: 25,030 presented fields with per-field present, audio and pad service,
`faults=0` and zero interpreter fallbacks, and a captured 368x480 PPM at field 24,782.

Gap: the resulting image is still the `NAMCO PRESENTS` card, verified gameplay input, title audio,
and sustained gameplay remain absent, and **no pad-driven frame exists** — the loopback endpoint's
`press`/`tap`/`hold` commands were not exercised, because the card's phase 12 reads no controller port
over 294 instructions (issue 0016), so a pad route would be compensating for nothing. Input evidence
is only obtainable past the CD completion, not before it.

### S009 — default playable widescreen product

Missing capability: `./run.sh` builds and launches the intended product, but that product does not yet
satisfy the observable frame, gameplay, or widescreen conditions of S007 and S008. Launcher and direct
product `-h/--help` contracts both exit zero before dependency, runtime, or disc discovery.

### S010 — asset-free hosted verification

The Linux workflow and `tools/verify.py` own one reproducible asset-free gate over the shipping
product boundary, title contracts, formatting, lint, and linked execution policy.
Evidence: the Linux x86_64 asset-free product composition gate passed on main commit
`3afb4cf0fa167cf197dd6056cf00d5cfaeaa63d1` in
[run 33960101763](https://github.com/SomeoneIsWorking/tekken3/actions/runs/33960101763).
This verifies composition only; gameplay and unsupported host gaps remain as recorded above.

### S011 — Tekken 3 loading removal

Missing. No load operation has been censused or classified for Tekken 3. Gap: enumerate its load
issuers and the wait and presentation each drives, then complete each through the title's own load
mechanics without its loading-only wait, with payload and terminal state compared against retail
and the absence of loading presentation captured.
