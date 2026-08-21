# Codemap

The repository currently layers a provisioned, measured title target and a deterministic hybrid
boundary harness over the shared psxport framework. Exact generated slices now advance from
direct-main through the first initializer return to the next initializer entry; there is still no
game runtime layer, and the honest frontier is execution inside the second initializer toward the
first hardware boundary or divergence.

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 hybrid boundary harness | `CMakeLists.txt`, `tools/boot_probe.cpp`, `tests/recomp_boundary.cpp`, `external/psxport/`, `psxport.pin` | Interpreter owns the verified entry window; shipping-emitter C owns 36 exact instructions through the first initializer return and next call; no runtime/game seam |
| Generated boundary slices | ✅ verified slices | `generated/boundary_slices.c` (gitignored, emitted by `tools/recomp_boundary.py`) | Exact 6 + 28 + 2 instruction slices are regenerated from the executable and shipping emitter; deliberately not a whole resident substrate |
| Target executable | ✅ provisioned and verified | `tools/provision_executable.py`, `titles/tekken3/executable.json` | USA `SLUS_004.02` resolution, extraction, identity, and PS-X EXE header are verified on real data; output remains gitignored |
| Startup model | ✅ RE-verified | `tools/verify_startup.py`, `titles/tekken3/README.md` | Direct `entry -> game_main`, return trap, first initializer range/return, next call, exact delay words, and main-loop back-edge match real bytes and Ghidra |
| Project tooling | 🟡 boundary-complete | `CMakeLists.txt` (`verify`, `cpp_policy`, `tekken3_recomp_boundary_check`) | Normal verifier covers identity/startup/oracle checks, generated-source integrity, opposite-answer/refusal cases, Clang format/tidy, and framework smoke; no whole resident substrate or game executable yet |
| Native engine | ⬜ missing | — | No `game/` tree or owned game code |
| Native graphics producers | ⬜ missing | — | No producer exists |
| Widescreen | ⬜ missing | — | Blocked on native camera and producers |
| Interpolation | ⬜ missing | — | Blocked on PC ownership of transform producers |
| Differential harness | ✅ first initializer return | `tools/boot_oracle.py`, `tools/recomp_boundary.py`, `tests/recomp_boundary.cpp` | True Mednafen and hybrid generated execution agree 35/35 at `0x80079D10`, return `0x80028BB8`, and next entry `0x800B0548`; no second initializer, BIOS/device, frame, or gameplay coverage |

## Where is X?

- Target identity, load map, and startup boundary: `titles/tekken3/README.md`
- Disc/executable provisioning: `tools/provision_executable.py`
- Direct-main executable verification: `tools/verify_startup.py`
- Framework smoke and game-owned boundary probe: `CMakeLists.txt` (`tekken3_scaffold`, `tekken3_boot_probe`)
- Deterministic two-engine call-boundary comparison: `tools/boot_oracle.py`
- Generated `game_main` prefix and true-oracle comparison: `tools/recomp_boundary.py`, `tests/recomp_boundary.cpp`
- Normal build/style/lint/smoke gate: `CMakeLists.txt` (`verify`)
- Ordered RE dependency chain: `docs/re-frontier.md`
- Symptom/finding history: `docs/issues/`
