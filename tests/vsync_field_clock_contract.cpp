// vsync_field_clock_contract.cpp — the Core-bound half of the VSync field-clock contract.
//
// gpu_sync_contract proves the arm/poll PROTOCOL. It cannot prove which word the product reads: it
// hands the protocol a machine and checks the arithmetic, and the defect this file exists for was
// entirely in the binding underneath it — the protocol was correct while the field clock it was
// given never moved. So this test builds a real Core, plants a distinct value at the measured word
// and DIFFERENT values at its neighbours, and asks the production reader which one it took.
//
// The decoys are the point. "0x8009AC68 minus four", "plus four", and the saved-count word the
// retail leaf subtracts from (0x80099B38) are all plausible neighbouring words, and a reader that
// resolved to any of them passes a test that only checked the happy path.
#include "core.h"
#include "sync_native.h"
#include "vsync_field_clock.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

constexpr std::uint32_t kMeasured = tekken3::vsync::kFieldCounter;
// Neighbours of the measured word, and the saved-count word FUN_800859A8 itself subtracts from.
constexpr std::uint32_t kDecoyBefore = tekken3::vsync::kFieldCounter - 4u;
constexpr std::uint32_t kDecoyAfter = tekken3::vsync::kFieldCounter + 4u;
constexpr std::uint32_t kDecoySaved = 0x80099B38u;

constexpr std::uint32_t kMeasuredValue = 0x01234567u;
constexpr std::uint32_t kDecoyValue = 0x89ABCDEFu;

} // namespace

int main() {
  // Core owns the complete 2 MiB guest RAM plus device state and is intentionally heap-resident in
  // every production Game. Keep this on the same lifetime path.
  auto core = std::make_unique<Core>();
  core->mem_w32(kMeasured, kMeasuredValue);
  core->mem_w32(kDecoyBefore, kDecoyValue);
  core->mem_w32(kDecoyAfter, kDecoyValue);
  core->mem_w32(kDecoySaved, kDecoyValue);

  const std::uint32_t read = tekken3::vsync::readFieldCounter(*core);
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

  // The reader is a read. If it wrote, the guest's own vblank callback would race it.
  if (core->mem_r32(kMeasured) != kMeasuredValue) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the field-clock read modified 0x%08X; a "
                 "producer that writes guest state is a defect\n",
                 kMeasured);
    return 1;
  }

  // A zero word is a legitimate field count (the library init zeroes it), so the reader must return
  // it rather than treat it as a refusal. A counter that has not run yet is not an error.
  core->mem_w32(kMeasured, 0u);
  if (tekken3::vsync::readFieldCounter(*core) != 0u) {
    std::fprintf(stderr, "vsync_field_clock_contract: FAIL — a field count of zero was not returned as zero\n");
    return 1;
  }

  // THE COUPLING. The framework answers the guest's 21 negative VSync queries from
  // PlatformHlePlan::vsyncQueryCounterAddress; this title's GPU-queue timeout owner reads the word
  // above. If those two ever name different words, the guest's own deadline and the port's answer
  // stop being the same clock, and neither of the two tests above would notice.
  const PlatformHlePlan &plan = tekken3::platformHlePlan();
  if (plan.vsyncQueryCounterAddress != tekken3::vsync::kFieldCounter) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the plan answers negative VSync queries from "
                 "0x%08X while the GPU timeout owner reads 0x%08X; the framework's answer and the "
                 "guest's own answer must be the same word\n",
                 plan.vsyncQueryCounterAddress,
                 tekken3::vsync::kFieldCounter);
    return 1;
  }
  if (plan.vsyncAddress != tekken3::vsync::kEntry || plan.windowLo[0] != tekken3::vsync::kEntry ||
      plan.windowHi[0] != tekken3::vsync::kBodyEnd) {
    std::fprintf(stderr,
                 "vsync_field_clock_contract: FAIL — the plan's VSync entry 0x%08X / window "
                 "[0x%08X, 0x%08X) does not match the measured entry 0x%08X and body end 0x%08X\n",
                 plan.vsyncAddress,
                 plan.windowLo[0],
                 plan.windowHi[0],
                 tekken3::vsync::kEntry,
                 tekken3::vsync::kBodyEnd);
    return 1;
  }
  // The window must still admit exactly the one library leaf. A widened window would let the
  // framework's protected handler claim engine text, which is the one thing it must never do.
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
              tekken3::vsync::kFieldCounter);
  std::printf("vsync_field_clock_contract: NOT covered — whether the guest's own vblank callback "
              "advances this word in a real run; that is a product measurement, not a unit fact\n");
  return 0;
}
