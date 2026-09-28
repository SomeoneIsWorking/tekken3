// pad_wait_exit.cpp — test-only. Answers one question about the authenticated SLUS_004.02 pad
// driver through the SHIPPING owners: does FUN_80093478's second wait loop, which exits on a
// root-counter-2 countdown, ever see the counter advance while the dynarec runs it?
//
// The fixture is built here, by this test, through the same MMIO entry the guest uses; nothing in
// the product is patched and no product state is forged. What the guest then does is the guest's.
//
// Three arms, and each answers a different question so a reader cannot mistake one for another:
//
//   arm=clock       the owner measurement, no guest code. How many DISTINCT values does
//                   Timing::rootCounter2() return across N polls with no guest accounting between
//                   them, versus with one advanceGuestInstructionTicks between them?
//   arm=retail      retail's own path: pad status bit 7 clear, so the second loop is entered, and
//                   retail's own 0x190 countdown. Does the loop exit?
//   arm=bit7        the SAME fixture with the SAME code and ONE fixture word different (pad status
//                   bit 7 set), which the driver tests at 0x8009354C before the loop. This is the
//                   control for REACHING the loop: it must RETURN, so a run where both arms behave
//                   alike is a tool that cannot tell the loop from the call.
//   arm=segmented   the SAME fixture and the SAME guest bytes, given the SAME total work allowance
//                   but handed back to the host every 65,536 cycles instead of once. This is the
//                   mutant that identifies the mechanism, and it is the arm that matters: guest
//                   accounting — the only thing that moves RCnt2 — happens once per SEGMENT, so a
//                   guest polling a counter inside one segment sees it frozen. If this arm leaves
//                   the loop where arm=retail does not, the difference is segment granularity and
//                   not the guest's code, its data, or the counter's correctness.
//
// The threshold word is NOT a usable mutant: FUN_800951B8 stores its own $a0 into 0x800AE228, so a
// fixture that presets it is overwritten before the loop reads it. That is recorded rather than
// worked around, because a planted word that the guest immediately replaces is a mutant that
// cannot fail.
#include "core.h"
#include "emulated_time.h"
#include "execution_exit.h"
#include "game.h"
#include "io_peripherals.h"
#include "lightrec_executor.h"
#include "native_dispatch.h"
#include "psx_exe_image.h"
#include "timing.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <iterator>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace {

// Guest facts, read out of the authenticated image. tools/verify_pad_wait_exit.py re-derives every
// one of them from the bytes and refuses to report on a disagreement; this file only consumes them.
constexpr std::uint32_t kPadByteExchange = 0x80093478u; // the function under test
constexpr std::uint32_t kFirstSpin = 0x800934D8u;       // the SIO0 STAT bit 1 spin
constexpr std::uint32_t kWaitLoopEntry = 0x80093584u;   // the second loop's top
constexpr std::uint32_t kWaitLoopExit = 0x80093604u;    // one past its last instruction
constexpr std::uint32_t kCountdownReturn = 0x80093690u; // the countdown-expiry early return
constexpr std::uint32_t kReturn = 0x800941D0u;          // the caller's own return address

// Guest globals the driver reads and writes.
constexpr std::uint32_t kSioBasePointerGlobal = 0x8009B964u;  // -> 0x1F801040
constexpr std::uint32_t kPadStatePointerGlobal = 0x8009B960u; // -> the two-word pad status
// The threshold is `lui $at,0x800B` + `sw $a0,-7640($at)`, i.e. 0x800B0000 - 0x1DD8. tools/
// verify_pad_wait_exit.py re-derives this from the instruction word and refuses if the two differ.
constexpr std::uint32_t kCountdownThresholdGlobal = 0x800AE228u; // the word FUN_800951B8 arms
// The snapshot latches at `lui $at,0x800B` + `sw $v0,-31104($at)`. The offset field is 0x8680, which
// sign-extends to -0x7980, so the word is 0x800B0000 - 0x7980 = 0x800A8680 — the same address
// issue 0016 names. The tool re-derives it from the instruction word rather than trusting this
// constant, and refuses on a disagreement.
constexpr std::uint32_t kCountdownSnapshotGlobal = 0x800A8680u;
constexpr std::uint32_t kPortModeGlobal = 0x8009B944u;

constexpr std::uint32_t kSio0Data = 0x1F801040u;
constexpr std::uint32_t kSio0Ctrl = 0x1F80104Au;

constexpr std::uint16_t kSio0StatRxReady = 0x0002u;

// Fixture RAM, past the loaded text (0x80010000..0x80131000), so nothing here aliases guest code.
constexpr std::uint32_t kPadStateStruct = 0x80140000u;
constexpr std::uint32_t kPadStatusStruct = 0x80140100u;
constexpr std::uint32_t kDeviceIdByte = 0x80140200u;

// Pad state struct fields, by the offsets the driver itself uses.
constexpr std::uint32_t kPadDeviceIdTable = 0x3Cu;
constexpr std::uint32_t kPadByteIndex = 0x44u;
constexpr std::uint32_t kPadRxCount = 0x45u;
constexpr std::uint32_t kPadPortType = 0xE8u;

// The driver selects "digital pad, halfword of data" from the top nibble of the byte its own table
// holds; 0x8F is that nibble with a nonzero low half.
constexpr std::uint8_t kDeviceIdNibblePad = 0x8Fu;

constexpr std::uint32_t kClockPolls = 4096u;
constexpr std::uint32_t kAccountingStep = 64u;

// The segmented arm's segment length. It must be far above the 0x190 (=3200 raw RCnt2 ticks, since
// the shifted arm compares (RCnt2 - snapshot) >> 3) the loop waits for, or the arm would pass for
// the wrong reason: the answer has to come from the counter MOVING across a segment boundary, not
// from a budget small enough to hand the loop the value it was waiting for.
constexpr std::uint64_t kSegmentedArmCycles = 65536u;

struct Fixture {
  std::unique_ptr<Game> game;
  Core &core() {
    return game->core;
  }
  Timing &timing() {
    return game->timing;
  }
};

std::uint8_t read8(Core &core, std::uint32_t address) {
  return static_cast<std::uint8_t>(core.mem_r32(address) & 0xFFu);
}

// The fixture the guest then runs in. Every word written here is a pad-state value retail's own
// driver writes on this path, applied through the shipping MMIO owner so the device's answer is a
// real one rather than a value this file made up.
bool buildFixture(Fixture &fixture,
                  const std::vector<std::uint8_t> &image,
                  std::uint32_t threshold,
                  bool padBusy,
                  std::string *refusal) {
  fixture.game = std::make_unique<Game>();
  Core &core = fixture.core();
  const auto loaded = psx::cpu::loadPsxExeImage(core, image, "authenticated SLUS_004.02");
  if (!loaded) {
    *refusal = std::string("image mapping refused: ") + loaded.detail;
    return false;
  }
  if (!core.currentImageIdentity(kPadByteExchange)) {
    *refusal = "the pad driver's entry is not inside the authenticated image";
    return false;
  }

  // The port, programmed the way the guest programs it: JOY_MODE 0, JOY_BAUD 0x22 = 400 kbaud,
  // CTRL bit 0 transmit enable and bit 1 controller on port 1.
  core.game->sio.mode = 0;
  core.game->sio.baud = 0x22;
  if (!io_peripheral_write(core, kSio0Ctrl, 0x0003u)) {
    *refusal = "SIO0 CTRL write was refused by the MMIO owner";
    return false;
  }
  core.mem_w32(kSioBasePointerGlobal, kSio0Data);
  core.mem_w32(kPadStatePointerGlobal, kPadStatusStruct);
  core.mem_w32(kPortModeGlobal, 0);

  // Pad status word 0, bit 7 set or clear per the arm: the driver tests that bit at 0x80093548 and
  // branches past the whole second loop when it is set.
  core.mem_w32(kPadStatusStruct, padBusy ? 0x000000FFu : 0x0000007Fu);
  core.mem_w32(kPadStatusStruct + 4u, 0);

  core.mem_w32(kDeviceIdByte, kDeviceIdNibblePad);
  core.mem_w32(kPadStateStruct + kPadDeviceIdTable, kDeviceIdByte);
  core.mem_w32(kPadStateStruct + kPadByteIndex, 1);
  core.mem_w32(kPadStateStruct + kPadRxCount, 0);
  core.mem_w32(kPadStateStruct + kPadPortType, 0);

  // Address the controller (0x01) exactly as the guest's own first byte does, through the same
  // MMIO entry, so SIO0 STAT bit 1 becomes true the way it becomes true on hardware; then let
  // enough emulated time pass for that byte to finish shifting.
  if (!io_peripheral_write(core, kSio0Data, 0x01u)) {
    *refusal = "SIO0 DATA write was refused by the MMIO owner";
    return false;
  }
  fixture.timing().advanceGuestInstructionTicks(8192u);
  if ((core.game->sio.status(fixture.timing().emulatedCpuTicks()) & kSio0StatRxReady) == 0u) {
    *refusal = "SIO0 STAT bit 1 never became true, so the fixture would not pass the driver's FIRST "
               "spin and this test would measure the wrong loop";
    return false;
  }

  core.mem_w32(kCountdownThresholdGlobal, threshold);
  return true;
}

struct GuestArm {
  bool reachedFirstSpin = false;
  bool exhaustedInsideWaitLoop = false;
  bool returnedByCountdown = false;
  bool returned = false;
  std::string exit{};
  std::uint32_t pc = 0;
  std::uint64_t cycles = 0;
  std::uint32_t segments = 0;
  std::uint64_t blocks = 0;
  std::uint64_t instructions = 0;
  std::uint64_t fallbackCalls = 0;
  std::uint16_t counterAtEntry = 0;
  std::uint16_t counterAtExit = 0;
  std::uint32_t threshold = 0;
  std::uint32_t snapshot = 0;
  std::uint16_t portBaud = 0;
};

GuestArm runGuest(const std::vector<std::uint8_t> &image,
                  std::uint32_t threshold,
                  bool padBusy,
                  std::uint64_t segmentCycles,
                  std::string *refusal) {
  GuestArm arm{};
  Fixture fixture;
  if (!buildFixture(fixture, image, threshold, padBusy, refusal)) {
    return arm;
  }
  Core &core = fixture.core();
  arm.threshold = core.mem_r32(kCountdownThresholdGlobal);
  arm.counterAtEntry = fixture.timing().rootCounter2();

  core.r[4] = kPadStateStruct;
  core.r[5] = 0x42u; // the standard digital-pad poll command
  core.r[31] = kReturn;

  // `segmentCycles` bounds how long the dynarec may run before control returns to the host, which
  // is the ONE thing this arm varies. 0 means the product's own per-turn budget, in one segment.
  // The TOTAL is always the product's own budget, so the two arms get the same total work
  // allowance and differ only in how often control comes home — otherwise a difference in the
  // outcome could be a smaller total rather than a different segment length.
  const std::uint64_t total = psx::cpu::ExecutionBudget::currentTurn(core).cycles;
  const std::uint64_t perSegment = segmentCycles == 0 ? total : segmentCycles;
  std::uint64_t spent = 0;
  std::uint64_t totalCycles = 0;
  psx::cpu::ExecutionResult result{};
  std::uint32_t segments = 0;
  while (spent < total && result.reason != psx::cpu::ExecutionExitReason::GuestReturn) {
    const std::uint64_t allowance = std::min(perSegment, total - spent);
    result = psx::cpu::dispatchGuest(core, kPadByteExchange, psx::cpu::ExecutionBudget::fromCycles(allowance));
    totalCycles += result.cycles;
    spent += result.cycles;
    ++segments;
  }
  const auto &counters = core.lightrecExecutor().counters();
  arm.segments = segments;

  arm.exit = psx::cpu::executionExitName(result.reason);
  arm.pc = result.guestPc;
  arm.cycles = totalCycles;
  arm.blocks = counters.executedBlocks;
  arm.instructions = counters.executedInstructions;
  arm.fallbackCalls = counters.fallback.calls;
  arm.counterAtExit = fixture.timing().rootCounter2();
  arm.snapshot = core.mem_r32(kCountdownSnapshotGlobal);
  arm.portBaud = core.game->sio.baud;
  arm.exhaustedInsideWaitLoop = result.reason == psx::cpu::ExecutionExitReason::BudgetExhausted &&
                                arm.pc >= kWaitLoopEntry && arm.pc < kWaitLoopExit;
  arm.returnedByCountdown = arm.pc == kCountdownReturn;
  arm.returned = result.reason == psx::cpu::ExecutionExitReason::GuestReturn && arm.pc == kReturn;
  // "The first spin was left behind" is established by the countdown snapshot existing at all:
  // FUN_800951B8 is the first thing this function does after that spin and its only writer.
  arm.reachedFirstSpin = arm.snapshot != 0;
  (void)kFirstSpin;
  return arm;
}

void printGuestArm(const char *name, const GuestArm &arm) {
  std::printf("arm=%s reached_first_spin=%u returned=%u exhausted_in_wait_loop=%u "
              "returned_by_countdown=%u exit=%s pc=0x%08X cycles=%llu segments=%u blocks=%llu "
              "instructions=%llu fallback_calls=%llu threshold=0x%08X snapshot=0x%08X "
              "counter_entry=%u counter_exit=%u port_baud=0x%04X\n",
              name,
              arm.reachedFirstSpin ? 1u : 0u,
              arm.returned ? 1u : 0u,
              arm.exhaustedInsideWaitLoop ? 1u : 0u,
              arm.returnedByCountdown ? 1u : 0u,
              arm.exit.c_str(),
              arm.pc,
              static_cast<unsigned long long>(arm.cycles),
              arm.segments,
              static_cast<unsigned long long>(arm.blocks),
              static_cast<unsigned long long>(arm.instructions),
              static_cast<unsigned long long>(arm.fallbackCalls),
              arm.threshold,
              arm.snapshot,
              arm.counterAtEntry,
              arm.counterAtExit,
              arm.portBaud);
}

struct ClockArm {
  std::size_t distinctWithoutAccounting = 0;
  std::size_t distinctWithAccounting = 0;
  std::uint32_t polls = 0;
};

ClockArm runClockArm() {
  ClockArm arm{};
  Fixture fixture;
  fixture.game = std::make_unique<Game>();
  Timing &timing = fixture.timing();
  arm.polls = kClockPolls;

  std::set<std::uint16_t> without;
  for (std::uint32_t poll = 0; poll < arm.polls; ++poll) {
    without.insert(timing.rootCounter2());
  }
  arm.distinctWithoutAccounting = without.size();

  std::set<std::uint16_t> with;
  for (std::uint32_t poll = 0; poll < arm.polls; ++poll) {
    with.insert(timing.rootCounter2());
    timing.advanceGuestInstructionTicks(kAccountingStep);
  }
  arm.distinctWithAccounting = with.size();
  return arm;
}

} // namespace

int main() {
  const std::vector<std::uint8_t> image{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()};
  if (image.empty() || image.size() > psx::cpu::kPsxExeMaxBytes) {
    std::fprintf(stderr, "pad_wait_exit: missing or oversized authenticated input\n");
    return 2;
  }

  const ClockArm clock = runClockArm();
  std::printf("arm=clock polls=%u distinct_without_accounting=%zu distinct_with_accounting=%zu "
              "accounting_step=%u\n",
              clock.polls,
              clock.distinctWithoutAccounting,
              clock.distinctWithAccounting,
              kAccountingStep);

  std::string refusal;
  const GuestArm retail = runGuest(image, 0x190u, false, 0, &refusal);
  if (!refusal.empty()) {
    std::fprintf(stderr, "pad_wait_exit: retail arm: %s\n", refusal.c_str());
    return 2;
  }
  printGuestArm("retail", retail);

  refusal.clear();
  const GuestArm control = runGuest(image, 0x190u, true, 0, &refusal);
  if (!refusal.empty()) {
    std::fprintf(stderr, "pad_wait_exit: bit7 control arm: %s\n", refusal.c_str());
    return 2;
  }
  printGuestArm("bit7", control);

  refusal.clear();
  const GuestArm segmented = runGuest(image, 0x190u, false, kSegmentedArmCycles, &refusal);
  if (!refusal.empty()) {
    std::fprintf(stderr, "pad_wait_exit: segmented mutant arm: %s\n", refusal.c_str());
    return 2;
  }
  printGuestArm("segmented", segmented);
  (void)read8;
  return 0;
}
