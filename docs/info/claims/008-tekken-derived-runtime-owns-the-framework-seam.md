---
id: C008
kind: claim
status: holds
created: 2026-08-22
tags: runtime,inheritance,architecture,t3-04
depends: game/core/tekken3_runtime.cpp, tests/runtime_seam.cpp#main, tests/recomp_boundary.cpp#main, tools/boot_probe.cpp#main
---

## Claim

Tekken 3's interpreter and generated-boundary harnesses install one derived, process-lifetime
`Tekken3Runtime`; neither entry point installs a raw `GameConfig`/`GameHooks` pair. The only legacy
adapter data is the two-field resident text extent still required by psxport's generated-code
router, and no Tekken behavior delegates through legacy callbacks.

## Evidence

The Clang build against psxport `7f5d3f13b7068f921d880b71181c61715100bc0c` passed the normal
`verify` target: format checked 5/5 first-party files, source-sized 5/5 at the 1,200-line cap, and
clang-tidy checked 4/4 compile-backed translation units. `tekken3_runtime_seam` proved that `Core`
snapshots the derived runtime, that exactly 2/2 resident-range facts reach the bounded compatibility
view, that no legacy context is created, and that 1/1 empty range is refused. The real generated
boundary gate still agreed 35/35 with independent Mednafen at all four boundaries through
`0x80085D98` and passed its 7/7 opposite-answer/refusal suite, proving the migration did not bypass
or advance the I_MASK frontier.

## What would falsify it

A Tekken entry point reinstalls `GameConfig`/`GameHooks` directly, the runtime gains legacy behavior
callbacks or additional compatibility fields, `Core` no longer snapshots the derived owner/range,
or the real boundary comparison ceases to agree 35/35 at any of the four measured edges.
