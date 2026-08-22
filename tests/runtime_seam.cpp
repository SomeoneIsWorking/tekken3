#include "core.h"
#include "tekken3_runtime.h"

#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>

namespace {

constexpr tekken3::ResidentProgramRange kFixtureRange{0x00001000u, 0x00002000u};

} // namespace

int main() {
  static tekken3::Tekken3Runtime interpreterOnlyRuntime;
  psxport_install_game(interpreterOnlyRuntime);
  {
    auto interpreterCore = std::make_unique<Core>();
    if (interpreterCore->guestProgramImage != nullptr) {
      std::fprintf(stderr, "runtime_seam: FAIL — interpreter-only runtime invented resident program facts\n");
      return 1;
    }
  }

  bool invalidRangeRefused = false;
  try {
    tekken3::Tekken3Runtime invalid{{0x00010000u, 0x00010000u}};
  } catch (const std::invalid_argument &) {
    invalidRangeRefused = true;
  }
  if (!invalidRangeRefused) {
    std::fprintf(stderr, "runtime_seam: FAIL — an empty resident program range was accepted\n");
    return 1;
  }

  static tekken3::Tekken3Runtime runtime{kFixtureRange};
  psxport_install_game(runtime);

  // Core owns the complete 2 MiB guest RAM plus device state and is intentionally heap-resident in
  // every production Game. Keep this seam check on the same lifetime path.
  auto core = std::make_unique<Core>();
  if (core->runtime != &runtime) {
    std::fprintf(stderr, "runtime_seam: FAIL — Core did not snapshot the derived Tekken runtime\n");
    return 1;
  }
  if (!core->guestProgramImage || core->guestProgramImage->residentText.begin != kFixtureRange.lo ||
      core->guestProgramImage->residentText.end != kFixtureRange.hi) {
    std::fprintf(stderr, "runtime_seam: FAIL — resident program facts did not reach GuestProgramImage\n");
    return 1;
  }
  if (core->cfg != nullptr || core->hooks != nullptr || core->gameCtx != nullptr) {
    std::fprintf(stderr, "runtime_seam: FAIL — direct runtime exposed legacy config, hooks, or context\n");
    return 1;
  }

  std::printf("runtime_seam: PASS — Core owns the direct runtime, 2/2 resident-range facts reach "
              "GuestProgramImage, 3/3 legacy views are null, and 1/1 invalid range is refused\n");
  std::printf("runtime_seam: NOT covered — generated execution, devices, frames, or gameplay\n");
  return 0;
}
