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
- status: re-verified
- deps: T3-01
- evidence: C002/I002. `tools/provision_executable.py` resolves CLI > `PSXPORT_TEKKEN3_DISC` > `.env` > one root CHD without falling through from a bad configured path, extracts the nested `TEKKEN3/SLUS_004.02`, and checks eight tracked identity/header facts from `titles/tekken3/executable.json`. Its shipping-path selftest passes 12/12 positive, byte-mismatch, malformed-executable, preservation, ambiguity, and refusal cases. A real USA CHD extraction produced 1,185,792 bytes with SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` under `scratch/bin/tekken3/`.
- where: `tools/provision_executable.py`; `titles/tekken3/executable.json`; gitignored `.env` or root drop-in input
- gap: None for reproducible executable provisioning. Disc provenance beyond the selected measured image remains outside this tool's claim.

### T3-03A — Model Tekken's direct-to-main startup boundary
- status: re-verified
- deps: T3-02
- evidence: C003/I003. `tools/verify_startup.py` checks the real executable's first entry call `0x80079D04 -> 0x80028BA0`, nop delay slot, immediate break-on-return guard, both initializer calls and delay words, the first initializer's exact return, and `0x80028E0C -> 0x80028BCC` main-loop back-edge without using the framework's `libcInit` name. It passes 10/10 agreement/disagreement/refusal fixtures and 18/18 structural facts on the provisioned USA executable. A fresh Ghidra 12.0.4 decompile of `FUN_80079c70`, `FUN_80028ba0`, and `FUN_80079d10` on the same hashed RAM image confirms the entry/main relationship and first initializer semantics.
- where: `tools/verify_startup.py`; `titles/tekken3/executable.json`; `titles/tekken3/README.md`
- gap: None for executable structure. T3-03 separately tests execution to this boundary; neither step
  proves a generated substrate or a booted frame.

### T3-03 — Bring up a deterministic psxport/oracle boot harness
- status: re-verified
- deps: T3-03A
- evidence: C004/I004. `tools/boot_oracle.py` runs the selected entry window twice through the game-owned psxport interpreter probe and twice through the independent vendored-Mednafen `oracle_trace`, stopping after the first JAL delay slot and before direct-main executes. On the provisioned USA executable, both legs were deterministic and agreed on all 32 GPRs, HI, LO, and PC (35/35 fields) at `0x80028BA0`; the independent oracle reached it at step 106153. The permanent 3/3 selftest uses both real engines, detects a forced `a0` disagreement, and refuses a window too short to reach a call. Real-data forced-negative and one-step refusal gates also return mismatch/refusal rather than agreement.
- where: `tools/boot_probe.cpp`; `tools/boot_oracle.py`; `CMakeLists.txt` (`tekken3_boot_oracle_selftest`)
- gap: None for deterministic execution from the selected entry to the verified direct-main call boundary. This does not execute `game_main`, generated code, BIOS/devices, a frame, or gameplay; those remain T3-04 and later work.

### T3-04 — Recompile through the first real divergence
- status: re-partial
- deps: T3-03
- evidence: C005/C006/I005. The verifier proves the exact first initializer range and return plus the next call. `tools/recomp_boundary.py` asks psxport's shipping emitter for exact 6 + 28 + 2 instruction slices; the port executes the verified entry window in the interpreter and those generated slices while independent Mednafen executes the whole window. Both agree on 35/35 CPU fields at `0x80079D10` step 106159, after return at `0x80028BB8` step 106181, and at next initializer `0x800B0548` step 106183. The permanent 6/6 selftest detects altered `a0`, altered generated source, missing trace boundaries, and unmeasured runner targets.
- where: `tools/recomp_boundary.py`; `tests/recomp_boundary.cpp`; generated, gitignored `generated/boundary_slices.c`; `scratch/raw/t3-04/oracle.trace`
- gap: Execute the second initializer from `0x800B0548` toward the independently observed first hardware stop at `0x1F801074`, preserving its measured indirect-call path rather than inventing whole-image seeds. This slice does not claim second-initializer completion, BIOS/device execution, a frame, or gameplay.
- notes: A whole-image trial discovered 593 roots and 1,884 functions, compiling downstream mode bodies irrelevant to this boundary. Issue #4 records why `emit.py --limit` is not a safe slice and why those pointer roots were not mislabeled as false positives.

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
