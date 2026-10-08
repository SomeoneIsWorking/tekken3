// Core-bound VSync field-clock contract: the production reader must return the measured word.
#include "core.h"
#include "fieldclock/field_clock.h"
#include "program/platform_hle_plan.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

constexpr std::uint32_t kMeasured = tekken3::field::kCounter;
// Neighbours and the saved-count word FUN_800859A8 subtracts from.
constexpr std::uint32_t kDecoyBefore = tekken3::field::kCounter - 4u;
constexpr std::uint32_t kDecoyAfter = tekken3::field::kCounter + 4u;
constexpr std::uint32_t kDecoySaved = 0x80099B38u;

constexpr std::uint32_t kMeasuredValue = 0x01234567u;
constexpr std::uint32_t kDecoyValue = 0x89ABCDEFu;

} // namespace

int main() {
  // Core is heap-resident (2 MiB RAM), as in production.
  auto core = std::make_unique<Core>();
  core->mem_w32(kMeasured, kMeasuredValue);
  core->mem_w32(kDecoyBefore, kDecoyValue);
  core->mem_w32(kDecoyAfter, kDecoyValue);
  core->mem_w32(kDecoySaved, kDecoyValue);

  const std::uint32_t read = tekken3::field::readCounter(*core);
  if (read != kMeasuredValue) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the production reader returned 0x%08X for the "
                 "measured word 0x%08X, whose value is 0x%08X. A neighbouring word reads 0x%08X, so "
                 "this is a wrong address, not an empty one\n",
                 read,
                 kMeasured,
                 kMeasuredValue,
                 kDecoyValue);
    return 1;
  }

  // The reader must not write guest state.
  if (core->mem_r32(kMeasured) != kMeasuredValue) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the field-clock read modified 0x%08X; a "
                 "producer that writes guest state is a defect\n",
                 kMeasured);
    return 1;
  }

  // Zero is a valid field count (library init zeroes it).
  core->mem_w32(kMeasured, 0u);
  if (tekken3::field::readCounter(*core) != 0u) {
    std::fprintf(stderr, "vsync_field_clock_contract: FAIL — a field count of zero was not returned as zero\n");
    return 1;
  }

  // The plan's query counter and the GPU timeout owner must name the same word.
  const PlatformHlePlan &plan = tekken3::hle::plan();
  if (plan.vsyncQueryCounterAddress != tekken3::field::kCounter) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the plan answers negative VSync queries from "
                 "0x%08X while the GPU timeout owner reads 0x%08X; the framework's answer and the "
                 "guest's own answer must be the same word\n",
                 plan.vsyncQueryCounterAddress,
                 tekken3::field::kCounter);
    return 1;
  }
  if (plan.vsyncAddress != tekken3::field::kEntry || plan.windowLo[0] != tekken3::field::kEntry ||
      plan.windowHi[0] != tekken3::field::kBodyEnd) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the plan's VSync entry 0x%08X / window "
                 "[0x%08X, 0x%08X) does not match the measured entry 0x%08X and body end 0x%08X\n",
                 plan.vsyncAddress,
                 plan.windowLo[0],
                 plan.windowHi[0],
                 tekken3::field::kEntry,
                 tekken3::field::kBodyEnd);
    return 1;
  }
  // The window admits exactly the one library leaf.
  if (plan.windowHi[1] != 0u || plan.bindingCount != 0) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the plan grew a second window or an engine "
                 "binding; only the measured VSync leaf may be hardware-owned\n");
    return 1;
  }

  std::printf("vsync_field_clock_contract: PASS — 6/6 checks: the production reader returns the "
              "measured word 0x%08X and not any of 3 planted decoy neighbours, a zero count is "
              "returned as zero, the read leaves guest RAM unchanged, the plan answers negative VSync "
              "queries from that same word, its entry/window match the measured leaf, and no second "
              "window or engine binding was added\n",
              tekken3::field::kCounter);
  std::printf("vsync_field_clock_contract: NOT covered — whether the guest's own vblank callback "
              "advances this word in a real run; that is a product measurement, not a unit fact\n");
  return 0;
}
