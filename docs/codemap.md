# Codemap

The repository currently layers a measured title target over the shared psxport framework scaffold.
There is no game runtime layer yet; the honest frontier is disc provisioning, then a differential
boot harness.

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 scaffold | `CMakeLists.txt`, `external/psxport/`, `psxport.pin` | Clang-built `tekken3_scaffold` links the smoke target against verified framework pin `be381503`; no game seam |
| Target executable | 🟡 measured, not integrated | `titles/tekken3/README.md` | USA `SLUS_004.02` identity/load map measured (C001); provision it without tracking disc-derived data |
| Project tooling | 🟡 scaffold | `CMakeLists.txt` (`verify`, `cpp_policy`), `tools/psxport_sync.py`, framework `discdump` / `crt0_extract` / Ghidra workflow | Framework `be381503` supplies the shared Clang format/tidy/size checker; no game boot gate or project-local registry CLI yet |
| Native engine | ⬜ missing | — | No `game/` tree or owned game code |
| Native graphics producers | ⬜ missing | — | No producer exists |
| Widescreen | ⬜ missing | — | Blocked on native camera and producers |
| Interpolation | ⬜ missing | — | Blocked on PC ownership of transform producers |
| Differential harness | ⬜ missing | — | Stand up oracle before game logic |

## Where is X?

- Target identity, load map, and startup boundary: `titles/tekken3/README.md`
- Framework-only build target: `CMakeLists.txt` (`tekken3_scaffold`)
- Normal build/style/lint/smoke gate: `CMakeLists.txt` (`verify`)
- Ordered RE dependency chain: `docs/re-frontier.md`
- Symptom/finding history: `docs/issues/`
