# Codemap

Tekken 3 follows the Dusklight ownership shape: a narrow host entry composes one process-lifetime
title runtime with shared platform subsystems. Generated guest code remains a derived input, while
title-specific policy and executable facts stay outside the framework.

```text
run.sh -> bootstrap.py -> tools/run.py -> game/core/main.cpp
                                          |
                                          v
                              game/core/tekken3_port.cpp
                               /                    \
                  Tekken3Runtime                 psxport devices
                       |                              |
          generated retail dispatch          GPU/SPU/MDEC/GTE/pad/CD
```

## Ownership

| Subsystem | Responsibility | Current / target location | Entry point | Deep doc |
|---|---|---|---|---|
| Player launcher | Resolve player inputs, provision, generate, configure, build, and launch the product | `run.sh`, `bootstrap.py`, `tools/run.py`, `pyproject.toml`, `uv.lock` | `run.sh` | `README.md` |
| Product composition | Install the title runtime and generated registry, load the retail program, and compose framework devices | `game/core/main.cpp`, `game/core/tekken3_port.*`, `cmake/tekken3_port.cmake` | `tekken3::runPort` | `CLAUDE.md` |
| Title runtime | Own executable facts, render capabilities, platform-HLE policy, override registration, and retail-entry dispatch | `game/core/tekken3_runtime.*`, `game/core/sync_native.*` | `tekken3::Tekken3Runtime` | `CLAUDE.md` |
| Frame cadence | Own the finite retail-main prefix, one measured title frame, RCntCNT2 event delivery, pad publication, presentation/audio service order, and retained generated supers | `game/core/frame_loop.*`, `game/core/recompiled_program_bindings.h`, `game/core/recomp_register.*` | `tekken3::Tekken3FrameDriver` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| CD synchronization | Preserve Tekken's linked-libcd wrapper/response state while delegating commands and the sole queued directory-read path to shared synchronous stock-libcd owners; retain every generated super | `game/core/cd_sync.*`, `game/core/recompiled_program_bindings.h`, `game/core/recomp_register.*` | `tekken3::installCdOverrides` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| GPU synchronization | Preserve Tekken's linked GPU queue timeout and reset contract while sourcing its field deadline from the native frame ledger; retain generated arm/poll supers | `game/core/gpu_sync.*`, `game/core/recompiled_program_bindings.h`, `game/core/recomp_register.*` | `tekken3::installGpuSyncOverrides` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| Generated program | Derive and register guest functions from the verified executable without hand edits | `tools/ensure_recomp.py`, `game/recomp_seeds.json`, `game/core/recomp_register.*`, gitignored `generated/port/` | `tools/ensure_recomp.py` | `docs/re-frontier.md` |
| Target executable | Record identity, load map, startup facts, projection facts, and controlled-boundary facts | `titles/tekken3/executable.json`, `titles/tekken3/README.md` | `tools/provision_executable.py` | `titles/tekken3/README.md` |
| Startup verification | Verify direct-main structure and independently compare the entry boundary | `tools/verify_startup.py`, `tools/boot_probe.cpp`, `tools/boot_oracle.py` | `tools/boot_oracle.py` | `docs/re-frontier.md` |
| Generated boundary verification | Emit measured slices and compare startup/device boundaries | `tools/recomp_boundary.py`, `tools/generated_runner.py`, `tools/bios_edge.py`, `tests/recomp_boundary.cpp`, `tests/irq_oracle.cpp` | `tekken3_recomp_boundary_check` | `docs/re-frontier.md` |
| CD-response verification | Emit and compare the controlled guest Getstat publication chain | `tools/cd_response_boundary.py`, `tests/cd_response_boundary.cpp` | `tekken3_cd_response_boundary_check` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| Projection and culling RE | Verify title-owned view, focal-length, display, stage-visibility, and clipping owners | `tools/verify_projection.py`, `titles/tekken3/executable.json` | `tools/verify_projection.py` | `titles/tekken3/README.md` |
| Widescreen projection and clipping | Apply the shared non-temporal guest-widescreen plan to Tekken's measured view-dimension owner and stage/effect right-edge clippers, retaining generated 4:3 supers | `game/core/widescreen.*`, `game/core/tekken3_runtime.*`, `game/core/recompiled_program_bindings.h` | `tekken3::Tekken3Widescreen` | `docs/issues/0008-tekken-wide-margins-lose-stage-and-effect-primit.md` |
| Verification policy | Compose executable, tool, test, source-structure, Clang format/tidy, and framework-pin checks | `CMakeLists.txt`, `.clang-format`, `.clang-tidy`, `tools/psxport_sync.py` | `verify` target | `README.md` |
| Project knowledge | Separate epic intent, factual capability state, atomic work, evidence, and ordered RE dependencies | `docs/project-goals.md`, `docs/project-state.md`, `docs/issues/`, `docs/info/`, `docs/re-frontier.md` | canonical shared project-info tool | `CLAUDE.md` |

## Where does X go?

- New host/platform composition: `game/core/tekken3_port.*`
- New title runtime policy or executable-facing seam: `game/core/tekken3_runtime.*`
- New frame ordering, finite-loop, or frame-event ownership: `game/core/frame_loop.*`
- New linked GPU queue wait/timeout ownership: `game/core/gpu_sync.*`
- New title projection or clipping behavior: `game/core/widescreen.*`; other rendering
  responsibilities get their own cohesive owner rather than growing product composition
- New executable-derived fact: `titles/tekken3/executable.json` plus its verifier
- New generated-function seed: `game/recomp_seeds.json` through `tools/ensure_recomp.py`
- New independent execution comparison: the focused owner under `tools/` plus a C++ runner under
  `tests/`
- Epic product scope: `docs/project-goals.md`
- Verified, partial, blocked, or missing capability: `docs/project-state.md`
- Atomic task, bug, finding, or dead end: `docs/issues/`
- Evidence claim or instrument trust: `docs/info/`
- Ordered binary-evidence dependency: `docs/re-frontier.md`
