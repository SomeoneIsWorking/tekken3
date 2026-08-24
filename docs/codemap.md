# Codemap

The repository now layers a dedicated whole-program player product and a deterministic hybrid
boundary harness over the provisioned, measured title target and shared psxport framework. Exact
generated slices advance from
direct-main through the first initializer, the observed second-initializer call chain, the DPCR
write, and the measured kernel-stub edge to the BIOS-call return at `0x80085DEC`; that last edge is
single-engine (framework HLE models the callee). A process-lifetime direct runtime owns the
game/framework seam; the shared Mednafen oracle still stops honestly on the DPCR write. A saved
generic-DPCR experiment identifies B(19) at `pc=0x000000B0` as the next independent boundary, but
the oracle maps no BIOS and therefore cannot return to title code yet.

| Subsystem | Status | Where | Gap / next |
|---|---|---|---|
| Framework consumer | 🟡 whole-program product, early runtime frontier | `CMakeLists.txt`, `cmake/tekken3_port.cmake`, `game/core/main.cpp`, `game/core/tekken3_port.*`, `game/core/tekken3_runtime.*`, `external/psxport/`, `psxport.pin` | `tekken3_port` installs the generated registry and direct process-lifetime runtime, loads the verified retail program, and composes framework hardware owners. Boundary slices reach the BIOS-call return `0x80085DEC`; no completed frame or gameplay claim |
| Generated program | 🟡 resident product plus verified slices | `tools/ensure_recomp.py`, `game/recomp_seeds.json`, gitignored `generated/port/` and `generated/boundary_slices.c` | The identity-checked executable, seed facts, and shipping emitter produce 1,885 resident functions plus the evidence-backed HookEntryInt re-entry. Exact boundary slices remain the independently compared evidence path; automatic pointer-root false positives still inflate whole-product builds (issue #4) |
| Target executable | ✅ provisioned and verified | `tools/provision_executable.py`, `titles/tekken3/executable.json` | USA `SLUS_004.02` resolution, extraction, identity, and PS-X EXE header are verified on real data; output remains gitignored |
| Startup model | ✅ RE-verified | `tools/verify_startup.py`, `titles/tekken3/README.md` | Direct `entry -> game_main`, return trap, first initializer range/return, next call, exact delay words, and main-loop back-edge match real bytes and Ghidra |
| Player launcher | 🟡 product-targeted | `run.sh`, `bootstrap.py`, `tools/run.py`, `pyproject.toml`, `uv.lock` | Zero args provision, emit, build, and launch `tekken3_port` through one frozen uv interpreter; `--prepare-only` is the hermetic non-launching path. Native dependency failures name DNF/APT/Homebrew/vcpkg commands; no compiler identity policy and no tests/smoke default |
| Project tooling | 🟡 player and boundary covered | `CMakeLists.txt` (`verify`, `cpp_policy`, `tekken3_recomp_boundary_check`), `tools/ensure_recomp.py`, `tools/test_run.py`, `tools/recomp_boundary.py`, `tools/generated_runner.py`, `tools/bios_edge.py`, `tools/verify_projection.py` | Normal verifier covers identity/startup/oracle checks, player-launcher and whole-substrate freshness contracts, the projection-owner census, generated-source integrity, opposite-answer/refusal cases, Clang format/tidy, and framework smoke |
| Native runtime | 🟡 direct seam only | `game/core/tekken3_runtime.h`, `game/core/tekken3_runtime.cpp`, `tests/runtime_seam.cpp`, `tests/runtime_contract.cpp` | Direct `GameRuntime` inheritance and immutable `GuestProgramImage` resident text are verified; all three legacy Core views are null, the anti-adapter contract bans six legacy tokens, and the boundary-only runtime explicitly reports guest VRAM is not picture content; no native engine/frame owners |
| Native graphics ownership | 🟡 projection owners verified | `tools/verify_projection.py`, `titles/tekken3/README.md`, `docs/re-frontier.md` (`T3-05`) | The title view-centre, focal-length, stage-wedge, and retail right-clip owners are measured from the binary. The shared-decoder-backed verifier proves the complete six-writer CR24/25/26 census without an address exemption; no native producer is justified. |
| Widescreen | 🟡 ownership measured, rendering missing | `titles/tekken3/README.md`, `docs/re-frontier.md` (`T3-05`, `T3-06`), issue #9 | Fix the framework's GP1 bit-6 decode (Tekken's 368 mode currently becomes 256), bind title projection/culling owners to the shared non-temporal guest-wide plan, then prove coordinated geometry/draw/present widening against a bit-identical 4:3 control. First-pixel evidence remains blocked on independent execution after DPCR. |
| Differential harness | 🟡 BIOS-call edge reached, single-engine there | `tools/boot_oracle.py`, `tools/recomp_boundary.py`, `tools/generated_runner.py`, `tools/bios_edge.py`, `tests/recomp_boundary.cpp`, `tests/irq_oracle.cpp` | Independent CPU and generated execution agree 35/35 at five boundaries through the unsupported DPCR access at `0x80085DB4`; same-CPU I_STAT/I_MASK modeling and the isolated 3/3 IRQ check provide both answers. The generated leg alone continues through B(19) to `0x80085DEC` using framework HLE. Independent continuation needs generic DPCR plus an independently sourced B(19) model; the next exact boundary is `pc=0xB0`, not a later hardware register (issue #10). Frames and gameplay remain uncovered. |

## Where is X?

- Target identity, load map, and startup boundary: `titles/tekken3/README.md`
- Disc/executable provisioning: `tools/provision_executable.py`
- Player launcher and product composition: `run.sh`, `tools/run.py`, `game/core/tekken3_port.*`
- Whole-program emission and registry installation: `tools/ensure_recomp.py`, `game/recomp_seeds.json`, `game/core/recomp_register.*`
- Direct-main executable verification: `tools/verify_startup.py`
- Projection/display/culling real-executable verification: `tools/verify_projection.py`
- Framework smoke and game-owned boundary probe: `CMakeLists.txt` (`tekken3_scaffold`, `tekken3_boot_probe`)
- Process-lifetime direct game owner and immutable program facts: `game/core/tekken3_runtime.h`, `game/core/tekken3_runtime.cpp`
- Measured display/projection/camera ownership: `titles/tekken3/README.md`
- Rendering-enhancement policy (already 60 fps; widescreen only): `CLAUDE.md`, `docs/re-frontier.md` (`T3-05`, `T3-06`)
- Deterministic two-engine call-boundary comparison: `tools/boot_oracle.py`
- Generated startup/hardware-frontier slices and true-oracle comparison: `tools/recomp_boundary.py`, `tools/generated_runner.py`, `tools/bios_edge.py`, `tests/recomp_boundary.cpp`
- Normal build/style/lint/smoke gate: `CMakeLists.txt` (`verify`)
- Ordered RE dependency chain: `docs/re-frontier.md`
- Symptom/finding history: `docs/issues/`
