#include "core.h"
#include "execution_exit.h"
#include "game.h"
#include "lightrec_executor.h"
#include "native_dispatch.h"
#include "psx_exe_image.h"

#include <cstdint>
#include <cstdio>
#include <iostream>
#include <iterator>
#include <memory>
#include <vector>

namespace {

constexpr std::uint32_t kFunction = 0x80031BFCu;
constexpr std::uint32_t kReturn = 0x8004CA9Cu;
constexpr std::uint32_t kSource = 0x800BAFCCu;
constexpr std::uint32_t kDestination = 0x8012867Cu;
constexpr std::uint32_t kMaximumOutput = 0x8240u;

bool run(const std::vector<std::uint8_t> &image, bool negative) {
  auto game = std::make_unique<Game>();
  auto &core = game->core;
  const auto loaded = psx::cpu::loadPsxExeImage(core, image, "authenticated SLUS_004.02");
  if (!loaded || !core.currentImageIdentity(kFunction)) {
    std::fprintf(stderr, "decompressor_lightrec: image mapping refused: %s\n", loaded.detail.c_str());
    return false;
  }

  core.r[4] = kSource;
  core.r[5] = kDestination;
  core.r[31] = kReturn;
  const auto budget =
      negative ? psx::cpu::ExecutionBudget::fromCycles(1) : psx::cpu::ExecutionBudget::currentTurn(core);
  const auto result = psx::cpu::dispatchGuest(core, kFunction, budget);
  const auto &counters = core.lightrecExecutor().counters();
  const auto mappedOutput = core.mappedMainRamRange(kDestination, kMaximumOutput);
  const auto reached = counters.executedBlocks > 0 && result.cycles > 0;
  const auto progressValid = core.r[5] >= kDestination && core.r[5] - kDestination <= kMaximumOutput;
  const auto outputBytes = progressValid ? core.r[5] - kDestination : 0u;
  std::printf("arm=%s reached=%u exit=%s pc=0x%08X cycles=%llu budget=%llu "
              "blocks=%llu instructions=%llu fallback_calls=%llu output_bytes=%u "
              "output_bounded=%u v0=%u source_cursor=0x%08X\n",
              negative ? "negative" : "normal",
              reached ? 1u : 0u,
              psx::cpu::executionExitName(result.reason),
              result.guestPc,
              static_cast<unsigned long long>(result.cycles),
              static_cast<unsigned long long>(budget.cycles),
              static_cast<unsigned long long>(counters.executedBlocks),
              static_cast<unsigned long long>(counters.executedInstructions),
              static_cast<unsigned long long>(counters.fallback.calls),
              outputBytes,
              mappedOutput && progressValid ? 1u : 0u,
              core.r[2],
              core.r[4]);
  if (!negative && mappedOutput && progressValid) {
    std::printf("output_hex=");
    for (std::uint32_t index = 0; index < outputBytes; ++index) {
      std::printf("%02x", core.ram[mappedOutput->begin + index]);
    }
    std::printf("\n");
  }
  return reached && mappedOutput && progressValid && counters.fallback.calls == 0 &&
         (!negative || result.reason == psx::cpu::ExecutionExitReason::BudgetExhausted);
}

} // namespace

int main() {
  const std::vector<std::uint8_t> image{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()};
  if (image.empty() || image.size() > psx::cpu::kPsxExeMaxBytes) {
    std::fprintf(stderr, "decompressor_lightrec: missing or oversized authenticated input\n");
    return 2;
  }
  if (!run(image, false) || !run(image, true)) {
    return 1;
  }
  return 0;
}
