#!/usr/bin/env python3
"""Verify Tekken 3's direct-to-main startup model against a real executable.

This tool deliberately uses Tekken vocabulary: the entry's first call is ``game_main``,
not a framework ``libcInit`` boundary. It checks the machine-code structure recorded in
``titles/tekken3/executable.json``; Ghidra supplies the independent semantic evidence
that the target initializes the game and then enters its non-returning frame loop.

Exit 0 means identity and all startup structure agree, exit 1 means real bytes disagree,
and exit 2 means no valid comparison was possible.
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
from collections.abc import Mapping, Sequence
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


def jump_target(address: int, word: int, opcode: int, label: str) -> int:
    measured_opcode = word >> 26
    if measured_opcode != opcode:
        raise Mismatch(
            f"{label} at 0x{address:08X} has opcode {measured_opcode}, expected {opcode}"
        )
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def is_call(word: int) -> bool:
    opcode = word >> 26
    return opcode == 3 or (opcode == 0 and (word & 0x3F) == 9)


def startup_fields(manifest: Mapping[str, Any]) -> dict[str, int | str]:
    startup = manifest.get("startup")
    if not isinstance(startup, dict):
        raise Refused("manifest field startup must be an object")
    entry_call = startup.get("entry_call")
    main_first_call = startup.get("main_first_call")
    first_initializer = startup.get("first_initializer")
    main_next_call = startup.get("main_next_call")
    main_loop = startup.get("main_loop")
    if (
        not isinstance(entry_call, dict)
        or not isinstance(main_first_call, dict)
        or not isinstance(first_initializer, dict)
        or not isinstance(main_next_call, dict)
        or not isinstance(main_loop, dict)
    ):
        raise Refused(
            "startup entry_call, main_first_call, first_initializer, main_next_call, "
            "and main_loop must be objects"
        )
    shape = startup.get("shape")
    if shape != "direct_main":
        raise Refused(f"unsupported startup shape {shape!r}; expected 'direct_main'")
    return {
        "shape": shape,
        "call_address": parse_hex(
            entry_call.get("address"), "startup.entry_call.address"
        ),
        "call_target": parse_hex(entry_call.get("target"), "startup.entry_call.target"),
        "delay_slot": str(entry_call.get("delay_slot")),
        "guard_address": parse_hex(
            entry_call.get("return_guard_address"),
            "startup.entry_call.return_guard_address",
        ),
        "return_guard": str(entry_call.get("return_guard")),
        "main_call_address": parse_hex(
            main_first_call.get("address"), "startup.main_first_call.address"
        ),
        "main_call_target": parse_hex(
            main_first_call.get("target"), "startup.main_first_call.target"
        ),
        "main_call_delay_word": parse_hex(
            main_first_call.get("delay_slot_word"),
            "startup.main_first_call.delay_slot_word",
        ),
        "initializer_end": parse_hex(
            first_initializer.get("end_address"),
            "startup.first_initializer.end_address",
        ),
        "initializer_return": parse_hex(
            first_initializer.get("return_address"),
            "startup.first_initializer.return_address",
        ),
        "initializer_return_delay_word": parse_hex(
            first_initializer.get("return_delay_slot_word"),
            "startup.first_initializer.return_delay_slot_word",
        ),
        "next_call_address": parse_hex(
            main_next_call.get("address"), "startup.main_next_call.address"
        ),
        "next_call_target": parse_hex(
            main_next_call.get("target"), "startup.main_next_call.target"
        ),
        "next_call_delay_word": parse_hex(
            main_next_call.get("delay_slot_word"),
            "startup.main_next_call.delay_slot_word",
        ),
        "back_edge_address": parse_hex(
            main_loop.get("back_edge_address"),
            "startup.main_loop.back_edge_address",
        ),
        "back_edge_target": parse_hex(
            main_loop.get("back_edge_target"),
            "startup.main_loop.back_edge_target",
        ),
    }


def verify_startup(manifest: Mapping[str, Any], executable: pathlib.Path) -> None:
    verify_executable(manifest, executable)
    try:
        image = psexe.load(str(executable))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot load {executable}: {exc}") from exc
    fields = startup_fields(manifest)
    call_address = int(fields["call_address"])
    call_target = int(fields["call_target"])
    guard_address = int(fields["guard_address"])
    main_call_address = int(fields["main_call_address"])
    main_call_target = int(fields["main_call_target"])
    main_call_delay_word = int(fields["main_call_delay_word"])
    initializer_end = int(fields["initializer_end"])
    initializer_return = int(fields["initializer_return"])
    initializer_return_delay_word = int(fields["initializer_return_delay_word"])
    next_call_address = int(fields["next_call_address"])
    next_call_target = int(fields["next_call_target"])
    next_call_delay_word = int(fields["next_call_delay_word"])
    back_edge_address = int(fields["back_edge_address"])
    back_edge_target = int(fields["back_edge_target"])

    if call_address < image.entry or call_address >= image.text_end:
        raise Mismatch(f"entry call 0x{call_address:08X} is outside the entry image")
    earlier_calls = [
        address
        for address in range(image.entry, call_address, 4)
        if is_call(image.word(address))
    ]
    if earlier_calls:
        raise Mismatch(
            "tracked game_main call is not the entry's first call; earlier call(s): "
            + ", ".join(f"0x{address:08X}" for address in earlier_calls)
        )

    measured_target = jump_target(
        call_address, image.word(call_address), 3, "entry game_main call"
    )
    if measured_target != call_target:
        raise Mismatch(
            f"entry game_main target is 0x{measured_target:08X}, expected 0x{call_target:08X}"
        )
    if not image.load <= call_target < image.text_end:
        raise Mismatch(f"game_main target 0x{call_target:08X} is outside the image")
    if fields["delay_slot"] != "nop" or image.word(call_address + 4) != 0:
        raise Mismatch("entry game_main call does not have the tracked nop delay slot")
    if guard_address != call_address + 8:
        raise Refused("return guard must immediately follow the game_main delay slot")
    guard_word = image.word(guard_address)
    if (
        fields["return_guard"] != "break"
        or (guard_word >> 26) != 0
        or (guard_word & 0x3F) != 0x0D
    ):
        raise Mismatch(
            f"game_main return guard at 0x{guard_address:08X} is not a MIPS break"
        )

    if not call_target <= main_call_address < back_edge_address:
        raise Mismatch("game_main first call is outside the one-time initialization prefix")
    earlier_main_calls = [
        address
        for address in range(call_target, main_call_address, 4)
        if is_call(image.word(address))
    ]
    if earlier_main_calls:
        raise Mismatch(
            "tracked initializer is not game_main's first call; earlier call(s): "
            + ", ".join(f"0x{address:08X}" for address in earlier_main_calls)
        )
    measured_main_target = jump_target(
        main_call_address,
        image.word(main_call_address),
        3,
        "game_main first call",
    )
    if measured_main_target != main_call_target:
        raise Mismatch(
            f"game_main first call targets 0x{measured_main_target:08X}, "
            f"expected 0x{main_call_target:08X}"
        )
    if not image.load <= main_call_target < image.text_end:
        raise Mismatch(
            f"game_main first-call target 0x{main_call_target:08X} is outside the image"
        )
    measured_delay_word = image.word(main_call_address + 4)
    if measured_delay_word != main_call_delay_word:
        raise Mismatch(
            f"game_main first-call delay word is 0x{measured_delay_word:08X}, "
            f"expected 0x{main_call_delay_word:08X}"
        )

    if not main_call_target <= initializer_return < initializer_end <= image.text_end:
        raise Refused("first initializer return range is empty or outside the image")
    if initializer_end != initializer_return + 8:
        raise Refused("first initializer end must follow its return delay slot")
    if image.word(initializer_return) != 0x03E00008:
        raise Mismatch(
            f"first initializer instruction at 0x{initializer_return:08X} is not jr ra"
        )
    measured_initializer_delay = image.word(initializer_return + 4)
    if measured_initializer_delay != initializer_return_delay_word:
        raise Mismatch(
            "first initializer return delay word is "
            f"0x{measured_initializer_delay:08X}, expected "
            f"0x{initializer_return_delay_word:08X}"
        )

    if next_call_address != main_call_address + 8:
        raise Refused("game_main next call must immediately follow the first call delay slot")
    measured_next_target = jump_target(
        next_call_address,
        image.word(next_call_address),
        3,
        "game_main next call",
    )
    if measured_next_target != next_call_target:
        raise Mismatch(
            f"game_main next call targets 0x{measured_next_target:08X}, "
            f"expected 0x{next_call_target:08X}"
        )
    if not image.load <= next_call_target < image.text_end:
        raise Mismatch(f"game_main next-call target 0x{next_call_target:08X} is outside the image")
    measured_next_delay = image.word(next_call_address + 4)
    if measured_next_delay != next_call_delay_word:
        raise Mismatch(
            f"game_main next-call delay word is 0x{measured_next_delay:08X}, "
            f"expected 0x{next_call_delay_word:08X}"
        )

    measured_back_target = jump_target(
        back_edge_address,
        image.word(back_edge_address),
        2,
        "game_main loop back-edge",
    )
    if measured_back_target != back_edge_target:
        raise Mismatch(
            f"game_main back-edge targets 0x{measured_back_target:08X}, "
            f"expected 0x{back_edge_target:08X}"
        )
    if not call_target <= back_edge_target < back_edge_address:
        raise Mismatch(
            "game_main back-edge does not target an earlier address inside game_main"
        )

    print(
        "[startup] MATCH 18/18 direct-main structural facts: "
        f"entry first-call 0x{call_address:08X}->0x{call_target:08X}, "
        f"main first-call 0x{main_call_address:08X}->0x{main_call_target:08X}, "
        f"initializer return 0x{initializer_return:08X}->0x{next_call_address:08X}, "
        f"next call ->0x{next_call_target:08X}, return guard break, "
        f"loop 0x{back_edge_address:08X}->0x{back_edge_target:08X}"
    )
    print(
        "[startup] semantic witness: Ghidra FUN_80079c70 calls FUN_80028ba0 then traps; "
        "FUN_80028ba0 initializes once and loops forever (titles/tekken3/README.md)"
    )
    print(
        "[startup] blind spot: this verifier models structure only; tools/boot_oracle.py separately "
        "tests execution to the call boundary, not a generated substrate or gameplay"
    )


def fixture_executable() -> bytearray:
    data = bytearray(0x900)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<II", data, 0x10, 0x80010000, 0)
    struct.pack_into("<II", data, 0x18, 0x80010000, 0x100)
    struct.pack_into("<II", data, 0x30, 0x801FFF00, 0x40)

    def store(address: int, word: int) -> None:
        struct.pack_into("<I", data, 0x800 + address - 0x80010000, word)

    store(0x80010010, (3 << 26) | ((0x80010040 >> 2) & 0x03FFFFFF))
    store(0x80010014, 0)
    store(0x80010018, 0x0000000D)
    store(0x80010040, 0x27BDFFE0)
    store(0x80010044, 0xAFBF001C)
    store(0x80010048, (3 << 26) | ((0x800100A0 >> 2) & 0x03FFFFFF))
    store(0x8001004C, 0xAFB00010)
    store(0x80010050, (3 << 26) | ((0x800100C0 >> 2) & 0x03FFFFFF))
    store(0x80010054, 0xAFB1000C)
    store(0x80010080, (2 << 26) | ((0x80010050 >> 2) & 0x03FFFFFF))
    store(0x800100A0, 0x27BDFFF0)
    store(0x800100B8, 0x03E00008)
    store(0x800100BC, 0x00000000)
    return data


def fixture_manifest(data: bytes) -> dict[str, Any]:
    return {
        "title": "startup fixture",
        "region": "test",
        "serial": "TEST",
        "disc_executable": "TEST.EXE",
        "output_name": "TEST.EXE",
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "header": {
            "entry": "0x80010000",
            "gp": "0x00000000",
            "text_address": "0x80010000",
            "text_size": "0x00000100",
            "stack_address": "0x801FFF00",
            "stack_offset": "0x00000040",
        },
        "startup": {
            "shape": "direct_main",
            "entry_call": {
                "address": "0x80010010",
                "target": "0x80010040",
                "delay_slot": "nop",
                "return_guard_address": "0x80010018",
                "return_guard": "break",
            },
            "main_first_call": {
                "address": "0x80010048",
                "target": "0x800100A0",
                "delay_slot_word": "0xAFB00010",
            },
            "first_initializer": {
                "end_address": "0x800100C0",
                "return_address": "0x800100B8",
                "return_delay_slot_word": "0x00000000",
            },
            "main_next_call": {
                "address": "0x80010050",
                "target": "0x800100C0",
                "delay_slot_word": "0xAFB1000C",
            },
            "main_loop": {
                "back_edge_address": "0x80010080",
                "back_edge_target": "0x80010050",
            },
        },
    }


def selftest() -> bool:
    results: list[tuple[str, bool]] = []
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="startup-selftest-", dir=scratch) as temp:
        directory = pathlib.Path(temp)
        data = fixture_executable()
        executable = directory / "TEST.EXE"
        executable.write_bytes(data)
        manifest = fixture_manifest(data)

        def check(
            candidate: Mapping[str, Any], path: pathlib.Path = executable
        ) -> type[Exception] | None:
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    verify_startup(candidate, path)
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        results.append(("direct-main fixture matches", check(manifest) is None))

        wrong_call = copy.deepcopy(manifest)
        wrong_call["startup"]["entry_call"]["target"] = "0x80010044"
        results.append(
            ("wrong game_main target is rejected", check(wrong_call) is Mismatch)
        )

        wrong_guard_data = bytearray(data)
        struct.pack_into("<I", wrong_guard_data, 0x800 + 0x18, 0)
        wrong_guard = directory / "wrong-guard.exe"
        wrong_guard.write_bytes(wrong_guard_data)
        wrong_guard_manifest = fixture_manifest(wrong_guard_data)
        results.append(
            (
                "missing return guard is rejected",
                check(wrong_guard_manifest, wrong_guard) is Mismatch,
            )
        )

        wrong_loop = copy.deepcopy(manifest)
        wrong_loop["startup"]["main_loop"]["back_edge_target"] = "0x80010030"
        results.append(
            ("wrong loop back-edge is rejected", check(wrong_loop) is Mismatch)
        )

        wrong_main_call = copy.deepcopy(manifest)
        wrong_main_call["startup"]["main_first_call"]["target"] = "0x800100A4"
        results.append(
            ("wrong game_main first-call target is rejected", check(wrong_main_call) is Mismatch)
        )

        wrong_main_delay = copy.deepcopy(manifest)
        wrong_main_delay["startup"]["main_first_call"]["delay_slot_word"] = "0x00000000"
        results.append(
            ("wrong game_main call delay is rejected", check(wrong_main_delay) is Mismatch)
        )

        wrong_initializer_return = copy.deepcopy(manifest)
        wrong_initializer_return["startup"]["first_initializer"]["return_address"] = (
            "0x800100B4"
        )
        results.append(
            (
                "wrong initializer return is rejected",
                check(wrong_initializer_return) is Refused,
            )
        )

        wrong_next_call = copy.deepcopy(manifest)
        wrong_next_call["startup"]["main_next_call"]["target"] = "0x800100C4"
        results.append(
            ("wrong next initializer target is rejected", check(wrong_next_call) is Mismatch)
        )

        wrong_next_delay = copy.deepcopy(manifest)
        wrong_next_delay["startup"]["main_next_call"]["delay_slot_word"] = "0x00000000"
        results.append(
            ("wrong next initializer delay is rejected", check(wrong_next_delay) is Mismatch)
        )

        wrong_shape = copy.deepcopy(manifest)
        wrong_shape["startup"]["shape"] = "libc_boundary"
        results.append(
            ("foreign startup vocabulary is refused", check(wrong_shape) is Refused)
        )

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"startup selftest: {passed_count}/{len(results)} cases")
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
        help="exercise agreement, disagreement, and refusal through the shipping verifier",
    )
    args = parser.parse_args(argv)
    if args.selftest:
        return 0 if selftest() else 1
    try:
        verify_startup(load_manifest(MANIFEST), args.exe)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
