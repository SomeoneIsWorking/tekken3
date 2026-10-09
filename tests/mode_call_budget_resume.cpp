// Frame loop over a mode call that outlives one field (mode 2, 0x8004FA60, spins on 0x800A069E):
// arm=resume must suspend, hold the field and finish when the host clears the byte; arm=control
// enters the same body through the non-suspending call in a forked child and must die on SIGABRT.
// The guest body is built from asm_fields.h, not hex.
#include "asm_fields.h"
#include "core.h"
#include "execution/finite_guest_call.h"
#include "execution_exit.h"
#include "frame/finite_frame.h"
#include "game.h"
#include "lightrec_executor.h"
#include "psx_exe_image.h"
#include "resumable_guest_call.h"

#include <array>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <sys/wait.h>
#include <unistd.h>

namespace {
using namespace tekken3::test;

// PS-X EXE layout: text at t_addr 0x80010000, big enough to reach the highest address the frame
// loop dispatches into (kSelectBuffer at 0x80080D98).
constexpr std::uint32_t kTextBase = 0x80010000u;
constexpr std::uint32_t kTextEnd = 0x80082000u;

// Mode table entry 2 and the guest words the body spins on.
constexpr std::uint32_t kModeFunction2 = 0x8004FA60u;
constexpr std::uint32_t kModeReturnPc2 = 0x80028C9Cu + 2u * 0x10u;
constexpr std::uint32_t kLoaderBusy = 0x800A069Eu;
constexpr std::uint32_t kSpinCounter = 0x800A0698u;
constexpr std::uint32_t kRenderMode = 0x800AE204u;
constexpr std::uint32_t kFrameCounter = 0x800AFA4Cu;
constexpr std::uint32_t kFrameBarrier = 0x800296C4u;

// Pacing only: the body waits on a byte only the host clears.
constexpr std::uint64_t kFieldCycles = 4000u;

// Guest body, built from fields:
//   2 lbu $t2,0x69E($t0)  busy byte; 4 beq $t2,$zero,exit; 6 lw $t3,0x698($t1); 8 addiu $t3,$t3,1;
//   9 sw $t3,0x698($t1)   spin progress; 10 j loop; 14 jr $ra. Every branch/jump is given its own PC.
// Word indices; every branch and jump is given the PC it is at.
constexpr std::uint32_t kBodyLoopPc = kModeFunction2 + 2u * 4u;  // index 2,  the lbu
constexpr std::uint32_t kBodyBeqPc = kModeFunction2 + 4u * 4u;   // index 4,  the beq
constexpr std::uint32_t kBodyExitPc = kModeFunction2 + 14u * 4u; // index 14, the jr $ra
constexpr std::uint32_t kBodyJmpPc = kModeFunction2 + 10u * 4u;  // index 10, the j

constexpr std::array<std::uint32_t, 16> kSpinBody{{
    mips::lui(mips::kT0, 0x800A),                               // 0
    mips::lui(mips::kT1, 0x800A),                               // 1
    mips::lbu(mips::kT0, mips::kT2, 0x69E),                     // 2   read the busy byte
    mips::nop(),                                                // 3   load delay slot
    mips::beq(mips::kT2, mips::kZero, kBodyBeqPc, kBodyExitPc), // 4
    mips::nop(),                                                // 5   branch delay slot
    mips::lw(mips::kT1, mips::kT3, 0x698),                      // 6   read the counter
    mips::nop(),                                                // 7   load delay slot
    mips::addiu(mips::kT3, mips::kT3, 1),                       // 8
    mips::sw(mips::kT1, mips::kT3, 0x698),                      // 9
    mips::j(kBodyJmpPc, kBodyLoopPc),                           // 10
    mips::nop(),                                                // 11  branch delay slot
    mips::nop(),                                                // 12
    mips::nop(),                                                // 13
    mips::jr(mips::kRa),                                        // 14
    mips::nop(),                                                // 15  branch delay slot
}};

// What each word must decode back to, as fields.
struct Expected {
  std::uint32_t op;
  std::uint32_t rs;
  std::uint32_t rt;
  std::int64_t imm; // sign-extended for the loads/stores/arith, raw for lui/branch/jump
  std::uint32_t branchTarget = 0;
  std::uint32_t jumpTarget = 0;
  std::uint32_t funct = 0;
};

constexpr std::array<Expected, 16> kSpinBodyIntended{{
    {mips::kOpLui, 0, mips::kT0, 0x800A},
    {mips::kOpLui, 0, mips::kT1, 0x800A},
    {mips::kOpLbu, mips::kT0, mips::kT2, 0x069E},
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll}, // 3  load delay slot
    {mips::kOpBeq, mips::kT2, mips::kZero, mips::branchOffset(kBodyBeqPc, kBodyExitPc), kBodyExitPc, 0},
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll}, // 5  branch delay slot
    {mips::kOpLw, mips::kT1, mips::kT3, 0x0698},
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll}, // 7  load delay slot
    {mips::kOpAddiu, mips::kT3, mips::kT3, 1},
    {mips::kOpSw, mips::kT1, mips::kT3, 0x0698},
    {mips::kOpJ, 0, 0, 0, 0, kBodyLoopPc},              // the jump's field is absolute>>2, checked as a target
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll}, // 11 branch delay slot
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll},
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll},
    {mips::kOpSpecial, mips::kRa, 0, 0, 0, 0, mips::kFunctJr},
    {mips::kOpSpecial, 0, 0, 0, 0, 0, mips::kFunctSll}, // 15 branch delay slot
}};

bool decodeMatches(const std::uint32_t *words,
                   const Expected *intended,
                   std::size_t count,
                   const std::uint32_t *addresses) {
  for (std::size_t index = 0; index < count; ++index) {
    const mips::Fields got = mips::decode(words[index]);
    const std::uint32_t pc = addresses[index];
    const Expected &want = intended[index];
    // Meaningful fields depend on the opcode: `j` compares only the target, `lui` has a raw immediate.
    if (want.op == mips::kOpJ) {
      const std::uint32_t target = mips::jumpTarget(words[index], pc);
      if (got.op != mips::kOpJ || target != want.jumpTarget) {
        std::fprintf(stderr,
                     "mode_call_budget_resume: word %zu at 0x%08X is 0x%08X, a jump to 0x%08X; the body "
                     "intends a jump to 0x%08X (op=0x%02X vs 0x%02X)\n",
                     index,
                     pc,
                     words[index],
                     target,
                     want.jumpTarget,
                     got.op,
                     want.op);
        return false;
      }
      continue;
    }
    const std::int64_t gotImm =
        want.op == mips::kOpLui ? static_cast<std::int64_t>(got.imm) : mips::signedImmediate(got.imm);
    // SPECIAL has no immediate; compare rs and funct.
    const bool special = want.op == mips::kOpSpecial;
    const bool fieldsOk = got.op == want.op && got.rt == want.rt && (special || gotImm == want.imm);
    // rs is don't-care for lui; funct is only meaningful for SPECIAL.
    const bool rsOk = want.op == mips::kOpLui || got.rs == want.rs;
    const bool functOk = !special || got.funct == want.funct;
    const bool targetOk = want.branchTarget == 0 || mips::branchTarget(words[index], pc) == want.branchTarget;
    if (!(fieldsOk && rsOk && functOk && targetOk)) {
      std::fprintf(stderr,
                   "mode_call_budget_resume: word %zu at 0x%08X is 0x%08X, which decodes op=0x%02X "
                   "rs=r%u rt=r%u imm=0x%04X funct=0x%02X branch->0x%08X\n"
                   "  intended: op=0x%02X rs=r%u rt=r%u imm=0x%04X branch->0x%08X\n"
                   "  fieldsOk=%d rsOk=%d functOk=%d targetOk=%d\n",
                   index,
                   pc,
                   words[index],
                   got.op,
                   got.rs,
                   got.rt,
                   got.imm,
                   got.funct,
                   mips::branchTarget(words[index], pc),
                   want.op,
                   want.rs,
                   want.rt,
                   static_cast<std::uint32_t>(want.imm),
                   want.branchTarget,
                   fieldsOk,
                   rsOk,
                   functOk,
                   targetOk);
      return false;
    }
  }
  return true;
}

void programAddresses(std::array<std::uint32_t, 16> *at, std::uint32_t base) {
  for (std::size_t index = 0; index < 16; ++index) {
    (*at)[index] = base + static_cast<std::uint32_t>(index) * 4u;
  }
}

// Each field-level perturbation of the body must be rejected by the decode check.
// Defined below: it runs the mis-scheduled body and needs the image and loader.
bool misScheduledBodyStoresNothing();

bool perturbedProgramsAreRejected() {
  const char *const kNames[] = {
      "sw base register", "lw base register", "beq condition register", "j target", "addiu immediate"};
  // sw base moved to $t0.
  std::array<std::uint32_t, 16> wrong = kSpinBody;
  wrong[9] = mips::sw(mips::kT0, mips::kT3, 0x698);
  // lw base moved to $at.
  wrong[6] = mips::lw(mips::kAt, mips::kT3, 0x698);
  std::array<std::uint32_t, 16> at{};
  programAddresses(&at, kModeFunction2);
  if (decodeMatches(wrong.data(), kSpinBodyIntended.data(), wrong.size(), at.data())) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: a program with the store's and load's base register moved "
                 "was ACCEPTED, so the field check cannot see a register-field slip\n");
    return false;
  }
  // Branch condition moved, jump retargeted, immediate widened past 16 bits.
  wrong = kSpinBody;
  wrong[4] = mips::beq(mips::kT3, mips::kZero, kBodyBeqPc, kBodyExitPc);
  if (decodeMatches(wrong.data(), kSpinBodyIntended.data(), wrong.size(), at.data())) {
    std::fprintf(stderr, "mode_call_budget_resume: a moved branch condition was ACCEPTED\n");
    return false;
  }
  wrong = kSpinBody;
  wrong[10] = mips::j(kBodyJmpPc, kModeFunction2); // retargeted to the wrong word
  if (decodeMatches(wrong.data(), kSpinBodyIntended.data(), wrong.size(), at.data())) {
    std::fprintf(stderr, "mode_call_budget_resume: a retargeted jump was ACCEPTED\n");
    return false;
  }
  // A PC-relative offset in a jump's absolute field.
  wrong = kSpinBody;
  wrong[10] = (0x0800FFF9u); // offset -7 as if it were a jump field
  if (decodeMatches(wrong.data(), kSpinBodyIntended.data(), wrong.size(), at.data())) {
    std::fprintf(stderr, "mode_call_budget_resume: a branch offset in a jump's absolute field was ACCEPTED\n");
    return false;
  }
  wrong = kSpinBody;
  wrong[8] = mips::addiu(mips::kT3, mips::kT3, 0x8000); // +32768 wraps to -32768
  if (mips::addiu(mips::kT3, mips::kT3, 0x8000) == wrong[8] && mips::signedImmediate(mips::decode(wrong[8]).imm) == 1) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: addiu(0x8000) silently produced the immediate -1's "
                 "neighbour instead of refusing\n");
    return false;
  }
  std::printf("program fields: %d field perturbation(s) rejected, so the field check can fail\n", 5);
  return misScheduledBodyStoresNothing();
}

bool programDecodesAsIntended() {
  std::array<std::uint32_t, 16> at{};
  programAddresses(&at, kModeFunction2);
  if (!decodeMatches(kSpinBody.data(), kSpinBodyIntended.data(), kSpinBody.size(), at.data())) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: FAIL — the guest body does not decode to what it is built "
                 "to mean, so the body under test is not the body that was described\n");
    return false;
  }
  return true;
}

void word(std::vector<std::uint8_t> &bytes, std::size_t offset, std::uint32_t value) {
  for (unsigned index = 0; index < 4; ++index) {
    bytes[offset + index] = static_cast<std::uint8_t>(value >> (index * 8u));
  }
}

// `jr $ra` / `nop`, optionally preceded by `addiu $v0,$zero,n` when the caller reads a result.
void stub(std::vector<std::uint8_t> &bytes, std::uint32_t address, int result) {
  if (result >= 0) {
    word(bytes, 0x800u + (address - kTextBase), mips::addiu(mips::kZero, mips::kV0, result));
  }
  const auto offset = 0x800u + (address - kTextBase) + (result >= 0 ? 4u : 0u);
  word(bytes, offset, mips::jr(mips::kRa));
  word(bytes, offset + 4u, mips::nop());
}

std::vector<std::uint8_t> syntheticImage() {
  // Unnamed words stay 0, a nop.
  std::vector<std::uint8_t> bytes(0x800u + (kTextEnd - kTextBase), 0u);
  std::memcpy(bytes.data(), "PS-X EXE", 8);
  word(bytes, 0x10, kTextBase);
  word(bytes, 0x18, kTextBase);
  word(bytes, 0x1c, kTextEnd - kTextBase);
  stub(bytes, kFrameBarrier, -1);
  stub(bytes, 0x8006B6FCu, -1); // kCdXaState
  stub(bytes, 0x80029628u, 0);  // kRenderModeQuery -> select a buffer
  stub(bytes, 0x80080D98u, 0);  // kSelectBuffer -> buffer index 0
  stub(bytes, 0x80081C38u, -1); // kSelectGeometry
  stub(bytes, 0x800817F8u, -1); // kClearMainOt
  stub(bytes, 0x8004C684u, -1); // kSelectOtRoots
  for (std::size_t index = 0; index < kSpinBody.size(); ++index) {
    word(bytes, 0x800u + (kModeFunction2 - kTextBase) + index * 4u, kSpinBody[index]);
  }
  return bytes;
}

// The Core adapter with the host services counted instead of driven, so the test stays headless.
class BudgetMachine final : public tekken3::frame::Machine {
public:
  BudgetMachine(Core &core, psx::cpu::ResumableGuestCall &modeCall) : core_(core), modeCall_(modeCall) {}

  void call(std::uint32_t address, std::uint32_t returnPc) override {
    ++suspendingEntryAbuses;
    tekken3::execution::FiniteGuestCall::callToReturn(core_, address, "mode_call_budget_resume control");
  }

  void call1(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0) override {
    call(address, returnPc);
  }

  void
  call3(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t a2) override {
    call(address, returnPc);
  }

  static bool settled(const psx::cpu::CallStep &step) {
    if (step.outcome == psx::cpu::CallOutcome::Refused) {
      std::fprintf(stderr, "mode_call_budget_resume: refused: %s\n", step.detail.c_str());
      std::abort();
    }
    return step.outcome == psx::cpu::CallOutcome::Returned;
  }

  bool beginSpanningCall(std::uint32_t address, std::uint32_t returnPc) override {
    ++boundedStarts;
    lastEntry = address;
    lastReturnPc = returnPc;
    modeCall_.begin(core_, "mode call", address, returnPc, psx::cpu::kUnboundedCallTurns);
    return settled(modeCall_.advance(std::nullopt, psx::cpu::ExecutionBudget::fromCycles(kFieldCycles)));
  }

  bool resumeSpanningCall() override {
    ++boundedResumes;
    return settled(modeCall_.advance(std::nullopt, psx::cpu::ExecutionBudget::fromCycles(kFieldCycles)));
  }

  void deliverEvent(std::uint32_t, std::uint32_t) override {
    ++events;
  }

  std::uint32_t returnValue() const override {
    return core_.r[2];
  }

  std::uint32_t readRegister(std::uint32_t index) const override {
    return core_.r[index];
  }

  void writeRegister(std::uint32_t index, std::uint32_t value) override {
    core_.r[index] = value;
  }

  void tick(std::uint32_t) override {
    ++ticks;
  }

  std::uint8_t read8(std::uint32_t address) const override {
    return core_.mem_r8(address);
  }

  std::uint16_t read16(std::uint32_t address) const override {
    return core_.mem_r16(address);
  }

  std::uint32_t read32(std::uint32_t address) const override {
    return core_.mem_r32(address);
  }

  void write8(std::uint32_t address, std::uint8_t value) override {
    core_.mem_w8(address, value);
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    core_.mem_w32(address, value);
  }

  void commitPresentation() override {
    ++presentations;
  }

  void serviceAudioSink() override {
    ++audioServices;
  }

  void servicePad() override {
    ++padServices;
  }

  unsigned suspendingEntryAbuses = 0;
  unsigned boundedStarts = 0;
  unsigned boundedResumes = 0;
  unsigned ticks = 0;
  unsigned events = 0;
  unsigned presentations = 0;
  unsigned audioServices = 0;
  unsigned padServices = 0;
  std::uint32_t lastEntry = 0;
  std::uint32_t lastReturnPc = 0;

private:
  Core &core_;
  psx::cpu::ResumableGuestCall &modeCall_;
};

unsigned storeObservations = 0;
unsigned storeObservationsBefore = 0;
std::uint32_t observerT0 = 0;
std::uint32_t observerT1 = 0;
std::uint32_t observerT2 = 0;
std::uint32_t observerT3 = 0;
std::uint32_t lastStorePc = 0;
std::uint32_t lastStoreAddress = 0;
std::uint32_t lastStoreValue = 0;
std::uint32_t lastStoreWord = 0;
std::uint32_t lastStoreBase = 0;
std::int32_t lastStoreDisplacement = 0;

bool loadFixture(Core &core) {
  const auto image = syntheticImage();
  const auto loaded = psx::cpu::loadPsxExeImage(core, image, "synthetic mode-2 loader wait");
  if (!loaded) {
    std::fprintf(stderr, "mode_call_budget_resume: synthetic image rejected: %s\n", loaded.detail.c_str());
    return false;
  }
  core.mem_w8(kLoaderBusy, 1);
  core.mem_w16(kRenderMode, 2);
  core.r[29] = 0x00020000u; // a guest stack the frame loop can build frames below
  return true;
}

// A missing load delay slot decodes correctly but misbehaves on an R3000, so run the mis-scheduled
// body and require that its store does not land.
bool misScheduledBodyStoresNothing() {
  // The `lw` at index 6 feeds the `addiu` at index 7 with no delay slot.
  std::array<std::uint32_t, 16> wrong = kSpinBody;
  wrong[7] = mips::addiu(mips::kT3, mips::kT3, 1); // delete the delay slot by overwriting it
  wrong[8] = mips::nop();
  wrong[9] = mips::sw(mips::kT1, mips::kT3, 0x698);
  {
    auto game = std::make_unique<Game>();
    Core &core = game->core;
    if (!loadFixture(core)) {
      return false;
    }
    const auto image = syntheticImage();
    std::vector<std::uint8_t> misScheduled = image;
    for (std::size_t index = 0; index < wrong.size(); ++index) {
      word(misScheduled, 0x800u + (kModeFunction2 - kTextBase) + index * 4u, wrong[index]);
    }
    if (!psx::cpu::loadPsxExeImage(core, misScheduled, "mis-scheduled body")) {
      return false;
    }
    core.mem_w8(kLoaderBusy, 1);
    core.mem_w16(kRenderMode, 2);
    core.r[29] = 0x00020000u;
    core.r[31] = kModeReturnPc2;
    psx::cpu::ResumableGuestCall probe;
    for (int field = 0; field < 7; ++field) {
      if (field == 0) {
        probe.begin(core, "negative", kModeFunction2, kModeReturnPc2, psx::cpu::kUnboundedCallTurns);
      }
      const psx::cpu::CallStep probeStep =
          probe.advance(std::nullopt, psx::cpu::ExecutionBudget::fromCycles(kFieldCycles));
      if (probeStep.outcome == psx::cpu::CallOutcome::Refused) {
        std::fprintf(stderr, "mode_call_budget_resume: negative probe refused: %s\n", probeStep.detail.c_str());
        return false;
      }
      if (!probe.pending()) {
        break;
      }
    }
    const std::uint32_t counter = core.mem_r32(kSpinCounter);
    std::printf("negative     : body with the load delay slot deleted stores counter=0x%08X %s\n",
                counter,
                counter == 0 ? "(as a real R3000 requires)" : "— THE ASSERTION BELOW IS NOT TESTING ANYTHING");
    if (counter != 0) {
      std::fprintf(stderr,
                   "mode_call_budget_resume: deleting a load delay slot still produced counter=0x%08X, so "
                   "the live counter assertion cannot detect a mis-scheduled body and proves nothing\n",
                   counter);
      return false;
    }
  }
  std::printf("negative     : the mis-scheduled body's store did NOT land, so the live counter assertion "
              "can fail and the correct body is what makes it pass\n");
  return true;
}

// Positive control on the read path: a host write at the counter address must be visible.
bool hostWriteToTheSameAddressIsVisible() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  if (!loadFixture(core)) {
    return false;
  }
  constexpr std::uint32_t kSentinel = 0x5A5A5A5Au;
  core.mem_w32(kSpinCounter, kSentinel);
  if (core.mem_r32(kSpinCounter) != kSentinel) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: FAIL — a host write of 0x%08X to 0x%08X read back as 0x%08X, so "
                 "a zero from the guest loop would say nothing about the guest\n",
                 kSentinel,
                 kSpinCounter,
                 core.mem_r32(kSpinCounter));
    return false;
  }
  core.mem_w32(kSpinCounter, 0u);
  if (core.mem_r32(kSpinCounter) != 0u) {
    std::fprintf(stderr, "mode_call_budget_resume: FAIL — the host write could not be cleared\n");
    return false;
  }
  return true;
}

bool resumeArm() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  if (!loadFixture(core)) {
    return false;
  }
  psx::cpu::ResumableGuestCall modeCall;
  BudgetMachine machine(core, modeCall);
  tekken3::frame::StepState state;
  state.stage = tekken3::frame::Stage::Running;

  tekken3::frame::FiniteFrame::step(machine, state);
  if (!state.callPending || machine.boundedStarts != 1 || machine.boundedResumes != 0 || !modeCall.pending() ||
      machine.lastEntry != kModeFunction2 || machine.lastReturnPc != kModeReturnPc2) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: field 1 — mode 2 did not suspend through the bounded "
                 "entry (starts=%u pending=%d entry=0x%08X return=0x%08X)\n",
                 machine.boundedStarts,
                 static_cast<int>(modeCall.pending()),
                 machine.lastEntry,
                 machine.lastReturnPc);
    return false;
  }
  if (core.mem_r32(kFrameCounter) != 1) {
    std::fprintf(stderr, "mode_call_budget_resume: field 1 — the guest frame counter did not advance once\n");
    return false;
  }
  const auto frameCounterAtSuspend = core.mem_r32(kFrameCounter);
  const auto presentationsAtSuspend = machine.presentations;
  const auto instructionsAtSuspend = core.lightrecExecutor().counters().executedInstructions;
  std::uint32_t spinAtSuspend = 0;

  constexpr unsigned kHeldFields = 6u;
  for (unsigned field = 0; field < kHeldFields; ++field) {
    tekken3::frame::FiniteFrame::step(machine, state);
    if (!state.callPending || !modeCall.pending()) {
      std::fprintf(stderr, "mode_call_budget_resume: held field %u left the wait early\n", field + 2u);
      return false;
    }
    spinAtSuspend = core.mem_r32(kSpinCounter);
  }
  // The body's `sw` must have landed in Core.
  if (spinAtSuspend == 0) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: the guest's own store never landed in 0x%08X across %u held "
                 "fields and %llu executed instructions. The program decodes as intended and a host "
                 "write to the same address IS visible (hostWriteToTheSameAddressIsVisible), so this is "
                 "the guest program, not a read or a synchronisation problem.\n",
                 kSpinCounter,
                 kHeldFields,
                 static_cast<unsigned long long>(core.lightrecExecutor().counters().executedInstructions -
                                                 instructionsAtSuspend));
    return false;
  }
  if (core.mem_r32(kFrameCounter) != frameCounterAtSuspend) {
    std::fprintf(stderr, "mode_call_budget_resume: the guest frame counter advanced on a held field\n");
    return false;
  }
  if (machine.presentations != presentationsAtSuspend + kHeldFields || machine.padServices < kHeldFields ||
      machine.audioServices < kHeldFields || machine.boundedResumes != kHeldFields || machine.boundedStarts != 1) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: held-field services — present=%u (expected %u) pad=%u audio=%u "
                 "resumes=%u starts=%u\n",
                 machine.presentations,
                 presentationsAtSuspend + kHeldFields,
                 machine.padServices,
                 machine.audioServices,
                 machine.boundedResumes,
                 machine.boundedStarts);
    return false;
  }
  if (machine.suspendingEntryAbuses != 7) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: %u non-suspending guest calls in the sequence; the frame "
                 "barrier, CD XA, render-mode query, buffer/geometry select and OT clear are the seven\n",
                 machine.suspendingEntryAbuses);
    return false;
  }

  // Release the wait as a sector completion does.
  core.mem_w8(kLoaderBusy, 0);
  tekken3::frame::FiniteFrame::step(machine, state);
  if (state.callPending || modeCall.pending()) {
    std::fprintf(stderr, "mode_call_budget_resume: the mode call did not return after the busy byte cleared\n");
    return false;
  }
  if (core.pc != kModeReturnPc2) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: the mode call returned to 0x%08X, not its own outer "
                 "boundary 0x%08X\n",
                 core.pc,
                 kModeReturnPc2);
    return false;
  }
  const auto &counters = core.lightrecExecutor().counters();
  std::printf("arm=resume fields=%u spin=%u frame_counter=%u blocks=%llu fallback=%llu return=0x%08X\n",
              kHeldFields + 2u,
              spinAtSuspend,
              core.mem_r32(kFrameCounter),
              static_cast<unsigned long long>(counters.executedBlocks),
              static_cast<unsigned long long>(counters.fallback.calls),
              core.pc);
  return counters.executedBlocks > 0 && counters.fallback.calls == 0;
}

bool controlArmAborts() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  if (!loadFixture(core)) {
    return false;
  }
  core.r[31] = kModeReturnPc2;
  tekken3::execution::FiniteGuestCall::callToReturn(core, kModeFunction2, "mode_call_budget_resume control");
  return false; // the entry returned, which is the claim being refuted
}

bool controlArm() {
  std::fflush(nullptr);
  const pid_t child = fork();
  if (child < 0) {
    std::fprintf(stderr, "mode_call_budget_resume: fork failed\n");
    return false;
  }
  if (child == 0) {
    _exit(controlArmAborts() ? 0 : 3);
  }
  int status = 0;
  if (waitpid(child, &status, 0) != child) {
    std::fprintf(stderr, "mode_call_budget_resume: waitpid failed\n");
    return false;
  }
  // Only SIGABRT counts; exit 0 or 3 means the non-suspending entry stopped refusing.
  if (!WIFSIGNALED(status) || WTERMSIG(status) != SIGABRT) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: the non-suspending entry did not abort (exited=%d signal=%d); "
                 "it no longer distinguishes a field-spanning call, so arm=resume proves nothing\n",
                 WIFEXITED(status) ? WEXITSTATUS(status) : -1,
                 WIFSIGNALED(status) ? WTERMSIG(status) : 0);
    return false;
  }
  std::printf("arm=control non-suspending entry on the same body: SIGABRT as expected\n");
  return true;
}

} // namespace

int main() {
  if (!programDecodesAsIntended() || !perturbedProgramsAreRejected() || !hostWriteToTheSameAddressIsVisible() ||
      !resumeArm() || !controlArm()) {
    std::fprintf(stderr, "mode_call_budget_resume: FAIL — a mode call that outlives one display field\n");
    return 1;
  }
  std::printf("mode_call_budget_resume: PASS — mode 2 suspended, resumed across held fields with the "
              "held-field services and no frame-counter advance, and returned to its own boundary\n");
  return 0;
}
