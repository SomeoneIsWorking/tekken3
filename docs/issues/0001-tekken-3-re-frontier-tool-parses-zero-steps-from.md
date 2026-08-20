---
id: 1
title: Tekken 3 RE-frontier tool parses zero steps from prose roadmap
status: resolved
symptom: re_frontier.py check refuses docs/re-frontier.md because the seven numbered prose tasks parse as zero structured entries
tags: workflow,re-frontier,registry
created: 2026-08-20
updated: 2026-08-20
---

## Root cause

`docs/re-frontier.md` was a prose numbered list, while `re_frontier.py` only indexes structured heading/field entries.

## What was tried / dead ends

The zero-entry parse was not accepted as an empty roadmap: `re_frontier.py check` correctly failed it, ruling out `next` alone as evidence that no work remained.

## Resolution

### Resolution (2026-08-20)
Rewriting the same seven tasks as T3-01 through T3-07 makes check parse all 7, next name T3-02, and hacks report zero tracked debt.
