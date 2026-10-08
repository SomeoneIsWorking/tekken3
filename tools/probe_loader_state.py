#!/usr/bin/env python3
"""Diagnosis only: samples the guest loader and CD command-chain state through the running
product's live debug endpoint (PSXPORT_DEBUG_SERVER) and flags values that did not change.

0x8009B774 (FUN_8008FCC0's outstanding-completion counter) is nonzero once a command reached the
controller; 0x8009B750 must be 1 for FUN_8008FB08 to issue anything.

Usage: probe_loader_state.py [port] [first-frame-to-sample]
Starts nothing; the product must already be running with PSXPORT_DEBUG_SERVER set.
"""
import os
import pathlib
import sys
import time

PSXPORT = pathlib.Path(os.environ.get("PSXPORT_DIR",
                                       pathlib.Path(__file__).resolve().parents[1] / "external" / "psxport"))
sys.path.insert(0, str(PSXPORT / "tools"))
try:
    from dbgclient import LiveClient
except ImportError as error:
    raise SystemExit(f"REFUSED: cannot import psxport's live endpoint client from {PSXPORT}: {error}")

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
    # RCnt2 countdown FUN_800951B8 was last armed with; 0x190 is only passed from 0x800934EC (pad read).
    ("rcnt2 countdown 0x800AE228", "rw", 0x800AE228),
    # Mode 3 handler body; the mode-0 loader writes it at run time.
    ("mode 3 handler 0x800DB1B8", "r", 0x800DB1B8),
    ("chain state 0x8009B750", "rw", 0x8009B750),
    ("outstanding cmd 0x8009B774", "rw", 0x8009B774),
    ("cd initialised 0x8009B730", "rw", 0x8009B730),
    ("live cmd byte 0x8009B734", "rw", 0x8009B734),
    ("cmd done flag 0x8009B778", "rw", 0x8009B778),
    ("cb registered 0x8009B8E8", "rw", 0x8009B8E8),
]


def wait_for_endpoint(port: int, seconds: float) -> tuple["LiveClient | None", object]:
    """Connect once the endpoint answers a `frame`; the listener opens before boot finishes."""
    deadline = time.time() + seconds
    error: object = "never attempted"
    while time.time() < deadline:
        client = None
        try:
            client = LiveClient(port=port, timeout=5.0)
            client.send("frame")
            return client, None
        except (OSError, RuntimeError) as problem:
            error = problem
            if client is not None:
                client.close()
            time.sleep(0.5)
    return None, error


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5959
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    client, error = wait_for_endpoint(port, 300.0)
    if client is None:
        print(f"probe: no debug endpoint on 127.0.0.1:{port} ({error})")
        return 1

    def frame_number() -> int:
        try:
            return client.frame()
        except (OSError, RuntimeError):
            return -1

    deadline = time.time() + 300.0
    while frame_number() < first and time.time() < deadline:
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
            reply = client.send(f"{kind} {address:X} {count}").strip()
            values.append(reply)
            row.append(reply)
        line = " | ".join(row)
        if previous is not None:
            marks = ["same" if a == b else "CHANGED" for a, b in zip(values, previous)]
            line += "   << " + ",".join(
                label for (label, _, _), mark in zip(WATCH, marks) if mark == "CHANGED"
            )
        print(line)
        previous = values
        time.sleep(0.4)

    print("\nprobe: guest execution denominators")
    print(client.send("guest"))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
