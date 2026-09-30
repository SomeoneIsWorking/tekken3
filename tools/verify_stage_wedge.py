#!/usr/bin/env python3
"""Verify Tekken 3's recovered stage-tile visibility wedge against the real executable.

`FUN_8006D95C` is the last horizontal culling owner the title owns: the stage owner `FUN_8006D014`
hands it one authored wedge word and it returns one word per cell of a 6x6 stage-tile block. This
tool proves the facts the native owner in `game/core/widescreen.*` is built from, so the port's
`Tekken3StageWedge` rests on bytes rather than on a transliteration nobody can check.

The facts that decide whether the wedge is a direction or an extent:

  * the authored wedge reaches the selector as `a0` and the selector consumes that register exactly
    once, by the halving shift at 0x8006D960;
  * the halved wedge is combined with the negated camera heading and masked into a 0x1000-unit turn
    (0x8006D9F0, 0x8006D9FC, 0x8006DAD0, 0x8006DAD4) and used only to index two tables;
  * those tables are exactly round(sin(2*pi*i/4096)*4096) and round(cos(2*pi*i/4096)*4096) over all
    4096 entries each, so 0x1000 is one full turn and the amplitude is Q12. No focal length, view
    width, or draw width appears anywhere in the selection.

The facts that decide whether a native port is the same function:

  * the block geometry the stage initializer `FUN_8006C95C` publishes (tile 10*unit, both origins
    -30*unit, step scale 7*unit) and the four measured words those relations produce for the retail
    wedges;
  * the block cell permutation at 0x80025804 is the identity, so a cell address is row*6 + column;
  * the 6x6 bounds tests, the 36-word zero fill, the block clamp, the camera-cell marker, the four
    near-ring probe cells and the prune comparison;
  * the block border walk has NO exit at the bottom of its loop: the branch pair at 0x8006DC54 and
    0x8006DC5C is a back edge to 0x8006DBC4, and the only four exits are the arrival branches to
    0x8006DC80. A port that treats that pair as a loop-exit condition culls a whole extra lap of
    border cells, which is exactly the defect this fact rules out.

Exit 0 means the executable agrees, exit 1 means real bytes disagree, and exit 2 means no valid
comparison was possible.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import math
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
        BREAK,
        GTE_MOVE,
        HILO,
        JUMP,
        JUMPR,
        LOAD,
        LUI,
        MULDIV,
        NOP,
        SHIFT_I,
        SHIFT_V,
        STORE,
        SYSCALL,
        decode,
    )
except ImportError as exc:
    raise SystemExit(
        "REFUSED: cannot import psxport's shared R3000A instruction decoder; "
        "run tools/psxport_fetch.py --auto or set PSXPORT_DIR"
    ) from exc

# Measured addresses. Each one is asserted against the hashed executable below.
STAGE_OWNER = 0x8006D014
SELECTOR = 0x8006D95C
SELECTOR_END = 0x8006DEAC
DISTANCE_HELPER = 0x8006DEAC
STAGE_INIT = 0x8006C95C
SINE_TABLE = 0x8001E8C4
COSINE_TABLE = 0x8001F0C4
PERMUTATION_TABLE = 0x80025804
TILE_SIZE_WORD = 0x800ADE00
FIRST_ORIGIN_WORD = 0x800A8C44
SECOND_ORIGIN_WORD = 0x800A8C50
STEP_SCALE_WORD = 0x800A8D70
TURN_UNITS = 0x1000
QUARTER_TURN = TURN_UNITS // 4
BLOCK_SPAN = 6
BLOCK_CELLS = BLOCK_SPAN * BLOCK_SPAN
# The two authored wedges and the addresses that materialize them, already recorded in
# titles/tekken3/executable.json; this tool re-derives and re-proves them against the bytes.
WEDGE_LOAD_SITES = ((0x8006D1C4, 600), (0x8006D24C, 780))
WEDGE_CALL_SITES = (0x8006D1EC, 0x8006D274)
# The stage tile unit the measured initializer facts are reported for. It is a stage-authored
# descriptor field, not a property of the selector.
MEASURED_TILE_UNIT = 2048


def check_exact(label: str, measured: object, expected: object) -> None:
    if measured != expected:
        raise Mismatch(f"{label}: measured {measured!r}, expected {expected!r}")


def signed16(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


def rounded(value: float) -> int:
    return int(math.floor(value + 0.5))


def expected_direction(index: int, sine: bool) -> int:
    """The title's Q12 direction table: 0x1000 units is one full turn, amplitude 4096."""
    turn = 2.0 * math.pi * index / TURN_UNITS
    exact = math.sin(turn) if sine else math.cos(turn)
    return rounded(exact * 4096.0)


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


def operands(found: Any) -> tuple[int, int, int]:
    """The three source/destination fields of an instruction, normalized by decoded kind, so measured
    facts are stated the same way whatever the encoding."""
    if found.kind == ALU_RRR:
        return (found.rs, found.rt, found.rd)
    if found.kind == SHIFT_I:
        return (found.rt, found.rd, found.shamt)
    if found.kind == MULDIV:
        return (found.rs, found.rt, 0)
    if found.kind == HILO:
        return (0, 0, found.rd)
    return (found.rs, found.rt, found.simm)


def source_registers(found: Any) -> frozenset[int]:
    """The guest registers an instruction reads, by decoded kind, so an argument's whole read surface
    is decidable without re-deriving MIPS encodings."""
    if found.kind in (ALU_RRR, SHIFT_V, MULDIV, STORE, BRANCH):
        return frozenset({found.rs, found.rt})
    if found.kind == SHIFT_I:
        return frozenset({found.rt})
    if found.kind in (ALU_RRI, LOAD, JUMPR):
        return frozenset({found.rs})
    if found.kind == HILO:
        return frozenset()
    if found.kind in (JUMP, LUI, NOP, SYSCALL, BREAK):
        return frozenset()
    if found.kind == GTE_MOVE:
        return frozenset({found.rt})
    return frozenset({found.rs, found.rt})


def destination_registers(found: Any) -> frozenset[int]:
    if found.kind in (ALU_RRR, SHIFT_I, SHIFT_V, HILO):
        return frozenset({found.rd})
    if found.kind in (ALU_RRI, LOAD, JUMPR):
        return frozenset({found.rt})
    if found.kind == LUI:
        return frozenset({found.rt})
    if found.kind == MULDIV:
        return frozenset()
    return frozenset()


def first_write(image: Any, low: int, high: int, register: int) -> int | None:
    for address in range(low, high, 4):
        if register in destination_registers(instruction(image, address)):
            return address
    return None


def reads_register(image: Any, low: int, high: int, register: int) -> tuple[int, ...]:
    """Addresses in [low, high) whose instruction reads `register`."""
    return tuple(
        address
        for address in range(low, high, 4)
        if register in source_registers(instruction(image, address))
    )


def verify_wedge_argument(image: Any) -> int:
    for address, wedge in WEDGE_LOAD_SITES:
        found = instruction(image, address)
        check_exact(
            f"wedge load 0x{address:08X}",
            (found.kind, found.op, found.rs, found.rt, found.simm),
            (ALU_RRI, "addiu", 0, 4, wedge),
        )
    check_exact("stage selector direct-call census", call_census(image, SELECTOR), WEDGE_CALL_SITES)

    # The wedge arrives in a0 and the guest reuses that register as scratch immediately afterwards, so
    # the decidable claim is about a0's live range: within it the wedge is read exactly once, by the
    # halving shift, and a0 is first overwritten at 0x8006D9B0. The halved wedge in t7 is likewise read
    # exactly twice, once per wedge edge, before t7 is reused for the permutation base.
    wedge_reuse = first_write(image, SELECTOR, SELECTOR_END, 4)
    check_exact("wedge argument register is reused at", wedge_reuse, 0x8006D9B0)
    check_exact(
        "reads of the wedge argument a0 in its live range",
        reads_register(image, SELECTOR, wedge_reuse, 4),
        (0x8006D960,),
    )
    halving = instruction(image, 0x8006D960)
    check_exact(
        "wedge half-angle shift",
        (halving.kind, halving.op, halving.rs, halving.rt, halving.rd, halving.shamt),
        (SHIFT_I, "sra", 0, 4, 15, 1),
    )
    half_reuse = first_write(image, 0x8006D964, SELECTOR_END, 15)
    check_exact("half-angle register is reused at", half_reuse, 0x8006DB24)
    check_exact(
        "reads of the wedge half-angle t7 in its live range",
        reads_register(image, 0x8006D964, half_reuse, 15),
        (0x8006D9F0, 0x8006DAD0),
    )
    return len(WEDGE_LOAD_SITES) * 2 + 2 + 4


def verify_direction_tables(image: Any) -> int:
    for address, op in ((0x8006D9F0, "subu"), (0x8006DAD0, "addu")):
        found = instruction(image, address)
        check_exact(
            f"wedge edge direction at 0x{address:08X}",
            (found.kind, found.op, found.rd, found.rs, found.rt),
            (ALU_RRR, op, 5, 14, 15),
        )
    for address in (0x8006D9FC, 0x8006DAD4):
        found = instruction(image, address)
        check_exact(
            f"turn mask at 0x{address:08X}",
            (found.kind, found.op, found.rs, found.rt, found.simm),
            (ALU_RRI, "andi", 5, 5, TURN_UNITS - 1),
        )

    sine = struct.unpack_from("<4096h", image.text, SINE_TABLE - image.load)
    cosine = struct.unpack_from("<4096h", image.text, COSINE_TABLE - image.load)
    mismatches = [
        index
        for index in range(TURN_UNITS)
        if sine[index] != expected_direction(index, True)
        or cosine[index] != expected_direction(index, False)
    ]
    if mismatches:
        raise Mismatch(
            f"direction tables are not round(sin/cos(2*pi*i/4096)*4096) at {len(mismatches)} of "
            f"{2 * TURN_UNITS} words, first at index {mismatches[0]}"
        )
    check_exact("quarter turn is the table maximum", max(sine), 4096)

    # The cosine word is read 2048 bytes above the sine word, which is what makes the cosine table
    # the same 4096-entry turn one 1024-entry stride later.
    cosine_read = instruction(image, 0x8006DA2C)
    check_exact(
        "cosine read offset from the sine base",
        (cosine_read.kind, cosine_read.op, cosine_read.simm),
        (LOAD, "lh", COSINE_TABLE - SINE_TABLE),
    )
    sine_read = instruction(image, 0x8006DA14)
    check_exact(
        "sine read offset from the sine base",
        (sine_read.kind, sine_read.op, sine_read.simm),
        (LOAD, "lh", 0),
    )
    return 4 + 2 * TURN_UNITS + 2


def verify_wedge_step(image: Any) -> int:
    scale_load = instruction(image, 0x8006DA18)
    check_exact(
        "step scale load kind",
        (scale_load.kind, scale_load.op, scale_load.rt),
        (LOAD, "lw", 4),
    )
    for address, source, destination in ((0x8006DA58, 10, 10), (0x8006DA64, 18, 4)):
        found = instruction(image, address)
        check_exact(
            f"step shift at 0x{address:08X}",
            (found.kind, found.op, found.rt, found.rd, found.shamt),
            (SHIFT_I, "sra", source, destination, 15),
        )
    return 1 + 2


def verify_block_geometry(image: Any) -> int:
    # FUN_8006C95C derives every block fact from the stage descriptor's second field `unit`:
    #   a0 = 5*unit, a3 = 10*unit, a2 = 140*unit, the origins -30*unit, and the direction step scale
    #   140*unit/20 through the 0x66666667 reciprocal. Assert the arithmetic chain, not just the
    #   results, so a port cannot agree by accident.
    chain = (
        (0x8006C9C8, LOAD, "lw", (5, 2, 4), "descriptor tile unit"),
        (0x8006C9D0, SHIFT_I, "sll", (2, 4, 2), "5*unit high half"),
        (0x8006C9D4, ALU_RRR, "addu", (4, 2, 4), "5*unit"),
        (0x8006C9D8, SHIFT_I, "sll", (4, 7, 1), "10*unit"),
        (0x8006C9DC, SHIFT_I, "sll", (4, 6, 4), "140*unit high"),
        (0x8006C9E0, ALU_RRR, "subu", (6, 7, 6), "140*unit minus 10*unit"),
        (0x8006C9E4, SHIFT_I, "sll", (6, 6, 1), "140*unit"),
        (0x8006C9E8, ALU_RRR, "subu", (0, 7, 9), "negated 10*unit"),
        (0x8006C9F0, SHIFT_I, "sll", (9, 2, 1), "-30*unit high"),
        (0x8006C9F4, ALU_RRR, "addu", (2, 9, 2), "-30*unit"),
        (0x8006C9EC, STORE, "sw", (10, 2, TILE_SIZE_WORD - 0x800B0000), "raw unit into the tile word"),
        (0x8006C9F8, STORE, "sw", (3, 2, FIRST_ORIGIN_WORD - 0x800B0000), "first block origin"),
        (0x8006CA00, MULDIV, "mult", (6, 8, 0), "step reciprocal times 140*unit"),
        (0x8006CA04, STORE, "sw", (3, 2, SECOND_ORIGIN_WORD - 0x800B0000), "second block origin"),
        (0x8006CA2C, STORE, "sw", (10, 7, TILE_SIZE_WORD - 0x800B0000), "10*unit over the tile word"),
        (0x8006CA34, HILO, "mfhi", (0, 0, 11), "step high word"),
        (0x8006CA38, SHIFT_I, "sra", (11, 2, 3), "step shift"),
        (0x8006CA3C, ALU_RRR, "subu", (2, 6, 2), "step sign fix"),
        (0x8006CA44, STORE, "sw", (4, 2, STEP_SCALE_WORD - 0x800B0000), "direction step scale"),
    )
    facts = 0
    for address, kind, op, expected, description in chain:
        found = instruction(image, address)
        check_exact(
            f"initializer {description} at 0x{address:08X}",
            (found.kind, found.op, operands(found)),
            (kind, op, expected),
        )
        facts += 1
    reciprocal = instruction(image, 0x8006C964)
    check_exact(
        "step reciprocal literal",
        (reciprocal.kind, reciprocal.op, operands(reciprocal)),
        (ALU_RRI, "ori", (8, 8, 0x6667)),
    )
    facts += 1

    # The runtime words start zeroed in the image, which is why the relations above are the only way
    # to know them: assert that too, so a build that initializes them differently is caught.
    expected_words = {
        TILE_SIZE_WORD: 10 * MEASURED_TILE_UNIT,
        FIRST_ORIGIN_WORD: -30 * MEASURED_TILE_UNIT,
        SECOND_ORIGIN_WORD: -30 * MEASURED_TILE_UNIT,
        STEP_SCALE_WORD: (((140 * MEASURED_TILE_UNIT) * 0x66666667) >> 32) >> 3,
    }
    for address, value in expected_words.items():
        check_exact(f"uninitialized block word 0x{address:08X}", image.word(address), 0)
        check_exact(
            f"derived block word 0x{address:08X}",
            derived_block_word(address, MEASURED_TILE_UNIT),
            value,
        )
        facts += 2
    check_exact("derived step scale is 7*unit", expected_words[STEP_SCALE_WORD], 7 * MEASURED_TILE_UNIT)
    facts += 1
    return facts


def derived_block_word(address: int, unit: int) -> int:
    """The value the initializer stores at `address` for a stage tile unit, from its own arithmetic."""
    five = 5 * unit
    ten = five << 1
    hundred_forty = ((five << 4) - ten) << 1
    negative_thirty = -3 * ten
    step = ((hundred_forty * 0x66666667) >> 32) >> 3
    if hundred_forty < 0:
        step -= 1
    if address == TILE_SIZE_WORD:
        return ten
    if address in (FIRST_ORIGIN_WORD, SECOND_ORIGIN_WORD):
        return negative_thirty
    if address == STEP_SCALE_WORD:
        return step
    raise Refused(f"no initializer relation for block word 0x{address:08X}")


def verify_permutation_and_bounds(image: Any) -> int:
    permutation = struct.unpack_from(f"<{BLOCK_CELLS}h", image.text, PERMUTATION_TABLE - image.load)
    check_exact("stage tile block permutation is the identity", permutation, tuple(range(BLOCK_CELLS)))
    perm_base = instruction(image, 0x8006DA4C)
    check_exact(
        "permutation base",
        (perm_base.kind, perm_base.op, perm_base.simm),
        (ALU_RRI, "addiu", PERMUTATION_TABLE - 0x80020000),
    )
    for address, register in ((0x8006DA84, 20), (0x8006DA8C, 19)):
        found = instruction(image, address)
        check_exact(
            f"block column bound at 0x{address:08X}",
            (found.kind, found.op, found.simm),
            (ALU_RRI, "sltiu", BLOCK_SPAN),
        )
        if found.rs != register:
            raise Mismatch(f"block bound at 0x{address:08X} reads s{register} not v{register}")
    zero_fill = instruction(image, 0x8006D998)
    check_exact(
        "block zero fill top",
        (zero_fill.kind, zero_fill.op, zero_fill.rs, zero_fill.simm),
        (ALU_RRI, "addiu", 23, BLOCK_CELLS * 4 - 4),
    )
    counter = instruction(image, 0x8006D978)
    check_exact(
        "block zero fill count",
        (counter.kind, counter.op, counter.rs, counter.simm),
        (ALU_RRI, "addiu", 0, BLOCK_CELLS - 1),
    )
    return 1 + 1 + 2 + 2


def verify_block_clamp(image: Any) -> int:
    # The selector clamps each camera coordinate into [-2*tile, 2*tile) and substitutes -3*tile or
    # 3*tile-1, so with the initializer's own -3*tile origins the block cell is always one of the 36.
    clamp = (
        (0x8006D9AC, ALU_RRR, "subu", (0, 11, 5), "negated tile size"),
        (0x8006D9B0, SHIFT_I, "sll", (5, 4, 1), "double tile size"),
        (0x8006D9B4, ALU_RRR, "slt", (6, 4, 2), "first coordinate below the low bound"),
        (0x8006D9C0, ALU_RRR, "addu", (4, 5, 6), "low clamp is -3*tile"),
        (0x8006D9C4, ALU_RRR, "slt", (6, 3, 2), "first coordinate below the high bound"),
        (0x8006D9D0, ALU_RRR, "addu", (3, 11, 2), "triple tile size"),
        (0x8006D9D4, ALU_RRI, "addiu", (2, 6, -1), "high clamp is 3*tile-1"),
        (0x8006D9D8, ALU_RRR, "slt", (7, 4, 2), "second coordinate below the low bound"),
        (0x8006D9E4, ALU_RRR, "addu", (4, 5, 7), "second low clamp is -3*tile"),
        (0x8006D9E8, ALU_RRR, "slt", (7, 3, 2), "second coordinate below the high bound"),
        (0x8006D9F8, ALU_RRI, "addiu", (2, 7, -1), "second high clamp is 3*tile-1"),
    )
    for address, kind, op, expected, description in clamp:
        found = instruction(image, address)
        check_exact(
            f"block clamp {description} at 0x{address:08X}",
            (found.kind, found.op, operands(found)),
            (kind, op, expected),
        )
    return len(clamp)


def verify_camera_marker_and_near_ring(image: Any) -> int:
    marker = instruction(image, 0x8006DD48)
    check_exact(
        "camera cell marker",
        (marker.kind, marker.op, marker.rs, marker.simm),
        (ALU_RRI, "addiu", 0, -2),
    )
    unreached = instruction(image, 0x8006DD40)
    check_exact(
        "unreached cell distance",
        (unreached.kind, unreached.op, unreached.rs, unreached.rt, unreached.simm),
        (ALU_RRI, "addiu", 0, 21, 0x7FFF),
    )
    # The four near-ring probes address the (column, row) box two and three of the block: a3 carries
    # the column and 16(sp) the row, and the two row literals are 2 (s0) and 3 (s2).
    probes = (
        (0x8006DD78, 0x8006DD4C, 0x8006DD50, 2, 2),
        (0x8006DDA4, 0x8006DDA8, 0x8006DD8C, 2, 3),
        (0x8006DDD0, 0x8006DDD4, 0x8006DD50, 3, 2),
        (0x8006DDFC, 0x8006DE00, 0x8006DD8C, 3, 3),
    )
    for call, column_at, row_at, column, row in probes:
        column_instruction = instruction(image, column_at)
        check_exact(
            f"near-ring probe column literal at 0x{column_at:08X}",
            (column_instruction.kind, column_instruction.op, operands(column_instruction)[1], column_instruction.simm),
            (ALU_RRI, "addiu", 7, column),
        )
        row_instruction = instruction(image, row_at)
        if row == 2:
            check_exact(
                f"near-ring probe row literal at 0x{row_at:08X}",
                (row_instruction.kind, row_instruction.op, operands(row_instruction)),
                (ALU_RRR, "addu", (7, 0, 16)),
            )
        else:
            check_exact(
                f"near-ring probe row literal at 0x{row_at:08X}",
                (row_instruction.kind, row_instruction.op, operands(row_instruction)),
                (ALU_RRI, "addiu", (0, 18, row)),
            )
        found = instruction(image, call)
        check_exact(f"near-ring probe call 0x{call:08X}", (found.kind, found.target), (JUMP, DISTANCE_HELPER))
    check_exact("near-ring probe call census", len(call_census(image, DISTANCE_HELPER)), 5)
    prune = instruction(image, 0x8006DE4C)
    check_exact(
        "near-ring prune comparison",
        (prune.kind, prune.op, prune.rs, prune.rt, prune.rd),
        (ALU_RRR, "slt", 21, 2, 2),
    )
    prune_store = instruction(image, 0x8006DE58)
    check_exact(
        "near-ring prune store",
        (prune_store.kind, prune_store.op, prune_store.rs, prune_store.rt, prune_store.simm),
        (STORE, "sw", 18, 0, 0),
    )
    return 2 + len(probes) * 3 + 1 + 1 + 1


def verify_border_walk(image: Any) -> int:
    # The only exits from the border walk are the four arrival branches to 0x8006DC80. The branch
    # pair that closes the loop body is a back edge, and a port that reads it as an exit condition
    # stops one lap early and leaves extra border cells selected.
    walk_body = (0x8006DBC4, 0x8006DC7C)
    arrivals = sorted(
        address
        for address in range(*walk_body)
        if (found := instruction(image, address)).kind in (JUMP, BRANCH) and found.target == 0x8006DC80
    )
    check_exact("border walk arrival branches", tuple(arrivals), (0x8006DBF0, 0x8006DC20, 0x8006DC4C))
    fallthrough = instruction(image, 0x8006DC7C)
    check_exact(
        "border walk fourth arrival is the fall-through into 0x8006DC80",
        (fallthrough.kind, fallthrough.op),
        (ALU_RRR, "addu"),
    )
    for address in (0x8006DC54, 0x8006DC5C):
        found = instruction(image, address)
        check_exact(
            f"border walk loop back edge at 0x{address:08X}",
            (found.kind, found.target),
            (BRANCH, walk_body[0]),
        )
    return len(arrivals) + 1 + 2


def verify_manifest_stage_visibility(manifest: dict[str, Any], image: Any) -> int:
    """The manifest is the measured authority; re-derive its recorded stage-visibility facts from the
    same bytes so the record and this tool cannot drift apart silently."""
    projection = manifest.get("projection")
    if not isinstance(projection, dict):
        raise Refused("manifest projection must be an object")
    stage = projection.get("stage_visibility")
    if not isinstance(stage, dict):
        raise Refused("manifest projection.stage_visibility must be an object")
    check_exact("recorded stage visibility owner", parse_hex(stage.get("owner"), "owner"), STAGE_OWNER)
    check_exact("recorded tile selector", parse_hex(stage.get("selector"), "selector"), SELECTOR)
    calls = stage.get("calls")
    if not isinstance(calls, list) or len(calls) != len(WEDGE_LOAD_SITES):
        raise Refused("manifest projection.stage_visibility.calls must hold the two measured calls")
    facts = 0
    for index, value in enumerate(calls):
        field = f"projection.stage_visibility.calls[{index}]"
        if not isinstance(value, dict):
            raise Refused(f"{field} must be an object")
        address, wedge = WEDGE_LOAD_SITES[index]
        check_exact(f"recorded call {index}", parse_hex(value.get("address"), f"{field}.address"), WEDGE_CALL_SITES[index])
        check_exact(
            f"recorded angle load {index}",
            parse_hex(value.get("angle_load_address"), f"{field}.angle_load_address"),
            address,
        )
        recorded = value.get("retail_angle")
        if not isinstance(recorded, int) or isinstance(recorded, bool):
            raise Refused(f"{field}.retail_angle must be an integer")
        check_exact(f"recorded retail angle {index}", recorded, wedge)
        facts += 3
    check_exact("recorded wedge call sites against the executable", call_census(image, SELECTOR), WEDGE_CALL_SITES)
    return facts + 1


def verify_wedge(
    manifest: dict[str, Any], executable: pathlib.Path
) -> None:
    verify_executable(manifest, executable)
    try:
        image = psexe.load(str(executable))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot load {executable}: {exc}") from exc

    scanned = (image.text_end - image.load) // 4
    facts = (
        verify_wedge_argument(image)
        + verify_direction_tables(image)
        + verify_wedge_step(image)
        + verify_block_geometry(image)
        + verify_permutation_and_bounds(image)
        + verify_block_clamp(image)
        + verify_camera_marker_and_near_ring(image)
        + verify_border_walk(image)
        + verify_manifest_stage_visibility(manifest, image)
    )
    print(
        f"[stage-wedge] MATCH {facts}/{facts} measured facts over {scanned} scanned instructions "
        f"in the hashed executable ({2 * TURN_UNITS} of them the direction-table words, "
        f"{facts - 2 * TURN_UNITS} structural)"
    )
    print(
        "[stage-wedge] the authored wedge is a 0x1000-unit direction half-angle: "
        "600 -> 26.3672 deg (table 1819/3670), 780 -> 34.2773 deg (2307/3385); it is read once, "
        "halved, offset by the negated heading and used only as a direction-table index, so no "
        "focal length, view width or draw width reaches the selection"
    )
    print(
        "[stage-wedge] block geometry for tile unit "
        f"{MEASURED_TILE_UNIT}: tile size {10 * MEASURED_TILE_UNIT}, both origins "
        f"{-30 * MEASURED_TILE_UNIT} (=-3*tile), direction step scale "
        f"{(((140 * MEASURED_TILE_UNIT) * 0x66666667) >> 32) >> 3} (=7*unit, 0.7*tile)"
    )
    print(
        "[stage-wedge] blind spot: static ownership is proven, but no stage frame is; the product "
        "cannot reach one, so the wide selection is compared against the real guest selector "
        "differentially rather than seen on screen"
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

    with tempfile.TemporaryDirectory(prefix="stage-wedge-selftest-", dir=scratch) as temp:
        directory = pathlib.Path(temp)

        def check(candidate_manifest: dict[str, Any], candidate_data: bytes) -> type[Exception] | None:
            path = directory / "SLUS_004.02"
            path.write_bytes(candidate_data)
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    verify_wedge(candidate_manifest, path)
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        results.append(("real executable matches", check(manifest, data) is None))

        cases = (
            (
                "changed authored wedge is rejected",
                0x8006D1C4,
                0x24040257,
                "600 -> 599",
            ),
            (
                "changed half-angle shift is rejected",
                0x8006D960,
                0x00047843 ^ (1 << 6),
                "sra 1 -> sll 1",
            ),
            (
                "added second read of the wedge argument is rejected",
                0x8006D964,
                0x00843821,
                "a0 consumed twice",
            ),
            (
                "changed turn mask is rejected",
                0x8006D9FC,
                0x30A507FF,
                "0xFFF -> 0x7FF",
            ),
            (
                "changed cosine table offset is rejected",
                0x8006DA2C,
                0x84620800 ^ 0x400,
                "cosine read moved by one entry",
            ),
            (
                "changed direction table entry is rejected",
                SINE_TABLE + 2 * 300,
                0x00000000,
                "sine quarter turn cleared",
            ),
            (
                "changed step shift is rejected",
                0x8006DA58,
                0x000A53C4,
                "sra 15 -> sra 16",
            ),
            (
                "changed block clamp is rejected",
                0x8006D9D4,
                0x2446FFFE,
                "3*tile-1 -> 3*tile-2",
            ),
            (
                "changed near-ring probe cell is rejected",
                0x8006DD4C,
                0x24070004,
                "probe column 2 -> 4",
            ),
            (
                "changed camera cell marker is rejected",
                0x8006DD48,
                0x2403FFFD,
                "-2 -> -3",
            ),
            (
                "changed prune comparison is rejected",
                0x8006DE4C,
                0x02A2102B,
                "slt -> sltu",
            ),
            (
                "a border-walk exit is added is rejected",
                0x8006DC5C,
                0x1040FFDB ^ 0x0C000000,
                "loop back edge turned into an exit",
            ),
        )
        for name, address, word, description in cases:
            if name == "changed direction table entry is rejected":
                candidate = bytearray(data)
                struct.pack_into("<H", candidate, 0x800 + address - image.load, word)
                candidate_bytes = bytes(candidate)
            else:
                candidate_bytes = mutate_word(data, image, address, word)
            results.append(
                (
                    f"{name} ({description})",
                    check(manifest_for_bytes(manifest, candidate_bytes), candidate_bytes) is Mismatch,
                )
            )

        missing = copy.deepcopy(manifest)
        del missing["projection"]
        results.append(("missing projection manifest is refused", check(missing, data) is Refused))

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"stage-wedge selftest: {passed_count}/{len(results)} cases")
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
        verify_wedge(load_manifest(MANIFEST), args.exe)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
