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
// `guest::BoundedCall`'s budget-resume, and `guest::call`'s refusal — is the shipping code.
//
// Arms, each answering a different question so a reader cannot mistake one for another:
//
//   arm=resume    the shipping frame loop over N fields. It MUST suspend, MUST resume, MUST hold
//                 the held field (pad + presentation + audio once per field, barrier NOT re-run,
//                 guest frame counter NOT advanced), and MUST finish when the host releases the
//                 busy byte — all with exit status 0. On the unfixed code this process dies inside
//                 `guest::call` on the first `step`, which is the failure this test exists for.
//   arm=control   the SAME image and the SAME spinning body entered through the NON-suspending
//                 `guest::call`, in a forked child, which must be observed dying on SIGABRT. It is
//                 the discriminator for arm=resume: a green arm=resume means the call suspends, not
//                 that the refusal stopped existing. If this arm ever stops aborting, the two
//                 entries have converged and the pairing above is no longer measuring anything.
#include "core.h"
#include "execution_exit.h"
#include "frame_loop.h"
#include "game.h"
#include "guest_execution.h"
#include "lightrec_executor.h"
#include "psx_exe_image.h"

#include <array>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <vector>

#include <sys/wait.h>
#include <unistd.h>

namespace {

// PS-X EXE layout: text at t_addr 0x80010000, big enough to reach the highest address the frame
// loop dispatches into (kSelectBuffer at 0x80080D98).
constexpr std::uint32_t kTextBase = 0x80010000u;
constexpr std::uint32_t kTextEnd = 0x80082000u;

// The measured mode table index and the guest words `FUN_8006BEA8` spins on.
constexpr std::uint32_t kModeFunction2 = 0x8004FA60u;
constexpr std::uint32_t kModeReturnPc2 = 0x80028C9Cu + 2u * 0x10u;
constexpr std::uint32_t kLoaderBusy = 0x800A069Eu;
constexpr std::uint32_t kSpinCounter = 0x800A0698u;

// The three fields of a MIPS word, read back out of the encoding.
//
// This exists because the body below was hand-assembled TWICE and was wrong twice, in two
// different registers' worth of the same mistake:
//
//   * `0x1000FFFF` for `b -7`. A branch offset is the 16-bit immediate SIGN-EXTENDED from (PC+4),
//     so -7 is 0xFFF9. 0xFFFF is -1, which is a one-instruction SELF LOOP that never reaches the
//     counter write, so the test failed for a reason that had nothing to do with what it exists to
//     detect.
//   * `0x8C2B0698` for `lw $t3,0x698($t1)`. The base register is bits 25..21: 0x8C2B0698 carries
//     rs = 1 ($at), not 9 ($t1). A four slipped in the register field and the load read from
//     $at, so the counter never advanced.
//
// The second is the SAME error class as the `0x8009B960` / `0x8009B964` four that issue 0019 records
// reaching a written record, and the first is the same class as the five wrong call targets
// `megamanx4` shipped from a hand-decoded listing. A hand-assembled instruction is a CLAIM, and this
// one has now been wrong twice in a row, so the words are decoded and checked here rather than
// trusted. If a word stops matching what its comment says, the test says so and fails.
struct Insn {
  std::uint32_t op;
  std::uint32_t rs;
  std::uint32_t rt;
  std::uint32_t imm;
};

Insn decode(std::uint32_t word) {
  return {word >> 26, (word >> 21) & 0x1Fu, (word >> 16) & 0x1Fu, word & 0xFFFFu};
}

// The spin body, written as (word, what the word must decode to) so the check is a COMPARISON
// against a separate reading rather than a restatement of the same constant. Each row is
// (op, rs, rt, imm).
struct Word {
  std::uint32_t word;
  std::uint32_t op;
  std::uint32_t rs;
  std::uint32_t rt;
  std::uint32_t imm;
};

bool spinWordsDecodeAsWritten(const Word *rows, std::size_t count) {
  for (std::size_t index = 0; index < count; ++index) {
    const Insn got = decode(rows[index].word);
    if (got.op != rows[index].op || got.rs != rows[index].rs || got.rt != rows[index].rt ||
        got.imm != rows[index].imm) {
      std::fprintf(stderr,
                   "mode_call_budget_resume: word %zu 0x%08X decodes op=0x%02X rs=r%u rt=r%u imm=0x%04X, "
                   "but the comment claims op=0x%02X rs=r%u rt=r%u imm=0x%04X\\n",
                   index,
                   rows[index].word,
                   got.op,
                   got.rs,
                   got.rt,
                   got.imm,
                   rows[index].op,
                   rows[index].rs,
                   rows[index].rt,
                   rows[index].imm);
      return false;
    }
  }
  return true;
}
constexpr std::uint32_t kRenderMode = 0x800AE204u;
constexpr std::uint32_t kFrameCounter = 0x800AFA4Cu;
constexpr std::uint32_t kFrameBarrier = 0x800296C4u;

// One field's worth of work for this fixture, so a field boundary lands inside the spin rather
// than after it. 564,480 is the real per-field allowance; the shape of the test does not depend on
// its magnitude, only on the body being longer than one of them.
constexpr std::uint64_t kFieldCycles = 400u;

void word(std::vector<std::uint8_t> &bytes, std::size_t offset, std::uint32_t value) {
  for (unsigned index = 0; index < 4; ++index) {
    bytes[offset + index] = static_cast<std::uint8_t>(value >> (index * 8u));
  }
}

// `jr $ra` / `nop`, optionally preceded by `addiu $v0,$zero,n` when the caller reads a result.
void stub(std::vector<std::uint8_t> &bytes, std::uint32_t address, int result) {
  if (result >= 0) {
    word(bytes, 0x800u + (address - kTextBase), static_cast<std::uint32_t>(0x24020000u | result));
  }
  const auto offset = 0x800u + (address - kTextBase) + (result >= 0 ? 4u : 0u);
  word(bytes, offset, 0x03E00008u);      // jr $ra
  word(bytes, offset + 4u, 0x00000000u); // nop
}

// FUN_8006BEA8's shape, re-derived from the same semantics rather than from any quoted listing:
//   lui  $t0,0x800A ; lui $t1,0x800A
//   lbu  $t2,0x69E($t0)          ; the loader busy byte
//   beq  $t2,$zero,exit          ; cleared -> the wait is over
//   lw   $t3,0x698($t1) ; addiu $t3,$t3,1 ; sw $t3,0x698($t1)   ; visible spin progress
//   b    loop
//   exit: jr $ra
//
// Register numbering used below: $t0 = 8, $t1 = 9, $t2 = 10, $t3 = 11, $ra = 31, $zero = 0.
constexpr std::array<Word, 12> kSpinBody{{
    {0x3C08800Au, 0x0F, 0, 8, 0x800A},   // 0  lui  $t0,0x800A
    {0x3C09800Au, 0x0F, 0, 9, 0x800A},   // 1  lui  $t1,0x800A
    {0x910A069Eu, 0x24, 8, 10, 0x069E},  // 2  lbu  $t2,0x69E($t0)
    {0x11400006u, 0x04, 10, 0, 0x0006},  // 3  beq  $t2,$zero, +6 -> the jr at index 10
    {0x00000000u, 0x00, 0, 0, 0x0000},   // 4  nop
    {0x8D2B0698u, 0x23, 9, 11, 0x0698},  // 5  lw   $t3,0x698($t1)   [was 0x8C2B0698: base was $at]
    {0x256B0001u, 0x09, 11, 11, 0x0001}, // 6  addiu $t3,$t3,1
    {0xAD2B0698u, 0x2B, 9, 11, 0x0698},  // 7  sw   $t3,0x698($t1)
    {0x1000FFF9u, 0x04, 0, 0, 0xFFF9},   // 8  b    -7  [was 0x1000FFFF: offset -1, a self loop]
    {0x00000000u, 0x00, 0, 0, 0x0000},   // 9  nop
    {0x03E00008u, 0x00, 31, 0, 0x0008},  // 10 jr   $ra  (SPECIAL funct 0x08: the target is rs,
                                         //     and rt is unused — the decoder check caught me
                                         //     writing rt=31, which would be `jalr`)
    {0x00000000u, 0x00, 0, 0, 0x0000},   // 11 nop
}};

void spinBody(std::vector<std::uint8_t> &bytes, std::uint32_t address) {
  for (std::size_t index = 0; index < kSpinBody.size(); ++index) {
    word(bytes, 0x800u + (address - kTextBase) + index * 4u, kSpinBody[index].word);
  }
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
  stub(bytes, 0x8007BAB0u, -1); // kSpliceOt
  spinBody(bytes, kModeFunction2);
  return bytes;
}

// The shipping Core adapter with the three host services counted instead of driven, so the test
// stays headless. Every GUEST call below goes through the shipping guest_execution.cpp entries.
class BudgetMachine final : public tekken3::FrameMachine {
public:
  BudgetMachine(Core &core, tekken3::guest::BoundedCall &modeCall) : core_(core), modeCall_(modeCall) {}

  void call(std::uint32_t address, std::uint32_t returnPc) override {
    ++suspendingEntryAbuses;
    tekken3::guest::call(core_, address, "mode_call_budget_resume control");
  }

  void call1(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0) override {
    call(address, returnPc);
  }

  void
  call3(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t a2) override {
    call(address, returnPc);
  }

  bool startModeCall(std::uint32_t address, std::uint32_t returnPc) override {
    ++boundedStarts;
    lastEntry = address;
    lastReturnPc = returnPc;
    return modeCall_.start(core_, address, returnPc, "mode call", psx::cpu::ExecutionBudget::fromCycles(kFieldCycles));
  }

  bool resumeModeCall() override {
    ++boundedResumes;
    return modeCall_.resume(core_, "mode call", psx::cpu::ExecutionBudget::fromCycles(kFieldCycles));
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
  tekken3::guest::BoundedCall &modeCall_;
};

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

bool resumeArm() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  if (!loadFixture(core)) {
    return false;
  }
  tekken3::guest::BoundedCall modeCall;
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
  // The guest call contract: the body kept making progress, and the held field did only the
  // services the retail loop does per field — no barrier re-run, no frame-counter advance.
  if (spinAtSuspend == 0) {
    std::fprintf(
        stderr, "mode_call_budget_resume: the spinning guest body made no progress in %u fields\n", kHeldFields);
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
  tekken3::guest::call(core, kModeFunction2, "mode_call_budget_resume control");
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
  // A child that exited 0 means `guest::call` returned a body that outlived its budget, and a child
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
  if (!spinWordsDecodeAsWritten(kSpinBody.data(), kSpinBody.size())) {
    std::fprintf(stderr,
                 "mode_call_budget_resume: FAIL — a hand-assembled word does not decode to what its "
                 "comment says, so the body under test is not the body that was read\n");
    return 1;
  }
  if (!resumeArm() || !controlArm()) {
    std::fprintf(stderr, "mode_call_budget_resume: FAIL — a mode call that outlives one display field\n");
    return 1;
  }
  std::printf("mode_call_budget_resume: PASS — mode 2 suspended, resumed across held fields with the "
              "held-field services and no frame-counter advance, and returned to its own boundary\n");
  return 0;
}
