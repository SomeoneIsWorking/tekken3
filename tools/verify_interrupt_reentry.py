#!/usr/bin/env python3
"""Verify Tekken 3's two resident interrupt re-entry seeds from retail code.

The first seed is the saved return PC of the game's setjmp-style context save. The
second is the caller return after B(19) HookEntryInt. Both addresses are inside the
interrupt initializer rather than ordinary function starts, so they belong only in
``main_reentry``. Exit 0 means the executable, seed file, and generated router agree;
exit 1 means they disagree; exit 2 means the check cannot establish a comparison.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
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

SEEDS = ROOT / "game" / "recomp_seeds.json"
GENERATED = ROOT / "generated" / "port"


def require_object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise Refused(f"manifest field {field} must be an object")
    return value


def jump_target(address: int, word: int, label: str) -> int:
    if word >> 26 != 3:
        raise Mismatch(f"{label} at 0x{address:08X} is not jal")
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def branch_target(address: int, word: int, label: str) -> int:
    if word >> 26 != 4:
        raise Mismatch(f"{label} at 0x{address:08X} is not beq")
    displacement = struct.unpack("<h", struct.pack("<H", word & 0xFFFF))[0]
    return address + 4 + displacement * 4


def materialized_address(lui_word: int, addiu_word: int) -> int:
    if (
        lui_word >> 26 != 0x0F
        or ((lui_word >> 16) & 0x1F) != 16
        or addiu_word >> 26 != 0x09
        or ((addiu_word >> 21) & 0x1F) != 16
        or ((addiu_word >> 16) & 0x1F) != 16
    ):
        raise Mismatch("interrupt context base is not materialized as lui/addiu s0,s0")
    high = (lui_word & 0xFFFF) << 16
    low = struct.unpack("<h", struct.pack("<H", addiu_word & 0xFFFF))[0]
    return (high + low) & 0xFFFFFFFF


def uncommented_json(path: pathlib.Path) -> Mapping[str, Any]:
    try:
        text = path.read_text()
        value = json.loads(
            "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("//")
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"cannot read recompiler seeds from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Refused(f"recompiler seeds in {path} must be an object")
    return value


def seed_addresses(data: Mapping[str, Any], field: str) -> tuple[int, ...]:
    values = data.get(field, [])
    if not isinstance(values, list):
        raise Refused(f"seed field {field} must be a list")
    return tuple(
        parse_hex(value, f"{field}[{index}]") for index, value in enumerate(values)
    )


def interrupt_fields(manifest: Mapping[str, Any]) -> dict[str, int]:
    startup = require_object(manifest.get("startup"), "startup")
    frontier = require_object(
        startup.get("hardware_frontier"), "startup.hardware_frontier"
    )
    context = require_object(
        frontier.get("interrupt_context_save"),
        "startup.hardware_frontier.interrupt_context_save",
    )
    bios = require_object(
        frontier.get("bios_call"), "startup.hardware_frontier.bios_call"
    )
    fields = {
        "context_start": parse_hex(
            context.get("start"), "interrupt_context_save.start"
        ),
        "context_end": parse_hex(context.get("end"), "interrupt_context_save.end"),
        "base_load": parse_hex(
            context.get("caller_base_load"), "interrupt_context_save.caller_base_load"
        ),
        "base_add": parse_hex(
            context.get("caller_base_add"), "interrupt_context_save.caller_base_add"
        ),
        "buffer": parse_hex(context.get("buffer"), "interrupt_context_save.buffer"),
        "call": parse_hex(
            context.get("call_address"), "interrupt_context_save.call_address"
        ),
        "call_delay": parse_hex(
            context.get("call_delay_word"), "interrupt_context_save.call_delay_word"
        ),
        "resume": parse_hex(
            context.get("resume_address"), "interrupt_context_save.resume_address"
        ),
        "resume_word": parse_hex(
            context.get("resume_word"), "interrupt_context_save.resume_word"
        ),
        "resume_target": parse_hex(
            context.get("resume_branch_target"),
            "interrupt_context_save.resume_branch_target",
        ),
        "hook_call": parse_hex(bios.get("call_address"), "bios_call.call_address"),
        "hook_word": parse_hex(bios.get("call_word"), "bios_call.call_word"),
        "hook_return": parse_hex(
            bios.get("return_address"), "bios_call.return_address"
        ),
        "hook_wrapper": parse_hex(bios.get("wrapper"), "bios_call.wrapper"),
    }
    return fields


def verify_generated_entry(generated: pathlib.Path, address: int) -> None:
    declarations = generated / "rec_decls.h"
    dispatcher = generated / "shard_disp.c"
    if not declarations.is_file() or not dispatcher.is_file():
        raise Refused(f"generated router is incomplete under {generated}")
    declaration = f"void gen_func_{address:08X}(Core*); void func_{address:08X}(Core*);"
    dispatch_case = (
        f"case 0x{address & 0x1FFFFFFF:08X}u: func_{address:08X}(c); return;"
    )
    if declarations.read_text().count(declaration) != 1:
        raise Mismatch(
            f"generated declarations do not contain exactly one 0x{address:08X} entry"
        )
    if dispatcher.read_text().count(dispatch_case) != 1:
        raise Mismatch(
            f"generated router does not contain exactly one 0x{address:08X} dispatch case"
        )


def verify_interrupt_reentry(
    manifest: Mapping[str, Any],
    executable: pathlib.Path,
    seeds_path: pathlib.Path = SEEDS,
    generated: pathlib.Path = GENERATED,
) -> None:
    verify_executable(manifest, executable)
    try:
        image = psexe.load(str(executable))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot load {executable}: {exc}") from exc
    fields = interrupt_fields(manifest)

    context_start = fields["context_start"]
    if image.word(context_start) != 0xAC9F0000:
        raise Mismatch("context saver does not store ra at jmp_buf +0")
    if fields["context_end"] != context_start + 0x3C:
        raise Refused("tracked context-save range does not cover the 15-word save path")
    if image.word(context_start + 0x30) != 0x00001021:
        raise Mismatch("context saver does not return zero in v0 on its initial path")
    if (
        image.word(context_start + 0x34) != 0x03E00008
        or image.word(context_start + 0x38) != 0
    ):
        raise Mismatch("context saver does not return through jr ra / nop")

    base = materialized_address(
        image.word(fields["base_load"]), image.word(fields["base_add"])
    )
    if base + 56 != fields["buffer"]:
        raise Mismatch(
            f"context call derives buffer 0x{base + 56:08X}, expected 0x{fields['buffer']:08X}"
        )
    call = fields["call"]
    if (
        jump_target(call, image.word(call), "interrupt context-save call")
        != context_start
    ):
        raise Mismatch("interrupt context-save call targets the wrong function")
    if image.word(call + 4) != fields["call_delay"]:
        raise Mismatch(
            "interrupt context-save call no longer passes s0 + 56 in its delay slot"
        )
    if fields["resume"] != call + 8:
        raise Refused("tracked context resume is not the call's saved ra")
    if image.word(fields["resume"]) != fields["resume_word"]:
        raise Mismatch("saved interrupt resume instruction changed")
    resume_word = image.word(fields["resume"])
    if ((resume_word >> 21) & 0x1F, (resume_word >> 16) & 0x1F) != (2, 0):
        raise Mismatch("saved interrupt resume does not branch on setjmp's v0 return")
    if (
        branch_target(fields["resume"], resume_word, "interrupt resume")
        != fields["resume_target"]
    ):
        raise Mismatch(
            "saved interrupt resume branches to the wrong initial-entry path"
        )

    hook_call = fields["hook_call"]
    if image.word(hook_call) != fields["hook_word"]:
        raise Mismatch("HookEntryInt wrapper call word changed")
    if (
        jump_target(hook_call, image.word(hook_call), "HookEntryInt wrapper call")
        != fields["hook_wrapper"]
    ):
        raise Mismatch("HookEntryInt wrapper call targets the wrong function")
    if fields["hook_return"] != hook_call + 8:
        raise Refused("tracked HookEntryInt return is not the call's saved ra")

    seeds = uncommented_json(seeds_path)
    reentries = seed_addresses(seeds, "main_reentry")
    expected = (fields["resume"], fields["hook_return"])
    if reentries != expected:
        raise Mismatch(
            "main_reentry must contain only the ordered measured continuations "
            + ", ".join(f"0x{address:08X}" for address in expected)
        )
    duplicated = set(reentries) & set(seed_addresses(seeds, "main"))
    if duplicated:
        raise Mismatch(
            "interrupt continuations are duplicated in main and main_reentry"
        )
    for address in expected:
        verify_generated_entry(generated, address)

    print(
        "[interrupt-reentry] MATCH 14/14 facts: "
        f"jmp_buf 0x{fields['buffer']:08X} saves 0x{fields['resume']:08X}, "
        f"HookEntryInt returns at 0x{fields['hook_return']:08X}, and both generated routes exist"
    )
    print(
        "[interrupt-reentry] boundary: the observed IRQ entered 0x80085DC4, but no later "
        "runtime, frame, audio, input, or gameplay behavior is claimed"
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

    with tempfile.TemporaryDirectory(
        prefix="interrupt-reentry-selftest-", dir=scratch
    ) as temp:
        directory = pathlib.Path(temp)
        candidate_executable = directory / "SLUS_004.02"
        candidate_seeds = directory / "recomp_seeds.json"

        def check(
            candidate_manifest: Mapping[str, Any],
            candidate_data: bytes,
            seed_text: str,
        ) -> type[Exception] | None:
            candidate_executable.write_bytes(candidate_data)
            candidate_seeds.write_text(seed_text)
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    verify_interrupt_reentry(
                        candidate_manifest,
                        candidate_executable,
                        candidate_seeds,
                        GENERATED,
                    )
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        seed_text = SEEDS.read_text()
        results.append(
            (
                "real executable, seeds, and generated router match",
                check(manifest, data, seed_text) is None,
            )
        )

        wrong_call = mutate_word(data, image, 0x80085DBC, image.word(0x80085DBC) + 1)
        results.append(
            (
                "changed context-save target is rejected",
                check(manifest_for_bytes(manifest, wrong_call), wrong_call, seed_text)
                is Mismatch,
            )
        )

        wrong_resume = mutate_word(data, image, 0x80085DC4, 0)
        results.append(
            (
                "changed saved resume instruction is rejected",
                check(
                    manifest_for_bytes(manifest, wrong_resume), wrong_resume, seed_text
                )
                is Mismatch,
            )
        )

        missing_seed = seed_text.replace('"0x80085DC4", ', "", 1)
        results.append(
            (
                "missing runtime-observed continuation is rejected",
                check(manifest, data, missing_seed) is Mismatch,
            )
        )

        duplicated_seed = seed_text.replace('"main": []', '"main": ["0x80085DC4"]', 1)
        results.append(
            (
                "duplicated main/main_reentry authority is rejected",
                check(manifest, data, duplicated_seed) is Mismatch,
            )
        )

        missing_manifest = copy.deepcopy(manifest)
        del missing_manifest["startup"]["hardware_frontier"]["interrupt_context_save"]
        results.append(
            (
                "missing interrupt context manifest is refused",
                check(missing_manifest, data, seed_text) is Refused,
            )
        )

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"interrupt reentry selftest: {passed_count}/{len(results)} cases")
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
        verify_interrupt_reentry(load_manifest(MANIFEST), args.exe)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
