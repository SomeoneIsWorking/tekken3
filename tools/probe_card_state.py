#!/usr/bin/env python3
"""probe_card_state.py — is the NAMCO PRESENTS card still waiting, and on WHAT.

WHY THIS EXISTS. `docs/issues/0020` recovered the causal chain from the bytes: the guest sets
0x800A069F and registers 0x8006C26C in the same breath, and the only writer that clears that byte
(0x8006C2EC) runs inside the sector callback the guest installs at 0x8009B8D0 and dispatches at
0x8009213C. Two of the numbers needed to decide whether that is the live blocker are only available
at RUN TIME, and one of them is the whole question:

  * 0x8009B8D0 — is the sector callback INSTALLED?  (0x8006C26C already ran, per issue 0018)
  * 0x8009B8E8 — is it REGISTERED (the flag 0x80091F38 sets last)?
  * 0x800A069F — the card's wait byte. Still 1 means the sector callback never ran.
  * 0x800AE204 / 0x800AE224 — mode and phase. Mode 3 is reached = success.

DESIGNED NEGATIVE FIRST, in the sense that matters here: a zero from a word nobody writes is
indistinguishable from a clean measurement of absence, so this probe prints EVERY word's address and
value at every sample, names the feeder for each, and reports a control word that IS known to change
so a run where the channel silently stopped answering is distinguishable from a run where nothing
moved. It refuses rather than reporting a zero it did not measure.

Usage: probe_card_state.py [--port 127.0.0.1:13943] [--samples 12] [--interval 1.0]
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

TERMINATOR = "---END---\n"

WATCH = [
    # (label, address, width, why it is in the list)
    ("mode", 0x800AE204, 2, "the render mode; 3 means the mode-3 handler is running"),
    ("phase", 0x800AE224, 2, "the title-card phase within the mode"),
    ("wait_0x800A069F", 0x800A069F, 1, "THE CARD'S WAIT BYTE. 1 forever = the sector callback never ran"),
    ("busy_0x800A069E", 0x800A069E, 1, "the loader busy byte the wait loop spins on"),
    ("cb_slot_0x8009B8D0", 0x8009B8D0, 4, "the sector-callback slot FUN_80091F38 writes"),
    ("cb_flag_0x8009B8E8", 0x8009B8E8, 4, "the registration flag FUN_80091F38 sets last"),
    ("cb_state_0x8009B8C8", 0x8009B8C8, 4, "the callback record's state word"),
    # The CONTROL is the frame counter the frame loop increments once per presented field
    # (`game/core/frame_loop.cpp`, `kFrameCounter`). It is here for one reason: every other watched
    # word is EXPECTED to be constant while the card is up, so without a word that provably moves,
    # "nothing changed" and "the channel stopped answering" are the same output. A first version
    # named 0x800A0698 as the control — a word the loader chain is not moving — and this probe
    # correctly REFUSED on its own readings, which is the guard working and is why it is written.
    ("CONTROL_frame_0x800AFA4C", 0x800AFA4C, 4, "CONTROL: the frame counter, +1 every presented field"),
]


def command(sock: socket.socket, text: str, timeout: float) -> str:
    """One request, read to the terminator.

    The reply formats are NOT interchangeable, and reading the wrong one is how an earlier probe in
    this repository reported every word as -1 and then printed a confident verdict built on those
    -1s:  `rw ADDR N` replies "ADDR: WW WW ..." and the FIRST token is the ADDRESS. So the address is
    stripped off after the colon and only then parsed.
    """
    sock.sendall((text + "\n").encode())
    chunks = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return ""
        decoded = chunk.decode(errors="replace")
        chunks.append(decoded)
        if decoded.endswith(TERMINATOR):
            break
    return "".join(chunks)


def read_value(sock: socket.socket, address: int, width: int, timeout: float) -> int | None:
    verb = "r" if width == 1 else "rw"
    reply = command(sock, f"{verb} {address:X} 1", timeout)
    if ":" not in reply:
        return None
    tail = reply.split(":", 1)[1].split()
    if not tail:
        return None
    try:
        return int(tail[0], 16)
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="127.0.0.1:13943")
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=5.0)
    args = ap.parse_args()

    print(f"probe_card_state: watching {len(WATCH)} word(s) on {args.port} for {args.samples} sample(s)")
    host, _, raw_port = args.port.rpartition(":")
    try:
        sock = socket.create_connection((host, int(raw_port)), timeout=args.timeout)
    except OSError as error:
        print(f"probe_card_state: REFUSED — cannot reach the control channel: {error}")
        return 2

    history: list[dict[int, int | None]] = []
    with sock:
        for sample in range(args.samples):
            values: dict[int, int | None] = {}
            for label, address, width, _ in WATCH:
                values[address] = read_value(sock, address, width, args.timeout)
            if all(v is None for v in values.values()):
                print(f"probe_card_state: REFUSED — sample {sample + 1} read nothing at all. Reporting the "
                      f"{len(history)} sample(s) already taken and refusing to print a zero.")
                break
            history.append(values)
            cells = "  ".join(
                f"{label}={'ERR' if values[address] is None else format(values[address], '#010x')}"
                for label, address, _, _ in WATCH)
            print(f"  sample {sample + 1:>3}: {cells}")
            if sample + 1 < args.samples:
                time.sleep(args.interval)

    if not history:
        print("probe_card_state: REFUSED — zero samples. Nothing was measured.")
        return 2

    print(f"\nprobe_card_state: {len(history)} sample(s) of {len(WATCH)} word(s)")
    moved = 0
    for label, address, _, why in WATCH:
        values = [sample.get(address) for sample in history if sample.get(address) is not None]
        if not values:
            print(f"  {label:24s} 0x{address:08X}  NEVER READ  — {why}")
            continue
        distinct = sorted(set(values))
        verdict = "MOVING" if len(distinct) > 1 else "constant"
        if len(distinct) > 1:
            moved += 1
        print(f"  {label:24s} 0x{address:08X}  {verdict:8s} "
              f"first={distinct[0]:#010x} last={distinct[-1]:#010x} distinct={len(distinct)}  — {why}")

    if moved == 0:
        print("probe_card_state: REFUSED — not one watched word moved, including the CONTROL. A run in "
              "which nothing at all moves is a dead channel, not a measured steady state.")
        return 2
    print(f"probe_card_state: {moved} of {len(WATCH)} word(s) moved, so the channel answered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
