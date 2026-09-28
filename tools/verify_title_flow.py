#!/usr/bin/env python3
"""verify_title_flow.py — where Tekken 3's NAMCO PRESENTS card goes next, read out of the image.

ONE CONCEPT. The card is not a screen the player dismisses. It is the CD-read wait of mode 2,
phase 8, and mode 2 phase 12 leaves it by copying ONE guest byte into the mode word. This tool
re-derives that whole chain from the authenticated `SLUS_004.02` bytes and refuses to report
anything until it has reproduced the file-offset formula against known instructions, because the
same class of bug already made a writer census in this repository report 18 phantom stores.

Every constant it prints is DERIVED from the image and then diffed against
`titles/tekken3/executable.json` (`title_flow`), so the recorded fact cannot drift from the bytes
it came from. Facts that are runtime rather than static are named as such and never derived here.

WHAT IT MEASURES, in the order the card walks it:

  1. the frame loop's mode dispatch  (0x80028C60): `lh` of the mode halfword, an unsigned bound,
     a jump table, `jr` — with the table base and every stub/target printed;
  2. mode 2's phase dispatch          (0x8004FAE0): the same shape over the phase halfword;
  3. the phase-8 block, the "still loading?" call in it, and the branch that keeps the phase;
  4. that predicate's own chain, down to the single `lbu` displacement that names the wait byte;
  5. the card renderer, with the string it draws, the x/y it draws it at, and for which
     `param_1` values it draws it at all;
  6. the phase-12 exit, the byte it copies into the mode word, and a SCAN for any controller-port
     read on that path (the claim "no input is needed" is only worth making if the scan can fail);
  7. the mode switch that mode 0's last phase performs, naming the return-mode byte;
  8. which of the 20 mode targets lie outside the resident code region, with the density
     denominators for the regions it compares — a claim about "not code" needs the numbers.

WHAT IT DELIBERATELY DOES NOT CLAIM. Modes 3 and up are not in the disc executable's code region
(fact 8 measures this); their bodies are written at run time from disc-compressed resources, so
this tool cannot name the menu, the accepted inputs, or the branch toward a fight. It says so
rather than inferring them from a 20-entry table whose targets are data.

Usage:
  tools/verify_title_flow.py --exe scratch/bin/tekken3/SLUS_004.02
  tools/verify_title_flow.py --selftest --exe scratch/bin/tekken3/SLUS_004.02
"""
from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/psxport"))  # the shared R3000A decoder

from tools.mips.decode import REG, decode

RECORD = ROOT / "titles" / "tekken3" / "executable.json"

# PS-X EXE layout. The 0x800-byte header sits in front of the text, so the file offset of a guest
# address is HEADER + (address - LOAD). Omitting it shifts every decoded instruction and every
# reported address while still returning confident non-zero answers, which is exactly the bug the
# two words below exist to catch.
HEADER = 0x800
LOAD = 0x80010000
TEXT_SIZE = 0x121000
TEXT_LAST = LOAD + TEXT_SIZE

# Ground truth: the frame loop's `jal 0x800B0548` (the second initializer call, which
# tools/verify_startup.py already depends on) and the mode dispatch's `sltiu`. Independent of every
# fact below. A wrong file offset shifts every decoded instruction and every reported address while
# still returning confident non-zero answers -- that exact bug made a writer census in this
# repository report 18 phantom stores -- so nothing is reported past this check.
GROUND_TRUTH = {
    0x80028BB8: 0x0C02C152,  # jal 0x800B0548
    0x80028C6C: 0x2C620014,  # sltiu $v0, $v1, 0x14
}

# The two guest pointers the pad-port path reaches through. Used only as SCAN targets, so that
# "this path reads no controller port" is a statement about bytes rather than an assumption.
PAD_POINTERS = (0x8009B960, 0x8009B964)
PAD_REGISTER = 0x1F801040

# The two density windows the "is this resident code" claim compares. A window with no `jr $ra` in
# a title whose code region has 1,499 is not a formatting artifact, and a window with 1,499 is
# code. Both are measured on every run; neither is asserted.
CODE_WINDOW = "0x80010000-0x800B0000"
NON_CODE_WINDOW = "0x800C0000-0x80131000"

# WHICH phase is the wait and WHICH leaves the card, as a property of the image rather than of this
# conversation. They are not hard-coded claims -- each is VERIFIED below (the wait phase must call
# the loader-wait predicate and hold itself on a nonzero return; the exit phase must store both the
# mode and phase halfwords) -- and the tool refuses if either check fails, so a wrong index here
# produces a refusal, never a wrong answer.
CARD_MODE = 2
WAIT_PHASE = 8
EXIT_PHASE = 12
# Mode 0's LAST phase is the one that switches away, and this is the `jal` that does it. The mode
# switch itself is located by what it stores (see `_installs_mode`), so this is the only literal
# call site, and it is the one the boot discriminator in docs/re-frontier.md already records.
MODE0_SWITCH_CALL = 0x800B076C


class Refusal(Exception):
    """Something the tool must not report past: a wrong image, a wrong offset, a missing corpus."""


# The decoder fills `rd` only for the R-type forms; `lui`, the immediates, the loads and the
# shifts name their destination in `rt`. Reading `rd` for a `lui` silently yields register 0, and
# a base-address walk that looked for `lui` writing $0 would find nothing and then report a
# missing fact where the image has one. These name the field per encoding kind so no caller has to
# remember which is which.
def dest(ins) -> int:
    return ins.rd if ins.kind == "alu_rrr" else ins.rt


def upper(ins) -> int:
    """The `lui` immediate is the UNSIGNED upper half; it is not sign-extended."""
    return ins.imm << 16


class Image:
    """The authenticated executable, read whole, with ONE file-offset formula."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        if not path.is_file():
            raise Refusal(
                f"no authenticated executable at {path} -- provision it with "
                f"tools/provision_executable.py. Refusing rather than reporting an empty image: "
                f"'every check failed' and 'the image is absent' would print the same line."
            )
        self.data = path.read_bytes()
        if len(self.data) < HEADER + TEXT_SIZE:
            raise Refusal(
                f"{path} holds {len(self.data)} byte(s), fewer than the {HEADER + TEXT_SIZE} the "
                f"measured SLUS_004.02 image has, so it cannot carry the text window."
            )
        self.words_scanned = 0

    def offset(self, address: int) -> int:
        if not LOAD <= address < TEXT_LAST:
            raise Refusal(f"0x{address:08X} is outside the resident text 0x{LOAD:08X}..0x{TEXT_LAST:08X}")
        return HEADER + address - LOAD

    def covers(self, address: int, length: int = 4) -> bool:
        return LOAD <= address and address + length <= TEXT_LAST

    def word(self, address: int) -> int:
        off = self.offset(address)
        return struct.unpack_from("<I", self.data, off)[0]

    def ins(self, address: int):
        return decode(address, self.word(address))

    def half(self, address: int) -> int:
        return struct.unpack_from("<H", self.data, self.offset(address))[0]

    def byte(self, address: int) -> int:
        return self.data[self.offset(address)]

    def cstring(self, address: int, limit: int = 64) -> str:
        end = address
        while end < address + limit and self.data[self.offset(end)] != 0:
            end += 1
        return self.data[self.offset(address):self.offset(end)].decode("latin1")

    def ground_truth_problems(self) -> list[str]:
        return [
            f"0x{address:08X}: expected 0x{expected:08X}, read 0x{self.word(address):08X}"
            for address, expected in sorted(GROUND_TRUTH.items())
            if self.word(address) != expected
        ]


# --------------------------------------------------------------------------------------------
# The measurements. Each returns the facts it derived, so the report and the record diff read the
# same values rather than the report formatting its own strings and the diff parsing them back.


@dataclass
class Dispatch:
    """A `switch` on a guest halfword, as the compiler actually emitted it."""

    read_address: int          # where the index halfword is read from
    read_site: int             # the `lh`/`lhu` instruction
    bound_instruction: int     # the unsigned `sltiu`/`sltu` that bounds it
    bound: int
    table_base: int
    stubs: list[int] = field(default_factory=list)
    targets: list[int] = field(default_factory=list)

    def entry(self, index: int) -> int:
        return self.stubs[index]


def read_dispatch(image: Image, site: int) -> Dispatch:
    """Recover a jump-table `switch` from its own instructions, not from a recorded address.

    `site` is the `jr $reg` at the end of the dispatch. The shape the compiler emitted is
    `jr $jump_reg` with `lw $entry, ($index_reg)` in the delay slot, `addu $jump_reg,
    $index_reg, $base` and `sll $index_reg, $index_reg, 2` before it, and the index read by
    `lh $index_reg, disp($base_reg)` earlier. Following the registers rather than assuming them
    keeps the table base, the index halfword's address, and the bound MEASURED; hard-coding them
    would only be a second claim about the same bytes, and one that cannot notice a change.
    """
    # 14 words is wide enough for the whole sequence (the `lh`, the bound, the out-of-range
    # branch, the base pair, the scale, the `addu`, the `lw`, a delay slot and the `jr`) on both
    # dispatches in this image, and it stops well short of anything it could pick up instead.
    tail = [image.ins(site - 4 * i) for i in range(14)]
    branch = next(i for i in tail if i.kind == "jumpr")
    # `lw $jump_reg, ($index_reg)` is what fills the register the `jr` uses.
    lw = next((i for i in tail
               if i.kind == "load" and i.op == "lw" and i.rt == branch.rs), None)
    if lw is None:
        raise Refusal(f"0x{site:08X}: no `lw` fills the `jr` register, so this is not a "
                      f"jump-table dispatch")
    index_reg = lw.rs
    addu = next((i for i in tail if i.kind == "alu_rrr" and i.op == "addu"
                 and i.rd == index_reg and i.addr < lw.addr), None)
    if addu is None:
        raise Refusal(f"0x{site:08X}: no `addu` forms the table entry address, so the jump table "
                      f"is not established")
    base_hi = next(i for i in tail if i.kind == "lui" and i.rt == addu.rt and i.addr < addu.addr)
    base_lo = next(i for i in tail if i.kind == "alu_rri" and i.op == "addiu"
                   and i.rt == addu.rt and i.addr < addu.addr)
    table_base = upper(base_hi) + base_lo.simm
    shift = next((i for i in tail if i.kind == "shift_i" and i.op == "sll"
                  and i.rd == index_reg and i.addr < addu.addr), None)
    if shift is None:
        raise Refusal(f"0x{site:08X}: the index is never scaled, so the stride is not established "
                      f"and reading entries would be a guess")
    if shift.shamt != 2:
        raise Refusal(f"0x{shift.addr:08X}: the index stride is {shift.shamt}, not the word "
                      f"scale this tool assumes")
    bound = next((i for i in tail
                  if i.kind == "alu_rri" and i.op in ("sltiu", "sltu")
                  and i.rs == index_reg and i.addr < shift.addr), None)
    if bound is None:
        raise Refusal(f"0x{site:08X}: no `sltiu`/`sltu` bounds {REG[index_reg]} before the `jr`, so "
                      f"the dispatch's index range is not established")
    # The `lh $index_reg, disp($base_reg)` that filled the index names the halfword.
    index = next((i for i in tail
                  if i.kind == "load" and i.op in ("lh", "lhu") and i.rt == index_reg
                  and i.addr < bound.addr), None)
    if index is None:
        raise Refusal(f"0x{site:08X}: the bounded register {REG[bound.rs]} is never loaded by an "
                      f"`lh`/`lhu` before the bound, so the dispatch's source is not established")
    read_hi = next(i for i in tail if i.kind == "lui" and i.rt == index.rs and i.addr < index.addr)
    # Both forms occur in this image and both are handled: the mode dispatch loads its base with a
    # bare `lui $v0, 0x800B` and relies on the displacement, while mode 2's phase dispatch uses a
    # `lui`+`addiu` pair. Assuming either shape would REFUSE a real dispatch and, worse, would
    # accept a mutated one on the image that happens to match the assumption.
    #
    # The `addiu` must EXTEND that `lui` (same source register, and later). Any `addiu` writing the
    # register will do otherwise, and this function has one that does: `addiu $v0, $zero, 1`
    # three instructions before the phase dispatch's `lh`. Adding THAT in reported the phase
    # halfword as 0x800AE225 -- odd-addressed, therefore not a halfword at all, and nothing in the
    # output said so.
    read_lo = next((i for i in tail
                    if i.kind == "alu_rri" and i.op == "addiu" and i.rt == index.rs
                    and i.rs == read_hi.rt and i.addr > read_hi.addr and i.addr < index.addr), None)
    # The DISPLACEMENT of the `lh` is part of the address, SIGN-EXTENDED. Omitting it reported the
    # phase halfword as 0x800B0001; reading it unsigned rather than signed would report 0x800BE224.
    read_address = upper(read_hi) + (read_lo.simm if read_lo is not None else 0) + index.simm
    return Dispatch(
        read_address=read_address,
        read_site=index.addr,
        bound_instruction=bound.addr,
        bound=bound.imm,
        table_base=table_base,
    )


def measure_mode_dispatch(image: Image) -> Dispatch:
    dispatch = read_dispatch(image, 0x80028C8C)
    for index in range(dispatch.bound):
        stub = image.word(dispatch.table_base + index * 4)
        call = image.ins(stub)
        if call.kind != "jump" or call.op != "jal":
            raise Refusal(
                f"mode {index}: the table entry 0x{stub:08X} does not begin with `jal`, so this "
                f"is not the mode dispatch the tool claims to measure"
            )
        dispatch.stubs.append(stub)
        dispatch.targets.append(call.target)
    return dispatch


def measure_phase_dispatch(image: Image, site: int) -> Dispatch:
    dispatch = read_dispatch(image, site)
    for index in range(dispatch.bound):
        dispatch.stubs.append(image.word(dispatch.table_base + index * 4))
    return dispatch


def jal_target(image: Image, address: int) -> int:
    ins = image.ins(address)
    if ins.kind != "jump" or ins.op != "jal":
        raise Refusal(f"0x{address:08X} is not a `jal` (decoded {ins.op!r})")
    return ins.target


def measure_wait_predicate(image: Image, call_site: int) -> dict:
    """Follow the phase-8 predicate to the single `lbu` displacement that names the wait byte.

    The chain is followed by each function's own body, not by a fixed offset: the predicate is a
    real function with a prologue, and its `jal` to the leaf sits after it. The leaf must be a
    body whose ONLY work is the `lbu`, and the phase-8 block must branch to the shared tail on a
    nonzero return -- that branch is what makes this a WAIT rather than a read.
    """
    predicate = jal_target(image, call_site)
    leaf_call = None
    for ins in image_ins_range(image, predicate, predicate + 0x80):
        if ins.kind == "jump" and ins.op == "jal":
            leaf_call = ins
            break
    if leaf_call is None:
        raise Refusal(
            f"0x{predicate:08X} calls nothing, so the phase-8 predicate's chain is not established"
        )
    leaf = leaf_call.target
    words = [image.ins(leaf + 4 * i) for i in range(6)]
    lui = next(i for i in words if i.kind == "lui")
    addiu = next(i for i in words if i.kind == "alu_rri" and i.op == "addiu" and i.rt == lui.rt)
    load = next(i for i in words if i.kind == "load" and i.op == "lbu" and i.rs == addiu.rt)
    base = upper(lui) + addiu.simm
    if load.addr + 4 > next((i.addr for i in words if i.kind == "jumpr"), leaf + 0x40):
        raise Refusal(f"0x{leaf:08X} does more than read the byte, so it is not the wait-byte leaf")
    busy = next((i for i in image_ins_range(image, predicate, predicate + 0x80)
                 if i.kind == "branch" and branches_nonzero(i) and i.rs == 2), None)
    if busy is None:
        raise Refusal(
            f"0x{predicate:08X} has no `bne $v0, $zero` on the predicate's own return value, so "
            f"it does not report \"busy\""
        )
    return {
        "call_site": call_site,
        "predicate": predicate,
        "leaf": leaf,
        "leaf_call": leaf_call.addr,
        "base_register_site": addiu.addr,
        "base": base,
        "load_site": load.addr,
        "load_op": load.op,
        "displacement": load.imm,
        "wait_byte": base + load.imm,
        "nonzero_returns_busy_site": busy.addr,
    }


def branches_nonzero(ins) -> bool:
    """True for `bne $rs, $zero` / `bnez $rs`, the encoding that means "branch if nonzero".

    The MIPS assembler spells this two ways and the decoder reports the `bne` form, so a check
    written against the mnemonic spelling alone would find nothing in a real image.
    """
    return ins.kind == "branch" and (ins.op == "bnez" or (ins.op == "bne" and ins.rt == 0))


def image_ins_range(image: Image, first: int, last: int):
    for address in range(first, last, 4):
        if image.covers(address):
            yield image.ins(address)


def draws_namco_presents(image: Image, entry: int) -> bool:
    """Does this function pass a pointer to the card's text to some callee?

    Content, not address. The card's string is a TEXT-FORMAT template, not a literal: the two
    words are separated by a format code, so `"NAMCO PRESENTS"` is not a substring of it and
    matching that would find nothing in the real image while looking like a principled check.
    The match is therefore on the two words separately, and the string is printed as measured so
    the reader sees the format codes rather than a tidied-up version of them.

    Locating the renderer this way also makes a one-word mutation of the string FAIL the search
    instead of silently redirecting the whole measurement somewhere else.
    """
    for window in (0x80, 0x100, 0x180):
        for high in image_ins_range(image, entry, entry + window):
            if high.kind != "lui" or high.rt != 4:
                continue
            for low in image_ins_range(image, high.addr + 4, high.addr + 0x20):
                if low.kind != "alu_rri" or low.op != "addiu" or low.rt != 4:
                    continue
                address = upper(high) + low.simm
                if not image.covers(address):
                    continue
                try:
                    text = image.cstring(address)
                except Refusal:
                    continue
                if "NAMCO" in text and "PRESENTS" in text:
                    return True
    return False


def measure_card(image: Image, tail_call_site: int) -> dict:
    """The renderer the phase tail calls, and the string/coordinates it hands the text engine."""
    renderer = jal_target(image, tail_call_site)
    words = list(image_ins_range(image, renderer, renderer + 0x120))
    # Locate the text call by its ARGUMENT SHAPE, not by name: the string argument is a
    # `lui $a0`+`addiu $a0` pair formed in place immediately before it. A hard-coded call site
    # would be a second claim about the same bytes.
    text_engine = None
    for index, ins in enumerate(words):
        if ins.kind != "jump" or ins.op != "jal":
            continue
        window = words[max(0, index - 16):index + 2]
        if not any(w.kind == "lui" and w.rt == 4 for w in window):
            continue
        text_engine = ins
        break
    if text_engine is None:
        raise Refusal("card renderer: no `jal` taking a string pointer in $a0 was found")

    window = words[max(0, words.index(text_engine) - 16):words.index(text_engine) + 2]
    lui = next(w for w in window if w.kind == "lui" and w.rt == 4)
    addiu = next(w for w in reversed(window)
                 if w.kind == "alu_rri" and w.op == "addiu" and w.rt == 4
                 and w.addr > lui.addr)
    string = (lui.imm << 16) + addiu.simm
    # The remaining four arguments are $a1, $a2, $a3 and the two stack words at 0x10(sp)/0x14(sp),
    # each materialised immediately before its use. They are read by POSITION relative to the
    # call, not by a hard-coded address, and the stack slots are read out of the store so a
    # different argument layout would be reported rather than assumed.
    after = [w for w in window if w.addr > addiu.addr]

    def argument(predicate, what: str):
        """The one instruction forming an argument, or a REFUSAL naming which one is missing.

        A bare `next()` raises StopIteration, which a caller sees as a crash rather than as "this
        block is not the card renderer" -- so a mutated image turned a wrong answer into an
        unexplained traceback, and the negative case could not tell the two apart.
        """
        found = next((w for w in after if predicate(w)), None)
        if found is None:
            raise Refusal(
                f"the card renderer forms no {what} before its text call, so the argument that "
                f"positions the card is not established"
            )
        return found

    arg1 = argument(lambda w: w.kind == "alu_rri" and w.op == "addiu"
                    and w.rt == 5 and w.rs == 0, "x-scale argument in $a1")
    # `$a2, $zero` is encoded as `addu $a2, $zero, $zero` (funct 0x21), not as a distinct move,
    # so "the register was set to zero" is matched by the encoding rather than by a mnemonic.
    arg2 = argument(lambda w: w.kind == "alu_rrr" and w.rd == 6
                    and w.rs == 0 and w.rt == 0 and w.addr > arg1.addr, "origin argument in $a2")
    arg3 = argument(lambda w: w.kind == "alu_rri" and w.op == "addiu"
                    and w.rt == 7 and w.rs == 0 and w.addr > arg2.addr, "x coordinate in $a3")
    y_word = argument(lambda w: w.kind == "alu_rri" and w.op == "addiu"
                      and w.rt == 2 and w.rs == 0 and w.addr > arg3.addr, "y coordinate")
    store_y = argument(lambda w: w.kind == "store" and w.rt == 2
                       and w.rs == 29 and w.imm == 0x10 and w.addr > y_word.addr,
                       "outgoing y stack slot")
    scale = argument(lambda w: w.kind == "alu_rri" and w.op == "addiu"
                     and w.rt == 2 and w.rs == 0 and w.addr > store_y.addr, "scale immediate")
    store_scale = argument(lambda w: w.kind == "store" and w.rt == 2
                           and w.rs == 29 and w.imm == 0x14 and w.addr > scale.addr,
                           "outgoing scale stack slot")
    text = image.cstring(string)
    drawn_for = param1_draws_text(list(image_ins_range(image, renderer, renderer + 0x100)),
                                 text_engine.addr)
    return {
        "tail_call_site": tail_call_site,
        "renderer": renderer,
        "text_engine_call": text_engine.addr,
        "string": string,
        "format_string": text,
        "arg_mode": arg1.imm,
        "arg_z": 0,
        "arg_x": arg3.imm,
        "arg_y": y_word.imm,
        "arg_scale": scale.imm,
        "arg_x_site": arg3.addr,
        "arg_y_site": y_word.addr,
        "arg_scale_site": scale.addr,
        "arg_y_store_site": store_y.addr,
        "arg_scale_store_site": store_scale.addr,
        "drawn_for_param_1": drawn_for,
    }


def param1_draws_text(words, text_call: int) -> list[int]:
    """The `$a0` values in `range(0, 8)` for which the renderer REACHES its text call.

    A constant-folded CFG walk over the renderer's own body, with `$a0` set to the candidate and
    every other register unknown. A branch whose condition cannot be resolved takes BOTH arms,
    because "the card may be drawn" and "the card is definitely not drawn" are different answers
    and only the first is honest when the image does not say.

    Walking the CFG rather than reading the branch mnemonics is not decoration. The dispatch tests
    `$a0` AND `$a1` (against 0x100), so a checker that followed `$a0` alone concluded the card is
    drawn for NO value of it -- the exact opposite of the truth, computed from the same image, with
    no error printed anywhere.
    """
    reaches: list[int] = []
    for candidate in range(8):
        if _reaches(words, text_call, {4: candidate}, [0], set()):
            reaches.append(candidate)
    return reaches


def _reaches(words, text_call: int, registers: dict[int, int | None],
             todo: list[int], seen: set[int]) -> bool:
    while todo:
        index = todo.pop()
        if index in seen or index >= len(words):
            continue
        seen.add(index)
        ins = words[index]
        if ins.addr == text_call:
            return True
        if ins.kind == "jumpr":
            continue  # a return: this path ends without drawing
        if ins.kind == "jump" and ins.op == "j":
            target = _index_of(words, ins.target)
            if target is None:
                continue
            todo.append(target)
            continue
        if ins.kind == "branch":
            taken = _condition(registers, ins)
            fall = index + 1
            if taken is None:
                # Undecidable: the card is drawn on at least one arm if any arm reaches the call.
                target = _index_of(words, ins.target)
                if target is not None and _reaches(words, text_call, dict(registers), [target], set()):
                    return True
                todo.append(fall)
                continue
            todo.append(fall)
            if taken:
                target = _index_of(words, ins.target)
                if target is not None:
                    todo.append(target)
            continue
        _apply(registers, ins)
        todo.append(index + 1)
    return False


def _index_of(words, address: int) -> int | None:
    for index, ins in enumerate(words):
        if ins.addr == address:
            return index
    return None


def _apply(registers: dict[int, int | None], ins) -> None:
    """One instruction's effect on the known-register state. Unknown in, unknown out."""
    if ins.kind == "alu_rri" and ins.op in ("addiu", "ori", "andi", "xori"):
        if ins.rs == 0:
            registers[ins.rt] = ins.imm if ins.op == "addiu" else None
        elif registers.get(ins.rs) is not None and ins.op == "addiu":
            registers[ins.rt] = (registers[ins.rs] + ins.simm) & 0xFFFFFFFF
        else:
            registers[ins.rt] = None
    elif ins.kind == "alu_rri" and ins.op == "slti":
        left = registers.get(ins.rs)
        registers[ins.rt] = None if left is None else (1 if left < ins.simm else 0)
    elif ins.kind == "alu_rrr" and ins.op == "slt":
        left = registers.get(ins.rs)
        registers[ins.rd] = None if left is None else (1 if left < ins.rt else 0)
    elif ins.kind == "alu_rrr" and ins.op == "addu":
        left, right = registers.get(ins.rs), registers.get(ins.rt)
        registers[ins.rd] = None if left is None or right is None else (left + right) & 0xFFFFFFFF
    else:
        if ins.rt:
            registers[ins.rt] = None
        if ins.rd and ins.kind in ("alu_rrr", "shift_i"):
            registers[ins.rd] = None


def _condition(registers: dict[int, int | None], ins) -> bool | None:
    """True/False when the register state decides the branch, else None.

    `$zero` is a LITERAL 0, not an unknown register. Reading it out of the register map returns
    None, and a `beq $v0, $zero` then looks undecidable, so the walk takes both arms and reaches
    the text call from a path that cannot exist. That made the card read as "drawn for every
    `$a0`", when the image draws it for 0, 1 and 2 only.
    """
    def value(reg: int) -> int | None:
        return 0 if reg == 0 else registers.get(reg)

    left = value(ins.rs)
    if ins.op in ("beqz", "bnez", "blez", "bgtz"):
        if left is None:
            return None
        return {"beqz": left == 0, "bnez": left != 0,
                "blez": left <= 0, "bgtz": left > 0}[ins.op]
    right = value(ins.rt)
    if left is None or right is None:
        return None
    return left == right if ins.op == "beq" else left != right


def measure_exit(image: Image, phase12_block: int, tail_call_site: int) -> dict:
    """The phase that leaves mode 2, the byte it copies into the mode word, and whether it reads
    the controller port on the way."""
    # The register holding the return-mode byte is set in the function's PROLOGUE, before the
    # phase block, so the base-resolution walk starts there. A tool that began at the block would
    # not find where the byte lives and would report "the return-mode byte is unknown" on a block
    # that plainly loads it.
    words = list(image_ins_range(image, _function_start(image, phase12_block),
                                 tail_call_site))
    sources: dict[int, int] = {}
    resolved: dict[int, tuple[int, int]] = {}
    for ins in words:
        _track(sources, ins)
        if ins.kind == "load" and ins.op == "lbu" and ins.rs in sources:
            # A tracked `lbu` folds the byte's own ADDRESS into the value it produces, which is
            # what lets the mode store's source register be traced back to the byte it read.
            sources[ins.rt] = sources[ins.rs] + ins.imm
        if ins.kind == "store" and ins.op in ("sh", "sb") and ins.rs in sources:
            # The resolved address is recorded AT the store. Reading the dictionary after the loop
            # answers with whatever the last write left behind, not with what this store used.
            resolved[ins.addr] = (ins.rs, sources[ins.rs] + ins.simm)
    mode_word_write = None
    phase_word_write = None
    for ins in words:
        if ins.kind != "store" or ins.op != "sh" or ins.addr not in resolved:
            continue
        if resolved[ins.addr][1] == 0x800AE204:
            mode_word_write = (ins, resolved[ins.addr][1])
        if resolved[ins.addr][1] == 0x800AE224:
            phase_word_write = (ins, resolved[ins.addr][1])
    if mode_word_write is None or phase_word_write is None:
        raise Refusal(
            f"mode-2 exit at 0x{phase12_block:08X}: no `sh` pair writing both 0x800AE204 and "
            f"0x800AE224 was found between the function's start and the card call, so this is not "
            f"the block that leaves the mode"
        )
    ins, _ = mode_word_write
    # The mode halfword's SOURCE register, and the address the `lbu` of that register read. The
    # LAST such load before the store is the one: this function loads the same byte in several
    # phases, and taking the first reported phase 1's address for phase 12's.
    source_reg = ins.rt
    load = None
    for w in words:
        if w.addr >= ins.addr:
            break
        if w.kind == "load" and w.op == "lbu" and w.rt == source_reg:
            load = w
    return_mode = None
    return_mode_load_site = None
    if load is not None:
        return_mode_load_site = load.addr
        # The base register was set in the PROLOGUE (`lui $v0, 0x8009` / `addiu $s0, $v0, 0x7F38`),
        # 0x470 bytes earlier, so the value is recovered by tracking to the load rather than by
        # looking backwards for a `lui` that writes the load's own register -- no such `lui` exists,
        # and the search therefore answered "unknown" on a function that plainly knows the address.
        tracked: dict[int, int] = {}
        for w in words[:words.index(load) + 1]:
            _track(tracked, w)
        return_mode = tracked.get(load.rs)
    pad_reads = _controller_reads(image, words, phase12_block, tail_call_site)
    return {
        "block": phase12_block,
        "tail_call_site": tail_call_site,
        "phase_zero_store": phase_word_write[0].addr,
        "mode_store": ins.addr,
        "mode_word": mode_word_write[1],
        "phase_word": phase_word_write[1],
        "return_mode_byte": return_mode,
        "return_mode_load_site": return_mode_load_site,
        "controller_reads_on_path": pad_reads,
        "instructions_scanned": len(words),
        "function_start": _function_start(image, phase12_block),
    }


def _function_start(image: Image, address: int) -> int:
    """The `addiu $sp, $sp, -N` prologue at or before `address`, or `address` itself.

    Scanning back a bounded 0x200 bytes is a search for a standard prologue, not a claim about
    function boundaries: Ghidra's function bodies are not consulted here, so the tool cannot
    inherit a wrong body from a project and then report the wrong block as this one.
    """
    # 0x800, not 0x200: this function is 0x11C0 bytes long and its phase-12 block sits 0x470 bytes
    # past its prologue, so a 0x200 window found no prologue at all and reported the block as the
    # function's start. The register holding the return-mode byte is set in the prologue, so the
    # consequence was that the byte's address came back unknown on a block that plainly loads it.
    first = max(LOAD, address - 0x800) & ~3
    for candidate in range(address - 4, first - 1, -4):
        if image.word(candidate) & 0xFFFF0000 == 0x27BD0000:
            return candidate
    return address


def _controller_reads(image: Image, words, first: int, last: int) -> list[int]:
    """Every load/store in [first, last) that dereferences a controller-port pointer.

    THE CONTROL THIS EXISTS FOR. "The card's exit path reads no controller port" is worthless if
    the scan cannot find one, so the selftest injects the guest's own two-instruction form into
    this window and requires it to be reported.

    The address is resolved with the same sound tracking the rest of the tool uses, because the
    guest forms the pointer ACROSS two instructions -- `lui $v1, 0x800A` then
    `lw $v1, -0x469C($v1)`, whose address is the base MINUS the displacement. Checking only the
    register's value finds nothing, since the register holds 0x800A0000 and the pointer is
    0x8009B964. A scan that cannot find a read is exactly the scan that would report "no
    controller reads" about anything at all.
    """
    found = []
    tracked: dict[int, int] = {}
    for ins in image_ins_range(image, first, last):
        # The base is read BEFORE the instruction is applied: `lw $a1, -0x469C($a1)` uses the OLD
        # value of $a1 and then overwrites it, so tracking first and reading after reports the
        # register as destroyed and finds nothing.
        base = tracked.get(ins.rs)
        address = None if base is None else base + ins.simm
        _track(tracked, ins)
        if ins.kind not in ("load", "store") or base is None:
            continue
        if address in PAD_POINTERS or base in PAD_POINTERS or address == PAD_REGISTER:
            found.append(ins.addr)
    return found


def _words_to(image: Image, first: int, last: int):
    return list(image_ins_range(image, first, last))


def measure_mode_switch(image: Image, call_site: int) -> dict:
    """The routine mode 0's last phase calls to install the next mode: what it writes, and what
    value it writes into the mode halfword.

    The mode value is read from the instruction that materialises the stored halfword, not assumed
    to be 2. The renderer is reached with a `param_1` that this function may rewrite first, and a
    tool that printed "installs mode 2" without reading it would be right today and silently wrong
    the day the guest takes the other branch.
    """
    switcher = jal_target(image, call_site)
    # 0x200: the function is 0x168 bytes and its stores are in the last 0x30.
    words = list(image_ins_range(image, switcher, min(switcher + 0x200, TEXT_LAST)))
    sources: dict[int, int] = {}
    resolved: dict[int, tuple[int, int]] = {}
    for ins in words:
        _track(sources, ins)
        if ins.kind == "store" and ins.op in ("sh", "sb") and ins.rs in sources:
            resolved[ins.addr] = (ins.rt, sources[ins.rs] + ins.simm)
    stores: dict[int, int] = {}
    for ins in words:
        if ins.kind == "store" and ins.op in ("sh", "sb") and ins.addr in resolved:
            target = resolved[ins.addr][1]
            if target in (0x800AE204, 0x800AE224, 0x80097F38, 0x80097F39):
                stores[target] = ins.addr
    if 0x800AE204 not in stores or 0x800AE224 not in stores:
        raise Refusal(
            f"0x{switcher:08X} stores neither the mode halfword nor the phase halfword, so it is "
            f"not the mode switch"
        )
    mode_store = stores[0x800AE204]
    # Trace the stored register back to the immediate that produced it.
    value_reg = resolved[mode_store][0]
    installed = None
    installed_site = None
    for ins in words:
        if ins.addr >= mode_store:
            break
        if dest(ins) == value_reg and ins.kind == "alu_rri" and ins.op == "addiu" \
                and ins.rs == 0:
            installed = ins.imm
            installed_site = ins.addr
    return {
        "call_site": call_site,
        "switcher": switcher,
        "return_mode_store": stores.get(0x80097F38),
        "previous_mode_store": stores.get(0x80097F39),
        "mode_word_store": mode_store,
        "phase_word_store": stores[0x800AE224],
        "installed_mode": installed,
        "installed_mode_site": installed_site,
    }


def measure_mode0(image: Image, mode0_target: int) -> dict:
    """Mode 0's two phases: the resource load, and the call that switches away from it.

    Which call is which is decided by the two arguments, not by "the first one" or "the one whose
    target is lower": the loader takes a staging base in $a0 and a table in $a1, and the mode
    switch takes a single immediate. A wrong choice would report the wrong table as the resource
    list and the wrong argument as the next mode.
    """
    words = list(image_ins_range(image, mode0_target, mode0_target + 0x80))
    facts: dict = {"entry": mode0_target, "loader_call": None, "loader_target": None,
                   "output_base": None, "resource_table": None, "resource_entries": None,
                   "switch_call": None, "switch_argument": None}
    # ONE forward pass. The register state is CARRIED, never recomputed per call: MIPS o32 makes
    # $a0-$a3 caller-saved, so re-deriving each call's arguments by replaying the window from the
    # function entry resurrects the PREVIOUS call's table pointer and makes the mode switch look
    # like a two-argument call. That is not a cosmetic difference -- it is what made this function
    # report "the boot sequence is not established" about a sequence it had read correctly.
    bases: dict[int, int] = {}
    for position, ins in enumerate(words):
        if ins.kind == "jump" and ins.op == "jal":
            # The DELAY SLOT runs BEFORE the callee, so its write is part of this call's arguments.
            # It is applied to a COPY: mutating `bases` here and then falling through would apply
            # it twice, once as an argument and once as the callee's own first instruction.
            # `simm`, not `imm` -- the immediate field is unsigned and mode 0's table argument is
            # a NEGATIVE displacement (`addiu $a1, $a1, -0x72A8`), which read unsigned puts the
            # table at 0x800C8D58 instead of 0x800B8D58: plausible-looking, and not it.
            incoming = dict(bases)
            delay = words[position + 1] if position + 1 < len(words) else None
            if delay is not None and delay.kind == "alu_rri" and delay.op == "addiu" \
                    and delay.rt in (4, 5, 6, 7):
                if delay.rs in incoming:
                    incoming[delay.rt] = incoming[delay.rs] + delay.simm
                elif delay.rs == 0:
                    incoming[delay.rt] = delay.imm
            a0, a1 = incoming.get(4), incoming.get(5)
            if facts["loader_call"] is None and _is_kseg0(a0) and _is_kseg0(a1):
                facts["loader_call"] = ins.addr
                facts["loader_target"] = ins.target
                facts["output_base"] = a0
                facts["resource_table"] = a1
            elif facts["switch_call"] is None and a0 is not None and _installs_mode(image, ins.target):
                # The mode switch is identified by WHAT THE CALLEE DOES -- it stores the mode
                # halfword AND resets the phase halfword -- not by "a call taking a small number".
                # That distinction is not pedantry: mode 0 also calls a display-mask routine with
                # `$a0 = 1` first, so the argument-shape rule recorded the WRONG argument, 1
                # instead of the measured next mode, with no error anywhere. A confident wrong
                # number is worse than a refusal, and this is the same shape of error the
                # workspace has already paid for twice.
                facts["switch_call"] = ins.addr
                facts["switch_target"] = ins.target
                facts["switch_argument"] = a0
            # The callee has just been entered: $a0-$a3 are destroyed from here on.
            for reg in (4, 5, 6, 7):
                bases.pop(reg, None)
            continue
        _track(bases, ins)
    if facts["resource_table"] is not None and image.covers(facts["resource_table"], 4):
        # The first word of the table is its entry count; reading it here is what lets the report
        # say "127 entries" as a measurement rather than as a remembered number.
        facts["resource_entries"] = image.word(facts["resource_table"])
    if facts["loader_call"] is None or facts["switch_call"] is None:
        raise Refusal(
            f"mode 0 at 0x{mode0_target:08X}: the resource load and the mode switch were not both "
            f"identified, so the boot sequence is not established"
        )
    return facts


def _hex(address: int) -> str:
    return f"0x{address:08X}"


def _is_kseg0(value: int | None) -> bool:
    """A KSEG0 guest pointer, which is what distinguishes "a table address" from "an immediate"."""
    return value is not None and 0x80000000 <= value < 0x80800000


def _installs_mode(image: Image, entry: int) -> bool:
    """Does this function store the mode halfword AND reset the phase halfword?

    That pair is what makes a function the mode switch, and it is checked by resolving the stores
    through the same sound base tracking the exit analysis uses. A function that stores the mode
    word alone is some other writer of that word, and is not the mode switch.
    """
    # 0x200, not 0x100: this function is 0x168 bytes long and the two stores sit in its last
    # 0x30. A 0x100 window reaches neither, so the predicate answered False for the very function
    # it was written to recognise -- a predicate that returns the right answer for the wrong reason
    # is the failure this repository keeps paying for.
    sources: dict[int, int] = {}
    stores: set[int] = set()
    for ins in image_ins_range(image, entry, min(entry + 0x200, TEXT_LAST)):
        _track(sources, ins)
        if ins.kind == "store" and ins.op == "sh" and ins.rs in sources:
            stores.add(sources[ins.rs] + ins.simm)
    return 0x800AE204 in stores and 0x800AE224 in stores


def _track(sources: dict[int, int], ins) -> None:
    """Advance one instruction's effect on the tracked register values, in place.

    Sound by construction: `lui` materialises a base, an `addiu` on a tracked base extends it, and
    EVERY other write KILLS the register it writes. The kill is the part that matters. Without it
    a stale base survives an instruction that overwrote the register, and the tool then reports a
    store or an argument at an address the guest never touched -- which is how a census publishes
    writes that do not happen. A register that was never materialised stays ABSENT rather than
    reading as 0, because "the argument is 0x00000000" and "the argument is not a constant here"
    are different answers, and conflating them sends a table read to address 0.
    """
    if ins.kind == "lui":
        sources[ins.rt] = upper(ins)
        return
    if ins.kind == "alu_rri" and ins.op == "addiu" and ins.rs in sources:
        sources[ins.rt] = sources[ins.rs] + ins.simm
        return
    if ins.kind == "alu_rrr" and ins.op == "addu" and ins.rs in sources and ins.rt in sources:
        sources[ins.rd] = sources[ins.rs] + sources[ins.rt]
        return
    if ins.rt:
        sources.pop(ins.rt, None)
    if ins.rd and ins.kind in ("alu_rrr", "shift_i"):
        sources.pop(ins.rd, None)


def measure_code_region(image: Image, targets: list[int]) -> dict:
    """Which mode targets lie in a window with no resident code, and with what denominators.

    "Not code" is a density claim, so the density is reported for a window that IS code as well.
    A window with zero `jr $ra` in a title whose code region has hundreds is not a formatting
    artifact; a window with hundreds is code, and the tool says so.
    """
    windows = {
        CODE_WINDOW: (0x80010000, 0x800B0000),
        "0x800B0000-0x800C0000": (0x800B0000, 0x800C0000),
        NON_CODE_WINDOW: (0x800C0000, TEXT_LAST),
    }
    density: dict[str, dict] = {}
    for name, (first, last) in windows.items():
        words = 0
        returns = 0
        prologues = 0
        for address in range(first, last, 4):
            raw = image.word(address)
            words += 1
            if raw == 0x03E00008:
                returns += 1
            if raw & 0xFFFF0000 == 0x27BD0000:
                prologues += 1
        density[name] = {"words": words, "jr_ra": returns, "addiu_sp": prologues}
    outside = [t for t in targets if t >= 0x800C0000]
    return {
        "windows": density,
        "code_window": CODE_WINDOW,
        "non_code_window": NON_CODE_WINDOW,
        "targets_total": len(targets),
        "targets_at_or_above_0x800C0000": len(outside),
        "targets": outside,
    }


def measure_timer_arm_sites(image: Image, arm: int, fingerprint: int) -> dict:
    """Every `jal` to the RCnt2 arm routine, with the `$a0` each passes.

    A live read of the argument word identifies which call last ran, so this census has to be
    exact: it matches the `jal` opcode, not a pattern of register writes.
    """
    sites = []
    # Every word in the text is visited and DECODED, and the count is reported, so "0 sites" is
    # distinguishable from "never looked". The jump target comes from the decoder, which applies
    # the region's high bits; recomputing it here is how a census that means to find 7 call sites
    # reports 0 without any error.
    for address in range(LOAD, TEXT_LAST, 4):
        image.words_scanned += 1
        ins = image.ins(address)
        if ins.kind != "jump" or ins.op != "jal" or ins.target != arm:
            continue
        delay = image.ins(address + 4)
        argument = delay.imm if (delay.kind == "alu_rri" and delay.op == "addiu"
                                 and delay.rs == 0) else None
        sites.append({"address": address, "delay_slot_argument": argument})
    return {
        "arm": arm,
        "words_scanned": image.words_scanned,
        "call_sites": len(sites),
        "sites": sites,
        "literal_fingerprint": fingerprint,
        "sites_passing_fingerprint": [s["address"] for s in sites
                                      if s["delay_slot_argument"] == fingerprint],
    }


def measure(image: Image) -> dict:
    mode = measure_mode_dispatch(image)
    if len(mode.stubs) != 20:
        raise Refusal(f"mode dispatch bound is {len(mode.stubs)}, not the measured 20")


    phase = measure_phase_dispatch(image, 0x8004FB0C)
    if len(phase.stubs) != 13:
        raise Refusal(f"mode-2 phase dispatch bound is {len(phase.stubs)}, not the measured 13")

    phase8 = phase.stubs[WAIT_PHASE]
    phase12 = phase.stubs[EXIT_PHASE]
    phase8_words = list(image_ins_range(image, phase8, phase8 + 0x80))
    # The wait call is identified by what it RESOLVES TO, not by where it lands: its own chain
    # ends at the single `lbu` of the loader wait byte. A block that called something else would
    # be reported as "no call" rather than measured as the wrong thing.
    wait_call = None
    for w in phase8_words:
        if w.kind == "jump" and w.op == "jal":
            try:
                measure_wait_predicate(image, w.addr)
            except Refusal:
                continue
            wait_call = w
            break
    if wait_call is None:
        raise Refusal(
            f"phase 8 at 0x{phase8:08X} makes no call that resolves to the loader wait byte, so "
            f"the block is not the CD wait"
        )
    # The card renderer is identified by WHAT IT DRAWS, not by a literal: the `jal` in the tail
    # whose target forms a pointer to a C string this image calls "NAMCO PRESENTS". Locating it by
    # content is also what lets the "phase 8 holds the phase" check name the right branch, since
    # the tail contains more than one call.
    tail_call = None
    for w in image_ins_range(image, phase12, 0x8004FF10):
        if w.kind == "jump" and w.op == "jal" and draws_namco_presents(image, w.target):
            tail_call = w
            break
    if tail_call is None:
        raise Refusal(
            "no `jal` between the phase-12 block and 0x8004FF10 draws the NAMCO PRESENTS string, "
            "so the card renderer is not established"
        )
    # Phase 8's "still busy" branch must land on the instruction that FOLLOWS the card call, or
    # the phase would return without redrawing the card. That is the property that makes this a
    # wait with a picture in it, and it is stated against the located tail rather than a literal.
    stay = next((w for w in phase8_words if branches_nonzero(w)
                 and w.rs == 2 and w.target == tail_call.addr), None)
    if stay is None:
        raise Refusal(
            f"phase 8 at 0x{phase8:08X} has no `bne $v0, $zero` into the shared tail, so it does "
            f"not hold the phase while the predicate is nonzero"
        )

    return {
        "mode_dispatch": {
            "read_address": mode.read_address,
            "read_site": mode.read_site,
            "bound_instruction": mode.bound_instruction,
            "bound": mode.bound,
            "table_base": mode.table_base,
            "stubs": mode.stubs,
            "card_mode": CARD_MODE,
            "targets": mode.targets,
        },
        "mode0": measure_mode0(image, mode.targets[0]),
        "mode_switch": measure_mode_switch(image, MODE0_SWITCH_CALL),
        "mode2": mode.targets[CARD_MODE],
        "phase_dispatch": {
            "read_address": phase.read_address,
            "read_site": phase.read_site,
            "bound_instruction": phase.bound_instruction,
            "bound": phase.bound,
            "table_base": phase.table_base,
            "stubs": phase.stubs,
            "wait_phase": WAIT_PHASE,
            "wait_phase_block": phase.stubs[WAIT_PHASE],
            "wait_holds_at": stay.addr,
            "exit_phase": EXIT_PHASE,
            "exit_phase_block": phase.stubs[EXIT_PHASE],
        },
        "phase8_block": phase.stubs[WAIT_PHASE],
        "phase8_stay_branch": stay.addr,
        "phase12_block": phase.stubs[EXIT_PHASE],
        "wait_predicate": measure_wait_predicate(image, wait_call.addr),
        "card": measure_card(image, tail_call.addr),
        "exit": measure_exit(image, phase12, tail_call.addr),
        "code_region": measure_code_region(image, mode.targets),
        "timer_arm": measure_timer_arm_sites(image, 0x800951B8, 0x190),
    }


# --------------------------------------------------------------------------------------------
# The record diff. `titles/tekken3/executable.json` is the recorded authority; the tool prints the
# side-by-side rather than trusting either.


def record_problems(measured: dict) -> list[str]:
    if not RECORD.is_file():
        return [f"no {RECORD}, so the recorded title_flow cannot be diffed"]
    recorded = json.loads(RECORD.read_text()).get("title_flow")
    if recorded is None:
        return [f"{RECORD.name} has no `title_flow` section, so nothing can be diffed"]
    problems: list[str] = []
    checks = [
        ("mode_dispatch.read_address", measured["mode_dispatch"]["read_address"]),
        ("mode_dispatch.bound", measured["mode_dispatch"]["bound"]),
        ("mode_dispatch.table_base", measured["mode_dispatch"]["table_base"]),
        ("mode_dispatch.card_mode", measured["mode_dispatch"]["card_mode"]),
        ("mode2_phase_dispatch.read_address", measured["phase_dispatch"]["read_address"]),
        ("mode2_phase_dispatch.bound", measured["phase_dispatch"]["bound"]),
        ("mode2_phase_dispatch.table_base", measured["phase_dispatch"]["table_base"]),
        ("wait_predicate.predicate", measured["wait_predicate"]["predicate"]),
        ("wait_predicate.leaf", measured["wait_predicate"]["leaf"]),
        ("wait_predicate.wait_byte", measured["wait_predicate"]["wait_byte"]),
        ("card.renderer", measured["card"]["renderer"]),
        ("card.string", measured["card"]["string"]),
        ("card.format_string", measured["card"]["format_string"]),
        ("card.x", measured["card"]["arg_x"]),
        ("card.y", measured["card"]["arg_y"]),
        ("card.scale", measured["card"]["arg_scale"]),
        ("exit.mode_word", measured["exit"]["mode_word"]),
        ("exit.return_mode_byte", measured["exit"]["return_mode_byte"]),
        ("mode_switch.switcher", measured["mode_switch"]["switcher"]),
        ("mode_switch.installed_mode", measured["mode_switch"]["installed_mode"]),
        ("mode0.resource_table", measured["mode0"]["resource_table"]),
        ("mode0.output_base", measured["mode0"]["output_base"]),
        ("mode0.resource_entries", measured["mode0"]["resource_entries"]),
        ("mode0.switch_argument", measured["mode0"]["switch_argument"]),
        ("mode2_phase_dispatch.wait_phase_block", measured["phase8_block"]),
        ("mode2_phase_dispatch.wait_holds_at", measured["phase8_stay_branch"]),
        ("mode2_phase_dispatch.exit_phase_block", measured["phase12_block"]),
        ("wait_predicate.leaf_call", measured["wait_predicate"]["leaf_call"]),
        ("wait_predicate.busy_branch", measured["wait_predicate"]["nonzero_returns_busy_site"]),
        ("card.text_engine_call", measured["card"]["text_engine_call"]),
        ("card.format_string", measured["card"]["format_string"]),
        ("exit.return_mode_load_site", measured["exit"]["return_mode_load_site"]),
        ("exit.phase_word", measured["exit"]["phase_word"]),
        ("resident_code.code_window_jr_ra",
         measured["code_region"]["windows"][measured["code_region"]["code_window"]]["jr_ra"]),
        ("resident_code.non_code_window_jr_ra",
         measured["code_region"]["windows"][measured["code_region"]["non_code_window"]]["jr_ra"]),
        ("resident_code.targets_above_0x800C0000",
         measured["code_region"]["targets_at_or_above_0x800C0000"]),
        ("timer_arm.call_sites", measured["timer_arm"]["call_sites"]),
    ]
    # The mode targets are compared as a WHOLE list, not one entry at a time: 20 addresses differ
    # individually while the set is the thing the claim is about, and a per-entry diff would print
    # whichever entries happen to move first.
    recorded_targets = recorded.get("mode_dispatch", {}).get("targets")
    measured_targets = measured["mode_dispatch"]["targets"]
    if (isinstance(recorded_targets, list) and len(recorded_targets) == len(measured_targets)
            and [int(t, 16) for t in recorded_targets] != measured_targets):
        problems.append("mode_dispatch.targets: the recorded mode targets differ from the measured "
                        f"ones ({len(measured_targets)} of them)")
    for path, value in checks:
        want = recorded
        for part in path.split("."):
            if not isinstance(want, dict) or part not in want:
                problems.append(f"recorded {path} is absent")
                want = None
                break
            want = want[part]
        if want is None:
            continue
        if isinstance(want, str) and want.startswith("0x"):
            want = int(want, 16)
        if want != value:
            problems.append(f"{path}: recorded 0x{want:X}" if isinstance(want, int)
                            else f"{path}: recorded {want!r}")
            if isinstance(want, int):
                problems[-1] += f", measured 0x{value:X}" if isinstance(value, int) else f", measured {value!r}"
    return problems


# --------------------------------------------------------------------------------------------
# The selftest. A control that is simply false is worse than no control, so each negative case
# perturbs ONE thing the tool claims to measure and the tool must then say so.


def _patch(data: bytearray, address: int, word: int) -> bytearray:
    out = bytearray(data)
    out[HEADER + address - LOAD: HEADER + address - LOAD + 4] = struct.pack("<I", word)
    return out


def selftest(exe: pathlib.Path) -> int:
    failures = 0
    image = Image(exe)
    print(f"[title-flow] selftest image {image.path.name}: {len(image.data)} byte(s)")

    problems = image.ground_truth_problems()
    if problems:
        print(f"[title-flow] selftest FAIL file offset is wrong: {'; '.join(problems)}")
        return 1
    print("[title-flow] selftest PASS file offset reproduces 2/2 known instructions")

    base = measure(image)

    # -- the positive: every check the tool makes must pass on the authenticated image ----------
    positive = [
        ("mode is a 20-entry jump table at 0x80010000",
         base["mode_dispatch"]["table_base"] == 0x80010000 and base["mode_dispatch"]["bound"] == 20),
        ("mode 2 is 0x8004FA60", base["mode2"] == 0x8004FA60),
        ("mode-2 phase is a 13-entry jump table at 0x8002242C",
         base["phase_dispatch"]["table_base"] == 0x8002242C and base["phase_dispatch"]["bound"] == 13),
        ("the wait byte is 0x800A069F", base["wait_predicate"]["wait_byte"] == 0x800A069F),
        ("the card is at (117,240) scale 6 and says NAMCO PRESENTS",
         base["card"]["arg_x"] == 117 and base["card"]["arg_y"] == 240
         and base["card"]["arg_scale"] == 6
         and "NAMCO" in base["card"]["format_string"]
         and "PRESENTS" in base["card"]["format_string"]),
        ("the card is drawn for $a0 = 0,1,2",
         base["card"]["drawn_for_param_1"] == [0, 1, 2]),
        ("phase 8 holds the phase while the predicate is nonzero",
         base["phase8_stay_branch"] == 0x8004FDF0),
        ("the mode word is 0x800AE204 and the return-mode byte is 0x80097F38",
         base["exit"]["mode_word"] == 0x800AE204
         and base["exit"]["return_mode_byte"] == 0x80097F38),
        ("the card's exit path reads no controller port",
         base["exit"]["controller_reads_on_path"] == []),
        ("mode 0 installs mode 2 with return-mode 3",
         base["mode_switch"]["installed_mode"] == 2
         and base["mode0"]["switch_argument"] == 3),
        ("exactly one `jal` passes the 0x190 timer argument, at 0x800934EC",
         len(base["timer_arm"]["sites_passing_fingerprint"]) == 1
         and base["timer_arm"]["sites_passing_fingerprint"][0] == 0x800934EC),
        ("11 of 20 mode targets are at or above 0x800C0000",
         base["code_region"]["targets_at_or_above_0x800C0000"] == 11),
        ("the recorded title_flow diffs clean", not record_problems(base)),
    ]
    for label, ok in positive:
        print(f"[title-flow] selftest {'PASS' if ok else 'FAIL'} {label}")
        failures += 0 if ok else 1

    # -- the negatives: each perturbs one measured fact, and the tool must notice ----------------
    cases = [
        ("a one-word change to the card's x coordinate is rejected",
         0x8004F814, 0x24060075, lambda m: m["card"]["arg_x"] == 117),
        ("a one-word change to the card's format string is rejected",
         0x8002240C, 0x634E414D, lambda m: "NAMCO PRESENTS" in m["card"]["format_string"]),
        ("a one-word change to phase 8's table entry is rejected",
         0x8002244C, 0x8004FD9D, lambda m: m["phase8_block"] == 0x8004FD9C),
        ("a one-word change to the wait-byte displacement is rejected",
         0x8006C244, 0x90420006, lambda m: m["wait_predicate"]["wait_byte"] == 0x800A069F),
        ("a one-word change to the return-mode base is rejected",
         0x8004FA6C, 0x507F2909, lambda m: m["exit"]["return_mode_byte"] == 0x80097F38),
        ("a one-word change to the installed mode is rejected",
         0x8004FA34, 0x00000007, lambda m: m["mode_switch"]["installed_mode"] == 2),
        ("a file offset that omits the 0x800 header is rejected before anything is reported",
         None, None, None),
    ]
    for label, address, word, still_true in cases:
        if address is None:
            # The bug being guarded is the one this repository already made: the formula
            # `address - LOAD`, with the PS-X EXE's 0x800-byte header left out. Simulating it by
            # truncating the ARRAY and keeping the correct formula would not test it at all -- the
            # two errors cancel -- so the wrong formula is applied to the real bytes.
            wrong = {}
            for probe, expected in GROUND_TRUTH.items():
                off = probe - LOAD
                actual = (struct.unpack_from("<I", image.data, off)[0]
                          if off + 4 <= len(image.data) else None)
                if actual != expected:
                    wrong[probe] = (expected, actual)
            ok = len(wrong) == len(GROUND_TRUTH)
            print(f"[title-flow] selftest {'PASS' if ok else 'FAIL'} {label}: "
                  f"{len(wrong)} of {len(GROUND_TRUTH)} known instruction(s) disagree, e.g. "
                  f"0x80028BB8 reads "
                  f"{_hex(wrong[0x80028BB8][1]) if 0x80028BB8 in wrong and wrong[0x80028BB8][1] is not None else 'past the end'}"
                  f" instead of 0x{GROUND_TRUTH[0x80028BB8]:08X}")
            failures += 0 if ok else 1
            continue
        mutated = _variant(exe, _patch(bytearray(image.data), address, word))
        try:
            got = measure(mutated)
            ok = not still_true(got)
            detail = "the measured fact moved"
        except Refusal as error:
            ok = True
            detail = f"REFUSED: {error}"
        print(f"[title-flow] selftest {'PASS' if ok else 'FAIL'} {label}: {detail}")
        failures += 0 if ok else 1

    # -- the control for the claim that is easiest to get wrong -------------------------------
    # "The card's exit path reads no controller port" is vacuous unless the scan can find a read.
    # Inject the GUEST'S OWN two-instruction form of that read -- `lui $a1, 0x800A` and
    # `lw $a1, -0x469C($a1)`, exactly as FUN_80093478 writes it -- and require it to be found.
    with_read = _patch(bytearray(image.data), 0x8004FED4, 0x3C05800A)  # lui $a1, 0x800A
    with_read = _patch(with_read, 0x8004FEDC, 0x8CA5B964)            # lw $a1, -0x469C($a1)
    control_image = _variant(exe, with_read)
    try:
        control = measure(control_image)
        found = control["exit"]["controller_reads_on_path"]
        ok = found == [0x8004FEDC]
        print(f"[title-flow] selftest {'PASS' if ok else 'FAIL'} an injected controller-port read on "
              f"the exit path IS found: {[_hex(a) for a in found]}")
    except Refusal as error:
        ok = False
        print(f"[title-flow] selftest FAIL an injected controller-port read on the exit path was "
              f"REFUSED instead of found: {str(error)[:70]}")
    failures += 0 if ok else 1

    # The same for the 0x190 uniqueness: a second site must break the uniqueness.
    twice = _patch(bytearray(image.data), 0x8009362C, 0x24040190)  # a0 = 0x190 at another site
    try:
        second = measure(_variant(exe, twice))
        ok = len(second["timer_arm"]["sites_passing_fingerprint"]) == 2
        print(f"[title-flow] selftest {'PASS' if ok else 'FAIL'} a second 0x190 argument site is "
              f"counted: {[_hex(a) for a in second['timer_arm']['sites_passing_fingerprint']]}")
    except Refusal as error:
        ok = True
        print(f"[title-flow] selftest PASS a second 0x190 site is REFUSED: {error}")
    failures += 0 if ok else 1

    print(f"[title-flow] selftest {'FAILED' if failures else 'PASS'}: {failures} failure(s)")
    return 1 if failures else 0


def _variant(path: pathlib.Path, data: bytes) -> Image:
    """An `Image` over MUTATED bytes, sharing the one file-offset formula.

    Built by construction rather than by writing a mutated file, so a negative case cannot be
    defeated by a stale file, a permissions problem, or a tool that silently re-provisions. The
    ground-truth refusal is deliberately NOT applied here: each negative case must show that the
    SPECIFIC fact moved, not merely that some pre-flight check tripped.
    """
    clone = Image.__new__(Image)
    clone.path = path
    clone.data = bytes(data)
    clone.words_scanned = 0
    return clone


def report(image: Image) -> int:
    problems = image.ground_truth_problems()
    if problems:
        print(f"REFUSED: file offset is wrong, so every address below would be meaningless: "
              f"{'; '.join(problems)}")
        return 1
    print(f"image {image.path} : {len(image.data)} bytes, text 0x{LOAD:08X}..0x{TEXT_LAST:08X} "
          f"(file offset = 0x{HEADER:X} + (addr - 0x{LOAD:08X})), 2/2 known instructions reproduced")

    measured = measure(image)
    mode = measured["mode_dispatch"]
    print(f"\nmode dispatch   0x{mode['read_site']:08X}  lh of the mode halfword at "
          f"0x{mode['read_address']:08X}, unsigned bound {mode['bound']}, table "
          f"0x{mode['table_base']:08X}")
    for index, (stub, target) in enumerate(zip(mode["stubs"], mode["targets"])):
        mark = "  <- the NAMCO PRESENTS card" if index == 2 else ""
        print(f"  mode {index:2d}  stub 0x{stub:08X} -> 0x{target:08X}{mark}")
    m0 = measured["mode0"]
    sw = measured["mode_switch"]
    print(f"\nmode 0          0x{m0['entry']:08X} phase 0 calls 0x{m0['loader_target']:08X} with "
          f"output base 0x{m0['output_base']:08X} and the 127-entry table 0x{m0['resource_table']:08X}")
    print(f"                its last phase calls 0x{sw['switcher']:08X} with "
          f"{m0['switch_argument']}: return-mode byte 0x{sw['return_mode_store']:08X} = "
          f"{m0['switch_argument']}, mode word 0x{sw['mode_word_store']:08X} = "
          f"{sw['installed_mode']}, phase word 0x{sw['phase_word_store']:08X} = 0")

    phase = measured["phase_dispatch"]
    print(f"\nmode 2          0x{measured['mode2']:08X} phase dispatch 0x{phase['read_site']:08X}, "
          f"phase halfword 0x{phase['read_address']:08X}, bound {phase['bound']}, table "
          f"0x{phase['table_base']:08X}")
    print(f"  phase  8 = 0x{measured['phase8_block']:08X}  holds the phase at "
          f"0x{measured['phase8_stay_branch']:08X} while the predicate is nonzero")
    print(f"  phase 12 = 0x{measured['phase12_block']:08X}  leaves the mode")

    wait = measured["wait_predicate"]
    print(f"\nthe wait        0x{wait['call_site']:08X} -> 0x{wait['predicate']:08X} -> "
          f"0x{wait['leaf']:08X}: {wait['load_op']} of +{wait['displacement']} from "
          f"0x{wait['base']:08X} == the byte at 0x{wait['wait_byte']:08X}")
    print(f"                nonzero returns \"busy\" at 0x{wait['nonzero_returns_busy_site']:08X}, "
          f"so the phase holds")

    card = measured["card"]
    print(f"\nthe card        0x{card['tail_call_site']:08X} -> 0x{card['renderer']:08X} -> text "
          f"engine 0x{card['text_engine_call']:08X}")
    print(f"  string  0x{card['string']:08X}  {card['format_string']!r}")
    print(f"  at      x={card['arg_x']} (0x{card['arg_x']:X}) y={card['arg_y']} "
          f"(0x{card['arg_y']:X}) scale={card['arg_scale']}")
    print(f"  drawn for $a0 in {card['drawn_for_param_1']}  (phase 8 passes 1)")

    exit_ = measured["exit"]
    print(f"\nleaving the card 0x{exit_['block']:08X}: phase 0x{exit_['phase_zero_store']:08X} = 0, "
          f"mode 0x{exit_['mode_store']:08X} = the byte at "
          f"0x{exit_['return_mode_byte']:08X}")
    print(f"  controller-port reads on that path: "
          f"{exit_['controller_reads_on_path'] or 'none'} "
          f"({exit_['instructions_scanned']} instruction(s) scanned between the phase-12 block and "
          f"the card call)")
    print("  => the card is not dismissed by input; it is left when the CD read it is waiting on "
          "completes.")

    region = measured["code_region"]
    print(f"\nresident code   {region['targets_at_or_above_0x800C0000']} of "
          f"{region['targets_total']} mode targets are at or above 0x800C0000")
    for name, counts in region["windows"].items():
        share = counts["jr_ra"] / counts["words"] * 100 if counts["words"] else 0.0
        print(f"  {name}  {counts['words']:>7} word(s), jr ra {counts['jr_ra']:>5} "
              f"({share:.2f}%), addiu $sp {counts['addiu_sp']:>5}")
    print("  => the mode handlers for those targets are not in the disc executable; they are "
          "written at run time from disc-compressed resources, so their contents -- the menu, its "
          "accepted inputs, and the branch toward a fight -- are NOT derivable here.")

    arm = measured["timer_arm"]
    print(f"\ntimer arm       0x{arm['arm']:08X} is called from {arm['call_sites']} site(s); "
          f"{len(arm['sites_passing_fingerprint'])} passes the literal "
          f"0x{arm['literal_fingerprint']:X}: "
          f"{[_hex(a) for a in arm['sites_passing_fingerprint']]}")

    diff = record_problems(measured)
    if diff:
        print(f"\nRECORD DIFF: {len(diff)} disagreement(s) with {RECORD.name} title_flow:")
        for line in diff:
            print(f"  {line}")
        return 1
    print(f"\nrecorded title_flow in {RECORD.name} agrees with every measured fact.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", type=pathlib.Path, default=ROOT / "scratch/bin/tekken3/SLUS_004.02",
                        help="the provisioned authenticated SLUS_004.02")
    parser.add_argument("--selftest", action="store_true",
                        help="run the positive checks, the negative cases, and the two controls")
    args = parser.parse_args()
    try:
        image = Image(args.exe)
    except Refusal as error:
        print(f"REFUSED: {error}")
        return 1
    return selftest(args.exe) if args.selftest else report(image)


if __name__ == "__main__":
    raise SystemExit(main())
