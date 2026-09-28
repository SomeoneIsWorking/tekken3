---
id: 19
title: The card's spin is on the CONTROLLER port, not on the CD completion
status: open
symptom: The NAMCO PRESENTS card never leaves; the loop at 0x800934D8 never exits at any field
state_items: S003
tags: tekken3,pad,sio,cd-completion,blocker
created: 2026-09-29
updated: 2026-09-29
---

## What this replaces

Issue 0018 named S003's loader blocker as **"a title-owned CD completion that nothing delivers"**, and
`CdProtocol::deliverCompletions` was written and landed for it (`c93d0b1`). **That part is now
measured working, and it was not the blocker.** The completion is delivered, the guest consumes it,
and the card still does not leave.

## Measured: the completion delivery works, in the shipping product

One disc-backed run, `PSXPORT_NATIVE_FRAMES=30000`, driven over the loopback control channel and
sampled every ~0.5 s:

| field | chain cursor `0x800A3E3C` | chain live `0x800A3E40` | CD completion count `0x8009B778` |
|---|---|---|---|
| 2,916 | 4 | 0 | 0x62 |
| 4,017 | 4 | 0 | 0x86 |
| 7,423 | 4 | 0 | 0xF7 |
| 10,448 | 4 | 0 | climbing |

**The cursor reached 4 and stopped, and the live count reached 0 and stayed there.** The host only
*reads* both words — the guest's class-2 branch at `0x8008EA1C` / `0x8008EA24` writes them — so a
cursor of 4 with a live count of 0 is the host's `call2` having entered `0x8008E928` four times and
the guest having consumed a record on each. **The owner fires, and the guest's own ring is drained
and stays drained.** The CD state machine is also alive, not wedged: the completion count keeps
climbing (`0x62` → `0xF7` over 7,500 fields) and `chain state` stays 2 with a changing outstanding
command, so commands keep being issued, completed and retried.

## Measured: the loop is waiting on SIO0, the controller port

The loop issue 0018 called the spin is guest `0x800934D8..0x800934E4`, which polls bit `0x0002` of
the halfword at `*0x8009B964 + 4`. **The pointer at `0x8009B964` holds `0x1F801040`.** In the
framework's own hardware map that is SIO0:

- `psxport/runtime/psx/io_peripherals.cpp:12` — `kSio0Lo = 0x1F801040`, `kSio0Hi = 0x1F80104F`
- `psxport/runtime/psx/pad_input.cpp:13` — "`0x1F801040` data / `0x1F801044` status / `0x1F80104A` control"

So the card is waiting on **SIO0's status register, `0x1F801044`, bit 1** — the transmit-complete
flag of the controller port. Read at field 10,242, 10,345 and 10,448:

    0x1F801040  SIO0 data   = 0x00FF     <- the port's "no pad" value
    0x1F801044  SIO0 status = 0x0001     <- bit 0 (data available) set, bit 1 CLEAR
    0x1F80104A  SIO0 ctrl   = 0x0000

**`0x00FF` is the pad-error code.** The framework's own pad notes (`pad_input.cpp:16`) record
`buf[0] = 0x00` for "pad present/ok" and `0xFF` for "no pad / error", and the same file's header
(`pad_input.cpp:25`) records the identical failure for Tomba! 2: "its guest body would spin on the
`0x1F801044` status poll and bail via its timeout (`LAB_80003da4` -> mark 'no pad')".

**So the title is not stuck on the disc. It is stuck on a controller that reports no pad**, and
unlike Tomba! 2 — which has a timeout that marks "no pad" and carries on — this spin has no exit
observed in 10,448 fields.

## Why this was misattributed twice

The same address was read three different ways before it was identified. The port at
`0x1F801040` was watched as a CD address, because the question in flight was about the CD, and a
`0x00FF` read at an address nobody had named looked like a stalled transfer. **A watch list built
from the question being asked will find the question's answer in whatever it points at.** The
address is SIO0, and nothing about S003 is about the disc.

## Next step, named

S003's blocker is a **controller/SIO0 condition**, and the pattern for it already exists in the
framework: Tomba! 2 answers its own `0x1F801044` poll with a native override that writes the pad
packet straight into the guest's registered slot buffer instead of emulating SIO. Tekken 3 needs
the equivalent: either SIO0's status bit 1 is raised when the native pad owner has a packet to
deliver, or the title's spin is given the same bounded escape its sibling has. Which one is correct
depends on whether the guest's own code bit-bangs SIO0 or calls a libpad routine — that is the next
measurement, and it is a small one: decode the call chain above `0x800934D8`.

## Falsifier

Each of these would make this issue wrong, and each is a measurement rather than an opinion:

- If `0x8009B964` does not hold `0x1F801040` in a run that reaches the spin, the port reading is an
  artifact of when it was sampled.
- If SIO0's data register reads something other than `0x00FF` on hardware that HAS a pad attached,
  the "no pad" attribution is wrong and the spin is waiting on something else.
- If the guest writes `0x1F801044` itself, the framework's hardware model is not the owner of the
  bit and the correct fix is elsewhere.
