# Codemap

The repository currently layers a provisioned, measured title target and a deterministic entry-boundary
harness over the shared psxport framework. There is no generated substrate or game runtime layer yet;
the honest frontier is recompilation through the first real divergence.

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 boundary harness | `CMakeLists.txt`, `tools/boot_probe.cpp`, `external/psxport/`, `psxport.pin` | Clang-built probe executes the selected entry window with psxport's interpreter against verified framework pin `2b5ef7b5`; no generated game seam |
| Target executable | ✅ provisioned and verified | `tools/provision_executable.py`, `titles/tekken3/executable.json` | USA `SLUS_004.02` resolution, extraction, identity, and PS-X EXE header are verified on real data; output remains gitignored |
| Startup model | ✅ RE-verified | `tools/verify_startup.py`, `titles/tekken3/README.md` | Direct `entry -> game_main` call, return trap, and main-loop back-edge match real bytes and Ghidra |
| Project tooling | 🟡 boundary-complete | `CMakeLists.txt` (`verify`, `cpp_policy`, `tekken3_tool_selftests`, `tekken3_boot_oracle_selftest`) | Normal verifier covers 20 positive/negative/refusal cases, one first-party Clang-format/size file, one real clang-tidy TU, framework smoke, and the boundary harness; no generated-substrate gate yet |
| Native engine | ⬜ missing | — | No `game/` tree or owned game code |
| Native graphics producers | ⬜ missing | — | No producer exists |
| Widescreen | ⬜ missing | — | Blocked on native camera and producers |
| Interpolation | ⬜ missing | — | Blocked on PC ownership of transform producers |
| Differential harness | ✅ entry boundary only | `tools/boot_oracle.py`, `tools/boot_probe.cpp` | Two psxport runs and two independent Mednafen runs agree on 35/35 CPU fields at direct-main; no BIOS/device, substrate, frame, or gameplay coverage |

## Where is X?

- Target identity, load map, and startup boundary: `titles/tekken3/README.md`
- Disc/executable provisioning: `tools/provision_executable.py`
- Direct-main executable verification: `tools/verify_startup.py`
- Framework smoke and game-owned boundary probe: `CMakeLists.txt` (`tekken3_scaffold`, `tekken3_boot_probe`)
- Deterministic two-engine call-boundary comparison: `tools/boot_oracle.py`
- Normal build/style/lint/smoke gate: `CMakeLists.txt` (`verify`)
- Ordered RE dependency chain: `docs/re-frontier.md`
- Symptom/finding history: `docs/issues/`
