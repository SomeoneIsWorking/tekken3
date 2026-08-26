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
| Generated program | Derive and register guest functions from the verified executable without hand edits | `tools/ensure_recomp.py`, `game/recomp_seeds.json`, `game/core/recomp_register.*`, gitignored `generated/port/` | `tools/ensure_recomp.py` | `docs/re-frontier.md` |
| Target executable | Record identity, load map, startup facts, projection facts, and controlled-boundary facts | `titles/tekken3/executable.json`, `titles/tekken3/README.md` | `tools/provision_executable.py` | `titles/tekken3/README.md` |
| Startup verification | Verify direct-main structure and independently compare the entry boundary | `tools/verify_startup.py`, `tools/boot_probe.cpp`, `tools/boot_oracle.py` | `tools/boot_oracle.py` | `docs/re-frontier.md` |
| Generated boundary verification | Emit measured slices and compare startup/device boundaries | `tools/recomp_boundary.py`, `tools/generated_runner.py`, `tools/bios_edge.py`, `tests/recomp_boundary.cpp`, `tests/irq_oracle.cpp` | `tekken3_recomp_boundary_check` | `docs/re-frontier.md` |
| CD-response verification | Emit and compare the controlled guest Getstat publication chain | `tools/cd_response_boundary.py`, `tests/cd_response_boundary.cpp` | `tekken3_cd_response_boundary_check` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| Projection and culling RE | Verify title-owned view, focal-length, display, stage-visibility, and clipping owners | `tools/verify_projection.py`, `titles/tekken3/executable.json` | `tools/verify_projection.py` | `titles/tekken3/README.md` |
| Widescreen policy | Apply the shared non-temporal guest-widescreen contract to measured title owners | `game/core/tekken3_runtime.*`; a future cohesive render owner is added only when measured behavior requires one | `Tekken3Runtime::renderCapabilities` | `docs/project-goals.md` |
| Verification policy | Compose executable, tool, test, source-structure, Clang format/tidy, and framework-pin checks | `CMakeLists.txt`, `.clang-format`, `.clang-tidy`, `tools/psxport_sync.py` | `verify` target | `README.md` |
| Project knowledge | Separate epic intent, factual capability state, atomic work, evidence, and ordered RE dependencies | `docs/project-goals.md`, `docs/project-state.md`, `docs/issues/`, `docs/info/`, `docs/re-frontier.md` | canonical shared project-info tool | `CLAUDE.md` |

## Where does X go?

- New host/platform composition: `game/core/tekken3_port.*`
- New title runtime policy or executable-facing seam: `game/core/tekken3_runtime.*`
- New rendering responsibility, if scope later changes: a new cohesive title-owned module rather
  than growth in the product composition entry point
- New executable-derived fact: `titles/tekken3/executable.json` plus its verifier
- New generated-function seed: `game/recomp_seeds.json` through `tools/ensure_recomp.py`
- New independent execution comparison: the focused owner under `tools/` plus a C++ runner under
  `tests/`
- Epic product scope: `docs/project-goals.md`
- Verified, partial, blocked, or missing capability: `docs/project-state.md`
- Atomic task, bug, finding, or dead end: `docs/issues/`
- Evidence claim or instrument trust: `docs/info/`
- Ordered binary-evidence dependency: `docs/re-frontier.md`
