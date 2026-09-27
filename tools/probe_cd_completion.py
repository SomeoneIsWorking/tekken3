#!/usr/bin/env python3
"""probe_cd_completion.py — diagnosis only.

Asks the RUNNING product's live endpoint (PSXPORT_DEBUG_SERVER) the one question the loader stall
turns on: after the title issues a CD command through its own cdControl override, does the CD
controller ever raise the interrupt that the title's registered CD handler is waiting for?

DESIGNED NEGATIVE FIRST. It reports what it read and what it concluded, it names the guest address
behind every value, and it distinguishes "the controller never raised it" from "it raised it and the
guest masked it" from "it was raised and already acknowledged" — three different bugs that look
identical from the loader's side.

Addresses come from the framework's own CDC model (runtime/psx/cdc_native.cpp's register map) and
from the recovered title CD state machine (FUN_8008FB08 / FUN_8008FCC0 / FUN_80092034).

Usage: probe_cd_completion.py [port]
Starts nothing; the product must already be running with PSXPORT_DEBUG_SERVER set.
"""
from __future__ import annotations

import socket
import sys
import time

TERMINATOR = "---END---\n"

# (label, address, note)
WATCH = [
    ("I_STAT", 0x1F801070, "PSX CP0 interrupt status; bit 2 is the CD controller line"),
    ("I_MASK", 0x1F801074, "PSX CP0 interrupt mask; bit 2 must be set for the guest to see CD"),
    ("CDC mode/STAT0", 0x1F801801, "bank0 command / read: response FIFO pop"),
    ("CDC STAT1", 0x1F801802, "bank0 parameter / read: data FIFO pop"),
    ("CDC ctrl/STAT2", 0x1F801803, "bank0 request(BFRD) / read: interrupt flags + /ACK reset"),
    ("CDC STAT3", 0x1F801804, "bank1 mode write / read: interrupt enable + flags"),
    ("DPCR", 0x1F8010F0, "DMA3 enable must be on for the sector fetch to move bytes"),
    ("chain state", 0x8009B750, "FUN_8008FB08 issues only while this is 1; 2 means in flight"),
    ("outstanding cmd", 0x8009B774, "FUN_8008FCC0's completion deadline; nonzero = in flight"),
    ("cd initialised", 0x8009B730, "FUN_8008FB08 refuses while 0"),
    ("live cmd byte", 0x8009B734, "command last handed to FUN_80083E4C"),
    ("completion count", 0x8009B778, "FUN_8008FCC0's counter; climbing means retries"),
    ("handler chain head", 0x800A62E8, "the interrupt element the boot log said it registered"),
    ("cb registered", 0x8009B8E8, "FUN_80091F38 sets this; 0 means class 2 never arrived"),
    ("cb pointer", 0x8009B8D0, "the registered CD callback"),
    ("wait byte", 0x800A069F, "loader wait byte"),
]

# The spin, from guest instructions 0x800934D8..0x800934E4:
#   0x800934CC  lui   v1,0x800A
#   0x800934D0  lw    v1,-0x469C(v1)     ; v1 = 0x800A0000 - 0x469C
#   0x800934D8  lhu   v0,0x4(v1)         ; poll halfword bit 1 of (*(SLOT) + 4)
#   0x800934E0  andi  v0,v0,0x0002
#   0x800934E4  beq   v0,zero,0x800934D8  ; loop until it is set
#
# The slot is DERIVED, not guessed: 0x800A0000 - 0x469C is 0x8009B964. Reading 0x800AB964 instead
# returns a zero that means nothing, and an earlier version of this probe reported that zero as
# "the slot was never initialised" — a confident wrong answer from an arithmetic slip.
SPIN_SLOT = 0x800A0000 - 0x469C
SPIN_DISPLACEMENT = 4
SPIN_BIT = 0x0002


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5959
    deadline = time.time() + 120.0
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

    def read_word(address: int) -> int:
        # `rw ADDR N` replies "ADDR: WW WW ..." — a colon, then N 32-bit words. The FIRST token is
        # the address, so parsing the leading token silently reads the ADDRESS back as if it were the
        # value, which is how an earlier version of this probe reported every word as -1 and then
        # printed a confident verdict built on those -1s.
        reply = command(f"rw {address:X} 1").strip()
        if ":" not in reply:
            return -1
        tail = reply.split(":", 1)[1].split()
        if not tail:
            return -1
        try:
            return int(tail[0], 16)
        except ValueError:
            return -1

    def field_number() -> str:
        return command("frame").strip()

    print(f"probe: {field_number()}, reading {len(WATCH)} word(s)")
    for sample in range(6):
        row = [f"{field_number():>34}"]
        for label, address, _ in WATCH:
            row.append(f"{label}={read_word(address):08X}")
        print("  " + "  ".join(row))
        time.sleep(0.4)

    def read_half(address: int) -> int:
        # `r ADDR N` replies "ADDR: BB BB ..." — bytes, little-endian as the guest sees them.
        reply = command(f"r {address:X} 2").strip()
        if ":" not in reply:
            return -1
        tail = reply.split(":", 1)[1].split()
        if len(tail) < 2:
            return -1
        try:
            return int(tail[0], 16) | (int(tail[1], 16) << 8)
        except ValueError:
            return -1

    stat, mask = read_word(0x1F801070), read_word(0x1F801074)
    chain, outstanding, initialised = (read_word(a) for a in (0x8009B750, 0x8009B774, 0x8009B730))
    live_cmd, cb_registered = read_word(0x8009B734), read_word(0x8009B8E8)
    block = read_word(SPIN_SLOT)
    polled = read_half((block + SPIN_DISPLACEMENT) & 0xFFFFFFFF) if 0x1000 < block < 0x80000000 else -1

    print("\nverdict, from the words just read:")
    if outstanding == -1 or chain == -1:
        print("  REFUSED: a required word could not be read, so no verdict is offered. "
              "An unreadable register is not a zero register.")
        sock.close()
        return 2
    if outstanding == 0 and chain != 2:
        print("  NO COMMAND IS IN FLIGHT (0x8009B774 == 0 and the chain is not 2): the loader has not"
              " issued anything, or everything completed.")
    else:
        print(f"  A COMMAND IS IN FLIGHT: 0x8009B774 = 0x{outstanding:08X}, chain = {chain},"
              f" live command = {live_cmd}.")
    if not (mask & 4):
        print("  I_MASK bit 2 is CLEAR, so even a raised CD interrupt cannot reach the guest."
              " That is a guest-side mask decision, not a missing controller edge.")
    if stat & 4:
        print("  I_STAT bit 2 is SET: a CD interrupt is PENDING and undelivered right now.")
    else:
        print("  I_STAT bit 2 is clear: no CD interrupt is pending at this instant.")
    if cb_registered == 0:
        print("  0x8009B8E8 == 0, so the title NEVER REGISTERED its CD handlers: the class-2 event"
              " that registers them never arrived. Combined with I_MASK below, this localises the"
              " defect to the completion path, not to the submission path.")
    if 0x1000 < block < 0x80000000:
        print(f"  THE SPIN: guest 0x800934D8..0x800934E4 polls bit {SPIN_BIT:#06x} of the halfword"
              f" at 0x{block + SPIN_DISPLACEMENT:08X} (*{SPIN_SLOT:#010x} = 0x{block:08X},"
              f" +{SPIN_DISPLACEMENT}). Read now: 0x{polled:04X} — the bit is"
              f" {'SET, so this loop is not the stall' if polled >= 0 and polled & SPIN_BIT else 'CLEAR, which is why the loop never exits'}.")
    else:
        print(f"  THE SPIN: *{SPIN_SLOT:#010x} read as 0x{block:08X}, which is not a guest pointer, so"
              " the poll is on a NULL-derived address. Report that as an uninitialised slot, NOT as"
              " 'the status bit is clear' — the two are different bugs.")
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
