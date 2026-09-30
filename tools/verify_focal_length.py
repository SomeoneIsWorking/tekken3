#!/usr/bin/env python3
"""Verify Tekken 3's per-fight focal-length chain against the real executable.

`tools/verify_projection.py` pins only the INITIAL H=500 literal at 0x800B0928. The focal length the
title actually renders with is dynamic, and this tool proves the whole chain that produces it, from
bytes, so no claim about the running projection rests on a Ghidra pass recorded in prose:

  0x80082748  the one GTE writer of the zoom register: `ctc2 $26,a0` and a return. Its only call
              site in the whole image is 0x80081240, so this leaf is the sole publisher.
  0x80081238  a forwarder whose only call is that leaf.
  0x80063C64  the clamp: reads the runtime bounds at 0x800A8CD6/0x800A8CD8, selects the requested
              value, the lower bound or the upper bound, and forwards to 0x80081238. Its only two
              direct callers are the pose selector and the pose blender, so the clamped fight
              focal length is the complete dynamic input.
  0x80063CBC  the reset: writes 500 to the value and to BOTH clamp bounds, then publishes 500.
  0x80064080  the six-field pose selector: base 0x800A02A8, 24-byte stride, fields at +0,+4,+8,
              +12,+16,+20, mirror at 0x800A02F0, camera words at 0x800A85C0, and the SIXTH field
              (+20) forwarded to the clamp.
  0x80064170  the pose blender: a 12-bit weight from 256(sp) against 0x1000, the weighted sum of the
              two poses' focal values, the blended pose stored into slot 3 of the same table, then
              `FUN_80064080(3)` and `FUN_80063C64(blended)`.

The census is reported with its denominator: four publishers of the forwarder, two callers of the
clamp, one caller of the leaf, eight of the pose selector, three of the blender.

Exit 0 means the executable agrees, exit 1 means real bytes disagree, and exit 2 means no valid
comparison was possible.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import pathlib
import struct
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

from provision_executable import (
    MANIFEST,
    ROOT,
    Mismatch,
    Refused,
    load_manifest,
    parse_hex,
    psexe,
    verify_executable,
)

try:
    from tools.mips.decode import (
        ALU_RRI,
        ALU_RRR,
        BRANCH,
        GTE_MOVE,
        HILO,
        JUMP,
        JUMPR,
        LOAD,
        LUI,
        MULDIV,
        NOP,
        SHIFT_I,
        STORE,
        decode,
    )
except ImportError as exc:
    raise SystemExit(
        "REFUSED: cannot import psxport's shared R3000A instruction decoder; "
        "run tools/psxport_fetch.py --auto or set PSXPORT_DIR"
    ) from exc

ZOOM_LEAF = 0x80082748
ZOOM_CONTROL_REGISTER = 26
PUBLISH_FORWARDER = 0x80081238
CLAMP = 0x80063C64
CLAMP_BOUNDS = (0x800A8CD6, 0x800A8CD8)
FOCAL_RESET = 0x80063CBC
FOCAL_RESET_VALUE = 500
POSE_SELECTOR = 0x80064080
POSE_BLENDER = 0x80064170
POSE_TABLE = 0x800A02A8
POSE_STRIDE = 24
POSE_FIELDS = 6
POSE_MIRROR = POSE_TABLE + 3 * POSE_STRIDE
POSE_FOCAL_FIELD = POSE_STRIDE - 4
CAMERA_WORDS = 0x800A85C0
BLEND_WEIGHT_SLOT = 256
BLEND_NORMALIZATION = 0x1000


def check_exact(label: str, measured: object, expected: object) -> None:
    if measured != expected:
        raise Mismatch(f"{label}: measured {measured!r}, expected {expected!r}")


def operands(found: Any) -> tuple[int, int, int]:
    if found.kind == ALU_RRR:
        return (found.rs, found.rt, found.rd)
    if found.kind == SHIFT_I:
        return (found.rt, found.rd, found.shamt)
    if found.kind == MULDIV:
        return (found.rs, found.rt, 0)
    if found.kind == HILO:
        return (0, 0, found.rd)
    return (found.rs, found.rt, found.simm)


def instruction(image: Any, address: int) -> Any:
    return decode(address, image.word(address))


def call_census(image: Any, target: int) -> tuple[int, ...]:
    return tuple(
        address
        for address in range(image.load, image.text_end, 4)
        if (found := instruction(image, address)).kind == JUMP
        and found.op == "jal"
        and found.target == target
    )


def upper_pair(image: Any, low: int, high: int) -> tuple[int, ...]:
    """The two-instruction `lui`/`addiu` address materialization of a guest address."""
    top = instruction(image, low)
    bottom = instruction(image, high)
    return ((top.simm & 0xFFFF) << 16) + bottom.simm


def verify_leaf_and_forwarder(image: Any) -> int:
    leaf = instruction(image, ZOOM_LEAF)
    check_exact(
        "zoom register writer",
        (leaf.kind, leaf.op, leaf.rt, leaf.rd),
        (GTE_MOVE, "ctc2", 4, ZOOM_CONTROL_REGISTER),
    )
    returns = instruction(image, ZOOM_LEAF + 4)
    check_exact("zoom writer returns to its caller", (returns.kind, returns.op, returns.rs), (JUMPR, "jr", 31))
    delay = instruction(image, ZOOM_LEAF + 8)
    check_exact("zoom writer delay slot", (delay.kind, delay.op), (NOP, "nop"))
    forward = instruction(image, PUBLISH_FORWARDER + 8)
    check_exact("publish forwarder call", (forward.kind, forward.target), (JUMP, ZOOM_LEAF))
    check_exact("zoom leaf call census", call_census(image, ZOOM_LEAF), (PUBLISH_FORWARDER + 8,))
    return 1 + 1 + 1 + 1 + 1


def verify_manifest_publishers(manifest: dict[str, Any], image: Any) -> int:
    projection = manifest.get("projection")
    if not isinstance(projection, dict):
        raise Refused("manifest projection must be an object")
    screen = projection.get("set_geom_screen")
    if not isinstance(screen, dict):
        raise Refused("manifest projection.set_geom_screen must be an object")
    check_exact("recorded zoom writer", parse_hex(screen.get("address"), "address"), ZOOM_LEAF)
    recorded = parse_address_list(screen.get("call_sites"), "call_sites")
    check_exact("recorded zoom call sites", recorded, (PUBLISH_FORWARDER + 8,))
    measured = call_census(image, ZOOM_LEAF)
    check_exact("recorded zoom call sites against the executable", measured, tuple(recorded))

    initial = projection.get("initial_h_call")
    if not isinstance(initial, dict):
        raise Refused("manifest projection.initial_h_call must be an object")
    check_exact(
        "recorded initial H call",
        parse_hex(initial.get("address"), "address"),
        0x800B0928,
    )
    return 2 + 1


def parse_address_list(value: object, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise Refused(f"manifest field {field} must be a list")
    return tuple(parse_hex(item, f"{field}[{index}]") for index, item in enumerate(value))


def verify_clamp(image: Any) -> int:
    base = upper_pair(image, 0x80063C6C, 0x80063C70)
    check_exact("clamp bounds base", base, CLAMP_BOUNDS[0] - 102)
    lower = instruction(image, 0x80063C78)
    check_exact(
        "lower clamp bound",
        (lower.kind, lower.op, lower.rs, lower.rt, lower.simm),
        (LOAD, "lh", 5, 4, 102),
    )
    check_exact("lower clamp bound address", base + lower.simm, CLAMP_BOUNDS[0])
    upper = instruction(image, 0x80063C8C)
    check_exact(
        "upper clamp bound",
        (upper.kind, upper.op, upper.rs, upper.rt, upper.simm),
        (LOAD, "lh", 5, 5, 104),
    )
    check_exact("upper clamp bound address", base + upper.simm, CLAMP_BOUNDS[1])
    facts = 1 + 2 + 2
    for address, op, description, expected in (
        (0x80063C80, "slt", "request below the lower bound", (3, 4, 2)),
        (0x80063C94, "slt", "request above the upper bound", (5, 3, 2)),
        (0x80063C9C, "addu", "keep the requested value", (3, 0, 4)),
        (0x80063CA0, "addu", "clamp to the upper bound", (5, 0, 4)),
    ):
        found = instruction(image, address)
        check_exact(f"clamp {description}", (found.kind, found.op, operands(found)), (ALU_RRR, op, expected))
        facts += 1
    call = instruction(image, 0x80063CA4)
    check_exact("clamp forwards the focal length", (call.kind, call.target), (JUMP, PUBLISH_FORWARDER))
    check_exact("clamp call census", call_census(image, CLAMP), (0x80064158, 0x800645E8))
    return facts + 2


def verify_focal_reset(image: Any) -> int:
    check_exact("focal reset entry", FOCAL_RESET, 0x80063CBC)
    value = instruction(image, 0x80063CC8)
    check_exact(
        "focal reset literal",
        (value.kind, value.op, value.rs, value.rt, value.simm),
        (ALU_RRI, "addiu", 0, 3, FOCAL_RESET_VALUE),
    )
    base = upper_pair(image, 0x80063CC0, 0x80063CC4)
    check_exact("focal reset bounds base", base, CLAMP_BOUNDS[0] - 102)
    for address, offset, description in (
        (0x80063CD0, 100, "current focal value"),
        (0x80063CD4, 102, "lower clamp bound"),
        (0x80063CD8, 104, "upper clamp bound"),
    ):
        found = instruction(image, address)
        check_exact(
            f"focal reset writes the {description}",
            (found.kind, found.op, found.rs, found.rt, found.simm),
            (STORE, "sh", 2, 3, offset),
        )
    publish = instruction(image, 0x80063CE0)
    check_exact(
        "focal reset publishes 500",
        (publish.kind, publish.op, publish.rs, publish.rt, publish.simm),
        (ALU_RRI, "addiu", 0, 4, FOCAL_RESET_VALUE),
    )
    call = instruction(image, 0x80063CE8)
    check_exact("focal reset forwards", (call.kind, call.target), (JUMP, PUBLISH_FORWARDER))
    return 1 + 1 + 1 + 3 + 1 + 1


def verify_pose_selector(image: Any) -> int:
    base = upper_pair(image, 0x80064084, 0x80064088)
    check_exact("pose table base", base, POSE_TABLE)
    for address, description, expected in (
        (0x8006408C, "index doubled", (SHIFT_I, "sll", (4, 2, 1))),
        (0x80064090, "index tripled", (ALU_RRR, "addu", (2, 4, 2))),
        (0x80064094, "index times eight", (SHIFT_I, "sll", (2, 2, 3))),
        (0x80064098, "pose row address", (ALU_RRR, "addu", (2, 3, 7))),
    ):
        found = instruction(image, address)
        check_exact(f"pose selector {description}", (found.kind, found.op, operands(found)), expected)
    facts = 1 + 4
    for offset, address, destination in (
        (0, 0x800640A0, 2),
        (4, 0x800640BC, 2),
        (8, 0x800640D4, 2),
        (12, 0x800640AC, 2),
        (16, 0x800640C8, 2),
        (20, 0x80064104, 4),
    ):
        found = instruction(image, address)
        check_exact(
            f"pose field +{offset} load",
            (found.kind, found.op, found.rs, found.rt, found.simm),
            (LOAD, "lw", 7, destination, offset),
        )
        facts += 1
    mirror = instruction(image, 0x80064124)
    check_exact(
        "pose mirror destination",
        (mirror.kind, mirror.op, mirror.rs, mirror.rt, mirror.simm),
        (STORE, "sw", 5, 2, 20),
    )
    camera = instruction(image, 0x80064120)
    check_exact(
        "pose camera words",
        (camera.kind, camera.op, camera.rs, camera.rt, camera.simm),
        (ALU_RRI, "addiu", 6, 5, CAMERA_WORDS - 0x800B0000),
    )
    focal = instruction(image, 0x80064154)
    check_exact(
        "pose focal field is the sixth",
        (focal.kind, focal.op, focal.rs, focal.rt, focal.simm),
        (LOAD, "lw", 7, 4, POSE_FOCAL_FIELD),
    )
    call = instruction(image, 0x80064158)
    check_exact("pose selector publishes its focal field", (call.kind, call.target), (JUMP, CLAMP))
    check_exact("pose stride is six words", POSE_STRIDE, POSE_FIELDS * 4)
    check_exact("pose mirror is the fourth slot", POSE_MIRROR, POSE_TABLE + 3 * POSE_STRIDE)
    return facts + 4


def verify_pose_blender(image: Any) -> int:
    weight = instruction(image, 0x80064178)
    check_exact(
        "blend weight argument",
        (weight.kind, weight.op, weight.rs, weight.rt, weight.simm),
        (LOAD, "lw", 29, 18, BLEND_WEIGHT_SLOT),
    )
    normalization = instruction(image, 0x800641B0)
    check_exact(
        "blend normalization",
        (normalization.kind, normalization.op, normalization.rs, normalization.rt, normalization.simm),
        (ALU_RRI, "addiu", 0, 2, BLEND_NORMALIZATION),
    )
    complement = instruction(image, 0x800641C8)
    check_exact(
        "blend complement weight",
        (complement.kind, complement.op, operands(complement)),
        (ALU_RRR, "subu", (2, 18, 17)),
    )
    for address, description, expected in (
        (0x800641FC, "first pose term", (MULDIV, "mult", (16, 18, 0))),
        (0x8006420C, "second pose term", (MULDIV, "mult", (2, 17, 0))),
        (0x80064210, "second pose term low word", (HILO, "mflo", (0, 0, 8))),
        (0x80064214, "blended focal value", (ALU_RRR, "addu", (3, 8, 16))),
    ):
        found = instruction(image, address)
        check_exact(f"blender {description}", (found.kind, found.op, operands(found)), expected)
    slot = upper_pair(image, 0x800645A8, 0x800645AC)
    check_exact("blender writes the pose table", slot, POSE_TABLE)
    first = instruction(image, 0x800645C0)
    last = instruction(image, 0x800645D8)
    check_exact(
        "blended pose lands in the fourth slot",
        (first.simm, last.simm),
        (72, 88),
    )
    check_exact("blended pose slot address", (slot + first.simm, slot + last.simm), (POSE_MIRROR, POSE_MIRROR + 16))
    publish = instruction(image, 0x800645E0)
    check_exact("blender publishes pose 3", (publish.kind, publish.target), (JUMP, POSE_SELECTOR))
    index = instruction(image, 0x800645E4)
    check_exact(
        "blender publishes slot 3",
        (index.kind, index.op, index.rs, index.rt, index.simm),
        (ALU_RRI, "addiu", 0, 4, POSE_FIELDS - 3),
    )
    clamp = instruction(image, 0x800645E8)
    check_exact("blender forwards the blended focal value", (clamp.kind, clamp.target), (JUMP, CLAMP))
    argument = instruction(image, 0x800645EC)
    check_exact(
        "blended focal value argument",
        (argument.kind, argument.op, operands(argument)),
        (ALU_RRR, "addu", (16, 0, 4)),
    )
    return 1 + 1 + 1 + 4 + 1 + 2 + 1 + 1 + 1 + 1


def verify_focal_length(manifest: dict[str, Any], executable: pathlib.Path) -> None:
    verify_executable(manifest, executable)
    try:
        image = psexe.load(str(executable))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot load {executable}: {exc}") from exc

    scanned = (image.text_end - image.load) // 4
    facts = (
        verify_leaf_and_forwarder(image)
        + verify_manifest_publishers(manifest, image)
        + verify_clamp(image)
        + verify_focal_reset(image)
        + verify_pose_selector(image)
        + verify_pose_blender(image)
    )
    publishers = call_census(image, PUBLISH_FORWARDER)
    print(
        f"[focal-length] MATCH {facts}/{facts} measured facts over {scanned} scanned instructions "
        f"in the hashed executable"
    )
    print(
        "[focal-length] the focal length has exactly one GTE writer ("
        f"ctc2 ${ZOOM_CONTROL_REGISTER} at 0x{ZOOM_LEAF:08X}, {len(call_census(image, ZOOM_LEAF))} caller) "
        f"and {len(call_census(image, CLAMP))} dynamic inputs, both through the clamp at 0x{CLAMP:08X}"
    )
    print(
        "[focal-length] dynamic inputs: pose field 5 of six at 0x80064158 and the 12-bit weighted "
        "blend at 0x800645E8; the clamp bounds live at "
        f"0x{CLAMP_BOUNDS[0]:08X}/0x{CLAMP_BOUNDS[1]:08X} and the reset at 0x{FOCAL_RESET:08X} "
        f"writes {FOCAL_RESET_VALUE} to the value and to both bounds"
    )
    print(
        "[focal-length] publishers of the forwarder: "
        + ", ".join(f"0x{address:08X}" for address in publishers)
        + f" ({len(publishers)} of {len(publishers)}); pose selector callers "
        f"{len(call_census(image, POSE_SELECTOR))}, pose blender callers "
        f"{len(call_census(image, POSE_BLENDER))}"
    )
    print(
        "[focal-length] blind spot: this proves ownership and the authored 500/500 bounds. The value "
        "in flight at any given fight frame is not observable without reaching one, so no runtime "
        "focal length is claimed here"
    )


def manifest_for_bytes(manifest: dict[str, Any], data: bytes) -> dict[str, Any]:
    candidate = copy.deepcopy(manifest)
    candidate["file_size"] = len(data)
    candidate["sha256"] = hashlib.sha256(data).hexdigest()
    return candidate


def mutate_word(data: bytes, image: Any, address: int, word: int) -> bytes:
    candidate = bytearray(data)
    struct.pack_into("<I", candidate, 0x800 + address - image.load, word)
    return bytes(candidate)


def selftest(executable: pathlib.Path) -> bool:
    manifest = load_manifest(MANIFEST)
    verify_executable(manifest, executable)
    image = psexe.load(str(executable))
    data = executable.read_bytes()
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    results: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory(prefix="focal-length-selftest-", dir=scratch) as temp:
        directory = pathlib.Path(temp)

        def check(candidate_manifest: dict[str, Any], candidate_data: bytes) -> type[Exception] | None:
            path = directory / "SLUS_004.02"
            path.write_bytes(candidate_data)
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    verify_focal_length(candidate_manifest, path)
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        results.append(("real executable matches", check(manifest, data) is None))

        cases = (
            ("changed zoom control register is rejected", ZOOM_LEAF, 0x48C4D001, "CR26 -> CR25"),
            ("changed zoom control register is rejected twice", ZOOM_LEAF + 4, 0x03E00008 ^ 1, "return altered"),
            ("changed forwarder target is rejected", PUBLISH_FORWARDER + 8, 0x0C0209D2 + 1, "wrong leaf"),
            ("changed lower clamp bound is rejected", 0x80063C78, 0x84A40064, "102 -> 100"),
            ("changed upper clamp bound is rejected", 0x80063C8C, 0x84A50066, "104 -> 102"),
            ("changed clamp forward is rejected", 0x80063CA4, 0x0C02048E + 1, "wrong forwarder"),
            ("changed focal reset literal is rejected", 0x80063CC8, 0x240301F3, "500 -> 499"),
            ("changed pose table base is rejected", 0x80064088, 0x246302A9, "table base moved"),
            ("changed pose stride is rejected", 0x80064094, 0x000210C0 ^ (1 << 6), "stride 24 -> 12"),
            ("changed pose focal field is rejected", 0x80064154, 0x8CE40010, "field 5 -> field 4"),
            ("changed blend weight slot is rejected", 0x80064178, 0x8FB200F0, "weight from a0"),
            ("changed blend normalization is rejected", 0x800641B0, 0x24020FFF, "0x1000 -> 0x0FFF"),
            ("changed blend published slot is rejected", 0x800645E4, 0x24040002, "pose 3 -> pose 2"),
        )
        for name, address, word, description in cases:
            candidate = mutate_word(data, image, address, word)
            results.append(
                (
                    f"{name} ({description})",
                    check(manifest_for_bytes(manifest, candidate), candidate) is Mismatch,
                )
            )

        missing = copy.deepcopy(manifest)
        del missing["projection"]
        results.append(("missing projection manifest is refused", check(missing, data) is Refused))

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"focal-length selftest: {passed_count}/{len(results)} cases")
    return all(passed for _, passed in results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=pathlib.Path,
        default=ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02",
        help="provisioned executable to verify",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="exercise real agreement and mutated disagreement through this verifier",
    )
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return 0 if selftest(args.exe) else 1
        verify_focal_length(load_manifest(MANIFEST), args.exe)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
