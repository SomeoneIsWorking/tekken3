---
id: 1
title: The RE-frontier check parses zero steps from a prose roadmap
status: resolved
symptom: the re-frontier check refuses docs/re-frontier.md because numbered prose tasks parse as zero structured entries
tags: workflow,re-frontier,registry
created: 2026-08-20
updated: 2026-08-20
---

**Dead end, kept so it is not repeated:** `docs/re-frontier.md` was a prose numbered list, while the
re-frontier checker only indexes structured entries. The fix was to give every step the structured
form it reads — a `### <id> — <title>` heading followed by `- status:`, `- deps:`, `- evidence:`,
`- where:`, `- gap:` and optional `- notes:` fields — which is the form the file still uses.

Do not rewrite the tracker back into prose; the checker will read it as zero steps.