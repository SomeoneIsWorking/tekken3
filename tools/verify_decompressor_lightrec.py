#!/usr/bin/env python3
"""Compare Tekken 3's original LZ guest call with a bounded asset-backed decoder."""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import struct
import subprocess
import sys

from provision_executable import Mismatch, Refused, load_manifest, verify_executable

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = 0x800BAFCC
MAX_OUTPUT = 0x8240


def reference_decode(image: bytes) -> tuple[int, bytes]:
    text_address = struct.unpack_from("<I", image, 0x18)[0]
    text_size = struct.unpack_from("<I", image, 0x1C)[0]
    offset = 0x800 + SOURCE - text_address
    end = 0x800 + text_size
    if offset < 0x800 or offset >= end or end > len(image):
        raise Refused("authenticated source is outside the loaded text")
    source = image[offset:end]
    cursor = 0
    output = bytearray()
    while cursor < len(source):
        control = source[cursor]
        cursor += 1
        if control == 0:
            return cursor, bytes(output)
        while control > 1:
            if control & 1:
                if cursor >= len(source):
                    raise Refused("literal exceeds mapped source")
                output.append(source[cursor])
                cursor += 1
            else:
                if cursor + 2 > len(source):
                    raise Refused("back-reference exceeds mapped source")
                token = (source[cursor] << 8) | source[cursor + 1]
                cursor += 2
                length = (token >> 11) or 32
                distance = (token & 0x7FF) or 2048
                if distance > len(output):
                    raise Refused("back-reference precedes output start")
                if len(output) + length > MAX_OUTPUT:
                    raise Refused("output exceeds guest wrapper bound")
                for _ in range(length):
                    output.append(output[-distance])
            if len(output) > MAX_OUTPUT:
                raise Refused("output exceeds guest wrapper bound")
            control >>= 1
    raise Refused(f"no LZ terminator in {len(source)} mapped source bytes")


def arm(line: str) -> dict[str, str]:
    fields = dict(re.findall(r"([a-z_][a-z_0-9]*)=([^ ]+)", line))
    required = {"arm", "reached", "exit", "pc", "cycles", "budget", "blocks",
                "instructions", "fallback_calls", "output_bytes", "output_bounded", "v0",
                "source_cursor"}
    if missing := required - fields.keys():
        raise Refused(f"guest test omitted fields: {', '.join(sorted(missing))}")
    return fields


def compare(stdout: str, expected: bytes, compressed_bytes: int) -> None:
    captured = stdout.splitlines()
    lines = [line for line in captured if line.startswith(("arm=", "output_hex="))]
    if len(lines) != 3 or not lines[1].startswith("output_hex="):
        preview = [(len(line), line[:160]) for line in captured]
        raise Refused(f"guest test did not report both arms and output; stdout lines={preview}")
    normal = arm(lines[0])
    negative = arm(lines[2])
    if normal["arm"] != "normal" or negative["arm"] != "negative":
        raise Refused("guest test arms are missing or reversed")
    if normal["reached"] != "1" or normal["blocks"] == "0" or normal["fallback_calls"] != "0":
        raise Refused("shipping Lightrec guest execution was not reached without fallback")
    if normal["output_bounded"] != "1":
        raise Refused("guest output pointer was not bounded in main RAM")
    if normal["exit"] not in {"guest-return", "budget-exhausted"}:
        raise Refused(f"guest call exited unexpectedly: {normal['exit']} at {normal['pc']}")
    observed = bytes.fromhex(lines[1].removeprefix("output_hex="))
    count = int(normal["output_bytes"])
    if len(observed) != count or count == 0 or count > len(expected):
        raise Refused("guest output length is absent or outside decoded extent")
    if observed != expected[:count]:
        first = next(i for i, (left, right) in enumerate(zip(observed, expected)) if left != right)
        raise Mismatch(f"guest output differs from decoder at byte {first}/{count}")
    consumed = int(normal["source_cursor"], 16) - SOURCE
    if not 0 <= consumed <= compressed_bytes:
        raise Refused(f"guest source cursor is outside encoded stream: {consumed}/{compressed_bytes}")
    if normal["exit"] == "guest-return" and (
        count != len(expected) or int(normal["v0"]) != len(expected) or consumed != compressed_bytes
    ):
        raise Mismatch("guest returned without the complete decoded stream and length")
    if (negative["reached"] != "1" or negative["exit"] != "budget-exhausted"
            or negative["budget"] != "1" or negative["blocks"] == "0"
            or negative["output_bytes"] != "0" or negative["fallback_calls"] != "0"):
        raise Refused("one-cycle negative control did not show a reached Lightrec budget exit")
    print(f"[lightrec-lz] normal exit={normal['exit']} pc={normal['pc']} cycles={normal['cycles']}/{normal['budget']} "
          f"source={consumed}/{compressed_bytes} output_prefix={count}/{len(expected)} exact=1 "
          f"blocks={normal['blocks']} fallback=0")
    print(f"[lightrec-lz] negative reached=1 exit={negative['exit']} "
          f"cycles={negative['cycles']}/{negative['budget']} blocks={negative['blocks']} fallback=0")


def selftest() -> None:
    image = bytearray(0x900)
    struct.pack_into("<II", image, 0x18, SOURCE, 0x100)
    image[0x800:0x803] = b"\x03A\x00"
    assert reference_decode(image) == (3, b"A")
    image[0x800:0x804] = b"\x02\x20\x01\x00"
    try:
        reference_decode(image)
    except Refused:
        pass
    else:
        raise AssertionError("pre-start back-reference was accepted")
    normal = ("arm=normal reached=1 exit=guest-return pc=0x8004CA9C cycles=10 "
              "budget=564480 blocks=2 instructions=5 fallback_calls=0 output_bytes=1 "
              "output_bounded=1 v0=1 source_cursor=0x800BAFCF")
    negative = ("arm=negative reached=1 exit=budget-exhausted pc=0x80031BFC "
                "cycles=12 budget=1 blocks=1 instructions=6 fallback_calls=0 "
                "output_bytes=0 output_bounded=1 v0=0 source_cursor=0x800BAFCD")
    transcript = f"logger line\n{normal}\noutput_hex=41\n{negative}\n"
    compare(transcript, b"A", 3)
    try:
        compare(transcript.replace("output_hex=41", "output_hex=42"), b"A", 3)
    except Mismatch:
        pass
    else:
        raise AssertionError("mismatching guest byte was accepted")
    print("[lightrec-lz] selftest passed matching, mismatch, and malformed input")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--exe", type=pathlib.Path, default=ROOT / "scratch/bin/tekken3/SLUS_004.02")
    parser.add_argument("--binary", type=pathlib.Path, default=ROOT / "build/ci/tekken3_decompressor_lightrec")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    try:
        image = verify_executable(load_manifest(), args.exe)
        compressed_bytes, expected = reference_decode(image)
        print(f"[lightrec-lz] decoder source={compressed_bytes} output={len(expected)} "
              f"sha256={hashlib.sha256(expected).hexdigest()}")
        environment = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="dummy")
        process = subprocess.Popen([args.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment)
        print(f"[lightrec-lz] owned guest test pid={process.pid} timeout=30s", flush=True)
        try:
            stdout, stderr = process.communicate(input=image, timeout=30)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise Refused(f"guest test timed out; killed owned pid={process.pid}") from exc
        if process.returncode:
            raise Refused(f"guest test pid={process.pid} exited {process.returncode}: {stderr.decode(errors='replace')}")
        diagnostic = ROOT / "scratch/diagnostics/decompressor-lightrec.stdout"
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        diagnostic.write_bytes(stdout)
        print(f"[lightrec-lz] retained guest stdout at {diagnostic}")
        compare(stdout.decode(), expected, compressed_bytes)
        print(f"[lightrec-lz] owned guest test pid={process.pid} exited 0")
    except (Refused, Mismatch, OSError, ValueError) as exc:
        print(f"[lightrec-lz] FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
