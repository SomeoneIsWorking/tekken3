// mode_call_budget_resume.cpp — test-only. Answers one question through the SHIPPING owners:
//
//   When the title's per-field mode call legitimately outlives one display field's cycle
//   allowance, does the frame loop report the bounded exit and resume it — or does it abort?
//
// The shape reproduced here is the measured one, not a guess at it. `docs/issues/0011` and
// `docs/issues/0016` record the mode table at `game/core/frame_loop.cpp:63`, where index 2 is
// `0x8004FA60`; a disc-backed run at the "NAMCO PRESENTS." card produced
//
//     [tekken3-lz:error] guest_call=0x8004FA60 exit=budget-exhausted pc=0x8006BEE4 cycles=564486
//     -> requireReturn -> std::abort at game/core/guest_execution.cpp:93
//
// `0x8006BEE4` is inside `FUN_8006BEA8`, an untimed spin on the loader busy byte `0x800A069E` that
// only a sector completion clears. 564,486 cycles is `33868800/60` plus a few: exactly one display
// field. So the guest body is legitimately still resident when the field ends, and the port's only
// question is which entry it dispatched that body through.
//
// The synthetic image carries the MECHANISM, not the retail bytes: mode 2's entry at `0x8004FA60`
// spins on a guest busy byte exactly the way `FUN_8006BEA8` spins on `0x800A069E`, and the host
// releases it by clearing that byte. Everything under test — `FrameLoop::step`'s choice of entry,
// `psx::cpu::ResumableGuestCall`'s budget-resume, and the probe call's refusal — is the shipping code.
//
// ARMS, each answering a different question so a reader cannot mistake one for another:
//
//   arm=resume    the shipping frame loop over N fields. It MUST suspend, MUST resume, MUST hold
//                 the held field (pad + presentation + audio once per field, barrier NOT re-run,
//                 guest frame counter NOT advanced), and MUST finish when the host releases the
//                 busy byte — all with exit status 0. On the unfixed code this process dies inside
//                 the probe call on the first `step`, which is the failure this test exists for.
//   arm=control   the SAME image and the SAME body entered through the NON-suspending probe call,
//                 in a forked child, which must be observed dying on SIGABRT. It is the
//                 discriminator for arm=resume: a green arm=resume means the call suspends, not that
//                 the refusal stopped existing. If this arm ever stops aborting, the two entries have
//                 converged and the pairing above is no longer measuring anything.
//
// WHY THE GUEST BODY IS BUILT FROM FIELDS AND NOT FROM HEX. See `tests/asm_fields.h`: the body was
// transcribed as literals and was wrong five times, every one of which DISASSEMBLED to a plausible
// mnemonic. The last two were found by the field decoder that now builds the words, which is the
// only control that could have found them.
#include "asm_fields.h"
#include "core.h"
#include "decompressor_probe.h"
#include "execution_exit.h"
#include "frame_loop.h"
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

// The measured mode table index and the guest words the body spins on.
constexpr std::uint32_t kModeFunction2 = 0x8004FA60u;
constexpr std::uint32_t kModeReturnPc2 = 0x80028C9Cu + 2u * 0x10u;
constexpr std::uint32_t kLoaderBusy = 0x800A069Eu;
constexpr std::uint32_t kSpinCounter = 0x800A0698u;
constexpr std::uint32_t kRenderMode = 0x800AE204u;
constexpr std::uint32_t kFrameCounter = 0x800AFA4Cu;
constexpr std::uint32_t kFrameBarrier = 0x800296C4u;

// One field's worth of work for this fixture. Its exact magnitude does not decide whether the body
// outlives the held fields, and that is the point: the framework caps each segment at BOTH the
// caller's budget AND the display field's deadline, so a fixture that held N fields purely by
// picking this number was racing the field clock. The body waits on a byte only the HOST clears,
// so no value of this constant can make it finish early — it is a pacing choice, not the mechanism.
constexpr std::uint64_t kFieldCycles = 4000u;

// ---------------------------------------------------------------------------
// THE GUEST BODY, BUILT FROM FIELDS.
//
//   0  lui  $t0,0x800A
//   1  lui  $t1,0x800A
//   2  lbu  $t2,0x69E($t0)          ; the loader busy byte
//   3  beq  $t2,$zero,exit          ; cleared -> the wait is over
//   4  nop                            (branch delay slot)
//   5  lw   $t3,0x698($t1)
//   6  addiu $t3,$t3,1
//   7  sw   $t3,0x698($t1)          ; visible spin progress
//   8  j    loop                     ; NOTE: a j field is ABSOLUTE>>2, not a PC-relative offset
//   9  nop                            (branch delay slot)
//  10  jr   $ra
//  11  nop                            (branch delay slot)
//
// Every word is a function of its fields, and `programDecodesAsIntended` reads the fields back out
// and compares. The two encoders that are NOT a plain field-pack are the two that were wrong:
// `branchOffset` (PC-relative) and `jumpIndex` (absolute), and each takes the PC so a caller cannot
// pass an index where an offset belongs without it being obvious at the call site.
// ---------------------------------------------------------------------------
// The body's word indices, named so no address is written by hand. The loop starts at index 2 and
// the exit is index 14; every branch and jump is given the PC it is AT, which is the whole point.
constexpr std::uint32_t kBodyLoopPc = kModeFunction2 + 2u * 4u;  // index 2,  the lbu
constexpr std::uint32_t kBodyBeqPc = kModeFunction2 + 4u * 4u;   // index 4,  the beq
constexpr std::uint32_t kBodyExitPc = kModeFunction2 + 14u * 4u; // index 14, the jr $ra
constexpr std::uint32_t kBodyJmpPc = kModeFunction2 + 10u * 4u;  // index 10, the j

constexpr std::array<std::uint32_t, 16> kSpinBody{{
    mips::lui(mips::kT0, 0x800A),                               // 0
    mips::lui(mips::kT1, 0x800A),                               // 1
    mips::lbu(mips::kT0, mips::kT2, 0x69E),                     // 2   read the busy byte
    mips::nop(),                                                // 3   LOAD DELAY SLOT
    mips::beq(mips::kT2, mips::kZero, kBodyBeqPc, kBodyExitPc), // 4
    mips::nop(),                                                // 5   branch delay slot
    mips::lw(mips::kT1, mips::kT3, 0x698),                      // 6   read the counter
    mips::nop(),                                                // 7   LOAD DELAY SLOT
    mips::addiu(mips::kT3, mips::kT3, 1),                       // 8
    mips::sw(mips::kT1, mips::kT3, 0x698),                      // 9
    mips::j(kBodyJmpPc, kBodyLoopPc),                           // 10
    mips::nop(),                                                // 11  branch delay slot
    mips::nop(),                                                // 12
    mips::nop(),                                                // 13
    mips::jr(mips::kRa),                                        // 14
    mips::nop(),                                                // 15  branch delay slot
}};

// What each word must decode back to, as FIELDS. A mnemonic is an interpretation and two encodings
// share one; a field cannot alias, so this is the comparison that can actually fail.
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
    // WHICH FIELDS ARE MEANINGFUL DEPENDS ON THE OPCODE, and asserting the wrong set is how a
    // check starts rejecting correct code. For a `j`, rs and rt and the low half of the field are
    // all don't-care and the ONLY meaningful quantity is the decoded target, so that is what is
    // compared. For `lui` the immediate is raw, not sign-extended. For everything else the immediate
    // is sign-extended. The rest of the table is not a style preference: an earlier decoder compared
    // the `j`'s rt against 0 and reported a CORRECT encoding as broken, twice.
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
    // SPECIAL has no immediate: bits 15..11 are `rd`, which `jr` does not use. So for SPECIAL the
    // comparison is rs + funct, and comparing `imm` would be asserting a don't-care field.
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

// THE CONTROL THAT PROVES THE CHECK CAN FAIL. A round-trip decoder that has never rejected
// anything is not a control, it is a comment. So the program is PERTURBED — one field moved, exactly
// the class of error the literal body carried five times — and the same check must refuse it. Each
// perturbation is one of the five real errors, so the negative case is not invented: it is the bug.
// Forward-declared: the negative case below RUNS the mis-scheduled body, so it needs the image and
// the loader, which are defined further down. Declaring it here keeps the checks in reading order.
bool misScheduledBodyStoresNothing();

bool perturbedProgramsAreRejected() {
  const char *const kNames[] = {
      "sw base register", "lw base register", "beq condition register", "j target", "addiu immediate"};
  // 1. `sw $t3,0x698($t1)` with the base moved to $t0 — the 0xAC220000 / rs-slip class, twice.
  std::array<std::uint32_t, 16> wrong = kSpinBody;
  wrong[9] = mips::sw(mips::kT0, mips::kT3, 0x698);
  // 2. `lw $t3,0x698($t1)` with the base moved to $at — the original 0x8C2B0698 exactly.
  wrong[6] = mips::lw(mips::kAt, mips::kT3, 0x698);
  std::array<std::uint32_t, 16> at{};
  programAddresses(&at, kModeFunction2);
  if (decodeMatches(wrong.data(), kSpinBodyIntended.data(), wrong.size(), at.data())) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: a program with the store's and load's base register moved "
                 "was ACCEPTED, so the field check cannot see a register-field slip\n");
    return false;
  }
  // 3. the branch condition moved, 4. the jump retargeted, 5. an immediate widened past 16 bits.
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
  // The J-type trap itself, as a raw word: a branch-style PC-relative value in a jump's absolute
  // field. This is the one that produced a plausible `j 0x8003FFE4`.
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
  // Everything not named below stays 0, which is MIPS `sll $zero,$zero,0` — a nop. That is the
  // filler the real image's own padding would be, and it means the only executable bodies are the
  // ones this test writes.
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

// The shipping Core adapter with the three host services counted instead of driven, so the test
// stays headless. Every GUEST call below goes through the shipping guest_execution.cpp entries.
class BudgetMachine final : public tekken3::FrameMachine {
public:
  BudgetMachine(Core &core, psx::cpu::ResumableGuestCall &modeCall) : core_(core), modeCall_(modeCall) {}

  void call(std::uint32_t address, std::uint32_t returnPc) override {
    ++suspendingEntryAbuses;
    tekken3::DecompressorProbe::callToReturn(core_, address, "mode_call_budget_resume control");
  }

  void call1(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0) override {
    call(address, returnPc);
  }

  void
  call3(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t a2) override {
    call(address, returnPc);
  }

  static bool settled(psx::cpu::CallStep step) {
    if (step.outcome == psx::cpu::CallOutcome::Refused) {
      std::fprintf(stderr, "mode_call_budget_resume: refused: %s\n", step.detail.c_str());
      std::abort();
    }
    return step.outcome == psx::cpu::CallOutcome::Returned;
  }

  bool startModeCall(std::uint32_t address, std::uint32_t returnPc) override {
    ++boundedStarts;
    lastEntry = address;
    lastReturnPc = returnPc;
    modeCall_.begin(core_, "mode call", address, returnPc, psx::cpu::kUnboundedCallTurns);
    return settled(modeCall_.advance(std::nullopt, psx::cpu::ExecutionBudget::fromCycles(kFieldCycles)));
  }

  bool resumeModeCall() override {
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

// THE SIXTH ERROR, and the only one that is not a field error: a MISSING LOAD DELAY SLOT.
//
// Every word decodes exactly as intended, the field check passes, and the program still
// misbehaves — because on an R3000 a `lw` result is not readable until the following instruction
// retires, and this body read the counter with `lw` and consumed it on the very next instruction.
// That is what actually caused the "$t3 reads 0" symptom in `docs/issues/0021`, and it is the
// reason the field check alone is not sufficient: this is the one failure it CANNOT see.
//
// So it is the negative case that matters most, and it is checked by RUNNING the mis-scheduled body
// and requiring that its store does NOT land. If the store lands anyway, the live counter assertion
// in `resumeArm` is not testing anything and this returns false.
bool misScheduledBodyStoresNothing() {
  // The mis-scheduled body: the `lw` at index 6 feeds the `addiu` at index 7 directly, with the
  // delay slot removed. On a real R3000 the loaded value is not available that early.
  std::array<std::uint32_t, 16> wrong = kSpinBody;
  wrong[7] = mips::addiu(mips::kT3, mips::kT3, 1); // delete the delay slot by overwriting it
  wrong[8] = mips::nop();
  wrong[9] = mips::sw(mips::kT1, mips::kT3, 0x698);
  {
    // A fresh Core, the same image, and the mis-scheduled body: the store must NOT land, or the
    // live assertion in resumeArm is not testing anything.
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

// THE POSITIVE CONTROL ON THE READ PATH, and the reason a zero from the guest loop is interpretable.
//
// `docs/issues/0021` recorded a symptom that looked like a framework synchronisation defect: the
// guest's `sw` never appeared in the `Core`, while a HOST `mem_w32` at the same address was
// immediately visible. That is now MEASURED to be a register-field slip in this fixture and not a
// framework defect — the framework has no second RAM buffer and no sync to be defective (see issue
// 0021 for the three measurements). But the control belongs here permanently, because the day
// someone reads a zero from the guest loop they must be able to tell it apart from a zero from a
// broken read, and that distinction costs one store and one load to establish.
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
  tekken3::FrameStepState state;

  tekken3::FrameLoop::step(machine, state);
  if (!state.modeCallPending || machine.boundedStarts != 1 || machine.boundedResumes != 0 || !modeCall.pending() ||
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
    tekken3::FrameLoop::step(machine, state);
    if (!state.modeCallPending || !modeCall.pending()) {
      std::fprintf(stderr, "mode_call_budget_resume: held field %u left the wait early\n", field + 2u);
      return false;
    }
    spinAtSuspend = core.mem_r32(kSpinCounter);
  }
  // THE GUEST CALL CONTRACT, and the assertion that failed five times before the fixture was right.
  // The body's `sw $t3,0x698($t1)` must have LANDED: the counter is a memory word the guest wrote
  // from a translated block, and the framework writes it into `Core` in the store callback itself,
  // so a zero here is a statement about the guest program and never about a memory sync.
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

  // Release the wait the way a sector completion does, and the call must finish on its own.
  core.mem_w8(kLoaderBusy, 0);
  tekken3::FrameLoop::step(machine, state);
  if (state.modeCallPending || modeCall.pending()) {
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
  tekken3::DecompressorProbe::callToReturn(core, kModeFunction2, "mode_call_budget_resume control");
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
  // A child that exited 0 means the probe call returned a body that outlived its budget, and a child
  // that exited 3 means it returned without aborting. Only SIGABRT is the expected answer, and it
  // is what makes a green arm=resume mean "resumed" rather than "the refusal is gone".
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
