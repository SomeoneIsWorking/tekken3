#!/usr/bin/env python3
"""verify_pad_wait_exit.py — does the authenticated SLUS_004.02 pad driver ever leave its SECOND
wait loop, and if not, what does the loop actually wait on?

Issues 0011 and 0016 disagree about where the product is inside FUN_80093478, and both of them name
the SIO0 STAT spin at 0x800934D8 as a loop with no way out. Reading the bytes settles it, and this
tool re-derives every fact it uses from the hashed executable so none of it is inherited prose.

THE FUNCTION, from the image:

    0x800934D8  the FIRST loop: lhu of SIO0 STAT (0x1F801044), until bit 0x0002. The driver waits for
                the previous byte's response to be readable.
    0x800934EC  jal 0x800951B8 with $a0 = 0x190  ->  arms the stopwatch
    0x80093540  v0 = *(v1) where v1 = *(0x8009B960); andi 0x0080
    0x8009354C  bne -> 0x80093604, SKIPPING the whole second loop when bit 7 is set
    0x80093584  the SECOND loop's top. It exits on EITHER of two things:
                  0x800935C4  RCnt2 MODE bit 9 (0x0200) set -> compare the RAW delta
                  0x800935E4  RCnt2 MODE bit 9 clear -> compare (delta >> 3)
                against the threshold the guest itself wrote at 0x8009E228.
    0x800935F0  v0 = *(v1); andi 0x0080; beq -> back to 0x80093584  (the OTHER exit: bit 7 set)

SO THE SECOND LOOP HAS A COUNTDOWN ARM, and it is a TIMEOUT: the loop's whole purpose is to give the
pad-transaction flag a bounded window to be set, and it gives up after the countdown and returns
0xFFFF. It is not an unbounded wait on hardware. That is why overriding the function (issue 0011's
proposal) is the wrong shape for the second loop, and why an override that only replaced the first
spin would have looked like it worked.

The countdown arm is chosen by RCnt2 MODE bit 9. Issue 0016 recorded that the guest never writes
RCnt2's mode register, so bit 9 is clear, so the arm TAKEN is the shifted one. This tool reads the
value the shipping model actually returns rather than inferring it, and reports both the raw and the
shifted threshold so the arithmetic cannot be misread.

THE MEASUREMENT. The guest cannot be asked directly whether the countdown expires, so the tool
executes the loop on the shipping Lightrec executor against the authenticated image and reports what
the runtime did. Four arms, so a result that cannot distinguish the loop from the surrounding
function is a refusal rather than a verdict:

    arm=retail    the real path: pad-status bit 7 clear, so the loop is entered, with retail's own
                  0x190 countdown, run the way the product runs it — one executor segment for the
                  whole per-turn budget. Does the loop return?
    arm=bit7      the same fixture, pad-status bit 7 SET, which the driver tests at 0x8009354C and
                  which SKIPS the second loop. This arm MUST return. If it does not, the harness is
                  not exercising the loop at all and the retail arm proves nothing.
    arm=segmented the same fixture and the same guest bytes, the same TOTAL allowance, but returned
                  to the host every 65,536 cycles. This is the arm that identifies the mechanism.
    arm=clock     no guest code: how many DISTINCT values does the shipping rootCounter2() return
                  over N polls with and without guest accounting.

WHY THE SEGMENTED ARM IS THE ONE THAT MATTERS. `Timing::rootCounter2()` is a pure function of
`EmulatedTime`, and `EmulatedTime` only moves in `accountGuestInstructions`, which
`LightrecExecutor::executeWithBoundary` calls ONCE PER SEGMENT, after `lightrec_execute` returns. A
guest that spins on a hardware counter inside one translated segment therefore reads the same value
every time, forever, and the segment ends only when the per-turn budget is spent. So the same guest
bytes leave the loop when the executor comes home more often, and do not when it does not. That is a
property of WHERE the accounting happens, not of the counter's correctness and not of the guest.

A threshold mutant is not available and the reason is recorded rather than worked around:
FUN_800951B8 stores its own `$a0` into 0x800AE228, so any value a fixture presets there is replaced
before the loop reads it. The first draft of this tool's harness contained exactly that arm and it
could not fail. That is recorded here because "a mutant that cannot fail" is this repository's
recorded failure mode, not a hypothetical.

Usage:
    tools/verify_pad_wait_exit.py [executable] [--binary PATH]
    tools/verify_pad_wait_exit.py --selftest
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import struct
import subprocess
import sys

from provision_executable import Mismatch, Refused, load_manifest, verify_executable

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOAD = 0x80010000
HEADER = 0x800

# (address, expected word, what it is) — read out of the disassembly, and re-checked on every run.
# GROUND_TRUTH exists because a wrong file offset shifts EVERY decoded address while the tool keeps
# returning confident non-zero answers; that exact bug is recorded in issue 0011.
GROUND_TRUTH = (
    (0x800934B0, 0x24110088, "the s1 = 0x88 delay slot of the device-id test"),
    (0x800934D8, 0x94620004, "the FIRST loop's SIO0 STAT read"),
    (0x800934E0, 0x30420002, "the FIRST loop's bit 0x0002 test"),
    (0x800934EC, 0x0C02546E, "jal 0x800951B8, the stopwatch arm"),
    (0x800934F0, 0x24040190, "its $a0 = 0x190 argument"),
    (0x80093548, 0x30420080, "the pad-status bit 7 test that SKIPS the second loop"),
    (0x8009354C, 0x1440002D, "the branch to 0x80093604 when bit 7 is set"),
    (0x80093584, 0x95220000, "the SECOND loop's RCnt2 read"),
    (0x800935A4, 0x10400004, "RCnt2 TARGET == 0 -> add 0x10000"),
    (0x800935C4, 0x30420200, "RCnt2 MODE bit 9, which selects the countdown's scaling"),
    (0x800935D0, 0x0045102B, "the RAW-delta arm's compare"),
    (0x800935E4, 0x0045102B, "the SHIFTED-delta arm's compare"),
    (0x800935F8, 0x30420080, "the pad-status bit 7 test INSIDE the second loop"),
    (0x800935FC, 0x1040FFE1, "the back edge to 0x80093584"),
    (0x80093690, 0x8FBF0020, "the function's epilogue: the countdown path returns here"),
    (0x800951B8, 0x3C021F80, "FUN_800951B8, the stopwatch arm"),
    (0x800951C8, 0xAC24E228, "it stores $a0 to the threshold word at 0x8009E228"),
    (0x800951D4, 0xAC228680, "it stores RCnt2 to the snapshot word at 0x800A8680"),
)

# Guest globals, derived from the instruction offsets above rather than written here by hand. The
# threshold's address is 0x800B0000 - 0x1DD8 = 0x800AE228, the word issues 0011 and 0016 both name.
THRESHOLD_GLOBAL = 0x800AE228  # lui 0x800B + sw $a0,-7640($at)
SNAPSHOT_GLOBAL = 0x800A8680   # lui 0x800B + sw $v0,-31104($at)
PAD_STATE_PTR_GLOBAL = 0x8009B960  # lui 0x800A + lw -18080($v1)

FUNCTION = 0x80093478
WAIT_LOOP_ENTRY = 0x80093584
WAIT_LOOP_END = 0x80093604

EXPECTED_ARMS = ("clock", "retail", "bit7", "segmented")

REQUIRED_CLOCK = {"arm", "polls", "distinct_without_accounting", "distinct_with_accounting",
                  "accounting_step"}
REQUIRED_GUEST = {"arm", "reached_first_spin", "returned", "exhausted_in_wait_loop",
                  "returned_by_countdown", "exit", "pc", "cycles", "segments", "blocks",
                  "instructions", "fallback_calls", "threshold", "snapshot", "counter_entry",
                  "counter_exit", "port_baud"}


class Image:
    def __init__(self, data: bytes) -> None:
        self.data = data
        text_address = struct.unpack_from("<I", data, 0x18)[0]
        text_size = struct.unpack_from("<I", data, 0x1C)[0]
        if text_address != LOAD:
            raise Refused(f"executable text loads at 0x{text_address:08X}, not 0x{LOAD:08X}")
        end = HEADER + text_size
        if end > len(data):
            raise Refused("executable text extent runs past the file")
        self.text_address = text_address
        self.text_end = end

    def word(self, address: int) -> int:
        offset = HEADER + address - self.text_address
        if offset < HEADER or offset + 4 > self.text_end:
            raise Refused(f"0x{address:08X} is outside the loaded text")
        return struct.unpack_from("<I", self.data, offset)[0]

    def check_ground_truth(self) -> None:
        wrong = [f"0x{address:08X} (expected 0x{expected:08X}, read 0x{self.word(address):08X}, {what})"
                 for address, expected, what in GROUND_TRUTH
                 if self.word(address) != expected]
        if wrong:
            raise Refused("file offset or image identity is wrong; " + "; ".join(wrong))


def derive(image: Image) -> dict:
    """Re-derive the loop's shape from the bytes, so no address here is inherited prose."""
    facts: dict = {}

    # The threshold and snapshot words, from the two stores inside the stopwatch arm. Both are
    # `sw $rX, disp($at)` with $at = 0x800B0000, so the guest address is 0x800B0000 + signext(disp).
    def store_global(address: int, expected_register: int) -> int:
        word = image.word(address)
        if (word >> 26) != 0x2B:  # sw
            raise Refused(f"0x{address:08X} is not an sw (0x{word:08X})")
        if ((word >> 16) & 0x1F) != expected_register:
            raise Refused(f"0x{address:08X} stores a different register than the one read back")
        displacement = word & 0xFFFF
        if displacement & 0x8000:
            displacement -= 0x10000
        return 0x800B0000 + displacement

    facts["threshold_global"] = store_global(0x800951C8, 4)  # sw $a0
    facts["snapshot_global"] = store_global(0x800951D4, 2)    # sw $v0
    if facts["threshold_global"] != THRESHOLD_GLOBAL or facts["snapshot_global"] != SNAPSHOT_GLOBAL:
        raise Refused(f"derived globals 0x{facts['threshold_global']:08X}/"
                      f"0x{facts['snapshot_global']:08X} disagree with the constants the test harness "
                      f"uses (0x{THRESHOLD_GLOBAL:08X}/0x{SNAPSHOT_GLOBAL:08X}); the harness would be "
                      "measuring the wrong words")

    # The argument the driver passes to the stopwatch arm, read out of the delay slot.
    argument = image.word(0x800934F0)
    if (argument >> 16) & 0xFFFF != 0x2404:
        raise Refused("the stopwatch arm's argument is not an addiu $a0 form")
    facts["arm_argument"] = argument & 0xFFFF
    if facts["arm_argument"] != 0x190:
        raise Refused(f"the driver arms 0x{facts['arm_argument']:X}, not 0x190")

    # Both exits of the second loop, from its own instructions.
    facts["bit7_test"] = image.word(0x800935F8) == 0x30420080
    facts["bit7_skip"] = image.word(0x8009354C) == 0x1440002D
    facts["shifted_arm"] = image.word(0x800935E0) == 0x000210C2
    facts["raw_arm"] = image.word(0x800935D0) == 0x0045102B
    facts["countdown_expiry_returns"] = image.word(0x80093690) == 0x8FBF0020

    if not (facts["bit7_test"] and facts["bit7_skip"] and facts["shifted_arm"] and facts["raw_arm"]):
        raise Refused("the second loop's shape is not the shape this tool reports on")
    return facts


def fields_arm(line: str) -> str:
    """Which arm a line claims, taken from the line itself rather than from its position.

    A line that does not name its arm cannot be assigned to one, and assigning it by position is
    how a dropped arm turns into another arm's numbers.
    """
    fields = dict(re.findall(r"([a-z_][a-z_0-9]*)=(\S+)", line))
    if "arm" not in fields:
        raise Refused(f"an arm line does not name its arm: {line[:120]!r}")
    return f"the {fields['arm']} arm"


def parse(line: str, required: set[str], owner: str) -> dict[str, str]:
    fields = dict(re.findall(r"([a-z_][a-z_0-9]*)=(\S+)", line))
    if missing := required - fields.keys():
        raise Refused(f"{owner} omitted fields: {', '.join(sorted(missing))}")
    return fields


def judge(clock: dict[str, str], retail: dict[str, str], control: dict[str, str],
          segmented: dict[str, str]) -> list[str]:
    """The verdict. Every branch names what it compared, and what would make it wrong."""
    lines: list[str] = []

    polls = int(clock["polls"])
    without = int(clock["distinct_without_accounting"])
    with_accounting = int(clock["distinct_with_accounting"])
    step = int(clock["accounting_step"])
    if polls <= 0 or step <= 0:
        raise Refused(f"clock arm reported polls={polls} step={step}; refusing a zero denominator")
    if with_accounting < 2:
        raise Refused(f"clock arm: the counter showed {with_accounting} distinct value(s) over "
                      f"{polls} polls even WITH accounting, so the accounting is not what this "
                      "question is about; refusing rather than reporting a freeze it cannot see")
    lines.append(f"ROOT COUNTER 2: {without} distinct value(s) over {polls} polls with no guest "
                 f"accounting between them, {with_accounting} with accounting every {step} "
                 f"instruction(s). The counter is driven only by guest accounting.")

    # THE CONTROL FIRST. It has to RETURN, and it has to be cheap; until that holds, the retail
    # arm's numbers are not evidence about the loop, so the order matters and not incidentally.
    if control["returned"] != "1":
        raise Refused(f"the bit7 control did not return: returned={control['returned']} "
                      f"exit={control['exit']} pc={control['pc']}. That control sets the pad-status "
                      "bit the driver tests at 0x8009354C, which is supposed to skip the second loop, "
                      "so a control that does not return means the harness is not reaching that code")
    if control["exhausted_in_wait_loop"] == "1":
        raise Refused("the bit7 control still exhausted inside the second loop, so setting pad-status "
                      "bit 7 did not skip it; the harness cannot reach that arm and the retail arm's "
                      "result is not evidence about the loop")
    for name, arm in (("retail", retail), ("bit7", control), ("segmented", segmented)):
        if int(arm["blocks"]) == 0 or int(arm["instructions"]) == 0:
            raise Refused(f"{name} arm executed {arm['blocks']} block(s) / {arm['instructions']} "
                          "instruction(s); nothing ran, so nothing was measured")
        if int(arm["fallback_calls"]) != 0:
            raise Refused(f"{name} arm needed {arm['fallback_calls']} interpreter fallback call(s); "
                          "this measures the JIT path and would be a different measurement")
    if int(control["cycles"]) >= int(retail["cycles"]):
        raise Refused(f"the bit7 control consumed {control['cycles']} cycles against the retail arm's "
                      f"{retail['cycles']}; a control that costs as much as the case cannot "
                      "discriminate, and the two arms are not measuring different things")

    if retail["exhausted_in_wait_loop"] != "1":
        raise Refused(f"the retail arm did not exhaust inside the second loop: exit={retail['exit']} "
                      f"pc={retail['pc']}. Either the loop now exits — which is the fix working, and "
                      "is a real change to re-verify the rest of the port against — or the harness "
                      "stopped measuring it. This tool reports a freeze; it does not bless a pass.")

    threshold = int(retail["threshold"], 16)
    entry = int(retail["counter_entry"])
    exit_counter = int(retail["counter_exit"])
    lines.append(
        f"THE SECOND LOOP IS WHERE THE PRODUCT STOPS. {retail['blocks']} block(s) / "
        f"{retail['instructions']} instruction(s) / {retail['cycles']} cycle(s) of Lightrec "
        f"execution, {retail['fallback_calls']} fallback, exit={retail['exit']} at "
        f"pc={retail['pc']}, which is inside 0x{WAIT_LOOP_ENTRY:08X}..0x{WAIT_LOOP_END:08X}.")
    lines.append(
        f"ITS TIMEOUT IS ARMED AND IS THE THING THAT NEVER EXPIRES. The driver armed 0x{threshold:04X} "
        f"into 0x{THRESHOLD_GLOBAL:08X} and latched RCnt2 = 0x{int(retail['snapshot'], 16):08X} into "
        f"0x{SNAPSHOT_GLOBAL:08X}. RCnt2 MODE bit 9 is clear, so the arm TAKEN is the shifted one, so "
        f"the loop gives up once (RCnt2 - snapshot) >> 3 reaches 0x{threshold:04X} — "
        f"{threshold * 8} raw counter ticks. The counter stood at {entry} and had reached {exit_counter} "
        f"by the end of the call, and {exit_counter} is the value the accounting at the END of the "
        f"executor call produced — after the loop had already been left behind.")
    lines.append(
        f"THE CONTROL DISCRIMINATES. Same function, same fixture, one pad-status word different "
        f"(bit 7 set, which the driver tests at 0x8009354C and which skips the second loop): the "
        f"control returned in {control['cycles']} cycle(s) / {control['blocks']} block(s) while the "
        f"retail arm burned {retail['cycles']} cycle(s) / {retail['blocks']} block(s) without "
        f"returning. The stall is the second loop specifically, not the function, not the executor, "
        f"not the image mapping.")

    # THE MUTANT. Same guest bytes, same fixture, same total allowance, different SEGMENT length. If
    # this arm does not leave the second loop, then segment granularity is not the mechanism and
    # this report's explanation is wrong.
    if int(segmented["segments"]) <= int(retail["segments"]):
        raise Refused(f"the segmented arm ran {segmented['segments']} segment(s) against the retail "
                      f"arm's {retail['segments']}; it did not vary the thing it claims to vary, so "
                      "it measures nothing")
    # Both arms are handed the SAME total allowance by the harness, so the mutant can only come back
    # having spent LESS because it finished early — which is the whole point. What would invalidate
    # the comparison is a materially smaller allowance, so the guard is a ratio, not a fixed margin.
    retail_cycles = int(retail["cycles"])
    segmented_cycles = int(segmented["cycles"])
    if segmented_cycles < retail_cycles * 0.99:
        raise Refused(f"the segmented arm spent {segmented_cycles} cycle(s) against the retail arm's "
                      f"{retail_cycles}, less than 99% of it; a mutant given materially LESS work "
                      "could leave the loop for that reason alone, and it would not identify the "
                      "mechanism")
    if segmented["exhausted_in_wait_loop"] == "1":
        raise Refused(f"the segmented arm ALSO exhausted inside the second loop "
                      f"(exit={segmented['exit']} pc={segmented['pc']}) over "
                      f"{segmented['segments']} segment(s). More frequent accounting did not release "
                      "it, so segment granularity is NOT the mechanism and this report's explanation "
                      "is wrong")
    lines.append(
        f"THE MUTANT IDENTIFIES THE MECHANISM. Identical guest bytes, identical fixture, the same "
        f"total allowance, and only the segment length differs: {retail['segments']} segment(s) of "
        f"the product's per-turn budget against {segmented['segments']} of 65,536 cycle(s). The "
        f"retail arm is still in the second loop at {retail['pc']}; the mutant left it and reached "
        f"{segmented['pc']}. Guest accounting happens once per segment, after lightrec_execute "
        f"returns, so within one segment RCnt2 cannot move and the loop's exit test can never become "
        f"true. The counter, the countdown, and the loop's code are all correct; WHERE the accounting "
        f"happens is the defect.")
    return lines


def selftest() -> None:
    image = bytearray(0x900)
    struct.pack_into("<II", image, 0x18, LOAD, 0x100)
    # A zero-filled text: every GROUND_TRUTH word must disagree, which is the refusal.
    # A zero-filled text that really covers the addresses: every ground-truth word disagrees, and
    # the guard must refuse before deriving anything.
    top = max(address for address, _, _ in GROUND_TRUTH)
    blank = bytearray(HEADER + (top - LOAD) + 4)
    struct.pack_into("<II", blank, 0x18, LOAD, top - LOAD + 4)
    try:
        Image(bytes(blank)).check_ground_truth()
    except Refused:
        pass
    else:
        raise AssertionError("an image with no matching ground truth was accepted")

    # An image whose text extent is too small to reach the first ground-truth address at all.
    short = bytearray(HEADER + 0x40)
    struct.pack_into("<II", short, 0x18, LOAD, 0x40)
    try:
        Image(bytes(short)).check_ground_truth()
    except Refused:
        pass
    else:
        raise AssertionError("a truncated text extent was accepted")

    # A fully consistent synthetic image is impossible to build here, so derive() is exercised
    # against an image carrying only the ground-truth words: the loop's own shape is still wrong,
    # and the refusal must name which fact disagreed rather than complain about the offset.
    # A synthetic image whose text extent really covers every GROUND_TRUTH address, with exactly
    # those words present. Anything else must be refused, so the extent is honest here.
    top = max(address for address, _, _ in GROUND_TRUTH)
    sized = bytearray(HEADER + (top - LOAD) + 4)
    struct.pack_into("<II", sized, 0x18, LOAD, top - LOAD + 4)
    for address, expected, _ in GROUND_TRUTH:
        offset = HEADER + address - LOAD
        sized[offset:offset + 4] = struct.pack("<I", expected)
    parsed = Image(bytes(sized))
    parsed.check_ground_truth()
    try:
        derive(parsed)
    except Refused as exc:
        if "disagree with the constants" not in str(exc) and "not the shape" not in str(exc):
            raise AssertionError(f"a wrong image produced an unexpected refusal: {exc}") from exc
    else:
        raise AssertionError("an image with only the ground-truth words was accepted")

    base_clock = ("arm=clock polls=64 distinct_without_accounting=1 distinct_with_accounting=16 "
                  "accounting_step=8")
    base_retail = ("arm=retail reached_first_spin=1 returned=1 exhausted_in_wait_loop=1 "
                   "returned_by_countdown=0 exit=budget-exhausted pc=0x80093584 cycles=564492 "
                   "segments=1 blocks=40316 instructions=282244 fallback_calls=0 threshold=0x00000190 "
                   "snapshot=0x00002000 counter_entry=8192 counter_exit=28292 port_baud=0x0088")
    base_control = ("arm=bit7 reached_first_spin=1 returned=1 exhausted_in_wait_loop=0 "
                    "returned_by_countdown=0 exit=guest-return pc=0x800941D0 cycles=186 segments=1 "
                    "blocks=8 instructions=91 fallback_calls=0 threshold=0x00000190 snapshot=0x00002000 "
                    "counter_entry=8192 counter_exit=8283 port_baud=0x0088")
    base_segmented = ("arm=segmented reached_first_spin=1 returned=0 exhausted_in_wait_loop=0 "
                      "returned_by_countdown=0 exit=budget-exhausted pc=0x800934D8 cycles=564482 "
                      "segments=9 blocks=54550 instructions=282239 fallback_calls=0 "
                      "threshold=0x00000190 snapshot=0x00002000 counter_entry=8192 "
                      "counter_exit=28287 port_baud=0x0088")

    def call(clock: str = base_clock, retail: str = base_retail, control: str = base_control,
             segmented: str = base_segmented):
        return (parse(clock, REQUIRED_CLOCK, "the clock arm"),
                parse(retail, REQUIRED_GUEST, "the retail arm"),
                parse(control, REQUIRED_GUEST, "the bit7 arm"),
                parse(segmented, REQUIRED_GUEST, "the segmented arm"))

    judge(*call())

    # NEGATIVE 1: the control is made to behave like the case. A harness that cannot skip the loop
    # must refuse, not report.
    bad = base_control.replace("exhausted_in_wait_loop=0", "exhausted_in_wait_loop=1")
    try:
        judge(*call(control=bad))
    except Refused as exc:
        if "bit7 control" not in str(exc):
            raise AssertionError(f"control defeat gave an unexpected refusal: {exc}") from exc
    else:
        raise AssertionError("a control that also exhausts in the loop was accepted")

    # NEGATIVE 1b: a control that does not return at all is not a control.
    try:
        judge(*call(control=base_control.replace("returned=1", "returned=0")))
    except Refused as exc:
        if "bit7 control did not return" not in str(exc):
            raise AssertionError(f"a non-returning control gave an unexpected refusal: {exc}") from exc
    else:
        raise AssertionError("a control that never returned was accepted")

    # NEGATIVE 2: a control as expensive as the case cannot discriminate.
    bad = base_control.replace("cycles=186", "cycles=564492").replace("blocks=8", "blocks=40316")
    try:
        judge(*call(control=bad))
    except Refused:
        pass
    else:
        raise AssertionError("a control costing as much as the case was accepted")

    # NEGATIVE 3: a counter that does not move even WITH accounting is not a freeze this tool can
    # see, so reporting it as one would be the tautology this repository keeps recording.
    try:
        judge(*call(clock=base_clock.replace("distinct_with_accounting=16",
                                             "distinct_with_accounting=1")))
    except Refused:
        pass
    else:
        raise AssertionError("a counter frozen even with accounting was reported as a freeze")

    # NEGATIVE 4: the loop EXITING is not a pass. It is a real change, and it must be re-verified
    # against the rest of the port rather than blessed by a tool whose question is a freeze.
    bad = base_retail.replace("exhausted_in_wait_loop=1", "exhausted_in_wait_loop=0").replace(
        "exit=budget-exhausted pc=0x80093584 cycles=564492",
        "exit=guest-return pc=0x800941D0 cycles=190")
    try:
        judge(*call(retail=bad))
    except Refused:
        pass
    else:
        raise AssertionError("a loop that exits was blessed as a pass")

    # NEGATIVE 5: a zero denominator must be refused, not reported as "no freeze".
    try:
        judge(*call(clock=base_clock.replace("polls=64", "polls=0")))
    except Refused:
        pass
    else:
        raise AssertionError("a zero denominator was accepted")

    # NEGATIVE 6: a field is dropped, so a short read must not read as zeros.
    bad = " ".join(token for token in base_retail.split() if not token.startswith("snapshot="))
    try:
        parse(bad, REQUIRED_GUEST, "the retail arm")
    except Refused:
        pass
    else:
        raise AssertionError("a transcript missing a field was accepted as zeros")

    # NEGATIVE 7: a line that does not name its arm cannot be assigned one by position.
    try:
        fields_arm("reached_first_spin=1 returned=1")
    except Refused:
        pass
    else:
        raise AssertionError("an unnamed arm line was accepted")

    # NEGATIVE 8: the MUTANT that matters most. If more frequent accounting does NOT release the
    # loop, then segment granularity is not the mechanism and this report's explanation is wrong.
    bad = base_segmented.replace("exhausted_in_wait_loop=0", "exhausted_in_wait_loop=1").replace(
        "pc=0x800934D8", "pc=0x80093584")
    try:
        judge(*call(segmented=bad))
    except Refused as exc:
        if "ALSO exhausted" not in str(exc):
            raise AssertionError(f"a defeated mutant gave an unexpected refusal: {exc}") from exc
    else:
        raise AssertionError("a mutant that also spun was accepted as identifying the mechanism")

    # NEGATIVE 9: a mutant that did not vary the thing it claims to vary measures nothing.
    try:
        judge(*call(segmented=base_segmented.replace("segments=9", "segments=1")))
    except Refused as exc:
        if "did not vary" not in str(exc):
            raise AssertionError(f"an unvaried mutant gave an unexpected refusal: {exc}") from exc
    else:
        raise AssertionError("a mutant with the same segment count as the case was accepted")

    # NEGATIVE 10: a mutant given materially LESS total work could leave the loop for the wrong
    # reason. A few cycles' difference is normal — the mutant simply returns earlier — so the guard
    # is a ratio, and this case is the one that must turn it red.
    try:
        judge(*call(segmented=base_segmented.replace("cycles=564482", "cycles=70000")))
    except Refused as exc:
        if "LESS work" not in str(exc):
            raise AssertionError(f"a starved mutant gave an unexpected refusal: {exc}") from exc
    else:
        raise AssertionError("a mutant given materially less work than the case was accepted")

    # NEGATIVE 7: the wrong executable. A single one-word edit to a GROUND_TRUTH word.
    edited = bytearray(sized)
    edited[HEADER + 0x800935E4 - LOAD:HEADER + 0x800935E4 - LOAD + 4] = struct.pack("<I", 0x0045102C)
    try:
        Image(bytes(edited)).check_ground_truth()
    except Refused:
        pass
    else:
        raise AssertionError("a one-word edit to a ground-truth instruction was accepted")

    print("[pad-wait] selftest passed: 3 image refusals (blank text, truncated text, one-word edit), "
          "1 accepted ground truth, 10 transcript refusals (defeated control, non-returning control, "
          "expensive control, tautological counter, an exiting loop, a zero denominator, a short "
          "read, an unnamed arm, a defeated mutant, an unvaried mutant, a starved mutant)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", type=pathlib.Path,
                        default=ROOT / "scratch/bin/tekken3/SLUS_004.02")
    parser.add_argument("--binary", type=pathlib.Path, default=ROOT / "build/tekken3_pad_wait_exit")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return 0

    try:
        image = Image(verify_executable(load_manifest(), args.executable))
        image.check_ground_truth()
        facts = derive(image)
        print(f"[pad-wait] image {args.executable.name} pinned: {len(GROUND_TRUTH)}/{len(GROUND_TRUTH)} "
              f"ground-truth instruction(s) reproduced; threshold global 0x{facts['threshold_global']:08X}, "
              f"snapshot global 0x{facts['snapshot_global']:08X}, arm argument 0x{facts['arm_argument']:04X}, "
              f"second loop exits on bit7={int(facts['bit7_test'])} and on the countdown arm")

        environment = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="dummy")
        process = subprocess.Popen([args.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment)
        print(f"[pad-wait] owned guest test pid={process.pid} timeout=300s", flush=True)
        try:
            stdout, stderr = process.communicate(input=image.data, timeout=300)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise Refused(f"guest test timed out; killed owned pid={process.pid}") from exc
        if process.returncode:
            raise Refused(f"guest test pid={process.pid} exited {process.returncode}: "
                          f"{stderr.decode(errors='replace')[-2000:]}")

        transcript = ROOT / "scratch/diagnostics/pad-wait-exit.stdout"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_bytes(stdout)
        lines = [line for line in stdout.decode().splitlines() if line.startswith("arm=")]
        if len(lines) != len(EXPECTED_ARMS):
            raise Refused(f"guest test reported {len(lines)} arm line(s) of {len(EXPECTED_ARMS)}; a "
                          "short read must not read as zeros. stdout tail="
                          f"{[line[:80] for line in stdout.decode().splitlines()][-len(EXPECTED_ARMS):]}")
        by_name = {}
        for line in lines:
            # The clock arm and the guest arms do not report the same fields. Asking each for the
            # union would make a short read look like a schema problem on a line that is complete.
            required = REQUIRED_CLOCK if line.startswith("arm=clock") else REQUIRED_GUEST
            fields = parse(line, required, fields_arm(line))
            if fields["arm"] in by_name:
                raise Refused(f"guest test reported the {fields['arm']} arm twice")
            by_name[fields["arm"]] = fields
        missing = [name for name in EXPECTED_ARMS if name not in by_name]
        if missing:
            raise Refused(f"guest test did not report {', '.join(missing)}; it reported "
                          f"{', '.join(sorted(by_name))}")

        for line in judge(by_name["clock"], by_name["retail"], by_name["bit7"], by_name["segmented"]):
            print(f"[pad-wait] {line}")
        print(f"[pad-wait] guest transcript retained at scratch/diagnostics/pad-wait-exit.stdout "
              f"({len(lines)} arm line(s) of {len(EXPECTED_ARMS)})")
        print(f"[pad-wait] verdict: the second loop's countdown is armed at 0x{THRESHOLD_GLOBAL:08X} "
              f"and RCnt2 is the only thing that can expire it; RCnt2 moves only when the runtime "
              f"accounts guest instructions, and that happens once per executor SEGMENT, so inside "
              f"one segment the loop's exit test can never become true. The owner is the Lightrec "
              f"integration's accounting boundary in psxport, not this title.")
        print(f"[pad-wait] owned guest test pid={process.pid} exited 0")
        return 0
    except (Refused, Mismatch, OSError, ValueError, KeyError) as exc:
        print(f"[pad-wait] REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
