#!/usr/bin/env python3
"""Verify Tekken 3's measured projection and retail clipping owners.

The COP2 census deliberately delegates instruction validity to psxport's shipping
decoder. This title tool owns only Tekken's measured addresses and relationships;
it does not exempt resident data that resembles an instruction or reproduce the
framework decoder.

Exit 0 means the executable agrees, exit 1 means real bytes disagree, and exit 2
means no valid comparison was possible.
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

try:
    import decode
except ImportError as exc:
    raise SystemExit(
        "REFUSED: cannot import psxport's shipping instruction decoder; "
        "run tools/psxport_sync.py --auto or set PSXPORT_DIR"
    ) from exc


def require_object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Refused(f"manifest field {field} must be an object")
    return value


def require_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise Refused(f"manifest field {field} must be a list")
    return value


def require_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise Refused(f"manifest field {field} must be an integer")
    return value


def parse_address_list(value: object, field: str) -> tuple[int, ...]:
    return tuple(
        parse_hex(item, f"{field}[{index}]")
        for index, item in enumerate(require_list(value, field))
    )


def decoded_words(image: Any):
    for address in range(image.load, image.text_end, 4):
        yield decode.decode(address, image.word(address))


def call_census(image: Any, target: int) -> tuple[int, ...]:
    return tuple(
        instruction.addr
        for instruction in decoded_words(image)
        if instruction.kind == decode.JUMP
        and instruction.op == "jal"
        and instruction.target == target
    )


def check_exact(label: str, measured: object, expected: object) -> None:
    if measured != expected:
        raise Mismatch(f"{label}: measured {measured!r}, expected {expected!r}")


def projection_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    return require_object(manifest.get("projection"), "projection")


def verify_control_writers(projection: Mapping[str, Any], image: Any) -> int:
    entries = require_list(projection.get("control_writers"), "projection.control_writers")
    expected: list[tuple[int, int, int]] = []
    for index, value in enumerate(entries):
        field = f"projection.control_writers[{index}]"
        entry = require_object(value, field)
        expected.append(
            (
                parse_hex(entry.get("address"), f"{field}.address"),
                require_int(entry.get("source_register"), f"{field}.source_register"),
                require_int(entry.get("control_register"), f"{field}.control_register"),
            )
        )
    if len(set(expected)) != len(expected):
        raise Refused("projection.control_writers contains duplicate entries")

    measured = sorted(
        (instruction.addr, instruction.rt, instruction.rd)
        for instruction in decoded_words(image)
        if instruction.kind == decode.GTE_MOVE
        and instruction.op == "ctc2"
        and instruction.rd in (24, 25, 26)
    )
    check_exact("canonical CR24/CR25/CR26 writer census", measured, sorted(expected))
    return len(expected)


def verify_leaf_calls(
    projection: Mapping[str, Any], image: Any, field: str
) -> tuple[int, int]:
    leaf = require_object(projection.get(field), f"projection.{field}")
    target = parse_hex(leaf.get("address"), f"projection.{field}.address")
    expected = parse_address_list(
        leaf.get("call_sites"), f"projection.{field}.call_sites"
    )
    if len(set(expected)) != len(expected):
        raise Refused(f"projection.{field}.call_sites contains duplicates")
    check_exact(f"{field} direct-call census", call_census(image, target), expected)
    return target, len(expected)


def int_sequence(value: object, field: str, length: int) -> tuple[int, ...]:
    items = require_list(value, field)
    if len(items) != length:
        raise Refused(f"manifest field {field} must contain {length} integers")
    return tuple(require_int(item, f"{field}[{index}]") for index, item in enumerate(items))


def verify_presets(projection: Mapping[str, Any], image: Any) -> tuple[int, int]:
    presets = require_object(projection.get("display_presets"), "projection.display_presets")
    address = parse_hex(presets.get("address"), "projection.display_presets.address")
    entries = require_list(presets.get("entries"), "projection.display_presets.entries")
    if not entries:
        raise Refused("projection.display_presets.entries must not be empty")

    initial_h_values: set[int] = set()
    for index, value in enumerate(entries):
        field = f"projection.display_presets.entries[{index}]"
        entry = require_object(value, field)
        active_rect = int_sequence(entry.get("active_rect"), f"{field}.active_rect", 4)
        view_extent = int_sequence(entry.get("view_extent"), f"{field}.view_extent", 2)
        graph_flags = require_int(entry.get("graph_flags"), f"{field}.graph_flags")
        second_buffer_y = require_int(
            entry.get("second_buffer_y"), f"{field}.second_buffer_y"
        )
        expected_words = (*active_rect, *view_extent, graph_flags, second_buffer_y)
        measured_words = struct.unpack_from(
            "<8H", image.text, address - image.load + index * 16
        )
        check_exact(f"display preset {index}", measured_words, expected_words)

        center = int_sequence(
            entry.get("initial_projection_center"),
            f"{field}.initial_projection_center",
            2,
        )
        check_exact(
            f"display preset {index} derived centre",
            center,
            (view_extent[0] // 2, view_extent[1] // 2),
        )
        initial_h_values.add(require_int(entry.get("initial_h"), f"{field}.initial_h"))

    boot = require_object(projection.get("boot_preset_call"), "projection.boot_preset_call")
    boot_address = parse_hex(boot.get("address"), "projection.boot_preset_call.address")
    boot_target = parse_hex(boot.get("target"), "projection.boot_preset_call.target")
    boot_index = require_int(boot.get("preset_index"), "projection.boot_preset_call.preset_index")
    if not 0 <= boot_index < len(entries):
        raise Refused("projection.boot_preset_call.preset_index is outside the preset table")
    boot_call = decode.decode(boot_address, image.word(boot_address))
    check_exact("boot preset call mnemonic", (boot_call.kind, boot_call.op), (decode.JUMP, "jal"))
    check_exact("boot preset call target", boot_call.target, boot_target)
    boot_delay = decode.decode(boot_address + 4, image.word(boot_address + 4))
    check_exact(
        "boot preset index delay slot",
        (boot_delay.kind, boot_delay.op, boot_delay.rs, boot_delay.rt, boot_delay.rd),
        (decode.ALU_RRR, "addu", 0, 0, 4),
    )
    check_exact("boot preset index", boot_index, 0)

    initial_h = require_object(projection.get("initial_h_call"), "projection.initial_h_call")
    h_address = parse_hex(initial_h.get("address"), "projection.initial_h_call.address")
    h_target = parse_hex(initial_h.get("target"), "projection.initial_h_call.target")
    h_delay_word = parse_hex(
        initial_h.get("delay_slot_word"), "projection.initial_h_call.delay_slot_word"
    )
    h_call = decode.decode(h_address, image.word(h_address))
    check_exact("initial H call mnemonic", (h_call.kind, h_call.op), (decode.JUMP, "jal"))
    check_exact("initial H call target", h_call.target, h_target)
    check_exact("initial H delay word", image.word(h_address + 4), h_delay_word)
    h_delay = decode.decode(h_address + 4, h_delay_word)
    check_exact(
        "initial H delay semantics",
        (h_delay.kind, h_delay.op, h_delay.rs, h_delay.rt),
        (decode.ALU_RRI, "addiu", 0, 4),
    )
    check_exact("preset H agreement", initial_h_values, {h_delay.simm})

    first = require_object(entries[0], "projection.display_presets.entries[0]")
    first_active = int_sequence(first.get("active_rect"), "preset 0 active_rect", 4)
    first_view = int_sequence(first.get("view_extent"), "preset 0 view_extent", 2)
    if first_active[2] == first_view[0]:
        raise Mismatch("boot active display width unexpectedly equals title projection width")
    return len(entries), 4


def verify_stage_visibility(projection: Mapping[str, Any], image: Any) -> int:
    stage = require_object(projection.get("stage_visibility"), "projection.stage_visibility")
    parse_hex(stage.get("owner"), "projection.stage_visibility.owner")
    selector = parse_hex(stage.get("selector"), "projection.stage_visibility.selector")
    calls = require_list(stage.get("calls"), "projection.stage_visibility.calls")
    expected_calls: list[int] = []
    for index, value in enumerate(calls):
        field = f"projection.stage_visibility.calls[{index}]"
        call = require_object(value, field)
        address = parse_hex(call.get("address"), f"{field}.address")
        load_address = parse_hex(call.get("angle_load_address"), f"{field}.angle_load_address")
        angle = require_int(call.get("retail_angle"), f"{field}.retail_angle")
        expected_calls.append(address)
        instruction = decode.decode(load_address, image.word(load_address))
        check_exact(
            f"stage angle load {index}",
            (instruction.kind, instruction.op, instruction.rs, instruction.rt, instruction.simm),
            (decode.ALU_RRI, "addiu", 0, 4, angle),
        )
    if len(set(expected_calls)) != len(expected_calls):
        raise Refused("projection.stage_visibility.calls contains duplicate addresses")
    check_exact("stage selector direct-call census", call_census(image, selector), tuple(expected_calls))
    return len(calls) * 2


def verify_retail_right_bound(projection: Mapping[str, Any], image: Any) -> int:
    bound = require_object(projection.get("retail_right_bound"), "projection.retail_right_bound")
    value = require_int(bound.get("value"), "projection.retail_right_bound.value")
    render_sites = parse_address_list(
        bound.get("render_sites"), "projection.retail_right_bound.render_sites"
    )
    retail_2d_site = parse_hex(
        bound.get("retail_2d_site"), "projection.retail_right_bound.retail_2d_site"
    )
    expected = (*render_sites, retail_2d_site)
    if len(set(expected)) != len(expected):
        raise Refused("projection.retail_right_bound sites contain duplicates")
    measured = tuple(
        instruction.addr
        for instruction in decoded_words(image)
        if instruction.kind == decode.ALU_RRI
        and instruction.op in ("addi", "addiu")
        and instruction.simm == -value
    )
    check_exact(
        "complete signed retail right-bound census", measured, tuple(sorted(expected))
    )
    return len(expected)


def verify_projection(manifest: Mapping[str, Any], executable: pathlib.Path) -> None:
    verify_executable(manifest, executable)
    try:
        image = psexe.load(str(executable))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot load {executable}: {exc}") from exc
    projection = projection_manifest(manifest)

    writer_count = verify_control_writers(projection, image)
    _, offset_call_count = verify_leaf_calls(projection, image, "set_geom_offset")
    _, screen_call_count = verify_leaf_calls(projection, image, "set_geom_screen")
    preset_count, preset_call_count = verify_presets(projection, image)
    stage_count = verify_stage_visibility(projection, image)
    bound_count = verify_retail_right_bound(projection, image)
    fact_count = (
        writer_count
        + offset_call_count
        + screen_call_count
        + preset_count
        + preset_call_count
        + stage_count
        + bound_count
    )
    print(
        f"[projection] MATCH {fact_count}/{fact_count} measured facts: "
        f"{writer_count} canonical CR24/25/26 writers, "
        f"{offset_call_count + screen_call_count} projection-leaf calls, "
        f"{preset_count} display/view presets, {stage_count // 2} stage-wedge calls, "
        f"{bound_count - 1} render bounds plus one retail-2D bound"
    )
    print(
        "[projection] blind spot: static ownership is proven, but no frame or pixel output is; "
        "same-CPU execution after IRQ reset 0x80085DA4 remains the next runtime boundary"
    )


def manifest_for_bytes(manifest: Mapping[str, Any], data: bytes) -> dict[str, Any]:
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

    with tempfile.TemporaryDirectory(prefix="projection-selftest-", dir=scratch) as temp:
        directory = pathlib.Path(temp)

        def check(candidate_manifest: Mapping[str, Any], candidate_data: bytes) -> type[Exception] | None:
            path = directory / "SLUS_004.02"
            path.write_bytes(candidate_data)
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    verify_projection(candidate_manifest, path)
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        results.append(("real executable matches", check(manifest, data) is None))

        writer_address = 0x80081C9C
        reserved_writer = mutate_word(
            data, image, writer_address, image.word(writer_address) | 1
        )
        results.append(
            (
                "reserved-bit COP2 writer is rejected by the shared decoder",
                check(manifest_for_bytes(manifest, reserved_writer), reserved_writer) is Mismatch,
            )
        )

        data_word_address = 0x800BAC20
        canonical_data_word = mutate_word(
            data, image, data_word_address, image.word(data_word_address) & ~0x7FF
        )
        results.append(
            (
                "new canonical data-shaped writer changes the complete census",
                check(manifest_for_bytes(manifest, canonical_data_word), canonical_data_word)
                is Mismatch,
            )
        )

        preset_address = 0x800B0CC8
        wrong_preset = bytearray(data)
        struct.pack_into(
            "<H", wrong_preset, 0x800 + preset_address - image.load + 4, 367
        )
        wrong_preset_bytes = bytes(wrong_preset)
        results.append(
            (
                "changed active-display width is rejected",
                check(manifest_for_bytes(manifest, wrong_preset_bytes), wrong_preset_bytes)
                is Mismatch,
            )
        )

        bound_address = 0x8006CD40
        wrong_bound = mutate_word(
            data,
            image,
            bound_address,
            (image.word(bound_address) & 0xFFFF0000) | ((-367) & 0xFFFF),
        )
        results.append(
            (
                "changed stage right bound is rejected",
                check(manifest_for_bytes(manifest, wrong_bound), wrong_bound) is Mismatch,
            )
        )

        call_address = 0x80080E84
        wrong_call = mutate_word(data, image, call_address, image.word(call_address) + 1)
        results.append(
            (
                "changed projection call target is rejected",
                check(manifest_for_bytes(manifest, wrong_call), wrong_call) is Mismatch,
            )
        )

        missing_projection = copy.deepcopy(manifest)
        del missing_projection["projection"]
        results.append(
            (
                "missing projection manifest is refused",
                check(missing_projection, data) is Refused,
            )
        )

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"projection selftest: {passed_count}/{len(results)} cases")
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
        help="exercise real agreement, disagreement, and refusal through this verifier",
    )
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return 0 if selftest(args.exe) else 1
        verify_projection(load_manifest(MANIFEST), args.exe)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
