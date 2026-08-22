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
- evidence: C005/C006/C010 and I005/I006. The verifier proves the exact first initializer and next call. The shipping emitter now generates the observed second-initializer chain, including the function-table dispatch 0x80085BC8 -> 0x80085D5C. Independent Mednafen and the hybrid generated runner agree on all 35 CPU fields at 0x80079D10, 0x80028BB8, 0x800B0548, and post-store 0x80085D98. The selected executable's exact I_MASK-write/read and I_STAT-write words are checked, and a separate vendored-Mednafen IRQ process agrees with the generated path on 3/3 device observations at 0x80085DA4. SELFTEST 9/9 plus IRQ SELFTEST 2/2 detect register/source/boundary/hardware-register/device errors.
- where: `game/core/tekken3_runtime.*`; `tools/recomp_boundary.py`; `tests/recomp_boundary.cpp`; generated, gitignored `generated/boundary_slices.c`; `scratch/raw/t3-04/oracle.trace`
- gap: Extend psxport's independent CPU oracle so a modeled I_MASK/I_STAT access can resume the same Mednafen CPU, then continue `FUN_80085d5c` from 0x80085DA4 toward the next independently observed hardware boundary or first divergence. `oracle_shim.c` currently stops on every device access by design; the game-local IRQ oracle proves the device transition but cannot resume CPU execution. This still does not claim later initialization, a frame, or gameplay.
- notes: Ghidra identifies the observed path as `FUN_800b0548 -> FUN_80055884 -> FUN_80079964/FUN_800799a8`, then indirect `FUN_80085bc8 -> FUN_80085d5c`. The generated leg preserves that indirect dispatch instead of replacing it with a direct call. `Tekken3Runtime` owns the framework seam directly and carries the measured resident range in immutable `GuestProgramImage`; no adapter/config/hooks view remains. This ownership migration does not advance or bypass the execution boundary. A whole-image trial discovered 593 roots and 1,884 functions, compiling downstream mode bodies irrelevant to this boundary. Issue #4 records why `emit.py --limit` is not a safe slice and why those pointer roots were not mislabeled as false positives.

## Widescreen ownership and enhancement

### T3-05 — Identify the widescreen projection owner
- status: re-partial
- deps: T3-04
- evidence: C012/I007. Static analysis of the complete hashed `SLUS_004.02` image plus Ghidra decompilation identifies all six canonical CR24/CR25/CR26 writes. `FUN_80080a40` owns the title's view dimensions; `FUN_80081148` derives the retail projection centre from those dimensions; `FUN_80080da8` publishes the centre plus the current double-buffer offsets through `SetGeomOffset` at `0x80082728`. `FUN_80063c64` clamps the title-owned focal length and publishes it through `SetGeomScreen` at `0x80082748`; `FUN_80064080` selects a six-field fight-camera pose containing that focal length and `FUN_80064170` blends between authored poses. The two resident display presets prove that title view/projection width is distinct from the active PSX display width: the boot preset owns a 384x480 view and OFX/OFY 192/240 while its active display rectangle is 368x448; the alternate preset owns 320x240 and OFX/OFY 160/120. Both initialize H=500. The stage owner `FUN_8006D014` supplies horizontal visibility angles 600/780 to the 6x6 tile selector `FUN_8006D95C`; stage/effect primitive clippers `FUN_8006CC28` and `FUN_8006E44C` contain eleven plus one rendering-path signed `-368` right-edge comparisons. `tools/verify_projection.py` now proves 33/33 facts on the real executable through psxport's canonical decoder and passes 7/7 real agreement, mutated disagreement, and refusal cases, including both sides of the reserved-bit COP2 distinction. Those bounds must widen with the resolved display plan; the separate player-select text-slide use remains 2D retail layout.
- where: `tools/verify_projection.py`; `titles/tekken3/executable.json`; `titles/tekken3/README.md`; Ghidra project and decompilation under gitignored `scratch/`
- gap: Before consuming the shared non-temporal guest-widescreen contract, fix its generic GP1 display-mode decoder: issue #9 proves that the documented 368-pixel bit is ignored and Tekken's preset 0 becomes 256 pixels in framework state. Then bind the measured view-centre/H owners and A/B the resulting geometry and final presentation against 4:3. A real pixel comparison remains blocked on T3-04's same-CPU hardware continuation. OT, GP0, and GTE output are diagnostic evidence, never producer input.

### T3-06 — Owned widescreen
- status: todo
- deps: T3-05
- evidence: Not started.
- where: future title-owned projection policy plus the shared non-temporal guest-widescreen contract
- gap: Tekken 3 already runs at 60 fps. Implement only true widescreen from the measured view-centre and focal-length state, preserving H and vertical scale while widening horizontal field of view. The 4:3 path must remain identical and the wide path must widen guest geometry, draw coverage, and final sampling together; a host viewport stretch or a projection-only crop is not completion. There is no fps60, interpolation/lerp, or interpolation-supporting temporal pipeline in this title's target scope.
