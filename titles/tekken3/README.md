# Tekken 3

## Measured target

The selected target is the supplied USA disc image (NTSC-U/C). Its `SYSTEM.CNF` names
`cdrom:\TEKKEN3\SLUS_004.02;1`, and the disc directory places that executable at LBA 25.

| Field | Measured value |
|---|---|
| Executable | `TEKKEN3/SLUS_004.02` |
| Disc extent | LBA 25, 1,185,792 bytes |
| SHA-256 (complete PS-X EXE) | `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` |
| Entry (`pc0`) | `0x80079C70` |
| Load address (`t_addr`) | `0x80010000` |
| Text size (`t_size`) | `0x00121000` bytes |
| Text extent | `[0x80010000, 0x80131000)` |
| Header stack | `0x801FFFF0` |

The startup body zeroes BSS `[0x8009B9A8, 0x800B0548)`, derives GP `0x8009B9A8`, stack top
`0x801FFFF8`, heap base `0x800B0548`, and heap size `0x00147AB0`, then stores the heap size/base
through `0x80098A6C` and `0x80098A68`. Ghidra decompilation and a post-decompile instruction
spot-check agree that the JAL at `0x80079D04` targets `0x80028BA0` with a `nop` delay slot.

That target is Tekken 3's non-returning main loop, not a libc initializer. `crt0_extract` labels the
first startup JAL `libcInit` generically and explicitly reports that this target is not the A(39h)
InitHeap thunk. The project-owned model instead names the boundary `game_main`: the entry's first JAL
at `0x80079D04` targets `0x80028BA0`, its delay slot is a nop, and a MIPS `break` immediately guards
against return at `0x80079D0C`. Inside `game_main`, the unconditional jump at `0x80028E0C` returns to
the frame-loop body at `0x80028BCC`.

The first six instructions of `game_main` allocate its 32-byte frame, save `ra/s2/s1`, and call
`0x80079D10` at `0x80028BB0`; its delay slot saves `s0` with word `0xAFB00010`. The tracked manifest
records those facts and `tools/verify_startup.py` checks that no earlier call exists in `game_main`.

`FUN_80079d10` is a 28-instruction executable function `[0x80079D10,0x80079D80)`. Ghidra and narrow
instruction inspection agree that it guards and sets the word at `0x80098A64`, contains a
zero-count constructor-loop path on this boot, restores its frame, and returns through `jr ra` at
`0x80079D78` with a nop delay slot. The continuation at `0x80028BB8` immediately calls
`0x800B0548`; its delay word `0x3C11800B` loads `s1`'s high half.

A fresh Ghidra 12.0.4 decompile of the provisioned image (SHA-256 above) confirms both semantics:
`FUN_80079c70` calls `FUN_80028ba0` and then traps, while `FUN_80028ba0` performs one-time calls and
then loops forever around the mode dispatch and two `FUN_8007bab0` calls. The tracked executable and
startup facts live in `executable.json`; `tools/verify_startup.py` checks those shipping facts against
the real executable and has agreement/disagreement fixtures. `tools/boot_oracle.py` then executes the
entry window in psxport and an independent Mednafen CPU, requiring two deterministic runs per leg to
agree on all 35 CPU fields at `0x80028BA0`. This is not a claim that `game_main`, a generated substrate,
devices, frames, or gameplay run.

`tools/recomp_boundary.py` advances without compiling unrelated mode bodies: psxport's interpreter
reproduces the already-verified entry-to-main state, then the shipping recompiler emits the measured
startup slices plus six bounded function slices along the observed second-initializer path. Ghidra
identifies that path as `FUN_800b0548 -> FUN_80055884 -> FUN_80079964/FUN_800799a8`, followed by
`FUN_80085bc8`'s indirect call through the initialized function table to `FUN_80085d5c`.

Independent Mednafen executes the whole window. Both engines agree on 35/35 CPU fields at
first-initializer entry step 106159, after return at `0x80028BB8` step 106181, at next-initializer
entry `0x800B0548` step 106183, and at `0x80085D98` step 106388. The final boundary is immediately
before `FUN_80085d5c` writes the PSX interrupt-mask register I_MASK at `0x1F801074`; the oracle stops
before executing that hardware access. The generated leg routes the measured indirect call through
its game-local generated registry rather than replacing it with a direct call. Generated source is
recomputed through the shipping emitter, and deliberate register/source/boundary/hardware-register
changes must fail. This does not execute the hardware access or response, later initialization, a
frame, or gameplay.

## Reproduce the identity measurement

After the root README's Clang configure, run the project-owned provisioner:

```sh
CCACHE_DISABLE=1 cmake --build build --target discdump
python3 tools/provision_executable.py "/path/to/disc.chd"
python3 tools/verify_startup.py
python3 tools/boot_oracle.py
cmake --build build --target tekken3_recomp_boundary_check -j16
```

Resolution is CLI argument > `PSXPORT_TEKKEN3_DISC` > `.env` > one root `*.chd` drop-in. A selected
path that does not exist refuses rather than falling through to another disc, and ambiguous drop-ins
also refuse. No disc-derived file belongs in git. The latest comparison establishes generated
execution through the first hardware boundary at `0x80085D98`; it does not establish the
interrupt-mask write or device response, later initialization, that a Tekken 3 port boots a frame,
or that a whole recompiled substrate exists.
