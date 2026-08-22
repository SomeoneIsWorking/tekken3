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
startup slices plus six bounded callable slices and the seven-instruction device-response
continuation along the observed second-initializer path. Ghidra
identifies that path as `FUN_800b0548 -> FUN_80055884 -> FUN_80079964/FUN_800799a8`, followed by
`FUN_80085bc8`'s indirect call through the initialized function table to `FUN_80085d5c`.

Independent Mednafen executes the whole window. Both engines agree on 35/35 CPU fields at
first-initializer entry step 106159, after return at `0x80028BB8` step 106181, at next-initializer
entry `0x800B0548` step 106183, at `0x80085D98` step 106388, and at the next unsupported-device
boundary `0x80085DB4` step 106395. The generated leg routes the measured indirect call through its
game-local generated registry rather than replacing it with a direct call.

The tracked executable writes I_MASK at `0x80085D94`, reads it at `0x80085D98`, writes that result to
I_STAT at `0x80085DA0`, then stores `0x33333333` to DPCR `0x1F8010F0` at `0x80085DB0`. The verifier
checks all five hardware-frontier instruction words directly against the hashed executable. The shared
oracle routes only I_STAT/I_MASK through vendored Mednafen `irq.c`, so the same independent CPU executes
the complete interrupt reset with its real load delay; its retained GPUSTAT negative case still stops.
The oracle then reports the DPCR WRITE32 rather than inventing DMA semantics. The generated path proves
the exact DPCR value, while a separate IRQ process still demonstrates non-zero and zero states and
agrees with generated execution on 3/3 observations at `0x80085DA4`. Deliberate
register/source/boundary/hardware-register changes must fail. This does not independently step the CPU
after DPCR or establish later DMA behavior, initialization, a frame, or gameplay.

## Measured display and projection ownership

A complete word scan of the hashed loaded image found six canonical writes to GTE control registers
CR24, CR25, and CR26. Ghidra's independent instruction listing agrees on the same six sites:

| Address | Owner | Measured operation |
|---|---|---|
| `0x80081CBC`, `0x80081CC0` | `FUN_80081c50` (`InitGeom`) | initialize OFX and OFY to zero |
| `0x80082730`, `0x80082734` | `FUN_80082728` (`SetGeomOffset`) | publish `a0 << 16` to OFX and `a1 << 16` to OFY |
| `0x80081C9C` | `FUN_80081c50` (`InitGeom`) | initialize H to 1000 |
| `0x80082748` | `FUN_80082748` (`SetGeomScreen`) | publish `a0` to H |

The scan also found the word `0x48CCCCCE` at `0x800BAC20`. It is undisassembled resident data with no
function or control-flow owner, and its reserved low 11 bits make it a noncanonical COP2 move. This
exposed a shared decoder defect which is now fixed at the framework owner: psxport rejects the word's
reserved bits instead of labeling it `ctc2`. Tekken neither exempts that address nor duplicates the
instruction decoder. `tools/verify_projection.py` uses the shipping decoder to prove the complete six-
writer census and mutates both a real writer and that resident data word to prove the decoder-backed
gate can produce the opposite answer.

The title-level owners above the Psy-Q leaves are now identified:

- `FUN_80080a40(width, height)` owns the current view dimensions. `FUN_80081148` derives the retail
  centre as `(width / 2, height / 2)`, and `FUN_80080da8` adds the current double-buffer offsets,
  calls `SetGeomOffset`, and records the live OFX/OFY at `0x800ADE7C`/`0x800ADE7E`.
- `FUN_80063c64(h)` clamps H to the title's current minimum and maximum before calling
  `SetGeomScreen`. `FUN_80064080` selects a six-field fight-camera pose whose final field is H;
  `FUN_80064170` blends two authored poses, including H, and republishes it through
  `FUN_80063c64`. Fight-camera initialization sets the current/minimum/maximum H to 500.
- The resident table at `0x800B0CC8` contains two 16-byte display/view presets. Preset 0 owns an
  active display rectangle `(0,20,368,448)`, a 384x480 title view, and initial OFX/OFY 192/240.
  Preset 1 owns `(0,10,320,224)`, a 320x240 title view, and initial OFX/OFY 160/120. Both publish
  H=500. Boot calls `FUN_800B0840(0)`.
- `FUN_8006D014` is the stage submit owner. It calls `FUN_8006D95C` with a horizontal visibility
  angle of 600 normally and `0x30C` in mode 6. That helper traces the two rays at camera yaw plus and
  minus half the supplied angle and selects visible cells from the stage's 6x6 tile grid.
- `FUN_8006CC28` converts the selected stage primitives into ordering-table packets. Its triangle,
  quad, and sprite paths contain eleven exact signed `-368` comparisons and discard primitives whose
  projected vertices are wholly beyond the retail active-display right edge. `FUN_8006E44C` applies
  the twelfth rendering-path comparison to an effect-primitive path. These are title culling owners, not host
  viewport policy. The separate `-368` use in `FUN_80054B48` is a player-select text slide distance
  and must remain in the retail 2D layout.

The 384-wide title projection and 368-wide active display are deliberately different facts. A wide
implementation must therefore carry the title-authored projection width/centre separately from the
PSX display mode, resolve both retail modes from their 4:3 presentation semantics, keep H and the
vertical centre unchanged, and widen guest geometry, draw coverage, and final sampling as one plan.
Changing only the host viewport would stretch the picture; changing only OFX would crop it.
Issue #9 records a framework blocker exposed by this preset: GP1(08) bit 6 selects 368 pixels, but
the current decoder ignores that bit and records 256. This must be fixed generically before Tekken's
native presentation extent can be trusted; a title-side 368 override would only split the two owners.
The stage/effect right-edge tests must consume the same resolved wide display bound, while the stage
tile visibility angle must be checked against the resolved wide frustum. Static evidence identifies
that owner but does not select an angle formula: if the authored wedge becomes too narrow, any change
must derive from the retail angle and resolved projection rather than a replacement constant. Porting
those title functions must retain their generated bodies as the 4:3 differential control; the
evidence does not justify a new renderer or producer.

Static ownership does not establish a rendered frame. The next execution boundary is generic DPCR/DMA
modeling after the unsupported write at `0x80085DB0`; once independent execution reaches a real
display/frame boundary, a final-presentation A/B must show a bit-identical 4:3 control, unchanged
vertical projection, horizontal translation about the widened centre without scale change, and new
scene geometry in the added margins.

The durable real-executable gate currently passes 33/33 measured projection/display/culling facts and
7/7 positive, disagreement, and refusal cases:

```sh
python3 tools/verify_projection.py
python3 tools/verify_projection.py --selftest
```

The gate checks six canonical control-register writers, exact direct-call censuses, both raw 16-byte
presets and their derived centres, preset-0 boot selection, initial H=500, both stage-wedge call/angle
pairs, twelve rendering-path `-368` bounds, and the separate retail-2D `-368` use. It is a static owner
gate, not evidence of a frame or pixels.

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
execution and independent CPU agreement at five boundaries through the DPCR stop at `0x80085DB4`, plus
independent IRQ-controller agreement through the reset boundary at `0x80085DA4`. It does not establish
DPCR/DMA semantics, independent CPU execution after that access, later initialization, that a Tekken 3
port boots a frame, or that a whole recompiled substrate exists.
