---
id: 5
title: Framework-pin check trusts stale configure provenance
status: open
symptom: psxport_sync.py --check reports the recorded framework pin even after the live framework checkout moved and dirty framework sources were rebuilt
tags: workflow,psxport,provenance,verification
created: 2026-08-22
updated: 2026-08-22
---

## Evidence

Tekken 3 build/psxport_resolved.txt records 3418a79b from configure time. During this audit, the shared framework checkout was at 858b39cf with dirty first-party sources, and the normal build consumed those live sources, yet tools/psxport_sync.py --check still printed that the build used 3418a79b. A separate detached clean worktree at 3418a79b was required to establish the milestone independently.

## Root cause

The check treats the configure-time psxport_resolved.txt SHA as current build provenance. It does not establish that the source tree used by the latest compilation still has that HEAD and cleanliness.

## Proper fix

Make the framework provenance gate compare the current resolved checkout identity and cleanliness with the configured record at build/verify time, or generate build provenance from the sources actually compiled. This belongs in the shared framework, outside this game-local task. Until fixed, a clean recorded-pin worktree is required for independent release evidence.
