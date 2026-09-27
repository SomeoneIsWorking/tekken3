#!/usr/bin/env python3
"""probe_loader_state.py — diagnosis only.

Drives psxport's own live debug endpoint (PSXPORT_DEBUG_SERVER) against a running
product and reads the guest-visible loader state that docs/issues/0011 names, so
the answer is a measurement of the running guest rather than an inference from a
disassembly.

The addresses and their meanings are quoted from
tekken3/docs/issues/0011-whole-product-interrupt-exit-reaches-unseeded-te.md
lines 70-83 and 203-205:

  0x800A069F  loader wait byte        (set by FUN_8006C084 before command 0xA0,
                                       cleared by FUN_8006C2A0 after the last extent)
  0x800A06A4  outstanding bytes
  0x800A06A8  destination
  0x800A3E40  raw-command queue count
  0x8009B8D0  callback pointer
  0x800A05D8  final loader state
  0x800AE204  mode
  0x800AE224  phase

It also watches the CD COMMAND-CHAIN state machine, because "the loader submitted a command" and
"the command reached the controller" are different events. FUN_8008F08C only ENQUEUES four records
into the eight-slot ring at 0x800A3D78; a record is executed one per pump by
FUN_8008E8B8 -> FUN_8008FB08 -> FUN_8008FCC0 -> FUN_80083E4C, and FUN_80083E4C is this title's own
installed cdControl override. So:

  0x8009B750  CD chain state. FUN_8008FB08 refuses to issue anything unless this is 1, and advances
              it to 2 on a successful issue.
  0x8009B774  FUN_8008FCC0's outstanding-completion counter. Zero until a command is really issued,
              then 0x1E or 0x3C0. FUN_8008FB08 also refuses while it is >= 1. THIS IS THE SHARPEST
              SINGLE WORD: nonzero proves a command reached the controller.
  0x8009B730  CD-initialised gate. FUN_8008FB08 refuses while it is 0.
  0x8009B734  the live CD command byte FUN_8008FCC0 last handed to FUN_80083E4C.
  0x8009B778  FUN_8008FCC0's completion flag.
  0x8009B8E8  sector-callback registration flag owned by FUN_80091F38.

Usage: probe_loader_state.py [port] [first-frame-to-sample]
It starts nothing: the product must already be running with PSXPORT_DEBUG_SERVER
set. It samples every 10 frames from the requested frame and prints a table, so a
value that never changes across many fields is visibly a stuck value rather than a
single sample.
"""
import socket
import sys
import time

TERMINATOR = "---END---\n"

# (label, kind, address) with kind "r" = bytes, "rw" = words.
WATCH = [
    ("wait byte 0x800A069F", "r", 0x800A069F),
    ("outstanding 0x800A06A4", "rw", 0x800A06A4),
    ("destination 0x800A06A8", "rw", 0x800A06A8),
    ("raw queue count 0x800A3E40", "rw", 0x800A3E40),
    ("callback 0x8009B8D0", "rw", 0x8009B8D0),
    ("loader state 0x800A05D8", "rw", 0x800A05D8),
    ("mode 0x800AE204", "rw", 0x800AE204),
    ("phase 0x800AE224", "rw", 0x800AE224),
    ("chain state 0x8009B750", "rw", 0x8009B750),
    ("outstanding cmd 0x8009B774", "rw", 0x8009B774),
    ("cd initialised 0x8009B730", "rw", 0x8009B730),
    ("live cmd byte 0x8009B734", "rw", 0x8009B734),
    ("cmd done flag 0x8009B778", "rw", 0x8009B778),
    ("cb registered 0x8009B8E8", "rw", 0x8009B8E8),
]


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5959
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    deadline = time.time() + 300.0
    while True:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=5.0)
            break
        except OSError as error:
            if time.time() > deadline:
                print(f"probe: no debug endpoint on 127.0.0.1:{port} ({error})")
                return 1
            time.sleep(0.5)
    stream = sock.makefile("rwb")

    def command(text: str) -> str:
        stream.write((text + "\n").encode())
        stream.flush()
        collected = []
        while True:
            line = stream.readline()
            if not line:
                return "<endpoint closed>"
            decoded = line.decode(errors="replace")
            if decoded == TERMINATOR:
                return "".join(collected).rstrip("\n")
            collected.append(decoded)

    def frame_number() -> int:
        reply = command("frame")
        for token in reply.replace("=", " ").split():
            if token.isdigit():
                return int(token)
        return -1

    while True:
        number = frame_number()
        if number >= first or time.time() > deadline:
            break
        time.sleep(0.2)

    print(f"probe: sampling from field {frame_number()}")
    header = "field " + " | ".join(label for label, _, _ in WATCH)
    print(header)
    previous = None
    for _ in range(12):
        number = frame_number()
        row = [f"{number:5d}"]
        values = []
        for _, kind, address in WATCH:
            count = 8 if kind == "r" else 2
            reply = command(f"{kind} {address:X} {count}").strip()
            values.append(reply)
            row.append(reply)
        line = " | ".join(row)
        # Mark only the fields whose raw value did not change since the previous sample.
        if previous is not None:
            marks = ["same" if a == b else "CHANGED" for a, b in zip(values, previous)]
            line += "   << " + ",".join(
                label for (label, _, _), mark in zip(WATCH, marks) if mark == "CHANGED"
            )
        print(line)
        previous = values
        time.sleep(0.4)

    print("\nprobe: guest execution denominators")
    print(command("guest"))
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
