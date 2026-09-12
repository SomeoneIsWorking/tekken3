#include "guest_execution.h"

#include "core.h"
#include "game.h"
#include "lightrec_executor.h"
#include "psx_exe_image.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <vector>

namespace {

constexpr std::uint32_t kEntry = 0x80010000u;
constexpr std::uint32_t kOuterReturn = 0x80010100u;
constexpr std::uint32_t kNestedReturn = kEntry + 12u;

void word(std::vector<std::uint8_t> &bytes, std::size_t offset, std::uint32_t value) {
  for (unsigned index = 0; index < 4; ++index) {
    bytes[offset + index] = static_cast<std::uint8_t>(value >> (index * 8u));
  }
}

std::vector<std::uint8_t> executable() {
  constexpr std::array<std::uint32_t, 16> code{
      0x03E08021u, // addu s0,ra,zero
      0x0C004008u, // jal inner
      0x00000000u, // nop
      0x0200F821u, // addu ra,s0,zero
      0x24420007u, // addiu v0,v0,7
      0x03E00008u, // jr ra
      0x00000000u, // nop
      0x00000000u, // nop
      0x24080064u, // inner: addiu t0,zero,100
      0x24020000u, // addiu v0,zero,0
      0x24420001u, // addiu v0,v0,1
      0x2508FFFFu, // addiu t0,t0,-1
      0x1500FFFDu, // bne t0,zero,inner loop
      0x00000000u, // nop
      0x03E00008u, // jr ra
      0x00000000u, // nop
  };
  std::vector<std::uint8_t> bytes(psx::cpu::kPsxExeHeaderBytes + code.size() * 4u);
  std::memcpy(bytes.data(), "PS-X EXE", 8);
  word(bytes, 0x10, kEntry);
  word(bytes, 0x18, kEntry);
  word(bytes, 0x1c, static_cast<std::uint32_t>(code.size() * 4u));
  for (std::size_t index = 0; index < code.size(); ++index) {
    word(bytes, psx::cpu::kPsxExeHeaderBytes + index * 4u, code[index]);
  }
  return bytes;
}

bool run(std::uint32_t returnPc, psx::cpu::ExecutionBudget firstBudget, bool expectSuspend, std::uint32_t expectedV0) {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  const auto loaded = psx::cpu::loadPsxExeImage(core, executable(), "synthetic nested guest call");
  if (!loaded) {
    std::fprintf(stderr, "bounded_guest_call: synthetic image rejected: %s\n", loaded.detail.c_str());
    return false;
  }
  tekken3::guest::BoundedCall call;
  const bool firstReturned = call.start(core, kEntry, returnPc, "synthetic frame mode call", firstBudget);
  if (firstReturned == expectSuspend || call.pending() != expectSuspend) {
    return false;
  }
  if (expectSuspend && core.r[31] != kNestedReturn) {
    return false;
  }
  unsigned resumedFields = 0;
  while (call.pending() && resumedFields < 8u) {
    ++resumedFields;
    call.resume(core, "synthetic frame mode call", psx::cpu::ExecutionBudget::fromCycles(200));
  }
  const auto &counters = core.lightrecExecutor().counters();
  std::printf("arm=%s first=%s resumes=%u final_pc=0x%08X ra=0x%08X v0=%u blocks=%llu fallback=%llu\n",
              expectSuspend ? "suspend" : (returnPc == kOuterReturn ? "single-field" : "wrong-boundary"),
              firstReturned ? "returned" : "budget-exhausted",
              resumedFields,
              core.pc,
              core.r[31],
              core.r[2],
              static_cast<unsigned long long>(counters.executedBlocks),
              static_cast<unsigned long long>(counters.fallback.calls));
  return !call.pending() && (expectSuspend == (resumedFields > 0)) && core.pc == returnPc && core.r[2] == expectedV0 &&
         counters.executedBlocks > 0 && counters.fallback.calls == 0;
}

} // namespace

int main() {
  if (!run(kOuterReturn, psx::cpu::ExecutionBudget::fromCycles(24), true, 107u) ||
      !run(kOuterReturn, psx::cpu::ExecutionBudget::fromCycles(2000), false, 107u) ||
      !run(kNestedReturn, psx::cpu::ExecutionBudget::fromCycles(24), true, 100u)) {
    std::fprintf(stderr, "bounded_guest_call: FAIL — nested return boundary or guest state changed\n");
    return 1;
  }
  std::printf("bounded_guest_call: PASS — suspended, single-field, and wrong-boundary controls\n");
  return 0;
}
