# Tekken 3 RE frontier

Statuses: `re-verified` means binary/disc ground truth plus executable verification; `re-partial`
names an honest remaining gap; `todo` is not started. No hacks are tracked.

## Boot spine

### T3-01 — Select and measure the target executable
- status: re-verified
- deps:
- evidence: C001/I001. The USA disc's `SYSTEM.CNF` names `cdrom:\TEKKEN3\SLUS_004.02;1`; `discdump list` reports that nested file at LBA 25 with 1,185,792 bytes. A fresh extraction has SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c`. The Clang-built shipping `crt0_extract` reports PS-X EXE entry `0x80079C70`, load `0x80010000`, text size `0x121000`, extent `[0x80010000,0x80131000)`, and eight resolved structural startup fields. Ghidra independently decompiled the entry and first JAL target; a narrow post-decompile disassembly confirms `jal 0x80028BA0` at `0x80079D04` with a `nop` delay slot. The target is the non-returning game main loop, not libcInit.
- where: `titles/tekken3/README.md`; untracked extraction and Ghidra project under `scratch/`
- gap: None for executable identity and the measured entry boundary. This does not prove a generated substrate or a booting port. Framework issue #2 records why the decoder's generic `libcInit` label is not semantic evidence here.
- notes: All disc-derived files remain gitignored. The target hash is over the complete 0x121800-byte PS-X EXE, including its 0x800-byte header.

### T3-02 — Provision the selected disc and executable reproducibly
- status: todo
- deps: T3-01
- evidence: Not started.
- where: future project-local provisioning tool; gitignored `.env` or root drop-in input
- gap: Implement CLI argument > `PSXPORT_TEKKEN3_DISC` > `.env` > root-drop-in resolution, extract `TEKKEN3/SLUS_004.02` to `scratch/`, and verify its SHA-256 before any recompilation.

### T3-03 — Bring up a deterministic psxport/oracle boot harness
- status: todo
- deps: T3-02
- evidence: Not started; `tekken3_scaffold` only links `psxport_smoke` and runs no Tekken 3 code.
- where: future `game/core/`, generated substrate, and project-owned gate
- gap: Build the first game seam and oracle driver, model the direct-to-main startup shape rather than assuming the first JAL is InitHeap, then prove the harness reports both an intentional agreement and an intentional disagreement on permanent fixtures.

### T3-04 — Recompile through the first real divergence
- status: todo
- deps: T3-03
- evidence: Not started.
- where: future `generated/`, `game/recomp_seeds.json`, and divergence logs
- gap: Recompile from the measured entry and advance only as far as executable evidence supports; never borrow another game's seeds or guess an overlay base.

## Native ownership and enhancements

### T3-05 — Identify camera state and graphics submitters
- status: todo
- deps: T3-04
- evidence: Not started.
- where: future Ghidra project and readable native ownership under `game/`
- gap: Decompile the game code that submits camera/transforms/geometry before creating any native producer. OT, GP0, and GTE output are diagnostic evidence, never producer input.

### T3-06 — Native widescreen
- status: todo
- deps: T3-05
- evidence: Not started.
- where: future native camera and render producers
- gap: Enable only after the PC owns the relevant camera/projection and display-list producers.

### T3-07 — Transform interpolation
- status: todo
- deps: T3-05
- evidence: Not started.
- where: future PC-owned transform producers
- gap: Interpolate only values computed by native producers; do not interpolate or invert quantised GTE results.
