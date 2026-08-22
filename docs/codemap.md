# Codemap

The repository currently layers a provisioned, measured title target and a deterministic hybrid
boundary harness over the shared psxport framework. Exact generated slices now advance from
direct-main through the first initializer and the observed second-initializer call chain to the
first hardware boundary. A process-lifetime direct runtime now owns the game/framework seam; the
shipping slice and an isolated Mednafen IRQ oracle now agree on the first interrupt-controller reset,
while independent CPU stepping beyond that device access remains the honest execution frontier.

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 direct-runtime boundary harness | `CMakeLists.txt`, `game/core/tekken3_runtime.cpp`, `tools/boot_probe.cpp`, `tests/recomp_boundary.cpp`, `external/psxport/`, `psxport.pin` | Direct `Tekken3Runtime` is the process-lifetime owner; interpreter and shipping-emitter slices reach the interrupt reset at `0x80085DA4`; no whole-program target |
| Generated boundary slices | ✅ verified slices | `generated/boundary_slices.c` (gitignored, emitted by `tools/recomp_boundary.py`) | Exact startup slices plus 717 pre-device and 3 device-response instructions are regenerated from the executable and shipping emitter; deliberately not a whole resident substrate |
| Target executable | ✅ provisioned and verified | `tools/provision_executable.py`, `titles/tekken3/executable.json` | USA `SLUS_004.02` resolution, extraction, identity, and PS-X EXE header are verified on real data; output remains gitignored |
| Startup model | ✅ RE-verified | `tools/verify_startup.py`, `titles/tekken3/README.md` | Direct `entry -> game_main`, return trap, first initializer range/return, next call, exact delay words, and main-loop back-edge match real bytes and Ghidra |
| Project tooling | 🟡 boundary-complete | `CMakeLists.txt` (`verify`, `cpp_policy`, `tekken3_recomp_boundary_check`) | Normal verifier covers identity/startup/oracle checks, generated-source integrity, opposite-answer/refusal cases, Clang format/tidy, and framework smoke; no whole resident substrate or game executable yet |
| Native runtime | 🟡 direct seam only | `game/core/tekken3_runtime.h`, `game/core/tekken3_runtime.cpp`, `tests/runtime_seam.cpp`, `tests/runtime_contract.cpp` | Direct `GameRuntime` inheritance and immutable `GuestProgramImage` resident text are verified; all three legacy Core views are null and the anti-adapter contract bans six legacy tokens; no native engine/frame owners |
| Native graphics ownership | ⬜ needs RE decision | — | Not a goal by itself; add only the camera/projection or producer ownership the measured widescreen path requires |
| Widescreen | ⬜ missing | — | Sole rendering enhancement; blocked on faithful boot plus RE of the camera/projection owner |
| Differential harness | 🟡 first device response | `tools/boot_oracle.py`, `tools/recomp_boundary.py`, `tests/recomp_boundary.cpp`, `tests/irq_oracle.cpp` | Independent CPU and generated execution agree 35/35 at four boundaries through post-store `0x80085D98`; isolated Mednafen IRQ and generated execution agree 3/3 through reset `0x80085DA4`; CPU execution past hardware, frames, and gameplay remain uncovered |

## Where is X?

- Target identity, load map, and startup boundary: `titles/tekken3/README.md`
- Disc/executable provisioning: `tools/provision_executable.py`
- Direct-main executable verification: `tools/verify_startup.py`
- Framework smoke and game-owned boundary probe: `CMakeLists.txt` (`tekken3_scaffold`, `tekken3_boot_probe`)
- Process-lifetime direct game owner and immutable program facts: `game/core/tekken3_runtime.h`, `game/core/tekken3_runtime.cpp`
- Rendering-enhancement policy (already 60 fps; widescreen only): `CLAUDE.md`, `docs/re-frontier.md` (`T3-05`, `T3-06`)
- Deterministic two-engine call-boundary comparison: `tools/boot_oracle.py`
- Generated startup/hardware-frontier slices and true-oracle comparison: `tools/recomp_boundary.py`, `tests/recomp_boundary.cpp`
- Normal build/style/lint/smoke gate: `CMakeLists.txt` (`verify`)
- Ordered RE dependency chain: `docs/re-frontier.md`
- Symptom/finding history: `docs/issues/`
