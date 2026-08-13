# Codemap

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 scaffold | `CMakeLists.txt`, `external/psxport/` | Smoke target only; no game seam |
| Title integration | ⬜ missing | `titles/tekken3/` | Select region and measure executable |
| Native engine | ⬜ missing | `game/` | No owned game code |
| Native graphics producers | ⬜ missing | `game/render/` | No producer exists |
| Widescreen | ⬜ missing | — | Blocked on native camera and producers |
| Interpolation | ⬜ missing | — | Blocked on PC ownership of transform producers |
| Differential harness | ⬜ missing | — | Stand up oracle before game logic |
