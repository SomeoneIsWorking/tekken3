# Codemap

Tekken 3 uses a project-owned composition shape: a narrow host entry composes one process-lifetime
title runtime with shared platform subsystems. The authenticated guest executable remains runtime
data, while title-specific policy and executable facts stay outside the framework.

```text
run.sh -> bootstrap.py -> tools/run.py -> game/core/main.cpp
                                          |
                                          v
                              game/core/tekken3_port.cpp
                         /             |                 \
            Tekken3Runtime      psxport Lightrec       psxport devices
                  |               executor                  |
       image-aware native       remaining guest       GPU/SPU/MDEC/GTE/
          overrides +             instructions             pad/CD
        original calls

separate test target -> independent oracle (never linked or selectable by the gameplay product)
```

## Ownership

| Subsystem | Responsibility | Current / target location | Entry point | Deep doc |
|---|---|---|---|---|
| Player launcher | Resolve player inputs, provision the authenticated runtime image, configure, build, and launch the product | `run.sh`, `bootstrap.py`, `tools/run.py`, `pyproject.toml`, `uv.lock` | `run.sh` | `README.md` |
| Product composition | Install the title runtime and native override registry, load the retail program as data, construct the per-Core Lightrec executor, and compose framework devices | target: `game/core/main.cpp`, `game/core/tekken3_port.*`, `cmake/tekken3_port.cmake` | `tekken3::runPort` | `CLAUDE.md` |
| Title runtime | Own executable facts, render capabilities, platform-HLE policy, image-aware native override registration, original calls, and retail-entry dispatch | target: `game/core/tekken3_runtime.*`, `game/core/sync_native.*`, a cohesive native-override registry | `tekken3::Tekken3Runtime` | `CLAUDE.md` |
| Dynamic executor | Translate every non-native guest instruction at runtime, synchronize canonical machine state at service boundaries, invalidate changed executable memory, and make bounded exits explicit | target: shared `external/psxport` Lightrec integration; Lightrec retains its own cache/code memory | target: per-`Core` psxport executor | `docs/re-frontier.md` |
| Frame cadence | Own the finite retail-main prefix, one measured title frame, RCntCNT2 event delivery, pad publication, and presentation/audio service order; original guest bodies execute through the dynarec | target: `game/core/frame_loop.*` plus psxport override/original-call API | `tekken3::Tekken3FrameDriver` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| CD synchronization | Preserve Tekken's linked-libcd wrapper/response state while delegating commands and the sole queued directory-read path to shared synchronous stock-libcd owners; original guest bodies execute by address through the dynarec | target: `game/core/cd_sync.*` plus native override/original-call bindings | `tekken3::installCdOverrides` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| GPU synchronization | Preserve Tekken's linked GPU queue timeout and reset contract while sourcing its field deadline from the native frame ledger; original arm/poll bodies execute by address through the dynarec | target: `game/core/gpu_sync.*` plus native override/original-call bindings | `tekken3::installGpuSyncOverrides` | `docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md` |
| Target executable | Record identity, load map, startup facts, projection facts, and controlled-boundary facts | `titles/tekken3/executable.json`, `titles/tekken3/README.md` | `tools/provision_executable.py` | `titles/tekken3/README.md` |
| Startup verification | Verify the authenticated executable's direct-main structure | `tools/verify_startup.py`, `titles/tekken3/executable.json` | `tools/verify_startup.py` | `docs/re-frontier.md` |
| Dynamic execution verification | Compare bounded Lightrec execution, overrides, original calls, invalidation, exits, and machine/device state against an independent emulator or separately built test oracle | target: focused game-owned drivers under `tools/` and test-only runners under `tests/` | target: native/Lightrec discriminator gate | `docs/re-frontier.md` |
| Projection and culling RE | Verify title-owned view, focal-length, display, stage-visibility, and clipping owners | `tools/verify_projection.py`, `titles/tekken3/executable.json` | `tools/verify_projection.py` | `titles/tekken3/README.md` |
| Widescreen projection and clipping | Apply the shared non-temporal guest-widescreen plan to Tekken's measured view-dimension owner and stage/effect right-edge clippers, with the faithful original bodies reached through dynarec original calls | target: `game/core/widescreen.*`, `game/core/tekken3_runtime.*`, native override/original-call bindings | `tekken3::Tekken3Widescreen` | `docs/issues/0008-tekken-wide-margins-lose-stage-and-effect-primit.md` |
| Runtime-input policy | Execute the authenticated user-provided executable as runtime data and keep provisioning non-executable | CMake, launcher, and repository structure | native/Lightrec conformance gate | `docs/project-state.md` |
| Verification policy | Compose executable, tool, test, source-structure, Clang format/tidy, and framework-pin checks | `CMakeLists.txt`, `.clang-format`, `.clang-tidy`, `tools/psxport_sync.py` | `verify` target | `README.md` |
| Project knowledge | Separate epic intent, factual capability state, atomic work, evidence, and ordered RE dependencies | `docs/project-goals.md`, `docs/project-state.md`, `docs/issues/`, `docs/info/`, `docs/re-frontier.md` | canonical shared project-info tool | `CLAUDE.md` |

## Where does X go?

- New host/platform composition: `game/core/tekken3_port.*`
- New title runtime policy or executable-facing seam: `game/core/tekken3_runtime.*`
- New guest instruction semantics, machine synchronization, bounded exit, or invalidation behavior:
  shared `external/psxport`; Lightrec owns only its embedded dynarec internals
- New native function ownership: a cohesive title module plus the image-and-address-keyed override
  registry; call the original guest body through psxport's scoped dynarec original-call API
- New frame ordering, finite-loop, or frame-event ownership: `game/core/frame_loop.*`
- New linked GPU queue wait/timeout ownership: `game/core/gpu_sync.*`
- New title projection or clipping behavior: `game/core/widescreen.*`; other rendering
  responsibilities get their own cohesive owner rather than growing product composition
- New executable-derived fact: `titles/tekken3/executable.json` plus its verifier
- New independent execution comparison: the focused owner under `tools/` plus a separately built
  test-only runner under `tests/`; any interpreter oracle stays test-only and out of the gameplay product
- Epic product scope: `docs/project-goals.md`
- Verified, partial, blocked, or missing capability: `docs/project-state.md`
- Atomic task, bug, finding, or dead end: `docs/issues/`
- Evidence claim or instrument trust: `docs/info/`
- Ordered binary-evidence dependency: `docs/re-frontier.md`
