# Codemap

The repository currently layers a provisioned, measured title target over the shared psxport framework
scaffold. There is no game runtime layer yet; the honest frontier is a differential boot harness.

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 scaffold | `CMakeLists.txt`, `external/psxport/`, `psxport.pin` | Clang-built `tekken3_scaffold` links the smoke target against verified framework pin `be381503`; no game seam |
| Target executable | ✅ provisioned and verified | `tools/provision_executable.py`, `titles/tekken3/executable.json` | USA `SLUS_004.02` resolution, extraction, identity, and PS-X EXE header are verified on real data; output remains gitignored |
| Startup model | ✅ RE-verified, not booted | `tools/verify_startup.py`, `titles/tekken3/README.md` | Direct `entry -> game_main` call, return trap, and main-loop back-edge match real bytes and Ghidra; next build the seam/harness without framework libc-boundary semantics |
| Project tooling | 🟡 scaffold | `CMakeLists.txt` (`verify`, `cpp_policy`, `tekken3_tool_selftests`), `tools/psxport_sync.py` | Normal verifier covers 17 positive/negative provisioning/startup cases plus shared Clang policy and smoke; no game boot gate or project-local registry CLI yet |
| Native engine | ⬜ missing | — | No `game/` tree or owned game code |
| Native graphics producers | ⬜ missing | — | No producer exists |
| Widescreen | ⬜ missing | — | Blocked on native camera and producers |
| Interpolation | ⬜ missing | — | Blocked on PC ownership of transform producers |
| Differential harness | ⬜ missing | — | Stand up oracle before game logic |

## Where is X?

- Target identity, load map, and startup boundary: `titles/tekken3/README.md`
- Disc/executable provisioning: `tools/provision_executable.py`
- Direct-main executable verification: `tools/verify_startup.py`
- Framework-only build target: `CMakeLists.txt` (`tekken3_scaffold`)
- Normal build/style/lint/smoke gate: `CMakeLists.txt` (`verify`)
- Ordered RE dependency chain: `docs/re-frontier.md`
- Symptom/finding history: `docs/issues/`
