#!/usr/bin/env python3
"""Emit Tekken's measured Getstat response-publication boundary.

The matching C++ test runs this shipping-recompiler output and the identity-checked executable in
psxport's interpreter from the same controller state. This file owns only emission and manifest
validation; the observed CPU, guest RAM, and controller results come from the two execution engines.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from provision_executable import MANIFEST, Refused, load_manifest, parse_hex
from recomp_boundary import FunctionSlice, load_recompiler, sha256, write_if_changed

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
DEFAULT_OUTPUT = ROOT / "generated"
SOURCE = "cd_response_slices.c"
METADATA = "cd_response_slices.json"


def measured_boundary(
    manifest: dict[str, object],
) -> tuple[int, int, int, tuple[FunctionSlice, ...], dict[str, int]]:
    raw = manifest.get("cd_response_boundary")
    if not isinstance(raw, dict):
        raise Refused("manifest field cd_response_boundary must be an object")
    entry = parse_hex(raw.get("entry"), "cd_response_boundary.entry")
    sentinel = parse_hex(raw.get("sentinel"), "cd_response_boundary.sentinel")
    stack = parse_hex(raw.get("stack"), "cd_response_boundary.stack")
    raw_functions = raw.get("functions")
    if not isinstance(raw_functions, list) or not raw_functions:
        raise Refused("cd_response_boundary.functions must be a non-empty array")
    functions: list[FunctionSlice] = []
    for index, item in enumerate(raw_functions):
        if not isinstance(item, dict):
            raise Refused(f"cd_response_boundary.functions[{index}] must be an object")
        start = parse_hex(
            item.get("start"), f"cd_response_boundary.functions[{index}].start"
        )
        end = parse_hex(item.get("end"), f"cd_response_boundary.functions[{index}].end")
        if end <= start or (end - start) % 4:
            raise Refused(
                f"cd_response_boundary.functions[{index}] is not a non-empty aligned range"
            )
        functions.append(
            FunctionSlice(
                f"CD response function {start:08X}",
                start,
                end,
                f"tekken3_cd_{start:08X}_body",
            )
        )
    if entry not in {item.start for item in functions}:
        raise Refused(
            "cd_response_boundary.entry is not one of the measured function starts"
        )
    raw_data = raw.get("data")
    if not isinstance(raw_data, dict):
        raise Refused("cd_response_boundary.data must be an object")
    data = {
        name: parse_hex(value, f"cd_response_boundary.data.{name}")
        for name, value in raw_data.items()
    }
    required = {
        "sync_callback",
        "sync_callback_target",
        "current_libcd_command",
        "getstat_int3_route",
        "ack_buffer",
        "state_command",
        "published_status",
        "response_copy",
        "callback_class",
        "cd_state",
        "cd_substate",
        "cd_init_step",
        "motor_on_flag",
        "cd_init_fields",
        "getstat_response_length",
    }
    if data.keys() != required:
        raise Refused(
            f"cd_response_boundary.data keys differ: missing={sorted(required - data.keys())} extra={sorted(data.keys() - required)}"
        )
    return entry, sentinel, stack, tuple(functions), data


def render(executable: pathlib.Path) -> tuple[str, dict[str, object]]:
    manifest = load_manifest(MANIFEST)
    entry, sentinel, stack, functions, data = measured_boundary(manifest)
    header = manifest.get("header")
    if not isinstance(header, dict):
        raise Refused("manifest field header must be an object")
    text_start = (
        parse_hex(header.get("text_address"), "header.text_address") & 0x1FFFFFFF
    )
    text_size = parse_hex(header.get("text_size"), "header.text_size")
    text_end = text_start + text_size
    emitter, psexe = load_recompiler()
    image = psexe.load(str(executable))
    raw_functions = manifest["cd_response_boundary"]["functions"]
    for index, item in enumerate(functions):
        expected = parse_hex(
            raw_functions[index].get("entry_word"),
            f"cd_response_boundary.functions[{index}].entry_word",
        )
        actual = image.word(item.start)
        if actual != expected:
            raise Refused(
                f"CD response entry word differs at 0x{item.start:08X}: 0x{actual:08X}, expected 0x{expected:08X}"
            )
    if image.word(data["getstat_int3_route"]) != 0:
        raise Refused("Getstat's measured INT3 route-table entry is no longer zero")
    if image.word(data["getstat_response_length"]) != 1:
        raise Refused("Getstat's measured response length is no longer one byte")

    known_entries = {item.start for item in functions}
    emitted: list[str] = []
    for item in functions:
        body: list[str] = []
        emitter.emit_func(
            image,
            item.start,
            item.end,
            known_entries,
            body,
            item.body_name,
            emitter.MAIN_NAMES,
        )
        emitted.extend(body)
        emitted.extend(
            ("", f"void func_{item.start:08X}(Core* c) {{ {item.body_name}(c); }}", "")
        )

    address_functions = {
        "tekken3_cd_response_entry": entry,
        "tekken3_cd_response_sentinel": sentinel,
        "tekken3_cd_response_stack": stack,
        "tekken3_cd_response_text_start": text_start,
        "tekken3_cd_response_text_end": text_end,
        **{f"tekken3_cd_{name}": address for name, address in data.items()},
    }
    source = "\n".join(
        (
            "// GENERATED by psxport tools/recomp/emit.py — DO NOT EDIT.",
            '#include "core.h"',
            *(f"void func_{item.start:08X}(Core*);" for item in functions),
            "",
            *emitted,
            "void tekken3_cd_response_dispatch(Core* c, uint32_t address) {",
            "  switch (address) {",
            *(
                line
                for item in functions
                for line in (
                    f"  case 0x{item.start:08X}u:",
                    f"    func_{item.start:08X}(c);",
                    "    return;",
                )
            ),
            "  default:",
            "    rec_dispatch_miss(c, address);",
            "  }",
            "}",
            "",
            "int tekken3_cd_response_func_index(uint32_t address) {",
            "  switch (address) {",
            *(
                f"  case 0x{item.start:08X}u: return {index};"
                for index, item in enumerate(functions)
            ),
            "  default: return -1;",
            "  }",
            "}",
            "",
            *(
                line
                for name, address in address_functions.items()
                for line in (f"uint32_t {name}() {{ return 0x{address:08X}u; }}",)
            ),
            "void tekken3_cd_response_run(Core* c) {",
            f"  func_{entry:08X}(c);",
            "}",
            "",
        )
    )
    metadata = {
        "emitter_version": emitter.RECOMP_VERSION,
        "executable_sha256": sha256(executable),
        "entry": f"0x{entry:08X}",
        "resident_text": [f"0x{text_start:08X}", f"0x{text_end:08X}"],
        "functions": [
            {
                "start": f"0x{item.start:08X}",
                "end": f"0x{item.end:08X}",
                "instructions": item.instructions,
            }
            for item in functions
        ],
    }
    return source, metadata


def emit(executable: pathlib.Path, output: pathlib.Path) -> None:
    source, metadata = render(executable)
    output.mkdir(parents=True, exist_ok=True)
    write_if_changed(output / SOURCE, source)
    write_if_changed(
        output / METADATA, json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )
    print(
        f"PASS CD response emission: {sum(item['instructions'] for item in metadata['functions'])} measured instructions"
    )


def check(executable: pathlib.Path, output: pathlib.Path) -> None:
    source, metadata = render(executable)
    expected = {
        SOURCE: source,
        METADATA: json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    }
    for name, content in expected.items():
        path = output / name
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Refused(
                f"cannot read generated CD response boundary {path}: {exc}"
            ) from exc
        if actual != content:
            raise Refused(
                f"generated CD response boundary differs from shipping emitter: {path}"
            )
    print(
        "PASS CD response source integrity: 2/2 generated files match shipping emission"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--exe", type=pathlib.Path, default=DEFAULT_EXE)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        if args.emit:
            emit(args.exe, args.output)
        else:
            check(args.exe, args.output)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
