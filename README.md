# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: the USA target executable can be provisioned, its direct-to-main startup shape is
verified, and independent Mednafen agrees with generated execution at four boundaries through the
first PSX hardware access: 35/35 CPU fields match at `0x80085D98`, after the instruction at
`0x80085D94` touches I_MASK. A separate-process build of Mednafen's IRQ controller agrees with the
shipping-emitted write/read/write reset sequence on 3/3 device observations through `0x80085DA4`.
Both harnesses install one process-lifetime `Tekken3Runtime` through psxport's direct runtime seam.
No extracted executable is tracked, and no independent CPU execution after that hardware access,
whole generated substrate, frame, gameplay, native producer, or widescreen path is claimed yet. Tekken 3
(`SLUS_004.02`) already
runs at 60 fps, so this port deliberately has no fps60 or interpolation target.

## Configure the framework scaffold

Configure with Clang before the first verification or after changing CMake inputs:

```sh
python3 tools/psxport_sync.py --auto
CCACHE_DISABLE=1 cmake --fresh -S . -B build \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++
```

The normal gate checks the recorded framework pin, runs the shared first-party `clang-format` /
`clang-tidy` / source-size policy, exercises provisioning/startup, all generated oracle boundaries,
generated-source integrity and opposite-answer/refusal selftests, and executes the framework smoke
test:

```sh
CCACHE_DISABLE=1 cmake --build build --target verify
```

The game-owned interpreter and generated-slice probes are first-party C++ translation units, so the
shared policy checks both with tracked Clang format/tidy configuration and real compile commands.
`game/core/tekken3_runtime.*` owns framework-facing game behavior. Its temporary legacy adapter view
has been removed: it derives directly from `GameRuntime`, returns an immutable `GuestProgramImage`
for measured resident text, and exposes null legacy config/hooks/context views. The interpreter-only
probe honestly supplies no program image because it never routes generated code.

`tekken3_scaffold` and its smoke test only prove that the game-agnostic framework links. The separate
boundary probes run real Tekken instructions through the first initializer and the measured
second-initializer call chain through its interrupt-controller reset sequence; no target launches a
frame or gameplay.
See `titles/tekken3/README.md` for the measured target and
`docs/re-frontier.md` for the ordered work required before a whole substrate or booted-frame claim is
possible.

## Provision the selected executable

Pass the USA CHD directly, set `PSXPORT_TEKKEN3_DISC`, copy `.env.example` to the gitignored `.env`,
or place one `*.chd` in the repository root. The command extracts the nested disc file and refuses
unless all tracked identity and PS-X EXE header fields match:

```sh
cmake --build build --target discdump
python3 tools/provision_executable.py "/path/to/Tekken 3 (USA).chd"
python3 tools/verify_startup.py
python3 tools/boot_oracle.py
cmake --build build --target tekken3_recomp_boundary_check -j16
```

The output is `scratch/bin/tekken3/SLUS_004.02`. Disc images and extracted executables are never
committed. The startup verifier models the actual `entry -> game_main -> non-returning frame loop`
shape; it does not reinterpret that call as a libc initialization boundary.

The boundary harness executes the entry window twice with psxport's interpreter and twice with the
independent Mednafen oracle. It requires deterministic agreement on all 35 CPU fields after the JAL
delay slot and before `game_main` begins. The generated harness reuses that verified interpreter
state and executes exact shipping-emitter slices containing six `game_main` instructions, the
28-instruction first initializer, the following two-instruction call, and the measured
second-initializer call chain. It compares all 35 CPU fields at the initializer entry, its return,
the next initializer entry, and `0x80085D98` immediately after the first I_MASK store. The standalone
CPU oracle deliberately refuses to invent device semantics there. The harness therefore compiles
Mednafen's IRQ controller in an isolated process, validates it can produce both zero and non-zero
states, and compares the emitted I_MASK write/read plus I_STAT write on 3/3 device observations at
`0x80085DA4`. Independent CPU stepping after the access, later initialization, frames, and gameplay
remain outside the result.
