---
id: 3
title: A boot probe crashed before the direct-main boundary
status: resolved
symptom: the first psxport leg exits with SIGSEGV after loading the PS-X EXE, before the observer reaches game_main
tags: harness,lifecycle
created: 2026-08-21
updated: 2026-08-21
---

**Two failures, both harness-side, both worth not repeating.** First, the probe placed the roughly
12 MB `Core` object on the process stack and overflowed it; `Core` belongs on the heap. Moving it
exposed a second lifecycle violation: constructing `Core` alone leaves `core.game` null while the
interpreter consults `game->platform_hle` at every JAL target, so the harness must heap-allocate
`Game` (the shipping machine owner) and use its `Core` member.

No framework change and no null bypass was added; the boundary is captured through the normal
`PcObserver` seam.